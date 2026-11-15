"""Крок 6: оптимізатор → strategies_<field>.json (контракт A9)."""
import re

import pytest

from model import optimize as O

A9_TOP = {"field_id", "area_ha", "next_season", "strategies"}
A9_STRAT = {"name", "sequence", "per_year", "metrics", "calendar", "explain", "confidence"}
A9_YEAR = {"year", "crop", "yield_t_ha", "yield_t_field", "channel", "revenue_uah_ha", "flags"}
A9_METRICS = {"income_p50", "income_p10", "water_deficit_mm", "legume_share", "bare_days", "feed_self_sufficiency",
              "violations_164", "rank_mode"}
A9_CAL = {"year", "crop", "sow", "harvest", "bare", "risks"}
A9_EXPLAIN = {"why", "data", "benefits", "gaps", "agronomist_check"}


@pytest.fixture(scope="module")
def out():
    return O.optimize_field("berezivka_od", allow_stubs=True, write=False, rank="yield_index")


def test_contract_a9_keys(out):
    assert A9_TOP <= set(out)
    assert {"crop", "why"} <= set(out["next_season"])
    names = [s["name"] for s in out["strategies"]]
    assert {"max_income", "min_risk", "balanced"} <= set(names)
    for s in out["strategies"]:
        assert A9_STRAT <= set(s)
        assert A9_METRICS <= set(s["metrics"])
        assert A9_EXPLAIN <= set(s["explain"])
        assert s["confidence"] in {"high", "medium", "low"}
        for y in s["per_year"]:
            assert A9_YEAR <= set(y)
            assert {"type", "buyer_id", "net_price_uah_t", "alternatives"} <= set(y["channel"])
            if y["yield_t_ha"]:
                assert set(y["yield_t_ha"]) == {"dry", "typical", "wet"}
                assert y["yield_t_ha"]["dry"] <= y["yield_t_ha"]["typical"] <= y["yield_t_ha"]["wet"]
        for c in s["calendar"]:
            assert A9_CAL <= set(c)
            for k in ("sow", "harvest"):
                assert c[k] is None or re.fullmatch(r"\d\d-\d\d", c[k])


def test_stub_visible_everywhere(out):
    """D17: календарі зі STUB лишились лише в буряку — де він є, STUB видно в gaps/календарі, confidence = low; деінде — ні."""
    for s in out["strategies"]:
        beet = "sugar_beet" in s["sequence"]
        assert any(g.startswith("STUB: календар") for g in s["explain"]["gaps"]) == beet
        assert any(c["stub"] and any(f.startswith("STUB") for f in c["flags"]) for c in s["calendar"]) == beet
        if beet:
            assert s["confidence"] == "low"
        for c in s["calendar"]:
            if c["crop"] in ("maize", "sunflower", "soybean", "pea", "spring_wheat"):
                assert re.fullmatch(r"\d\d-\d\d", c["sow_range"][0]) and c["sow_rule"].startswith("сівба щороку")


def test_demo_mode_no_income_metric_and_label(out):
    for s in out["strategies"]:
        assert s["metrics"]["income_p50"] is None                     # дохід як критерій лише в режимі money
        if s["name"] != "current":
            assert s["explain"]["why"].startswith(O.DEMO_LABEL)
    assert out["ranking"]["mode"] == "yield_index" and out["ranking"]["label"] == O.DEMO_LABEL


def test_plans_pass_164_in_main_branch(out):
    from model import rules as R
    hist = O.field_history("berezivka_od")
    br = R.history_branches(hist, R.load_rules(), plan_start_year=2026)
    for s in out["strategies"]:
        if s["name"] != "current":
            assert R.check_linear(br[-1][1], s["sequence"]).ok


def test_wheat_after_maize_explained(out):
    assert out["run"]["n_calendar_pruned"] > 0
    s = next(s for s in out["strategies"] if s["name"] == "max_income")
    assert any(O.WHEAT_AFTER_MAIZE in g for g in s["explain"]["gaps"])


def test_speed(out):
    assert out["run"]["seconds"] < 10


def test_current_practice_violations_flagged():
    o = O.optimize_field("berezivka_od", allow_stubs=True, write=False)       # D22: HLS — соняшник 2022 і 2023 поспіль
    cur = next(s for s in o["strategies"] if s["name"] == "current")
    v = cur["metrics"]["violations_164"]
    assert v["count"] > 0 and any("Соняшник" in x for x in v["list"])
    assert cur["explain"]["why"].startswith(O.CUR_VIOL) and cur["explain"]["gaps"][0] == O.CUR_VIOL


def test_auto_with_prices_ranks_by_money():
    o = O.optimize_field("berezivka_od", allow_stubs=True, write=False)          # rank=auto, зріз DSSU_2025
    assert o["ranking"]["mode"] == "margin" and o["ranking"]["prices_snapshot"] == "DSSU_2025"
    s = next(s for s in o["strategies"] if s["name"] == "max_income")
    assert s["metrics"]["income_p50"] > 0 and all(y["revenue_uah_ha"] for y in s["per_year"] if y["rel_yield"])
    nd = {d["crop"] for d in o["candidates_without_data"]}
    assert {"sorghum", "chickpea", "flax"} <= nd                                # без ціни / заблоковані
    u = O.optimize_field("berezivka_od", allow_stubs=True, write=False,
                         prices_file="data/raw/prices_candidates.csv", prices_snapshot="UUB_2026-11")
    assert u["ranking"]["prices_snapshot"] == "UUB_2026-11"
    assert {"pea", "sugar_beet"} <= {d["crop"] for d in u["candidates_without_data"]}      # у UUB цін немає


def test_auto_without_prices_does_not_rank(monkeypatch):
    cfg = dict(O.load_cfg()); cfg["prices_file"] = "data/raw/prices.csv"; cfg["prices_snapshot"] = None
    monkeypatch.setattr(O, "load_cfg", lambda: cfg)
    o = O.optimize_field("berezivka_od", allow_stubs=True, write=False)          # порожній шаблон цін
    assert o["ranking"]["mode"] == "none"
    assert [s["name"] for s in o["strategies"]] == ["current"] and o["next_season"]["crop"] is None
    assert "ранжування неможливе" in o["next_season"]["why"]


def test_crops_without_yx_excluded_and_listed(out):
    no = {d["crop"] for d in out["candidates_without_data"]}
    assert no and not (no & set(out["run"]["strategy_crops"]))
    for s in out["strategies"]:
        if s["name"] != "current":
            assert not (set(s["sequence"]) & no)
    assert all(d["flags"][0].startswith(("перспективна, але без", "заблоковано параметрами")) for d in out["candidates_without_data"])


def test_current_unknown_year_branches():
    """Невідомий клас («?») у роках поточної → гілки W/S з прапорцем «підтвердіть культуру» (історія — синтетична)."""
    from model import rules as R
    cfg = O.load_cfg()
    hist = [dict(year=y, c=c, sub=s, confirmed_crop=None) for y, c, s in
            [(2022, "?", ""), (2023, "W", ""), (2024, "S", "late"), (2025, "W", "")]]
    opts, flags = O.current_variants(hist, 4, R.load_rules(), cfg["plan_start_year"], cfg["current_max_lag_years"],
                                     cfg["current_max_unknown_years"])
    assert [lab for lab, _ in opts] == ["2022=W", "2022=S"] and opts[0][1][0] == "winter_wheat"
    assert any("підтвердіть культуру 2022" in g for g in flags)


def test_history_confirmed_recomputes():
    o = O.optimize_field("berezivka_od", allow_stubs=True, write=False, rank="yield_index",
                         history_confirmed={2022: "sunflower"})
    assert o["history_confirmed"] == {"2022": "sunflower"}
    cur = next(s for s in o["strategies"] if s["name"] == "current")
    assert cur["sequence"][0] == "sunflower" and cur["variants"] == []


def test_volyn_old_history_flag():
    o = O.optimize_field("volyn:f3735", allow_stubs=True, write=False)
    cur = next(s for s in o["strategies"] if s["name"] == "current")
    last, cfg = o["history"][-1]["year"], O.load_cfg()
    old = last < cfg["plan_start_year"] - 1 - cfg["current_max_lag_years"]
    assert any(f"історія до {last}" in g for g in cur["explain"]["gaps"]) == old       # залежить від глибини HLS
    assert o["ranking"]["mode"] == "margin" and len(o["strategies"]) >= 2      # Держстат Волині з 12.11


def test_prices_by_oblast_with_fallback():
    o = O.optimize_field("berezivka_od", allow_stubs=True, write=False, prices_by_oblast=True)
    assert o["ranking"]["prices_snapshot"] == "DSSU_2025_odesa" and o["ranking"]["prices_fallback"] == "DSSU_2025"
    beet = [y for s in o["strategies"] for y in s["per_year"] if y["crop"] == "sugar_beet"]
    nd = {d["crop"]: d for d in o["candidates_without_data"]}
    if beet:                                                                  # буряка немає в DSSU_2025_odesa → fallback
        assert any("fallback на DSSU_2025" in f for f in beet[0]["flags"])


def test_enterprises_yield_file():
    o = O.optimize_field("berezivka_od", allow_stubs=True, write=False,
                         yield_file="data/raw/yield/derzhstat_yield_enterprises.csv")
    assert o["ranking"]["yield_file"].endswith("derzhstat_yield_enterprises.csv")
    a = O.optimize_field("berezivka_od", allow_stubs=True, write=False)
    assert o["run"]["yx_t_ha"] != a["run"]["yx_t_ha"]


def test_fallow_forbidden_in_max_income_and_balanced_water_for_steppe():
    """D16: пар без витрат з джерелом → заборонений у max_income/balanced; water — лише степ, маржа пару = null."""
    o = O.optimize_field("berezivka_od", allow_stubs=True, write=False)
    st = {s["name"]: s for s in o["strategies"]}
    assert o["zone"] == "steppe" and "water" in st
    for n in ("max_income", "min_risk", "balanced"):                     # пар — лише у water
        assert "fallow" not in st[n]["sequence"] and O.FALLOW_FORBIDDEN in st[n]["explain"]["gaps"]
        m = st[n]["metrics"]
        near0 = m["margin_p10"] < 0 and m["margin_p50"] <= 0.1 * m["income_p50"]
        assert (st[n]["explain"]["gaps"][0] == O.CLIMATE_RISK) == near0     # правило D16 (поріг 10 % виручки)
    wn = st["current"]["explain"]["why_not_repeat"]
    assert wn["compare_with"] == "balanced" and [r["metric"] for r in wn["rows"]] ==         ["violations_164", "end_moisture_frac", "drying_share"] and wn["rows"][0]["current"] > 0
    w = st["water"]
    for y in w["per_year"]:
        if y["crop"] == "fallow":
            assert y["margin_uah_ha"] is None and y["cost_uah_ha"] is None
            assert any(f.startswith(O.FALLOW_NO_COST) for f in y["flags"])
    if "fallow" in w["sequence"]:
        assert w["metrics"]["margin_excludes_fallow_cost"] and w["confidence"] != "high"
        assert any(g.startswith(O.FALLOW_NO_COST) for g in w["explain"]["gaps"])
    k = O.optimize_field("kalynivka_vn", allow_stubs=True, write=False)
    assert k["zone"] != "steppe" and "water" not in {s["name"] for s in k["strategies"]}


def test_water_pick_pareto_on_moisture_and_p10():
    ev = [dict(end_moisture=0.9, p10=-100, p50=0), dict(end_moisture=0.5, p10=500, p50=1),
          dict(end_moisture=0.8, p10=400, p50=2), dict(end_moisture=0.4, p10=300, p50=9)]   # 3 — домінований
    assert O.water_pick(ev, [0, 1, 2, 3], {"end_moisture": 0.5, "value_p10": 0.5}) == 2
    assert O.water_pick(ev, [0, 1, 2, 3], {"end_moisture": 1, "value_p10": 0}) == 0


def test_beet_logistics_flag():
    o = O.optimize_field("volyn:f3735", allow_stubs=True, write=False)
    beet = [y for s in o["strategies"] for y in s["per_year"] if y["crop"] == "sugar_beet"]
    assert beet and all(any("цукровий завод у радіусі доставки" in f for f in y["flags"]) for y in beet)


# ---------- «ефект у грошах» і пресети (нові виходи; вибір стратегій не змінюється)
@pytest.fixture(scope="module")
def kal():
    return O.optimize_field("kalynivka_vn", allow_stubs=True, write=False)


def test_vs_current_drawdown_breakeven_unit():
    """Рік 1 гірший за поточну, далі краще: drawdown 2027, breakeven — перший рік, з якого накопичена P50 ≥ 0 до кінця."""
    import numpy as np
    cur = dict(rows=np.full((4, 25), 100.0))
    e = dict(rows=np.array([[0.0] * 25, [150.0] * 25, [150.0] * 25, [200.0] * 25]))
    v = O.vs_current(e, cur, 10.0, 2027, 1)
    assert v["drawdown_year"] == 2027 and v["drawdown_years"] == [2027]
    assert [y["cum_delta_ha_p50"] for y in v["years"]] == [-100, -50, 0, 100] and v["breakeven_year"] == 2029
    assert v["delta_vs_current_uah_ha"] == {"p50": 100, "p10": 100} and v["delta_vs_current_uah_field"] == {"p50": 1000, "p10": 1000}
    assert v["current_violates_164"]
    never = O.vs_current(dict(rows=np.zeros((4, 25))), cur, 10.0, 2027, 0)
    assert never["breakeven_year"] is None and never["drawdown_year"] == 2027 and not never["current_violates_164"]
    assert O.vs_current(e, None, 10.0, 2027, 0) is None


def test_money_block_per_year_and_cumulative(kal):
    area = kal["area_ha"]
    for s in kal["strategies"]:
        mb = s["metrics"]["money"]
        assert [y["season"] for y in mb["years"]] == [2027, 2028, 2029, 2030] and mb["area_ha"] == area
        assert mb["years"][-1]["cumulative_ha"] == mb["total_ha"]
        for y in mb["years"]:
            assert y["margin_ha"]["p10"] <= y["margin_ha"]["p50"] <= y["margin_ha"]["p90"]
            assert abs(y["cumulative_field"]["p50"] - y["cumulative_ha"]["p50"] * area) <= area     # округлення
        # середня маржа за рік P50 (metrics.margin_p50) — інша статистика, ніж P50 суми / 4, але того ж знака порядку
        if s["name"] == "current":
            assert "vs_current" not in s["metrics"]
        else:
            v = s["metrics"]["vs_current"]
            cur_v = next(x for x in kal["strategies"] if x["name"] == "current")["metrics"]["violations_164"]["count"]
            assert v["current_violates_164"] == (cur_v > 0)
            assert abs(v["delta_vs_current_uah_field"]["p50"] - v["delta_vs_current_uah_ha"]["p50"] * area) <= area
            assert (v["breakeven_year"] is None) == (v["years"][-1]["cum_delta_ha_p50"] < 0)
            assert (v["drawdown_year"] is None) == (not v["drawdown_years"])


def test_money_null_without_prices(out):
    """rank=yield_index (без цін) → грошей немає, нічого не підставляємо."""
    for s in out["strategies"]:
        assert s["metrics"]["money"] is None and s["metrics"].get("vs_current") is None


def test_presets_null_with_reason(kal):
    P = {p["id"]: p for p in kal["presets"]}
    assert set(P) == {"nnc_1", "nnc_2", "cherkasy", "ww_sun", "maize_soy_ww_sun", "soy_ww_maize_pea", "ww_sun_maize_soy"}
    assert P["nnc_1"]["status"] == "no_data" and any(r.startswith("Просо: заблоковано") for r in P["nnc_1"]["reasons"])
    assert any(r.startswith("Гречка: немає в model/crops.yaml") for r in P["nnc_2"]["reasons"])
    assert P["ww_sun"]["status"] == "ok" and P["ww_sun"]["violations_164"]["count"] > 0      # типова практика порушує №164
    for k in ("maize_soy_ww_sun", "soy_ww_maize_pea"):                    # соя → озима в Лісостепу: календар, не обходимо
        assert P[k]["status"] == "ok" or any(r.startswith("календар") for r in P[k]["reasons"])
    for p in P.values():
        assert len(p["sequence"]) == 4 and p["sequence"] == [p["rotation"][i % len(p["rotation"])] for i in range(4)]
        if p["status"] == "no_data":
            assert p["reasons"] and p["metrics"] is None and p["money"] is None and p["vs_current"] is None
        else:
            assert not p["reasons"] and p["money"]["total_field"]["p10"] <= p["money"]["total_field"]["p50"]
            assert p["vs_current"]["delta_vs_current_uah_field"] is not None
    assert P["cherkasy"]["status"] == "ok"                               # соя, кукурудза — усі параметри є
    assert P["nnc_1"]["violations_164"]["count"] is not None              # №164 перевіряється й без моделі



def test_sunflower_effect_applied_and_sensitivity():
    """D20: ефект у поточній (соняшник поспіль — HLS Березівки) і в т/га; без ефекту — множники 1,0 і поточна заробляє більше."""
    kal = O.optimize_field("berezivka_od", allow_stubs=True, write=False)
    assert kal["ranking"]["sunflower_return_effect"]
    cur = next(s for s in kal["strategies"] if s["name"] == "current")
    sf = [y for y in cur["per_year"] if y["crop"] == "sunflower"]
    assert sf and all(y["prev_effect_mult"] < 1 for y in sf)
    assert any("Кохан" in f for y in sf for f in y["flags"]) and not any(f == "ефект попередника не враховано" for y in sf for f in y["flags"])
    off = O.optimize_field("berezivka_od", allow_stubs=True, write=False, sunflower_effect=False)
    cur_off = next(s for s in off["strategies"] if s["name"] == "current")
    assert not off["ranking"]["sunflower_return_effect"] and all(y["prev_effect_mult"] == 1.0 for y in cur_off["per_year"])
    assert cur_off["metrics"]["margin_p50"] > cur["metrics"]["margin_p50"]
