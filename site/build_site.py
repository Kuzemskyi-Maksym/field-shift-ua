#!/usr/bin/env python3
"""Збирає дані для сайту-карти Field Shift і вбудовує їх у site/index.html.
Запуск (з папки nasa): python site/build_site.py out site/ndvi_seasons.csv site/data.json"""
import json
import sys

import numpy as np
import pandas as pd

OUT, NDVI, DST = sys.argv[1:4]

UA_NAMES = {
    "Autonomous Republic of Crimea": "АР Крим", "Cherkasy Oblast": "Черкаська", "Chernihiv Oblast": "Чернігівська",
    "Chernivtsi Oblast": "Чернівецька", "Dnipropetrovsk Oblast": "Дніпропетровська", "Donetsk Oblast": "Донецька",
    "Ivano-Frankivsk Oblast": "Івано-Франківська", "Kharkiv Oblast": "Харківська", "Kherson Oblast": "Херсонська",
    "Khmelnytskyi Oblast": "Хмельницька", "Kirovohrad Oblast": "Кіровоградська", "Kyiv Oblast": "Київська",
    "Kyiv": "м. Київ", "Luhansk Oblast": "Луганська", "Lviv Oblast": "Львівська", "Mykolaiv Oblast": "Миколаївська",
    "Odessa Oblast": "Одеська", "Poltava Oblast": "Полтавська", "Rivne Oblast": "Рівненська", "Sevastopol": "м. Севастополь",
    "Sumy Oblast": "Сумська", "Ternopil Oblast": "Тернопільська", "Vinnytsia Oblast": "Вінницька",
    "Volyn Oblast": "Волинська", "Zakarpattia Oblast": "Закарпатська", "Zaporizhia Oblast": "Запорізька",
    "Zhytomyr Oblast": "Житомирська",
}
# Лівобережний Лісостеп — зона досліду ННЦ «ІЗ НААН»; межі по областях приблизні
ZONE_CORE = {"Poltava Oblast"}
ZONE_PART = {"Kyiv Oblast", "Cherkasy Oblast", "Chernihiv Oblast", "Sumy Oblast", "Kharkiv Oblast"}

FIELDS = {
    "berezivka_od": dict(name="Березівка", oblast="Одеська", zone="сухий степ", lat=47.103423, lon=30.671618, elev=95),
    "arbuzynka_mk": dict(name="Арбузинка", oblast="Миколаївська", zone="степ", lat=47.997982, lon=31.364381, elev=167),
    "karlivka_pl": dict(name="Карлівка", oblast="Полтавська", zone="лісостеп, схід", lat=49.366228, lon=35.013165, elev=133),
    "kalynivka_vn": dict(name="Калинівка", oblast="Вінницька", zone="лісостеп, захід", lat=49.621918, lon=28.688890, elev=312),
}
CROP_UA = {"winter_wheat": "Пшениця озима", "maize": "Кукурудза", "sunflower": "Соняшник"}


def rnd(c, k=3):
    if isinstance(c[0], (int, float)):
        return [round(c[0], k), round(c[1], k)]
    out = [rnd(x, k) for x in c]
    if out and isinstance(out[0], list) and out[0] and isinstance(out[0][0], float):   # кільце: прибрати дублікати
        ded = [out[0]] + [p for i, p in enumerate(out[1:], 1) if p != out[i - 1]]
        return ded
    return out


fc = json.load(open(f"{OUT}/boundary_UKR_ADM1.geojson", encoding="utf-8"))
feats = []
for f in fc["features"]:
    en = f["properties"]["shapeName"]
    feats.append(dict(type="Feature", geometry=dict(type=f["geometry"]["type"], coordinates=rnd(f["geometry"]["coordinates"])),
                      properties=dict(name=UA_NAMES.get(en, en),
                                      zone="core" if en in ZONE_CORE else "part" if en in ZONE_PART else "")))
missing = [f["properties"]["shapeName"] for f in fc["features"] if f["properties"]["shapeName"] not in UA_NAMES]
if missing:
    print("Немає перекладу назв:", missing)

power = pd.read_csv(f"{OUT}/ukraine_points_power.csv")
smap = pd.read_csv(f"{OUT}/ukraine_points_smap.csv")
counts = pd.read_csv(f"{OUT}/ukraine_points_by_region.csv") if __import__("os").path.exists(f"{OUT}/ukraine_points_by_region.csv") else None

sim = pd.read_csv(f"{OUT}/model/sim_yearly.csv")
val = pd.read_csv(f"{OUT}/model/validation.csv")
ndvi = pd.read_csv(NDVI)

fields = []
for pid, meta in FIELDS.items():
    w = pd.read_csv(f"{OUT}/power_{pid}.csv", parse_dates=["date"], index_col="date")
    y = pd.DataFrame({"precip": w.PRECTOTCORR.resample("YE").sum(min_count=330),
                      "hot": (w.T2M_MAX >= 30).resample("YE").sum(),
                      "frost": (w.T2M_MIN < 0).resample("YE").sum(),
                      "t": w.T2M.resample("YE").mean()})
    y.index = y.index.year
    a, b = y.loc[2001:2010].mean(), y.loc[2016:2025].mean()
    clim = dict(precip_now=round(b.precip), precip_d=round(b.precip - a.precip),
                hot_now=round(b.hot), hot_d=round(b.hot - a.hot, 1),
                frost_d=round(b.frost - a.frost, 1), t_d=round(b.t - a.t, 2),
                series=[dict(year=int(i), precip=None if pd.isna(r.precip) else round(r.precip), hot=int(r.hot))
                        for i, r in y.iterrows()])
    crops = []
    for crop, g in sim[sim.point == pid].groupby("crop"):
        ry = g.set_index("year").rel_yield
        crops.append(dict(crop=CROP_UA[crop], p10=round(float(ry.quantile(0.1)), 2), p50=round(float(ry.median()), 2),
                          p90=round(float(ry.quantile(0.9)), 2),
                          worst=[int(x) for x in ry.nsmallest(3).index],
                          years=[dict(year=int(k), rel=round(float(v), 2)) for k, v in ry.items()]))
    v = val[val.point == pid]
    validation = [dict(crop=CROP_UA[r.crop], year=int(r.year), obs=r.obs, pred=r.pred_model) for r in v.itertuples()]
    nd = ndvi[ndvi.ID == pid].sort_values("y")
    rotation = [dict(year=int(r.y), type=r.c, peak=r.peak, date=r.peak_date) for r in nd.itertuples()]
    fields.append(dict(id=pid, **meta, climate=clim, crops=crops, validation=validation, rotation=rotation))

# метрики моделі
def metr(col):
    e = (val[col] - val.obs).abs() / val.obs
    return dict(mape=round(100 * float(e.mean()), 1), rho=round(float(val[col].corr(val.obs, method="spearman")), 2))
metrics = [dict(name="Наша модель (FAO-56 + Ky)", **metr("pred_model")),
           dict(name="Середнє попередніх років", **metr("pred_clim")),
           dict(name="Лише опади сезону", **metr("pred_rain"))]

scatter = [dict(crop=CROP_UA[r.crop], oblast=r.oblast, year=int(r.year), obs=r.obs, pred=r.pred_model) for r in val.itertuples()]

data = dict(
    oblasts=dict(type="FeatureCollection", features=feats),
    power=power[["lon", "lat"]].round(3).values.tolist(),
    smap=smap[["lon", "lat"]].round(3).values.tolist(),
    fields=fields, metrics=metrics, scatter=scatter, n_val=len(val),
    grid_counts=None if counts is None else counts.assign(
        region=counts.region.map(lambda s: UA_NAMES.get(s, s))).to_dict("records"),
)
# реальні поля (site/export_fields.py) + точки HLS-запиту (appeears_hls.py points)
import os
fw = os.path.join(os.path.dirname(os.path.abspath(DST)), "fields_windows.json")
if os.path.exists(fw):
    win = json.load(open(fw, encoding="utf-8"))
    for ob, w in win.items():
        pts = f"{OUT}/hls/{ob}_points.csv"
        w["hls_points"] = {}
        if os.path.exists(pts):
            for r in pd.read_csv(pts).itertuples():
                w["hls_points"].setdefault(str(r.Category).lstrip("f"), []).append([round(r.Longitude, 6), round(r.Latitude, 6)])
        # HLS 30 м: сезони і ряд NDVI по полях (appeears_hls.py ndvi)
        se, ts = f"{OUT}/hls/{ob}_ndvi_seasons.csv", f"{OUT}/hls/{ob}_ndvi_timeseries.csv"
        if os.path.exists(se) and os.path.exists(ts):
            S = pd.read_csv(se); T = pd.read_csv(ts, parse_dates=["date"])
            T["d"] = (T.date - pd.Timestamp("2016-01-01")).dt.days
            hls = {}
            for fid, g in S.groupby("field"):
                k = str(fid).lstrip("f")
                hls[k] = dict(seasons=[[int(r.y), r.c, "" if pd.isna(r.sub) else r.sub,
                                        None if pd.isna(r.peak) else float(r.peak),
                                        None if pd.isna(r.peak_date) else r.peak_date] for r in g.sort_values("y").itertuples()])
            for fid, g in T.groupby("field"):
                k = str(fid).lstrip("f")
                if k in hls:
                    hls[k]["ts"] = [[int(d), round(float(v), 2)] for d, v in zip(g.d, g.ndvi)]
            w["hls"] = hls
            w["hls_years"] = sorted(int(y) for y in S.y.unique())
    data["windows"] = win
else:
    print("немає", fw, "- секція реальних полів буде порожня (python site/export_fields.py)")
fg = os.path.join(os.path.dirname(os.path.abspath(DST)), "fields_grid.json")
if os.path.exists(fg):
    data["fgrid"] = json.load(open(fg, encoding="utf-8"))
for sj in ("strategies.json", "ecostress.json", "portfolio.json", "market.json"):   # export_site_strategies, ecostress_compare, portfolio, market_*
    if os.path.exists(sj := os.path.join(os.path.dirname(os.path.abspath(DST)), sj)):
        data.update({k: v for k, v in json.load(open(sj, encoding="utf-8")).items()
                     if k in ("strategies", "strategies_demo", "ecostress", "portfolio", "market_export", "market_ports")})
json.dump(data, open(DST, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("ok", DST, round(len(json.dumps(data)) / 1024), "KB; metrics:", metrics)

# вбудувати дані в сторінку: site/template.html -> site/index.html
import os
tpl = os.path.join(os.path.dirname(os.path.abspath(DST)), "template.html")
if os.path.exists(tpl):
    i18n = os.path.join(os.path.dirname(os.path.abspath(DST)), "i18n.json")      # словник EN/UA (site/i18n.json)
    i18n = open(i18n, encoding="utf-8").read() if os.path.exists(i18n) else '{"names": {}, "strings": {}}'
    html = (open(tpl, encoding="utf-8").read().replace("__I18N__", i18n)
            .replace("__DATA__", open(DST, encoding="utf-8").read()))
    idx = os.path.join(os.path.dirname(os.path.abspath(DST)), "index.html")
    open(idx, "w", encoding="utf-8").write(html)
    print("сторінка:", idx)
