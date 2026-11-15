"""Крок 2: №164 — порт checkRot сайту, лінійний фільтр, гілки «можливо соняшник», циклічний прапорець, обмеження.

Очікування для 6 пресетів сайту згенеровано СПРАВЖНІМ JS сайту: node tests/gen_site_presets.js
→ tests/fixtures/site_presets.json. Якщо node є — тест ще й перегенеровує фікстуру й звіряє з закоміченою.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from model import rules as R

FIX = Path(__file__).parent / "fixtures" / "site_presets.json"


@pytest.fixture(scope="module")
def rules():
    return R.load_rules()


@pytest.fixture(scope="module")
def presets():
    return json.loads(FIX.read_text(encoding="utf-8"))


# ---------- a/b) порт checkRot = сайт на 6 пресетах
def test_six_presets(presets):
    assert len(presets) == 6


@pytest.mark.parametrize("i", range(6))
def test_site_port_matches_js(presets, i):
    p = presets[i]
    rows, shares = R.check_rot_site(p["seq"])
    assert rows == p["ret"], p["label"]
    assert shares == p["shares"], p["label"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node недоступний")
def test_fixture_regenerates_identically(tmp_path):
    before = FIX.read_text(encoding="utf-8")
    subprocess.run(["node", str(Path(__file__).parent / "gen_site_presets.js")], check=True, capture_output=True)
    assert FIX.read_text(encoding="utf-8") == before, "site/template.html змінився — перегенеруй фікстуру й перевір порт"


def test_js_round_half_up():
    assert R._js_round(12.5) == 13 and R._js_round(37.5) == 38      # Python round(12.5) == 12


# ---------- c) лінійна перевірка
def test_sunflower_seven_years_literal(rules):
    h = ["sunflower"] + ["winter_wheat"] * 6        # соняшник 7 років тому від року плану 1 → між ними 6 років
    assert not R.check_linear(h, ["sunflower"], rules).ok
    h = ["sunflower"] + [None] * 7                  # між ними 7 років — ок
    assert R.check_linear(h, ["sunflower"], rules).ok


def test_winter_wheat_two_years_literal(rules):
    assert not R.check_linear([], ["winter_wheat", "pea", "winter_wheat"], rules).ok       # між — 1 рік
    assert R.check_linear([], ["winter_wheat", "pea", "maize", "winter_wheat"], rules).ok  # між — 2 роки


def test_history_counts(rules):
    r = R.check_linear(["winter_wheat"], ["pea", "winter_wheat"], rules)
    assert not r.ok and "історія" in r.violations[0]


@pytest.mark.parametrize("hist,plan,ok", [
    ([], ["maize", "maize", "maize"], True),                            # 3 поспіль — ок
    (["maize"], ["maize", "maize", "maize"], False),                    # 4 поспіль — ні
    ([], ["maize", "maize", "maize", "maize"], False),                  # монокультура 4 роки — ні
    (["maize", "maize"], ["maize_silage", "maize"], False),             # силос рахується як кукурудза
    (["maize", "maize"], ["soybean", "maize"], True),
])
def test_maize_run(rules, hist, plan, ok):
    assert R.check_linear(hist, plan, rules).ok is ok


def test_maize_silage_flag(rules):
    r = R.check_linear([], ["maize_silage", "pea", "winter_wheat"], rules)
    assert "правило для кукурудзи застосовано до силосної" in r.flags


def test_barley_group(rules):
    assert not R.check_linear([], ["winter_barley", "spring_barley"], rules).ok   # ячмінь після ячменю
    assert R.check_linear([], ["winter_barley", "pea", "spring_barley"], rules).ok


def test_not_normed_flag(rules):
    r = R.check_linear([], ["spring_wheat", "spring_wheat", "spring_wheat"], rules)
    assert r.ok and "пшениця яра: №164 не нормує" in r.flags


def test_unknown_history_flag(rules):
    r = R.check_linear([None, "pea"], ["winter_wheat"], rules)
    assert r.ok and any("невідома" in f for f in r.flags)


def test_unknown_crop_raises(rules):
    with pytest.raises(KeyError):
        R.check_linear([], ["banana"], rules)


# ---------- гілки історії з HLS
SAMPLE = [  # формат out/hls/*_ndvi_seasons.csv (c, sub) + підтвердження фермера
    {"year": 2019, "c": "S", "sub": "early", "confirmed_crop": None},
    {"year": 2020, "c": "W", "sub": "", "confirmed_crop": None},
    {"year": 2021, "c": "S", "sub": "late", "confirmed_crop": None},
    {"year": 2022, "c": "S", "sub": "early", "confirmed_crop": None},
    {"year": 2023, "c": "W", "sub": "", "confirmed_crop": "winter_wheat"},
]


def test_history_branches(rules):
    br = R.history_branches(SAMPLE, rules)
    assert len(br) == 2
    (l0, h0), (l1, h1) = br
    assert h0 == [None, None, None, None, "winter_wheat"]
    assert h1 == [None, None, None, "sunflower", "winter_wheat"]      # останній S/early — 2022
    assert "2019, 2022" in l0 and "2022" in l1


def test_branches_change_sunflower_decision(rules):
    (_, no), (_, yes) = R.history_branches(SAMPLE, rules)
    plan = ["sunflower", "pea", "maize"]
    assert R.check_linear(no, plan, rules).ok
    r = R.check_linear(yes, plan, rules)
    assert not r.ok and "Соняшник" in r.violations[0]


def test_confirmed_year_not_branched(rules):
    s = [dict(r) for r in SAMPLE]
    for r in s:
        if r["sub"] == "early":
            r["confirmed_crop"] = "spring_barley"
    br = R.history_branches(s, rules)
    assert len(br) == 1


def test_real_hls_values_known():
    """Значення c/sub у реальних файлах — ті, що обробляє history_branches."""
    import glob
    import pandas as pd
    files = glob.glob(str(Path(__file__).parents[1] / "out" / "hls" / "*_ndvi_seasons.csv"))
    if not files:
        pytest.skip("немає out/hls")
    d = pd.concat(pd.read_csv(f, keep_default_na=False) for f in files)
    assert set(d.c) <= {"W", "S", "F", "?"}
    assert set(d["sub"]) <= {"early", "late", ""}


# ---------- d) циклічний прапорець
def test_cyclic_flag(rules):
    f = R.cyclic_flag(["winter_wheat", "sunflower", "maize"], rules)
    assert any("Соняшник" in x and "норма ≥ 7" in x for x in f)
    assert all(x.startswith("якщо повторювати цю сівозміну") for x in f)
    assert R.cyclic_flag(["maize", "maize", "maize"], rules)                 # монокультура
    assert not any("Пшениця" in x for x in R.cyclic_flag(["winter_wheat", "pea", "maize"], rules))


def test_cyclic_is_not_filter(rules):
    plan = ["sunflower", "winter_wheat", "pea"]
    assert R.check_linear([], plan, rules).ok and R.cyclic_flag(plan, rules)


# ---------- e) обмеження фермера
def test_constraints(rules):
    plan = ["maize", "soybean", "winter_wheat"]
    assert not R.check_constraints(plan, {"forbidden": ["soybean"]}, rules).ok
    assert not R.check_constraints(plan, {"no_machinery_for": ["maize"]}, rules).ok
    assert not R.check_constraints(plan, {"min_share": {"pea": 25}}, rules).ok
    assert not R.check_constraints(plan, {"max_share": {"maize": 20}}, rules).ok
    r = R.check_constraints(plan, {"no_machinery": ["corn_header"]}, rules)
    assert r.ok and any("TODO" in x for x in r.flags)


def test_site_shares_are_flags_by_default(rules):
    r = R.check_constraints(["sunflower", "winter_wheat", "pea", "maize"], {}, rules)
    assert r.ok and any("Соняшник" in x for x in r.flags)


def test_scaffolds_flag(rules):
    assert R.prev_effect("pea", "winter_wheat", rules) == (1.0, ["ефект попередника не враховано"])
    assert R.predecessor_class("pea", "winter_wheat", "steppe", rules)[0] is None


def test_every_norm_has_source(rules):
    for c, n in rules["norm164"].items():
        assert n["source"] in rules["sources"], c
        assert n["kind"] in {"return", "maize_run", "none"}, c


def test_all_crops_yaml_ids_have_norm(rules):
    from model import crops as C
    assert set(C.load_yaml()["crops"]) <= set(rules["norm164"])


# ---------- регресії за рев'ю кроку 2
def test_noncontiguous_history_years_filled_unknown():
    br = R.history_branches([{"year": 2019, "c": "S", "sub": "early"},
                             {"year": 2022, "c": "W", "confirmed_crop": "winter_wheat"}])
    assert [len(h) for _, h in br] == [4, 4]
    assert br[1][1] == ["sunflower", None, None, "winter_wheat"]


def test_history_padded_to_plan_start():
    br = R.history_branches([{"year": 2020, "c": "W", "confirmed_crop": "winter_wheat"}], plan_start_year=2023)
    assert br[0][1] == ["winter_wheat", None, None]


def test_history_crop_without_norm_flags_not_crashes():
    r = R.check_linear(["lupin"], ["pea"])
    assert r.ok and any("lupin" in f for f in r.flags)


def test_confirmed_later_sunflower_drops_redundant_branch():
    br = R.history_branches([{"year": 2019, "c": "S", "sub": "early"},
                             {"year": 2020, "c": "S", "confirmed_crop": "sunflower"}])
    assert len(br) == 1


def test_empty_plan_rejected():
    with pytest.raises(ValueError):
        R.check_linear([], [])
    with pytest.raises(ValueError):
        R.check_constraints([])


def test_unknown_year_breaks_maize_run_and_flags():
    r = R.check_linear(["maize", None, "maize", "maize"], ["maize"])
    assert r.ok and any("невідома" in f for f in r.flags)
    assert not R.check_linear(["maize", "maize", "maize"], ["maize"]).ok


def test_cyclic_maize_wrap():
    assert any("5 роки поспіль" in f for f in R.cyclic_flag(["maize"] * 4 + ["pea", "maize"]))
    assert not R.cyclic_flag(["maize", "maize", "maize", "pea"])


def test_legume_after_legume_flag_only_without_source():
    cls, fl = R.predecessor_class("pea", "soybean", "steppe", groups={"pea": "legume", "soybean": "legume"})
    assert cls is None and any("бобові після бобових" in f for f in fl)


def test_s_empty_subtype_is_maybe_sunflower():
    br = R.history_branches([{"year": 2020, "c": "S", "sub": ""}, {"year": 2021, "c": "W"}])
    assert len(br) == 2 and br[1][1][0] == "sunflower"


def test_barley_shared_norm_flag():
    r = R.check_linear([], ["winter_barley", "pea", "spring_barley"])
    assert any("ячменю застосована спільно" in f for f in r.flags)


def test_sunflower_return_multipliers_kohan2016(rules):
    """D20: ×(1 − 0,55/2,76) за 0–1 рік, ×(1 − 0,27/2,76) за 2, 3–5 — інтерполяція до 1,0 при ≥ 6 (KOHAN2016)."""
    c = rules["prev_effect"]["sunflower_return"]
    assert c["source"] == "KOHAN2016" and c["source"] in rules["sources"]
    m1, m2 = 1 - 0.55 / 2.76, 1 - 0.27 / 2.76
    sf = "sunflower"
    cases = {0: m1, 1: m1, 2: m2, 3: m2 + (1 - m2) / 4, 4: m2 + (1 - m2) / 2, 5: m2 + 3 * (1 - m2) / 4, 6: 1.0, 9: 1.0}
    for gap, want in cases.items():
        hist = [sf] + [None] * gap                    # попередній посів, потім gap невідомих/інших років
        mult, fl = R.sunflower_multipliers(hist, [sf, "maize"], "forest_steppe", rules)
        assert abs(mult[0] - want) < 1e-9 and mult[1] == 1.0, gap
        assert any("Кохан" in x for x in fl[0]) and not any("Степу" in x for x in fl[0])
        assert (c["flags"]["gap0"] in fl[0]) == (gap == 0) and (c["flags"]["interp"] in fl[0]) == (3 <= gap <= 5)
    mult, fl = R.sunflower_multipliers([None] * 5, [sf, "winter_wheat", sf, "maize"], "steppe", rules)
    assert mult == [1.0, 1.0, m1, 1.0]                # перший — невідомий попередній посів; другий — через 1 рік у плані
    assert c["flags"]["unknown"] in fl[0][0] and c["flags"]["zone"] in fl[2]
