#!/usr/bin/env python3
"""Завантаження NASA POWER (daily, community=AG) по ВУЗЛАХ сітки, з кешем.

Вузли збираються з out/fields/*_fields_window.geojson (поля power_lat/power_lon).
Кеш: data/raw/power/power_<lat>_<lon>.csv + .meta.json (запитані й фактично повернуті координати,
одиниці, URL, час). Наявний файл не перекачується.

Параметри й період — ті самі, що в baseline_model.py (POWER_PARAMS, 2001–2025), плюс T2MDEW (точка роси,
для оцінки RHmin на кроці 3), якщо POWER її повертає.

  python scripts/fetch_power.py --list                       # показати вузли, нічого не качати
  python scripts/fetch_power.py --node 47.0 30.625 --compare out/power_berezivka_od.csv
  python scripts/fetch_power.py --all                        # усі вузли вікон
"""
import argparse
import glob
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from baseline_model import POWER_PARAMS  # noqa: E402  — той самий набір, що в наявних power_*.csv

CACHE = ROOT / "data" / "raw" / "power"
API = "https://power.larc.nasa.gov/api/temporal/daily/point"
START, END = "20010101", "20251231"          # як у baseline_model.load_power
EXTRA = ["T2MDEW"]


def node_name(lat, lon):
    return f"power_{lat:.3f}_{lon:.3f}"


def list_nodes():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "out" / "fields" / "*_fields_window.geojson"))):
        ob = Path(f).name.split("_fields")[0]
        with open(f, encoding="utf-8") as fh:
            feats = json.load(fh)["features"]
        for p in (x["properties"] for x in feats):
            rows.append((ob, float(p["power_lat"]), float(p["power_lon"])))
    df = pd.DataFrame(rows, columns=["window", "lat", "lon"])
    return df.groupby(["lat", "lon"]).agg(windows=("window", lambda s: ",".join(sorted(set(s)))),
                                          n_fields=("window", "size")).reset_index()


def fetch(lat, lon, params, retries=3):
    import requests
    q = dict(parameters=",".join(params), community="AG", latitude=lat, longitude=lon,
             start=START, end=END, format="JSON")
    for i in range(retries):
        r = requests.get(API, params=q, timeout=300)
        if r.status_code == 200:
            return r.json(), r.url
        if r.status_code in (422, 400):
            raise ValueError(f"POWER {r.status_code}: {r.text[:500]}")
        time.sleep(5 * (i + 1))
    r.raise_for_status()


def get_node(lat, lon, force=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    csv, meta = CACHE / f"{node_name(lat, lon)}.csv", CACHE / f"{node_name(lat, lon)}.meta.json"
    if csv.exists() and meta.exists() and not force:
        with open(meta, encoding="utf-8") as fh:
            return pd.read_csv(csv, parse_dates=["date"], index_col="date"), json.load(fh)
    params = POWER_PARAMS.split(",") + EXTRA
    try:
        js, url = fetch(lat, lon, params)
        missing = []
    except ValueError as e:                     # параметр не прийнято — повтор без EXTRA, фіксуємо в meta
        print(f"  увага: {EXTRA} не прийнято: {e}")
        js, url = fetch(lat, lon, POWER_PARAMS.split(","))
        missing, params = EXTRA, POWER_PARAMS.split(",")
    df = pd.DataFrame(js["properties"]["parameter"])
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    fill = js.get("header", {}).get("fill_value", -999.0)
    df = df.replace(fill, np.nan)[params]
    df.to_csv(csv)
    m = dict(requested=dict(lat=lat, lon=lon), returned_geometry=js.get("geometry"),
             params=params, params_missing=missing,
             units={k: v.get("units") for k, v in js.get("parameters", {}).items()},
             longnames={k: v.get("longname") for k, v in js.get("parameters", {}).items()},
             header={k: v for k, v in js.get("header", {}).items() if k != "sources"},
             sources=js.get("header", {}).get("sources"),
             url=url, fetched_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
             nan_share={k: round(float(df[k].isna().mean()), 4) for k in params},
             flag="погода — клітинка POWER ~50 км, клімат району, не поля")
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=1)
    return df, m


# Пілотні точки лежать у своїх вузлах (перевірено); їхні CSV не перекачуємо — докачуємо лише EXTRA.
# Еквівалентність «запит у точку пілота = запит у вузол» перевірено на Одесі: 9131 день × 7 параметрів, 0 розбіжностей.
PILOT_CSV = {(48.0, 31.25): "out/power_arbuzynka_mk.csv", (49.5, 35.0): "out/power_karlivka_pl.csv",
             (49.5, 28.75): "out/power_kalynivka_vn.csv"}


def get_pilot_node(lat, lon, ref):
    csv, meta = CACHE / f"{node_name(lat, lon)}.csv", CACHE / f"{node_name(lat, lon)}.meta.json"
    if csv.exists() and meta.exists():
        return get_node(lat, lon)
    CACHE.mkdir(parents=True, exist_ok=True)
    base = pd.read_csv(ROOT / ref, parse_dates=["date"], index_col="date")
    js, url = fetch(lat, lon, EXTRA)
    ex = pd.DataFrame(js["properties"]["parameter"])
    ex.index = pd.to_datetime(ex.index, format="%Y%m%d")
    ex = ex.replace(js.get("header", {}).get("fill_value", -999.0), np.nan)
    df = base.join(ex[EXTRA], how="left")
    df.index.name = "date"
    df.to_csv(csv)
    m = dict(requested=dict(lat=lat, lon=lon), returned_geometry=js.get("geometry"),
             params=list(df.columns), params_missing=[], copied_from=ref, extra_fetched=EXTRA,
             units={k: v.get("units") for k, v in js.get("parameters", {}).items()},
             header={k: v for k, v in js.get("header", {}).items() if k != "sources"},
             url=url, fetched_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
             nan_share={k: round(float(df[k].isna().mean()), 4) for k in df.columns},
             flag="погода — клітинка POWER ~50 км, клімат району, не поля")
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(m, fh, ensure_ascii=False, indent=1)
    return df, m


TSOIL = ["TSOIL1", "T2M"]     # TSOIL1 — MERRA-2, шар 0.018–0.0988 м (≈ 10 см глибини загортання); T2M — для порівняння з проксі


def get_tsoil(lat, lon, force=False):
    """Температура ґрунту для динамічної сівби ярих — окремий файл tsoil_<вузол>.csv (основні power_*.csv не чіпаємо)."""
    csv = CACHE / f"tsoil_{lat:.3f}_{lon:.3f}.csv"
    meta = csv.with_suffix(".meta.json")
    if csv.exists() and meta.exists() and not force:
        return pd.read_csv(csv, parse_dates=["date"], index_col="date")
    js, url = fetch(lat, lon, TSOIL)
    df = pd.DataFrame(js["properties"]["parameter"])
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    df = df.replace(js.get("header", {}).get("fill_value", -999.0), np.nan)[TSOIL]
    df.to_csv(csv)
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump(dict(requested=dict(lat=lat, lon=lon), returned_geometry=js.get("geometry"), params=TSOIL,
                       units={k: v.get("units") for k, v in js.get("parameters", {}).items()},
                       definition="TSOIL1: The estimate of soil temperatures at layer 1; 0.018 to 0.0988 m depth (POWER parameter manager, community=AG)",
                       header={k: v for k, v in js.get("header", {}).items() if k != "sources"},
                       sources=js.get("header", {}).get("sources"), url=url,
                       fetched_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       nan_share={k: round(float(df[k].isna().mean()), 4) for k in TSOIL}), fh, ensure_ascii=False, indent=1)
    return df


def compare(df, ref_path):
    ref = pd.read_csv(ref_path, parse_dates=["date"], index_col="date")
    idx = df.index.intersection(ref.index)
    rows = []
    for c in ref.columns:
        a, b = df.loc[idx, c], ref.loc[idx, c]
        d = (a - b).abs()
        rows.append(dict(param=c, days=len(idx), days_diff=int((d > 1e-9).sum()), max_abs_diff=round(float(d.max()), 4),
                         mean_abs_diff=round(float(d.mean()), 4), nan_new=int(a.isna().sum()), nan_ref=int(b.isna().sum())))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--node", nargs=2, type=float)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--compare", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--tsoil", action="store_true", help="лише TSOIL1 (+T2M) → tsoil_<вузол>.csv для --node/--all")
    a = ap.parse_args()
    if a.tsoil:
        todo = [tuple(a.node)] if a.node else [(r.lat, r.lon) for r in list_nodes().itertuples()]
        for lat, lon in todo:
            df = get_tsoil(lat, lon, a.force)
            print(f"tsoil_{lat:.3f}_{lon:.3f}: {len(df)} днів, NaN TSOIL1 {df.TSOIL1.isna().mean():.3%}")
        return
    if a.list:
        n = list_nodes()
        print(n.to_string(index=False), f"\nвузлів: {len(n)}, полів: {n.n_fields.sum()}")
        return
    todo = [tuple(a.node)] if a.node else ([(r.lat, r.lon) for r in list_nodes().itertuples()] if a.all else [])
    for lat, lon in todo:
        if (lat, lon) in PILOT_CSV and not a.force:
            df, m = get_pilot_node(lat, lon, PILOT_CSV[(lat, lon)])
        else:
            df, m = get_node(lat, lon, a.force)
        print(f"{node_name(lat, lon)}: {len(df)} днів, {df.index.min().date()}..{df.index.max().date()}, "
              f"POWER повернув {m['returned_geometry']}, без параметрів: {m['params_missing']}")
        if a.compare:
            print(compare(df, a.compare).to_string(index=False))


if __name__ == "__main__":
    main()
