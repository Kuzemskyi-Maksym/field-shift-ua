"""Крок 1: схема crops.yaml/soils.yaml, блокування TODO, заглушки календаря, рівн. 7-3 FAO-56."""
import copy
import math

import pytest
import yaml

from model import crops as C


@pytest.fixture(scope="module")
def doc():
    return C.load_yaml()


def test_schema_valid(doc):
    C.validate_schema(doc)


def test_every_number_has_known_source(doc):
    srcs = set(doc["sources"])
    for cid, c in doc["crops"].items():
        for k, p in c.items():
            if isinstance(p, dict) and "value" in p:
                assert p["src"] in srcs, (cid, k)


def test_unknown_source_rejected(doc):
    bad = copy.deepcopy(doc)
    bad["crops"]["maize"]["ky"]["src"] = "FROM_MEMORY"
    with pytest.raises(C.SchemaError):
        C.validate_schema(bad)


def test_typo_number_rejected(doc):
    bad = copy.deepcopy(doc)
    bad["crops"]["maize"]["kc_mid"]["value"] = 12.0
    with pytest.raises(C.SchemaError):
        C.validate_schema(bad)


def test_todo_blocks_crop(doc):
    st = C.crop_status(doc, "rye", "steppe", allow_stubs=True)
    assert not st.ready and any("ky" in r for r in st.reasons)


def test_stub_calendar_requires_flag(doc):
    strict = C.crop_status(doc, "sugar_beet", "steppe", allow_stubs=False)       # буряк — єдиний STUB серед готових (D17)
    loose = C.crop_status(doc, "sugar_beet", "steppe", allow_stubs=True)
    assert not strict.ready
    assert loose.ready and any(f.startswith("STUB:") for f in loose.flags)


def test_strict_mode_ready_only_with_sourced_calendar(doc):
    """D17: у строгому режимі готові лише культури з календарем із джерела (буряк — STUB, лише з allow_stubs)."""
    for z in ("steppe", "forest_steppe", "polissia"):
        ready = {s.crop for s in C.all_status(doc, z, allow_stubs=False) if s.ready}
        assert ready == {"winter_wheat", "spring_wheat", "maize", "sunflower", "soybean", "pea", "black_fallow"}


def test_ready_crops_returns_numbers_only():
    rc = C.ready_crops("steppe", allow_stubs=True)
    assert set(rc) >= {"winter_wheat", "maize", "sunflower", "black_fallow"}
    for cid, c in rc.items():
        for k in C.PARAMS:
            if k in c:
                assert not C.is_todo(c[k]), (cid, k)


# ---------- FAO-56 Annex 7, рівн. 7-3: перевірка на прикладі 7-1 джерела
def kc_ini_73(tw, et0, tew, rew, eso_factor=1.15):
    eso = eso_factor * et0
    t1 = rew / eso
    if tw < t1:
        return eso / et0
    return (tew - (tew - rew) * math.exp(-(tw - t1) * eso * (1 + rew / (tew - rew)) / tew)) / (tw * et0)


def test_annex7_example_fig30a_matches_source():
    with open(C.SOILS_YAML, encoding="utf-8") as f:
        s = yaml.safe_load(f)["bare_soil_kc"]
    et0 = 5.0
    tew = min(s["fig30a"]["tew_cor"]["max"], s["fig30a"]["tew_cor"]["coef"] * et0 ** 0.5)
    rew = min(s["fig30a"]["rew_cor"]["max"], tew - 0.01)
    assert round(kc_ini_73(3.5, et0, tew, rew), 2) == 0.75      # у джерелі 0.75


def test_annex7_example_fig29_documented_discrepancy():
    with open(C.SOILS_YAML, encoding="utf-8") as f:
        s = yaml.safe_load(f)["bare_soil_kc"]
    et0 = 5.0
    r = s["fig29"]["rew_cor"]
    rew = min(max(r["min"], r["coef"] / et0 ** 0.5), r["max"])
    k = kc_ini_73(3.5, et0, s["fig29"]["tew_cor"], rew)
    assert 0.52 < k < 0.54            # у джерелі надруковано 0.57 — розбіжність задокументовано в soils.yaml


# ---------- регресії за рев'ю кроку 1 (кожен — обхід, знайдений пробою)
def _raises(doc):
    with pytest.raises(C.SchemaError):
        C.validate_schema(doc)


def test_number_with_todo_source_rejected(doc):
    bad = copy.deepcopy(doc)
    bad["crops"]["maize"]["kc_mid"]["src"] = "NAAN_R2R3"
    _raises(bad)


def test_number_with_stub_source_rejected(doc):
    bad = copy.deepcopy(doc)
    bad["crops"]["maize"]["ky"]["src"] = "BASELINE_V0"
    _raises(bad)


def test_stub_detected_by_source_even_without_status(doc):
    bad = copy.deepcopy(doc)
    del bad["crops"]["sugar_beet"]["calendar"]["steppe"]["status"]
    _raises(bad)                                                   # схема вимагає status
    assert not C.crop_status(bad, "sugar_beet", "steppe", allow_stubs=False).ready   # і статус усе одно ловить


def test_todo_inside_list_rejected(doc):
    bad = copy.deepcopy(doc)
    bad["crops"]["maize"]["stages_days"]["value"] = [30, "TODO", 50, 50]
    _raises(bad)
    assert not C.crop_status(bad, "maize", "steppe", allow_stubs=True).ready


@pytest.mark.parametrize("sow", ["13-45", "4-25", "02-30", 425])
def test_malformed_sow_rejected(doc, sow):
    bad = copy.deepcopy(doc)
    bad["crops"]["sugar_beet"]["calendar"]["steppe"]["sow"] = sow
    _raises(bad)


def test_winter_stage_dates_must_increase_after_sowing(doc):
    bad = copy.deepcopy(doc)
    bad["crops"]["winter_wheat"]["calendar"]["steppe"]["stage_dates"] = ["03-15", "06-10", "04-25", "07-10"]
    _raises(bad)
    bad["crops"]["winter_wheat"]["calendar"]["steppe"]["stage_dates"] = ["03-15", "04-25", "06-10", "11-10"]
    _raises(bad)                                                   # кінець після дати сівби — не той рік


def test_winter_crop_uses_stage_dates_not_fao_lengths(doc):
    st = C.crop_status(doc, "winter_wheat", "steppe", allow_stubs=True)
    assert st.ready and not any(f.startswith("довжини фаз FAO-56 Т11") for f in st.flags) and C.HLS_STAGE_FLAG in st.flags
    nod = copy.deepcopy(doc)
    del nod["crops"]["winter_wheat"]["calendar"]["steppe"]["stage_dates"]
    st = C.crop_status(nod, "winter_wheat", "steppe", allow_stubs=True)
    assert "calendar.steppe.stage_dates: TODO (озимі — дати фаз від R2/R3)" in st.reasons


def test_winter_calendar_from_sources_and_hls(doc):
    """D17: сівба озимої пшениці — opt з calendar_sources.yaml, фази — HLS (клас W, медіана областей зони)."""
    import datetime as dt
    import pandas as pd
    src = yaml.safe_load(open(C.HERE.parent / "data" / "raw" / "calendar_sources.yaml", encoding="utf-8"))
    ph = pd.read_csv(C.HERE.parent / "data" / "raw" / "hls_phenology_by_oblast.csv")
    doy = lambda s: (dt.date(2001, int(s[:2]), int(s[3:])) - dt.date(2001, 1, 1)).days     # noqa: E731
    md = lambda n: (dt.date(2001, 1, 1) + dt.timedelta(days=n)).strftime("%m-%d")         # noqa: E731
    for z in ("steppe", "forest_steppe", "polissia"):
        cal = doc["crops"]["winter_wheat"]["calendar"][z]
        ref = src["winter"]["winter_wheat"][z]
        assert cal["sow"] == ref["opt"] and cal["src"] == ref["src"] and cal["window"] == ref["window"]
        assert cal.get("status") != "stub" and cal["stage_src"] == "HLS_PHENO"
        g = ph[(ph.cls == "W") & (ph.zone == z)]
        m = {k: math.floor(g[k + "_median"].map(doy).median() + 0.5) for k in ("greenup", "peak", "senes")}
        assert cal["stage_dates"] == [md(m["greenup"]), md(m["peak"]), md(m["senes"] - 25), md(m["senes"])]
        assert C.crop_status(doc, "winter_wheat", z).ready                          # строгий режим


def test_unknown_zone_clear_error(doc):
    with pytest.raises(ValueError, match="невідома зона"):
        C.crop_status(doc, "maize", "nozone")


def test_missing_group_and_bad_season_rejected(doc):
    bad = copy.deepcopy(doc)
    del bad["crops"]["maize"]["group"]
    bad["crops"]["pea"]["season"] = "summer"
    _raises(bad)


def test_bool_not_accepted_as_number(doc):
    bad = copy.deepcopy(doc)
    bad["crops"]["maize"]["p"]["value"] = True
    _raises(bad)


def test_midpoint_flag_is_explicit(doc):
    st = C.crop_status(doc, "sorghum", "steppe", allow_stubs=True)
    assert "kc_mid: середина діапазону без примітки FAO" in st.flags


def test_ky_todo_reason_exact(doc):
    st = C.crop_status(doc, "oats", "steppe")
    assert "ky: TODO (вівса немає в Табл. 24 / FAO-66 Табл. 1)" in st.reasons


def test_soils_schema():
    with open(C.SOILS_YAML, encoding="utf-8") as f:
        s = yaml.safe_load(f)
    for name, t in s["textures"].items():
        assert t["src"] in s["sources"], name
        for k in ("theta_fc", "theta_wp", "rew_mm"):
            lo, hi = t[k]
            assert lo < hi, (name, k)
        assert t["theta_wp"][1] <= t["theta_fc"][1] and t["theta_wp"][0] < t["theta_fc"][0], name
    assert set(s["bare_soil_kc"]["coarse_textures"]) <= set(s["textures"])


# Регрес перенесення: (культура, параметр, значення, рядок джерела)
TRANSCRIBED = [
    ("winter_wheat", "kc_ini", 0.4, "T12 Winter Wheat - with frozen soils 0.4"),
    ("winter_wheat", "ky", 1.0, "FAO-66 T2 Winter wheat FAO Tr-0000 1.00 (рішення 12.11; 1.05 — чутливість)"),
    ("maize", "kc_end", 0.35, "T12 Maize 0.60-0.35 fn11"),
    ("maize", "stages_days", [30, 40, 50, 50], "T11 Maize Idaho April"),
    ("sunflower", "kc_mid", 1.0, "T12 Sunflower 1.0-1.15 fn9"),
    ("sugar_beet", "kc_end", 0.70, "T12 Sugar Beet 0.70 fn5"),
    ("sugar_beet", "p", 0.55, "T22 Sugar Beet 0.55 fn3"),
    ("pea", "ky", 1.15, "T24 Peas 1,15"),
    ("soybean", "zr_m", 1.3, "T22 Soybeans 0.6-1.3"),
    ("alfalfa", "kc_mid", 0.95, "T12 Alfalfa averaged 0.95 fn13"),
]


@pytest.mark.parametrize("crop,param,expected,row", TRANSCRIBED)
def test_transcription(doc, crop, param, expected, row):
    assert doc["crops"][crop][param]["value"] == expected, row


def test_report_is_fresh(doc, tmp_path):
    """Закомічений reports/crops_params.md має збігатися з тим, що генерує CLI."""
    import subprocess, sys
    out = tmp_path / "r.md"
    subprocess.run([sys.executable, "-m", "model.crops", "--report", str(out)], check=True,
                   cwd=C.HERE.parent, capture_output=True)
    committed = (C.HERE.parent / "reports" / "crops_params.md").read_text(encoding="utf-8")
    assert out.read_text(encoding="utf-8") == committed, "перегенеруй: python -m model.crops --report reports/crops_params.md"


def test_stub_no_source_forbidden_for_numbers(doc):
    for k in ("kc_mid", "ky", "zr_m", "p"):
        bad = copy.deepcopy(doc)
        bad["crops"]["soybean"][k]["src"] = "STUB_NO_SOURCE"
        _raises(bad)


def test_stub_no_source_dates_need_allow_stubs(doc):
    assert not C.crop_status(doc, "sugar_beet", "steppe").ready
    st = C.crop_status(doc, "sugar_beet", "steppe", allow_stubs=True)
    assert st.ready and "STUB: календар steppe — заглушка без джерела (STUB_NO_SOURCE)" in st.flags


def test_prototype_crop_set():
    rc = C.ready_crops("steppe", allow_stubs=True)
    assert set(rc) == {"winter_wheat", "maize", "sunflower", "soybean", "pea", "spring_wheat",
                       "sugar_beet", "black_fallow"}


def test_dynamic_sow_schema(doc):
    """sow: dynamic — лише ярі, з sow_rule (поріг, not_before, mean_days, src)."""
    bad = copy.deepcopy(doc)
    bad["crops"]["winter_wheat"]["calendar"]["steppe"]["sow"] = "dynamic"
    _raises(bad)
    for k, v in (("threshold_c", None), ("not_before", "3-1"), ("mean_days", 0), ("src", "NAAN_R2R3"), ("var", "T2M")):
        bad = copy.deepcopy(doc)
        bad["crops"]["maize"]["sow_rule"][k] = v
        _raises(bad)


def test_dynamic_sow_rules_match_calendar_sources(doc):
    src = yaml.safe_load(open(C.HERE.parent / "data" / "raw" / "calendar_sources.yaml", encoding="utf-8"))["spring"]
    for crop, thr in (("maize", 10), ("sunflower", 10), ("soybean", 10), ("pea", 4), ("spring_wheat", 4)):
        r = doc["crops"][crop]["sow_rule"]
        assert r["threshold_c"] == thr and r["mean_days"] == 5 and r["var"] == "TSOIL1"
        if "threshold_used" in src[crop]:
            assert r["threshold_c"] == src[crop]["threshold_used"]
        for z in ("steppe", "forest_steppe", "polissia"):
            assert doc["crops"][crop]["calendar"][z]["sow"] == "dynamic"
    st = C.crop_status(doc, "spring_wheat", "steppe")
    assert any(f.startswith("сівба: поріг гороху") for f in st.flags)        # поріг гороху для ранніх ярих — прапорець
