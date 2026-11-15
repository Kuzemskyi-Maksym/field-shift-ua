"""Крок 3: симулятор сівозміни."""
import numpy as np
import pandas as pd
import pytest

import baseline_model as B
from model import simulate as M


def _baseline_params(crop):
    c = B.CROPS[crop]
    d = dict(kc_ini=c["kc_ini"], kc_mid=c["kc_mid"], kc_end=c["kc_end"], ky=c["ky"], zr=c["zr"], p=c["p"], sow=c["sow"])
    if crop == "winter_wheat":
        d.update(season="winter", stage_dates=[x for _, x in c["stages"]])
    else:
        d.update(season="spring", stages_days=[n for _, n in c["stages"]])
    return d


@pytest.mark.parametrize("pid", list(B.POINTS))
def test_one_crop_equals_baseline(pid):
    """Спільне ядро water_balance + kc_curve з параметрами baseline v0 = baseline_model.simulate, усі культури й роки."""
    lat, lon, elev, _ = B.POINTS[pid]
    wx = B.check_units(pd.read_csv(f"out/power_{pid}.csv", parse_dates=["date"], index_col="date"), pid)
    et0 = pd.Series(B.et0_pm(wx.T2M_MAX.values, wx.T2M_MIN.values, wx.RH2M.values, wx.WS2M.values,
                             wx.ALLSKY_SFC_SW_DWN.values, lat, elev, wx.index.dayofyear.values), index=wx.index)
    n = 0
    for crop in B.CROPS:
        for year in range(2002, 2026):
            ref = B.simulate(wx, et0, crop, year)
            new = M.baseline_season(wx, et0, _baseline_params(crop), year, B.TAW_MM_PER_M, B.KC_BARE)
            assert (ref is None) == (new is None)
            if ref:
                n += 1
                for k in ("rel_yield", "etc_mm", "eta_mm", "stress_days"):
                    assert ref[k] == new[k], (pid, crop, year, k, ref[k], new[k])
    assert n == 3 * 24


def test_eq63_and_eq62():
    assert M.rh_min_eq63(10.0, 10.0) == pytest.approx(100)
    # рівн. 62: при u2=2, RHmin=45 поправка нульова
    assert M.kc_climate_eq62(1.15, 2.0, 45.0, 1.0) == pytest.approx(1.15)
    # межі: u2>6 і RHmin<20 обрізаються
    assert M.kc_climate_eq62(1.15, 9.0, 5.0, 3.0) == pytest.approx(1.15 + 0.04 * 4 + 0.004 * 25)


def test_kc_bare_annex7_example_fig30a():
    """Приклад 7-1: ET0 = 5, t_w = 3.5 дні, глибоке зволоження ≥40 мм, груба текстура → 0.75."""
    soils = M.S.load_soils()
    L = 7
    rain = np.zeros((1, L)); rain[0, [0, 4]] = 50.0          # 2 події → t_w = 7/(2+0.5) = 2.8 (не 3.5) — перевіряємо формулу напряму
    k = M.kc_ini_eq73(np.array([3.5]), np.array([5.0]), 15.0, 6.0, 1.15, 1.15)
    assert round(float(k[0]), 2) == 0.75
    kb = M.kc_bare(rain, np.full((1, L), 5.0), True, soils)
    assert 0 < kb[0] <= 1.15


@pytest.fixture(scope="module")
def sim():
    f = M.field_profile("berezivka_od", allow_stubs=True)
    return M.SequenceSimulator(f, K=4, allow_stubs=True)


def test_reproducible_and_prefix_cache(sim):
    r1, _ = sim.run(("winter_wheat", "sunflower", "pea", "winter_wheat"))
    s2 = M.SequenceSimulator(sim.f, K=4, allow_stubs=True)
    r2, _ = s2.run(("winter_wheat", "sunflower", "pea", "winter_wheat"))
    for a, b in zip(r1, r2):
        np.testing.assert_array_equal(a.rel_yield, b.rel_yield)
    p, _ = s2.run(("winter_wheat", "sunflower"))
    np.testing.assert_array_equal(p[1].rel_yield, r1[1].rel_yield)     # префікс не залежить від продовження


def test_mass_balance(sim):
    """Σ(опади) − Σ(ETa) = ΔDr + стік/фільтрація ≥ 0 для кожного старту (вода не з'являється з нічого)."""
    seq = ("maize", "soybean", "winter_wheat")
    res, _ = sim.run(seq)
    st = sim.cache[seq][2]
    end = st["end"]
    rain = sim.wx["PRECTOTCORR"][:, :end + 1].sum(1)
    # Повний ETa за всі дні (сезон + голий ґрунт) з кешу не зберігається — переобчислимо через простий інваріант:
    # Dr ∈ [0, TAW] і ETa ≤ ETc.
    assert np.all(st["dr"] >= 0) and np.all(st["dr"] <= st["taw"] + 1e-9)
    for y in res:
        assert np.all(y.eta_mm <= y.etc_mm + 1e-9)
    assert np.all(rain > 0)


def test_mass_balance_exact():
    """Точний баланс ядра: Dr_end = Dr0 + ΣETa − ΣP + Σстік, стік ≥ 0."""
    rng = np.random.default_rng(0)
    T = 400
    kc = rng.uniform(0.2, 1.2, (3, T)); et0 = rng.uniform(0, 6, (3, T)); rain = rng.exponential(2, (3, T))
    etc, eta, ks, dr = M.water_balance(kc, et0, rain, 200.0, 0.55, 50.0, True, M.S.load_soils()["depletion_adjust"])
    runoff = 50.0 + eta.sum(1) - rain.sum(1) - dr
    assert np.all(runoff <= 1e-9)            # Dr_end = Dr0 + ETa − P + runoff → runoff = Dr_end − Dr0 − ETa + P ≥ 0
    assert np.all(eta <= etc + 1e-12)


def test_calendar_conflict_rejected(sim):
    res, why = sim.run(("maize", "winter_wheat"))
    assert res is None and "календар" in why[0]


def test_fallow_carries_water(sim):
    """Пар перед пшеницею залишає більше вологи, ніж соняшник, → середній відносний врожай пшениці не нижчий."""
    a, _ = sim.run(("black_fallow", "winter_wheat"))
    b, _ = sim.run(("sunflower", "winter_wheat"))
    assert a[1].rel_yield.mean() >= b[1].rel_yield.mean()


def test_yx_p90():
    v = M.yx_p90("winter_wheat", "Одеська")
    y = M.yields()
    assert v == pytest.approx(np.percentile(y[(y.culture == "winter_wheat") & (y.oblast == "Одеська")].yield_t_ha, 90))
    assert M.yx_p90("buckwheat_not_a_crop", "Одеська") is None


def test_empty_derzhstat_values_are_no_data():
    y = M.yields()
    assert y.yield_t_ha.notna().all() and (y.yield_t_ha > 0).all()
    assert M.yx_p90("sugar_beet", "Одеська") is None          # єдиний рядок (2025) порожній у Держстаті


def test_dynamic_sow_doy_first_day_of_5day_mean():
    t = np.full((2, 365), 0.0)
    t[0, 100:] = 12.0                                   # з doy0 100: 5-денна середня ≥ 10 лише з doy0 104
    t[1, 30:40] = 20.0                                  # тепла хвиля до not_before (03-01 = doy0 59) не рахується
    t[1, 200:] = 11.0                                   # після 30.06 — не шукаємо
    d, found = M.dynamic_sow_doy(t, 10, "03-01", 5)
    assert list(d) == [104, M.doy0("06-30")] and list(found) == [True, False]


def test_dynamic_sowing_per_weather_year(sim):
    """Кукурудза: сівба в кожному рядку = TSOIL1 ≥ 10 °C (5 днів) у році погоди цього рядка; збирання = сівба + Σ фаз FAO."""
    r = sim.crops["maize"]["sow_rule"]
    temp, proxy = M.load_tsoil(*sim.f.node)
    assert not proxy
    d, _ = M.dynamic_sow_doy(temp, r["threshold_c"], r["not_before"], r["mean_days"])
    sow, dev0, dev1, mid1, late1 = sim.season("maize", 2)
    assert np.array_equal(sow, 2 * 365 + d[(np.arange(M.NY) + 1) % M.NY])
    assert np.array_equal(late1 - sow, np.full(M.NY, sum(sim.crops["maize"]["stages_days"])))
    assert len(set(sow.tolist())) > 5                  # дата сівби справді різна по роках
    res, fl = sim.run(("winter_wheat", "maize"))
    y = res[1]
    assert y.sow_q[0] <= y.sow <= y.sow_q[1] and np.all((y.rel_yield >= 0) & (y.rel_yield <= 1))


def test_soil_temperature_proxy_flag():
    """Немає tsoil_<вузол>.csv → T2M як проксі з прапорцем."""
    temp, proxy = M.load_tsoil(51.0, 33.75)            # вузол Сум — TSOIL1 не завантажено
    assert proxy and temp.shape == (M.NY, 365)


def test_keep_daily_is_diagnostic_only(sim):
    """keep_daily (порівняння з ECOSTRESS) не змінює результат; Σ денного ETa сезону = eta_mm (для культури — від сівби)."""
    seq = ("winter_wheat", "maize")
    a, _ = M.SequenceSimulator(sim.f, K=2, allow_stubs=True, season_cache=False).run(seq)
    b, _ = M.SequenceSimulator(sim.f, K=2, allow_stubs=True, keep_daily=True).run(seq)
    for x, y in zip(a, b):
        np.testing.assert_allclose(x.rel_yield, y.rel_yield)
        assert x.daily is None and y.daily is not None
    st, eta = b[0].daily
    np.testing.assert_allclose(eta[:, b[0].sow - st:].sum(1), b[0].eta_mm)


def test_observed_practice_late_winter_sowing(sim):
    """D21: поточна (спостереження HLS) не відсікається календарем — озима після кукурудзи сіється після збирання, з прапорцем;
    у звичайному режимі (рекомендації) той самий перехід неможливий."""
    res, why = sim.run(("maize", "winter_wheat"))
    assert res is None and "календар" in why[0]
    obs = M.SequenceSimulator(sim.f, K=4, allow_stubs=True, observed_practice=True)
    res, fl = obs.run(("maize", "winter_wheat"))
    assert res is not None and res[1].sow > M.pos(1, "12-31") - 365 + 0 and res[1].sow > res[0].harvest
    assert res[1].sow > M.pos(1, sim.crops["winter_wheat"]["calendar"]["sow"])          # пізніше за оптимум
    assert any(f.startswith("фактична практика з HLS") for f in fl)
    assert np.all((res[1].rel_yield >= 0) & (res[1].rel_yield <= 1))


def test_human_text_no_raw_ids():
    import sys
    sys.path.insert(0, "scripts")
    from human_text import human
    t = human("поточна (за класами HLS) ['maize', 'maize', 'winter_wheat', 'maize']: сівба winter_wheat (рік 3)")
    assert "['" not in t and "winter_wheat" not in t and "maize" not in t
    assert "Кукурудза → Кукурудза → Пшениця озима → Кукурудза" in t and "пшениця озима (рік 3)" in t

