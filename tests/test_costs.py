"""Витрати Держстату: правила заповнення пропусків і викидів, маржа в оптимізаторі."""
import numpy as np
import pandas as pd
import pytest

from model import costs as CO
from model import optimize as O


def _write(tmp_path, rows):
    p = tmp_path / "c.csv"
    base = dict(prod_cost_uah_t=1, sale_price_uah_t=1, yield_ent_t_ha=1, full_cost_uah_t=1, note="", source="тест")
    pd.DataFrame([base | r for r in rows]).to_csv(p, index=False)
    CO.load_costs.cache_clear()
    return str(p)


def test_missing_oblast_uses_mean_of_others(tmp_path):
    p = _write(tmp_path, [dict(crop="x", oblast=o, year=2025, prod_cost_uah_ha=v, full_cost_uah_ha=v, profitability_pct=10)
                          for o, v in [("A", 100), ("B", 120), ("C", np.nan)]])
    c = CO.cost_ha("x", "C", 2025, path=p)
    assert c.value == pytest.approx(110) and any("витрати з інших областей" in f for f in c.flags)


def test_outlier_replaced_by_median(tmp_path):
    p = _write(tmp_path, [dict(crop="x", oblast=o, year=2025, prod_cost_uah_ha=v, full_cost_uah_ha=v, profitability_pct=10)
                          for o, v in [("A", 100), ("B", 110), ("C", 120), ("D", 105), ("E", 500)]])
    c = CO.cost_ha("x", "E", 2025, path=p)
    assert c.value == pytest.approx(110) and any("викид" in f for f in c.flags)
    assert CO.cost_ha("x", "A", 2025, path=p).value == 100


def test_real_file_notes_and_gaps():
    CO.load_costs.cache_clear()
    w = CO.cost_ha("winter_wheat", "Одеська", 2025)
    assert w.value and any("озим" in f.lower() for f in w.flags)                     # без поділу на озимі/ярі
    b = CO.cost_ha("sugar_beet", "Одеська", 2025)
    assert b.value and any("витрати з інших областей" in f for f in b.flags)        # пропуск Одеса
    line, warn = CO.profitability_line("sugar_beet", "Буряк цукровий", "Вінницька",
                                       CO.cost_ha("sugar_beet", "Вінницька", 2025), 2025)
    assert "2025" in line and warn and warn.startswith("УВАГА")


def test_margin_is_main_metric_with_fixed_costs():
    o = O.optimize_field("karlivka_pl", allow_stubs=True, write=False)
    assert o["ranking"]["mode"] == "margin"
    s = next(s for s in o["strategies"] if s["name"] == "max_income")
    m = s["metrics"]
    assert m["margin_p50"] is not None and m["income_p50"] is not None and m["income_p50"] > m["margin_p50"]
    for y in s["per_year"]:
        if y["rel_yield"]:
            # витрати фіксовані: маржа сухого року = валовий сухого року − ті самі витрати
            assert y["margin_uah_ha"]["dry"] == pytest.approx(y["revenue_uah_ha"]["dry"] - y["cost_uah_ha"], abs=1)
            assert y["margin_uah_ha"]["wet"] == pytest.approx(y["revenue_uah_ha"]["wet"] - y["cost_uah_ha"], abs=1)
    assert any("за Держстатом, 2025" in x for x in s["explain"]["profitability"])


def test_beet_negative_profitability_warning():
    o = O.optimize_field("karlivka_pl", allow_stubs=True, write=False, cost_column="prod_cost_uah_ha")    # чутливість; Полтавська −42,2 %
    beet = [s for s in o["strategies"] if "sugar_beet" in s["sequence"]]
    assert beet and any(g.startswith("УВАГА") and "Буряк" in g for g in beet[0]["explain"]["gaps"])


def test_full_cost_is_main_and_beet_loses_like_derzhstat():
    """D16: повна собівартість — основна; буряк у Вінницькій/Полтавській збитковий у моделі, як у Держстаті 2025."""
    assert O.load_cfg()["cost_column"] == "full_cost_uah_ha"
    for f in ("kalynivka_vn", "karlivka_pl"):
        o = O.optimize_field(f, allow_stubs=True, write=False)
        assert o["ranking"]["cost_column"] == "full_cost_uah_ha"
        assert not any("sugar_beet" in s["sequence"] for s in o["strategies"] if s["name"] != "current")
        price, yx = o["run"]["unit_values"]["margin"]["sugar_beet"], o["run"]["yx_t_ha"]["sugar_beet"]
        c = CO.cost_ha("sugar_beet", o["oblast"], 2025, "full_cost_uah_ha")
        from model import simulate as M
        res, _ = M.SequenceSimulator(M.field_profile(f, True), K=1, allow_stubs=True).run(("sugar_beet",))
        m = yx * res[0].rel_yield * price - c.value                 # маржа буряку одного сезону, 25 років погоди
        assert np.percentile(m, 50) < 0 and np.percentile(m, 90) < 0


def test_not_sunflower_confirmation_unblocks_sunflower():
    # D22: історія з HLS поля Березівки — S/early 2020, 2022 і S/'' 2023 → гілка «соняшник у 2023» блокує соняшник
    a = O.optimize_field("berezivka_od", allow_stubs=True, write=False)
    b = O.optimize_field("berezivka_od", allow_stubs=True, write=False,
                         history_confirmed={2020: "not_sunflower", 2022: "not_sunflower", 2023: "not_sunflower"})
    seqs = lambda o: [c for s in o["strategies"] if s["name"] != "current" for c in s["sequence"]]  # noqa: E731
    assert "sunflower" not in seqs(a) and "sunflower" in seqs(b)
