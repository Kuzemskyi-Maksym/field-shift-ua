#!/usr/bin/env python3
"""HLS 30 м NDVI по реальних полях через AppEEARS API (NASA LP DAAC).

Кроки (з папки nasa):
  1) python appeears_hls.py points            # точки всередині полів -> out/hls/*_points.csv (без мережі)
  2) python appeears_hls.py check             # логін Earthdata + перевірка, що продукти/шари існують
  3) python appeears_hls.py submit            # відправити запит(и), task_id запишеться в out/hls/tasks.json
  4) python appeears_hls.py status            # статус (обробка — від кількох годин до доби)
  5) python appeears_hls.py download          # завантажити CSV результатів
  6) python appeears_hls.py ndvi              # NDVI по полях + сезони/сівозміна -> out/hls/*_ndvi_*.csv

Логін Earthdata: змінні EARTHDATA_USER / EARTHDATA_PASS або запит у консолі.
Точки беруться з out/fields/<oblast>_appeears_fields.geojson (пілот + 50 найбільших полів),
їх робить fields_map.py. Точка ставиться не ближче 45 м до межі, щоб піксель 30 м не зачіпав сусіда.
Запасний варіант без API: файл out/hls/<oblast>_points.csv можна завантажити вручну
в AppEEARS -> Point Sample -> Upload CSV (колонки ID, Category, Latitude, Longitude).
"""
import argparse
import csv
import getpass
import json
import math
import os
import re
import sys
import time

import numpy as np

API = "https://appeears.earthdatacloud.nasa.gov/api"
OUT = os.path.join("out", "hls")
FIELDS_DIR = os.path.join("out", "fields")
# HLS v2.0: Sentinel-2 (S30) NIR = B8A, Landsat (L30) NIR = B05; Red = B04 в обох; Fmask — хмари/тіні/сніг
LAYERS = {"HLSS30.020": ["B04", "B8A", "Fmask"], "HLSL30.020": ["B04", "B05", "Fmask"]}
NIR = {"HLSS30": "B8A", "HLSL30": "B05"}
TASKS_FILE = os.path.join(OUT, "tasks.json")


# ------------------------------------------------------------------ точки всередині полів (без мережі)
def _local_xy(lon, lat, lon0, lat0):
    R = 6371008.8
    return (np.radians(lon - lon0) * R * math.cos(math.radians(lat0)), np.radians(lat - lat0) * R)


def _inside(px, py, ring):
    """Векторний ray casting: точки (N) × ребра кільця (M)."""
    x1, y1 = ring[:-1, 0], ring[:-1, 1]
    x2, y2 = ring[1:, 0], ring[1:, 1]
    P, Q = px[:, None], py[:, None]
    cond = (y1 > Q) != (y2 > Q)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = x1 + (Q - y1) * (x2 - x1) / (y2 - y1)
    return (cond & (P < xint)).sum(1) % 2 == 1


def _dist_to_edges(px, py, rings):
    d = np.full(len(px), np.inf)
    for ring in rings:
        a, b = ring[:-1], ring[1:]
        for s in range(0, len(a), 4000):  # частинами, щоб не роздувати пам'ять
            ax, ay, bx, by = a[s:s + 4000, 0], a[s:s + 4000, 1], b[s:s + 4000, 0], b[s:s + 4000, 1]
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            L[L == 0] = 1e-9
            t = np.clip(((px[:, None] - ax) * dx + (py[:, None] - ay) * dy) / L, 0, 1)
            cx, cy = ax + t * dx, ay + t * dy
            d = np.minimum(d, np.sqrt((px[:, None] - cx) ** 2 + (py[:, None] - cy) ** 2).min(1))
    return d


def field_points(geom, k=5, inset=45.0, step=30.0):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    allc = np.array([c for p in polys for c in p[0]], float)
    lon0, lat0 = allc[:, 0].mean(), allc[:, 1].mean()
    rings_xy, outer = [], []
    for p in polys:
        for j, r in enumerate(p):
            r = np.array(r, float)
            xy = np.column_stack(_local_xy(r[:, 0], r[:, 1], lon0, lat0))
            rings_xy.append(xy)
            outer.append(j == 0)
    xs = np.concatenate([r[:, 0] for r in rings_xy]); ys = np.concatenate([r[:, 1] for r in rings_xy])
    gx, gy = np.meshgrid(np.arange(xs.min(), xs.max(), step), np.arange(ys.min(), ys.max(), step))
    px, py = gx.ravel(), gy.ravel()
    if len(px) > 20000:  # великі поля: прорідити сітку
        sel = np.linspace(0, len(px) - 1, 20000).astype(int); px, py = px[sel], py[sel]
    inside = np.zeros(len(px), bool)
    for xy, is_outer in zip(rings_xy, outer):
        m = _inside(px, py, xy)
        inside = inside | m if is_outer else inside & ~m
    px, py = px[inside], py[inside]
    if len(px) == 0:
        return [], 0.0
    d = _dist_to_edges(px, py, rings_xy)
    used = inset
    ok = d >= inset
    if ok.sum() == 0:  # вузьке поле — беремо найглибші точки
        used = float(d.max()); ok = d >= used - 1e-6
    px, py, d = px[ok], py[ok], d[ok]
    # перша — найглибша, далі — найвіддаленіші від уже вибраних (рівномірно по полю)
    idx = [int(d.argmax())]
    md = np.hypot(px - px[idx[0]], py - py[idx[0]])
    while len(idx) < min(k, len(px)):
        j = int(md.argmax())
        if md[j] < 60:  # точки ближче 60 м дублюють той самий піксель/сусіда
            break
        idx.append(j); md = np.minimum(md, np.hypot(px - px[j], py - py[j]))
    R = 6371008.8
    pts = [(lon0 + math.degrees(px[i] / (R * math.cos(math.radians(lat0)))), lat0 + math.degrees(py[i] / R)) for i in idx]
    return pts, used


def cmd_points(a):
    os.makedirs(OUT, exist_ok=True)
    for ob in a.oblast:
        src = os.path.join(FIELDS_DIR, f"{ob}_appeears_fields.geojson")
        if not os.path.exists(src):
            print(f"[{ob}] немає {src} — спершу python fields_map.py --oblast {ob} ..."); continue
        fc = json.load(open(src, encoding="utf-8"))
        rows, narrow = [], 0
        for f in fc["features"]:
            fid = str(f["properties"]["id"])
            pts, used = field_points(f["geometry"], k=a.k)
            if used < 45: narrow += 1
            for n, (lon, lat) in enumerate(pts, 1):
                rows.append(dict(ID=f"{fid}_{n}", Category=fid, Latitude=round(lat, 6), Longitude=round(lon, 6)))
        dst = os.path.join(OUT, f"{ob}_points.csv")
        with open(dst, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["ID", "Category", "Latitude", "Longitude"]); w.writeheader(); w.writerows(rows)
        print(f"[{ob}] полів {len(fc['features'])}, точок {len(rows)} (вузьких полів з відступом < 45 м: {narrow}) -> {dst}")


# ------------------------------------------------------------------ AppEEARS API
def _req():
    try:
        import requests
        return requests
    except ImportError:
        sys.exit("Потрібен пакет requests: pip install requests")


def login():
    rq = _req()
    user = os.environ.get("EARTHDATA_USER") or input("Earthdata логін: ").strip()
    pw = os.environ.get("EARTHDATA_PASS") or getpass.getpass("Earthdata пароль (не відображається): ")
    r = rq.post(f"{API}/login", auth=(user, pw), timeout=60)
    if r.status_code != 200:
        sys.exit(f"Логін не вдався: HTTP {r.status_code} {r.text[:300]}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def cmd_check(a):
    rq = _req(); H = login()
    print("Логін OK.")
    for prod, lays in LAYERS.items():
        r = rq.get(f"{API}/product/{prod}", headers=H, timeout=60)
        if r.status_code != 200:
            print(f"  {prod}: HTTP {r.status_code} — продукту з такою назвою немає, перевір у {API}/product"); continue
        have = set(r.json().keys())
        miss = [l for l in lays if l not in have]
        print(f"  {prod}: шари {lays} {'OK' if not miss else 'НЕМАЄ ' + str(miss) + '; є: ' + str(sorted(have))}")


def load_tasks():
    return json.load(open(TASKS_FILE, encoding="utf-8")) if os.path.exists(TASKS_FILE) else {}


def _split_dates(start, end, n):
    """Ділить період MM-DD-YYYY на n частин по цілих роках (останній шматок — до end)."""
    y0, y1 = int(start[-4:]), int(end[-4:])
    years = list(range(y0, y1 + 1)); n = min(n, len(years))
    chunks = [years[i * len(years) // n:(i + 1) * len(years) // n] for i in range(n)]
    return [(start if c[0] == y0 else f"01-01-{c[0]}", end if c[-1] == y1 else f"12-31-{c[-1]}") for c in chunks]


def cmd_submit(a):
    rq = _req(); H = login(); tasks = load_tasks()
    for ob in a.oblast:
        src = os.path.join(OUT, f"{ob}_points.csv")
        if not os.path.exists(src):
            print(f"[{ob}] немає {src} — спершу: python appeears_hls.py points"); continue
        pts = list(csv.DictReader(open(src, encoding="utf-8")))
        coords = [{"id": p["ID"], "category": p["Category"],
                   "latitude": float(p["Latitude"]), "longitude": float(p["Longitude"])} for p in pts]
        layers = [{"product": p, "layer": l} for p, ls in LAYERS.items() for l in ls]
        n = a.chunks
        while True:
            parts = _split_dates(a.start, a.end, n); done = []; too_big = None
            for i, (d0, d1) in enumerate(parts, 1):
                body = {"task_type": "point", "task_name": f"fieldshift_hls_{ob}_{d0[-4:]}_{d1[-4:]}",
                        "params": {"dates": [{"startDate": d0, "endDate": d1}], "layers": layers, "coordinates": coords}}
                r = rq.post(f"{API}/task", json=body, headers=H, timeout=120)
                if r.status_code in (200, 202):
                    done.append(dict(task_id=r.json()["task_id"], dates=f"{d0}..{d1}"))
                    print(f"[{ob}] відправлено {d0}..{d1}: {len(pts)} точок, task_id {done[-1]['task_id']}")
                    continue
                m = re.search(r"exceeds the maximum allowed by ([\d.]+)%", r.text)
                if m and not done:
                    too_big = float(m.group(1)); break
                print(f"[{ob}] помилка HTTP {r.status_code} для {d0}..{d1}: {r.text[:400]}")
            if too_big is not None:
                # скільки частин треба: обсяг × (1 + перевищення), із запасом 15%
                need = math.ceil(n * (1 + too_big / 100) * 1.15)
                if need > 20 or need <= n:
                    print(f"[{ob}] запит завеликий навіть після поділу; зменш --k або період"); break
                print(f"[{ob}] перевищення {too_big}% — ділю період на {need} запит(и)")
                n = need; continue
            if done:
                tasks[ob] = tasks.get(ob, []) if isinstance(tasks.get(ob), list) else []
                tasks[ob] += done
            break
    json.dump(tasks, open(TASKS_FILE, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def _task_list(tasks):
    for ob, v in tasks.items():
        for t in (v if isinstance(v, list) else [dict(task_id=v, dates="")]):
            yield ob, t["task_id"], t.get("dates", "")


def cmd_status(a):
    rq = _req(); H = login()
    for ob, tid, dates in _task_list(load_tasks()):
        r = rq.get(f"{API}/task/{tid}", headers=H, timeout=60).json()
        print(f"[{ob}] {dates} {tid}: {r.get('status')} {r.get('progress', '')}")


def _all_done_tasks(rq, H):
    """Усі готові запити fieldshift_hls_<oblast>_* в акаунті (незалежно від tasks.json)."""
    out = []
    for t in rq.get(f"{API}/task", headers=H, timeout=60).json():
        m = re.match(r"fieldshift_hls_([a-z-]+)_(\d{4})_(\d{4})$", t.get("task_name", ""))
        if m and t.get("status") == "done":
            out.append((m.group(1), t["task_id"], f"{m.group(2)}..{m.group(3)}"))
    return out


def cmd_download(a):
    rq = _req(); H = login()
    lst = _all_done_tasks(rq, H) if a.all else list(_task_list(load_tasks()))
    if a.all:
        lst = [x for x in lst if x[0] in a.oblast]
        print(f"Готових запитів в акаунті: {len(lst)}")
    for ob, tid, dates in lst:
        st = rq.get(f"{API}/task/{tid}", headers=H, timeout=60).json().get("status")
        if st != "done":
            print(f"[{ob}] {dates} ще не готово: {st}"); continue
        files = rq.get(f"{API}/bundle/{tid}", headers=H, timeout=60).json()["files"]
        d = os.path.join(OUT, ob); os.makedirs(d, exist_ok=True)
        for f in files:
            if not f["file_name"].endswith(".csv"):
                continue
            dst = os.path.join(d, f"{tid[:8]}_" + os.path.basename(f["file_name"]))
            if os.path.exists(dst):
                print(f"[{ob}] вже є {dst}"); continue
            with rq.get(f"{API}/bundle/{tid}/{f['file_id']}", headers=H, stream=True, allow_redirects=True, timeout=600) as r:
                r.raise_for_status()
                with open(dst, "wb") as fh:
                    for ch in r.iter_content(1 << 20): fh.write(ch)
            print(f"[{ob}] {dst} ({os.path.getsize(dst) / 1e6:.1f} МБ)")


# ------------------------------------------------------------------ NDVI
def fmask_clear(v):
    """Біти Fmask HLS v2: 1 хмара, 2 поруч з хмарою, 3 тінь, 4 сніг/лід, 5 вода. Чисто = всі нулі."""
    v = v.fillna(255).astype(int)
    return ((v & 0b111110) == 0) & ((v // 64) != 3)  # + без високого аерозолю (біти 6–7 = 11)


def cmd_ndvi(a):
    import pandas as pd
    for ob in a.oblast:
        d = os.path.join(OUT, ob)
        if not os.path.isdir(d):
            print(f"[{ob}] немає {d} — спершу download"); continue
        parts = []
        for fn in os.listdir(d):
            if not fn.endswith(".csv"):
                continue
            df = pd.read_csv(os.path.join(d, fn))
            sensor = "HLSS30" if "HLSS30" in fn else "HLSL30" if "HLSL30" in fn else None
            if sensor is None:
                continue
            col = lambda band: next((c for c in df.columns if re.search(rf"{sensor}_020_{band}$", c)), None)
            red, nir, fm = col("B04"), col(NIR[sensor]), col("Fmask")
            if not (red and nir and fm):
                print(f"  {fn}: не знайшов колонки B04/{NIR[sensor]}/Fmask. Колонки: {list(df.columns)}"); continue
            x = df[["ID", "Category", "Date", red, nir, fm]].copy()
            x.columns = ["pid", "field", "date", "red", "nir", "fmask"]
            x["sensor"] = sensor
            parts.append(x)
            print(f"  {fn}: {len(x)} рядків")
        if not parts:
            continue
        x = pd.concat(parts)
        x["date"] = pd.to_datetime(x["date"])
        scale = 1.0 if x.nir.median() < 2 else 1e-4   # AppEEARS віддає відбивання вже масштабованим (0–1)
        x["red"], x["nir"] = x.red * scale, x.nir * scale
        ok = fmask_clear(x.fmask) & (x.red > 0) & (x.nir > 0) & (x.red < 0.35) & (x.nir < 1.0)  # red > 0,35 — пропущена хмара/сніг
        x = x[ok]
        x["ndvi"] = (x.nir - x.red) / (x.nir + x.red)   # масштаб відбивання скорочується
        # поле×дата: медіана по точках; беремо дату, якщо чисті ≥ половини точок поля
        npts = x.groupby("field").pid.nunique()
        g = x.groupby(["field", "date"]).agg(ndvi=("ndvi", "median"), n=("pid", "nunique"), sensor=("sensor", "first")).reset_index()
        g = g[g.n >= np.ceil(g.field.map(npts) / 2)]
        ts = os.path.join(OUT, f"{ob}_ndvi_timeseries.csv"); g.assign(ndvi=g.ndvi.round(4)).to_csv(ts, index=False)
        # сезони: та сама логіка, що й для MODIS (W — зелене вже у квітні, S — пік з липня), плюс деталі з 30 м
        g["y"], g["m"] = g.date.dt.year, g.date.dt.month
        rows = []
        for (fid, y), s in g[g.m.between(3, 10)].groupby(["field", "y"]):
            if len(s) < 6:
                rows.append(dict(field=fid, y=y, n_obs=len(s), c="?", note="мало чистих знімків")); continue
            sm = s.set_index("date").ndvi.rolling("20D").median()  # прибрати поодинокі хмари, що проскочили
            pk_d = sm.idxmax(); pk = sm.max()
            apr = s[s.m == 4].ndvi.median(); aug = s[s.m == 8].ndvi.median(); sep = s[s.m == 9].ndvi.median()
            # Головна ознака — квітень: озима вже зелена (≥0,5), ярова ще не зійшла (поле голе, < 0,3).
            # Проміжне значення (холодна весна, напр. 2018) — дивимось, коли пік і чи зібране поле в серпні.
            has_apr, has_aug = apr == apr, aug == aug
            early_peak = pk_d.strftime("%m-%d") <= "06-30" and has_aug and aug < 0.45
            if has_apr and apr >= 0.5:
                c = "W"
            elif has_apr and apr < 0.3:
                c = "S"
            elif has_apr and early_peak:
                c = "W"
            elif pk_d.month >= 7:
                c = "S"
            else:
                c = "?"
            if pk < 0.4:
                c = "F"  # слабка рослинність увесь сезон: пар/незасіяне/пошкоджене
            # підтип ярої (гіпотеза, не культура): рання — пік до 20.07 і в серпні вже суха (соняшник/ярі зернові?),
            # пізня — у серпні ще зелена (кукурудза/соя?)
            sub = ""
            if c == "S":
                sub = "early" if pk_d.strftime("%m-%d") <= "07-20" and has_aug and aug < 0.5 else "late" if has_aug and aug >= 0.6 else ""
            rows.append(dict(field=fid, y=y, n_obs=len(s), peak=round(pk, 2), peak_date=pk_d.strftime("%m-%d"),
                             apr=round(apr, 2) if apr == apr else None, aug=round(aug, 2) if aug == aug else None,
                             sep=round(sep, 2) if sep == sep else None, c=c, sub=sub))
        r = pd.DataFrame(rows)
        dst = os.path.join(OUT, f"{ob}_ndvi_seasons.csv"); r.to_csv(dst, index=False)
        print(f"[{ob}] полів {r.field.nunique()}, поле-років {len(r)}: " + ", ".join(f"{k}={v}" for k, v in r.c.value_counts().items()))
        print(f"   -> {ts}\n   -> {dst}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["points", "check", "submit", "status", "download", "ndvi"])
    ap.add_argument("--oblast", nargs="+", default=["poltava", "volyn"])
    ap.add_argument("--start", default="01-01-2016", help="MM-DD-YYYY")
    ap.add_argument("--end", default="12-31-2025", help="MM-DD-YYYY")
    ap.add_argument("--k", type=int, default=5, help="точок на поле")
    ap.add_argument("--all", action="store_true", help="download: усі готові запити fieldshift_hls_* з акаунта")
    ap.add_argument("--chunks", type=int, default=1, help="на скільки запитів ділити період (підбирається сам)")
    a = ap.parse_args()
    {"points": cmd_points, "check": cmd_check, "submit": cmd_submit, "status": cmd_status,
     "download": cmd_download, "ndvi": cmd_ndvi}[a.cmd](a)
