#!/usr/bin/env python3
"""
Field Shift — базова модель прогнозу врожаю (baseline v0).

Ідея: фізична модель без навчання (FAO-56 + FAO-33/66), а не «чорна скринька».
  погода NASA POWER (щодня) -> ET0 (Penman–Monteith) -> ETc = Kc(t)·ET0
  -> водний баланс ґрунту (бакет) -> ETa -> відносний врожай Ya/Yx = 1 − Ky·(1 − ΣETa/ΣETc)
  -> прогноз т/га = Yx · Ya/Yx, де Yx — максимум обласної врожайності Держстату за ІНШІ роки (leave-one-year-out)
Потім порівнюємо з фактичною врожайністю Держстату і з бейзлайнами.

Запуск (потрібен інтернет для NASA POWER, якщо немає локальних CSV):
  pip install requests numpy pandas matplotlib
  python baseline_model.py                       # 4 пілотні поля, 2001–2025
  python baseline_model.py --power-dir data      # якщо вже є data/power_<id>.csv з fieldshift_data.py

Вихід: out/model/sim_yearly.csv, out/model/validation.csv, out/model/report.md, out/model/validation.png

ВАЖЛИВО: параметри культур нижче — РОБОЧІ ЗАГЛУШКИ (позначені SOURCE/TODO).
Їх треба звірити з FAO-56/FAO-66 і українським календарем (ролі R2/R3), перш ніж робити висновки.
"""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("out/model")

POINTS = {  # id: (lat, lon, elevation_m (SRTM), область)
    "berezivka_od": (47.103423, 30.671618, 95, "Одеська"),
    "arbuzynka_mk": (47.997982, 31.364381, 167, "Миколаївська"),
    "karlivka_pl": (49.366228, 35.013165, 133, "Полтавська"),
    "kalynivka_vn": (49.621918, 28.688890, 312, "Вінницька"),
}

# ---------------------------------------------------------------- параметри культур (ЗАГЛУШКИ)
# Kc — FAO-56 табл. 12 (аркуш «R2 Kc FAO»). Ky — FAO-33/66 сезонні значення: TODO звірити з FAO-66.
# Календар — орієнтовний для України: TODO замінити даними R2/R3 (по зонах).
CROPS = {
    "winter_wheat": dict(
        name="Пшениця", kc_ini=0.4, kc_mid=1.15, kc_end=0.3, ky=1.0, zr=1.2, p=0.55,
        sow="10-01", stages=[("dormant", "03-15"), ("dev", "04-25"), ("mid", "06-10"), ("late", "07-10")],
        src="Kc: FAO-56 t.12; Ky: FAO-33 (TODO FAO-66); календар: заглушка"),
    "maize": dict(
        name="Кукурудза", kc_ini=0.3, kc_mid=1.2, kc_end=0.5, ky=1.25, zr=1.2, p=0.55,
        sow="04-25", stages=[("ini", 25), ("dev", 40), ("mid", 45), ("late", 35)],
        src="Kc: FAO-56 t.12; Ky: FAO-33 (TODO FAO-66); фази: FAO-56 t.11 як заглушка"),
    "sunflower": dict(
        name="Соняшник", kc_ini=0.35, kc_mid=1.1, kc_end=0.35, ky=0.95, zr=1.2, p=0.45,
        sow="04-25", stages=[("ini", 25), ("dev", 35), ("mid", 45), ("late", 25)],
        src="Kc: FAO-56 t.12; Ky: FAO-33 (TODO FAO-66); фази: FAO-56 t.11 як заглушка"),
}
KC_BARE = 0.3          # поза сезоном (голий ґрунт) — заглушка
TAW_MM_PER_M = 140.0   # доступна волога, мм на 1 м ґрунту — заглушка до SoilGrids (суглинок ~110–180)

# Держстат, обласна врожайність т/га (аркуш «R2 Врожайність»; поки лише ці роки)
YIELD = pd.DataFrame([
    # crop, oblast, year, t/ha
    *[("winter_wheat", o, y, v) for o, vals in {
        "Вінницька": [4.8, 4.27, 5.57, 4.03], "Миколаївська": [3.42, 2.7, 4.23, 3.2],
        "Одеська": [3.21, 1.78, 3.9, 2.63], "Полтавська": [4.37, 4.48, 4.83, 4.13]}.items()
      for y, v in zip([2015, 2020, 2021, 2022], vals)],
    *[("maize", o, y, v) for o, vals in {
        "Вінницька": [4.93, 5.06, 9.37, 5.14], "Миколаївська": [3.2, 2.82, 5.23, 3.44],
        "Одеська": [2.83, 2.67, 6.1, 2.88], "Полтавська": [7.3, 5.48, 6.79, 7.24]}.items()
      for y, v in zip([2015, 2020, 2021, 2022], vals)],
    *[("sunflower", o, y, v) for o, vals in {
        "Вінницька": [2.69, 2.68, 3.2, 2.29], "Миколаївська": [1.97, 1.35, 2.24, 1.54],
        "Одеська": [1.81, 1.27, 2.32, 1.35], "Полтавська": [2.69, 2.54, 2.57, 2.81]}.items()
      for y, v in zip([2015, 2020, 2021, 2022], vals)],
], columns=["crop", "oblast", "year", "yield_t_ha"])


# ---------------------------------------------------------------- погода
POWER_PARAMS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,WS2M,ALLSKY_SFC_SW_DWN"


def load_power(pid, lat, lon, power_dir, start="20010101", end="20251231"):
    for cand in [Path(power_dir) / f"power_{pid}.csv", OUT.parent / f"power_{pid}.csv"]:
        if cand.exists():
            df = pd.read_csv(cand, parse_dates=["date"], index_col="date")
            print(f"[{pid}] погода з {cand}")
            return df
    import requests
    r = requests.get("https://power.larc.nasa.gov/api/temporal/daily/point",
                     params=dict(parameters=POWER_PARAMS, community="AG", latitude=lat, longitude=lon,
                                 start=start, end=end, format="JSON"), timeout=300)
    r.raise_for_status()
    js = r.json()
    units = {k: v.get("units") for k, v in js.get("parameters", {}).items()}
    print(f"[{pid}] POWER одиниці: {units}")
    df = pd.DataFrame(js["properties"]["parameter"])
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999.0, np.nan)
    df.index.name = "date"
    (OUT.parent).mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT.parent / f"power_{pid}.csv")
    return df


def check_units(df, pid):
    rs = df["ALLSKY_SFC_SW_DWN"].median()
    if not (3 <= rs <= 30):
        raise SystemExit(f"СТОП [{pid}]: медіана ALLSKY_SFC_SW_DWN = {rs:.1f}. Очікував МДж/м²/добу (3–30). "
                         "Перевір одиниці в POWER, не продовжую.")
    miss = df[POWER_PARAMS.split(",")].isna().mean().round(3)
    if (miss > 0.02).any():
        print(f"[{pid}] увага, пропуски: {miss[miss > 0].to_dict()} — заповнюю інтерполяцією")
    return df.interpolate(limit=5).ffill().bfill()


# ---------------------------------------------------------------- FAO-56 ET0 (денний Penman–Monteith)
def et0_pm(tmax, tmin, rh_mean, u2, rs, lat_deg, elev, doy, ea=None):
    """FAO-56: рівн. 7, 8, 11–13, 19, 21–25, 34–40, 6. Одиниці: °C, %, м/с, МДж/м²/добу."""
    tmean = (tmax + tmin) / 2
    P = 101.3 * ((293 - 0.0065 * elev) / 293) ** 5.26                 # рівн. 7
    gamma = 0.000665 * P                                              # рівн. 8
    e0 = lambda t: 0.6108 * np.exp(17.27 * t / (t + 237.3))           # рівн. 11
    es = (e0(tmax) + e0(tmin)) / 2                                    # рівн. 12
    if ea is None:
        ea = rh_mean / 100 * es                                       # рівн. 19
    delta = 4098 * e0(tmean) / (tmean + 237.3) ** 2                   # рівн. 13
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)                    # рівн. 23
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)                # рівн. 24
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))        # рівн. 25
    ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec)
                                          + np.cos(phi) * np.cos(dec) * np.sin(ws))  # рівн. 21
    rso = (0.75 + 2e-5 * elev) * ra                                   # рівн. 37
    rns = (1 - 0.23) * rs                                             # рівн. 38
    rel = np.clip(rs / np.where(rso > 0, rso, np.nan), 0.25, 1.0)
    rnl = 4.903e-9 * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2) \
        * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * rel - 0.35)          # рівн. 39
    rn = rns - rnl                                                    # рівн. 40
    return (0.408 * delta * rn + gamma * 900 / (tmean + 273) * u2 * (es - ea)) / \
           (delta + gamma * (1 + 0.34 * u2))                          # рівн. 6 (G = 0)


# ---------------------------------------------------------------- Kc і водний баланс
def season_kc(crop, year):
    """Повертає Series Kc на кожен день сезону (від сівби до збирання), сезон врожаю = year."""
    c = CROPS[crop]
    if crop == "winter_wheat":
        sow = pd.Timestamp(f"{year - 1}-{c['sow']}")
        marks = [pd.Timestamp(f"{year}-{d}") for _, d in c["stages"]]
        days = pd.date_range(sow, marks[-1])
        kc = pd.Series(c["kc_ini"], index=days)
        dev0, dev1, mid1, late1 = marks[0], marks[1], marks[2], marks[3]
    else:
        sow = pd.Timestamp(f"{year}-{c['sow']}")
        lens = [n for _, n in c["stages"]]
        dev0 = sow + pd.Timedelta(days=lens[0])
        dev1 = dev0 + pd.Timedelta(days=lens[1])
        mid1 = dev1 + pd.Timedelta(days=lens[2])
        late1 = mid1 + pd.Timedelta(days=lens[3])
        days = pd.date_range(sow, late1)
        kc = pd.Series(c["kc_ini"], index=days)
    t = kc.index
    m = (t >= dev0) & (t < dev1)
    kc[m] = c["kc_ini"] + (c["kc_mid"] - c["kc_ini"]) * ((t[m] - dev0).days / max((dev1 - dev0).days, 1))
    kc[(t >= dev1) & (t < mid1)] = c["kc_mid"]
    m = t >= mid1
    kc[m] = c["kc_mid"] + (c["kc_end"] - c["kc_mid"]) * ((t[m] - mid1).days / max((late1 - mid1).days, 1))
    return kc


def simulate(wx, et0, crop, year, taw_per_m=TAW_MM_PER_M):
    """Бакет FAO-56 розд. 8 (спрощено): старт від повного профілю на 1 січня (або 1 серпня для озимих)."""
    c = CROPS[crop]
    kc_season = season_kc(crop, year)
    start = kc_season.index[0] - pd.Timedelta(days=60)              # 60 днів «голого» ґрунту перед сівбою
    idx = pd.date_range(start, kc_season.index[-1])
    if idx[0] < wx.index[0] or idx[-1] > wx.index[-1]:
        return None
    kc = pd.Series(KC_BARE, index=idx)
    kc.loc[kc_season.index] = kc_season
    taw = taw_per_m * c["zr"]
    raw = c["p"] * taw
    dr = 0.5 * taw                                                   # стартове виснаження: половина (заглушка)
    etc_sum = eta_sum = 0.0
    stress_days = 0
    p = wx["PRECTOTCORR"].reindex(idx).values
    e = et0.reindex(idx).values
    in_season = idx >= kc_season.index[0]
    for i in range(len(idx)):
        etc = kc.values[i] * e[i]
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / (taw - raw))   # рівн. 84
        eta = ks * etc
        dr = min(max(dr - p[i] + eta, 0.0), taw)                        # надлишок -> стік/фільтрація
        if in_season[i]:
            etc_sum += etc
            eta_sum += eta
            stress_days += ks < 1.0
    rel = float(np.clip(1 - c["ky"] * (1 - eta_sum / etc_sum), 0, 1))  # FAO-33/66
    season = kc_season.index
    return dict(crop=crop, year=year, etc_mm=round(etc_sum), eta_mm=round(eta_sum),
                deficit_mm=round(etc_sum - eta_sum), stress_days=int(stress_days), rel_yield=round(rel, 3),
                precip_season_mm=round(float(wx["PRECTOTCORR"].reindex(season).sum())),
                hot_days=int((wx["T2M_MAX"].reindex(season) >= 30).sum()))


# ---------------------------------------------------------------- валідація
def validate(sim):
    rows = []
    for (crop, oblast), g in YIELD.groupby(["crop", "oblast"]):
        pid = [k for k, v in POINTS.items() if v[3] == oblast][0]
        s = sim[(sim.point == pid) & (sim.crop == crop)].set_index("year")
        for _, r in g.iterrows():
            others = g[g.year != r.year]
            yx = others.yield_t_ha.max() / max(
                s.loc[others.year, "rel_yield"].values.max(), 1e-6) if set(others.year) <= set(s.index) else np.nan
            if r.year not in s.index or np.isnan(yx):
                continue
            pred = yx * s.loc[r.year, "rel_yield"]
            # бейзлайн 1: кліматологія (середнє інших років); бейзлайн 2: регресія на опади сезону
            clim = others.yield_t_ha.mean()
            xo = s.loc[others.year, "precip_season_mm"].values
            if np.ptp(xo) > 0:
                k, b = np.polyfit(xo, others.yield_t_ha.values, 1)
                rain = k * s.loc[r.year, "precip_season_mm"] + b
            else:
                rain = clim
            rows.append(dict(crop=crop, oblast=oblast, point=pid, year=r.year, obs=r.yield_t_ha,
                             pred_model=round(pred, 2), pred_clim=round(clim, 2), pred_rain=round(rain, 2),
                             rel_yield=s.loc[r.year, "rel_yield"], deficit_mm=s.loc[r.year, "deficit_mm"]))
    v = pd.DataFrame(rows)
    out = []
    for name, col in [("Модель FAO (наша)", "pred_model"), ("Кліматологія (середнє)", "pred_clim"),
                      ("Лише опади сезону", "pred_rain")]:
        err = (v[col] - v.obs).abs() / v.obs
        out.append(dict(method=name, MAPE_pct=round(100 * err.mean(), 1),
                        spearman=round(v[col].corr(v.obs, method="spearman"), 2), n=len(v)))
    return v, pd.DataFrame(out)


def md_table(df):
    cols = list(df.columns)
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] +
                     ["| " + " | ".join(str(x) for x in r) + " |" for r in df.itertuples(index=False)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--power-dir", default="data")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    sims = []
    for pid, (lat, lon, elev, obl) in POINTS.items():
        wx = check_units(load_power(pid, lat, lon, a.power_dir), pid)
        et0 = pd.Series(et0_pm(wx.T2M_MAX.values, wx.T2M_MIN.values, wx.RH2M.values, wx.WS2M.values,
                               wx.ALLSKY_SFC_SW_DWN.values, lat, elev, wx.index.dayofyear.values), index=wx.index)
        print(f"[{pid}] ET0 середнє {et0.mean():.2f} мм/добу, сума за рік ≈ {et0.groupby(et0.index.year).sum().median():.0f} мм")
        for crop in CROPS:
            for year in range(2002, wx.index.year.max() + 1):
                r = simulate(wx, et0, crop, year)
                if r:
                    sims.append(dict(point=pid, oblast=obl, **r))
    sim = pd.DataFrame(sims)
    sim.to_csv(OUT / "sim_yearly.csv", index=False)

    v, metrics = validate(sim)
    v.to_csv(OUT / "validation.csv", index=False)
    print("\n", metrics.to_string(index=False))

    # контрольний кейс
    case = v[(v.crop == "winter_wheat") & (v.oblast == "Одеська") & v.year.isin([2020, 2021])]
    # графік
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(11, 4.5))
        for crop, mk in zip(CROPS, "o^s"):
            g = v[v.crop == crop]
            ax[0].scatter(g.obs, g.pred_model, marker=mk, label=CROPS[crop]["name"])
        lim = [0, v[["obs", "pred_model"]].max().max() * 1.1]
        ax[0].plot(lim, lim, "k--", lw=1); ax[0].set_xlim(lim); ax[0].set_ylim(lim)
        ax[0].set_xlabel("Факт, т/га (Держстат, область)"); ax[0].set_ylabel("Модель, т/га")
        ax[0].set_title("Прогноз vs факт (рік не входив у калібрування Yx)"); ax[0].legend()
        piv = sim[sim.crop == "winter_wheat"].pivot(index="year", columns="point", values="rel_yield")
        piv.plot(ax=ax[1]); ax[1].set_ylim(0, 1.05)
        ax[1].set_title("Пшениця: відносний врожай за водним стресом"); ax[1].set_ylabel("Ya/Yx")
        fig.tight_layout(); fig.savefig(OUT / "validation.png", dpi=130)
    except Exception as e:
        print("графік не зроблено:", e)

    rep = ["# Baseline v0 — звіт валідації", "",
           "Модель: FAO-56 ET0 + водний баланс + FAO-33/66 Ky. Параметри культур — **заглушки** (див. код).", "",
           "## Метрики (leave-one-year-out, n = пар «область × культура × рік»)", "",
           md_table(metrics), "",
           "## Контрольний кейс: пшениця, Одеська", "",
           case[["year", "obs", "pred_model", "rel_yield", "deficit_mm"]].to_string(index=False), "",
           "## Обмеження", "",
           "- лише 4 роки Держстату (2015, 2020–2022) → метрики дуже грубі;",
           "- точка поля (POWER ~50 км) порівнюється з середнім по області;",
           "- календар, Ky, TAW — заглушки; спека/заморозки не враховано у врожаї;",
           "- Yx = max інших років / їхній відносний врожай — простий калібрувальний підхід."]
    (OUT / "report.md").write_text("\n".join(rep), encoding="utf-8")
    print("\nГотово:", (OUT / "report.md").resolve())


if __name__ == "__main__":
    main()
