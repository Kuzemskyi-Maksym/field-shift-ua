#!/usr/bin/env python3
"""SoilGrids 2.0 → clay/sand/silt (+ wv0033/wv1500) у центроїдах полів, з кешем.

REST API ISRIC (rest.isric.org) 12.11.2026 віддавав 503, тому — WCS maps.isric.org (той самий продукт SoilGrids 2.0).
Один GeoTIFF на (група полів × властивість × шар), пікселі EPSG:4326; значення беремо в пікселі, що містить центроїд.

Одиниці (docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html, табл. «Mapped units / Conversion factor»):
  clay, sand, silt: g/kg, коефіцієнт 10 → %;  wv0033, wv1500: 10^-3 cm³/cm³, коефіцієнт 10 → об. %.
Шари: 0-5, 5-15, 15-30, 30-60, 60-100, 100-200 см.

Поля: 4 пілоти (baseline_model.POINTS) + 250 HLS-полів (out/hls/<oblast>_points.csv → центроїд з *_fields_stats.csv).

  python scripts/fetch_soilgrids.py            # завантажити/взяти з кешу, записати data/raw/soil/soil_fields.csv
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from baseline_model import POINTS  # noqa: E402

CACHE = ROOT / "data" / "raw" / "soil"
WCS = "https://maps.isric.org/mapserv"
PROPS = {"clay": 10, "sand": 10, "silt": 10, "wv0033": 10, "wv1500": 10}     # conversion factor (ISRIC FAQ)
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]
MARGIN = 0.01   # град. навколо крайніх полів групи
HLS_OBLASTS = ["odesa", "mykolaiv", "poltava", "vinnytsia", "volyn"]
PILOT_OBLAST = {"berezivka_od": "odesa", "arbuzynka_mk": "mykolaiv", "karlivka_pl": "poltava", "kalynivka_vn": "vinnytsia"}


def fields():
    rows = [dict(field_id=k, group=PILOT_OBLAST[k], lat=v[0], lon=v[1], kind="pilot") for k, v in POINTS.items()]
    for ob in HLS_OBLASTS:
        ids = pd.read_csv(ROOT / "out" / "hls" / f"{ob}_points.csv").Category.unique()
        st = pd.read_csv(ROOT / "out" / "fields" / f"{ob}_fields_stats.csv", usecols=["fid", "lat", "lon"]).set_index("fid")
        for f in ids:
            r = st.loc[int(f[1:])]
            rows.append(dict(field_id=f"{ob}:{f}", group=ob, lat=float(r.lat), lon=float(r.lon), kind="hls"))
    return pd.DataFrame(rows)


def get_tile(group, prop, depth, bbox, retries=4):
    import requests
    path = CACHE / f"{group}_{prop}_{depth}.tif"
    if path.exists() and path.stat().st_size > 200:
        return path
    lon0, lat0, lon1, lat1 = bbox
    q = [("map", f"/map/{prop}.map"), ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
         ("COVERAGEID", f"{prop}_{depth}_mean"), ("FORMAT", "GEOTIFF_INT16"),
         ("SUBSET", f"X({lon0},{lon1})"), ("SUBSET", f"Y({lat0},{lat1})"),
         ("SUBSETTINGCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
         ("OUTPUTCRS", "http://www.opengis.net/def/crs/EPSG/0/4326")]
    for i in range(retries):
        try:
            r = requests.get(WCS, params=q, timeout=180)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/tiff"):
                CACHE.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                return path
            print(f"  {group} {prop} {depth}: HTTP {r.status_code} {r.text[:200]!r}")
        except Exception as e:  # noqa: BLE001 — мережа; повтор
            print(f"  {group} {prop} {depth}: {e}")
        time.sleep(5 * (i + 1))
    return None


def sample(path, lats, lons):
    from PIL import Image
    im = Image.open(path)
    a = np.array(im).astype(float)
    sx, sy = im.tag_v2[33550][:2]                    # ModelPixelScale
    x0, y0 = im.tag_v2[33922][3:5]                   # ModelTiepoint: верхній лівий кут
    nodata = im.tag_v2.get(42113)
    col = np.floor((np.asarray(lons) - x0) / sx).astype(int)
    row = np.floor((y0 - np.asarray(lats)) / sy).astype(int)
    ok = (row >= 0) & (row < a.shape[0]) & (col >= 0) & (col < a.shape[1])
    out = np.full(len(col), np.nan)
    out[ok] = a[row[ok], col[ok]]
    if nodata is not None:
        out[out == float(nodata)] = np.nan
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--props", default=",".join(PROPS))
    a = ap.parse_args()
    F = fields()
    out = []
    for g, gf in F.groupby("group"):
        bbox = (gf.lon.min() - MARGIN, gf.lat.min() - MARGIN, gf.lon.max() + MARGIN, gf.lat.max() + MARGIN)
        print(f"{g}: {len(gf)} полів, bbox {tuple(round(x, 3) for x in bbox)}")
        for prop in a.props.split(","):
            for d in DEPTHS:
                p = get_tile(g, prop, d, bbox)
                raw = sample(p, gf.lat, gf.lon) if p else np.full(len(gf), np.nan)
                for (_, r), v in zip(gf.iterrows(), raw):
                    out.append(dict(field_id=r.field_id, kind=r.kind, group=g, lat=r.lat, lon=r.lon, prop=prop, depth=d,
                                    raw=v, value=v / PROPS[prop]))
    df = pd.DataFrame(out)
    df.to_csv(CACHE / "soil_fields.csv", index=False)
    miss = df[df.raw.isna()]
    print(f"записано {len(df)} рядків, {df.field_id.nunique()} полів; пропусків: {len(miss)}")
    if len(miss):
        print(miss.groupby(["prop", "depth"]).size())


if __name__ == "__main__":
    main()
