#!/usr/bin/env python3
"""Готує реальні поля (вікна навколо пілотів) для сайту: спрощує межі і пише site/fields_windows.json.
Запуск з папки nasa: python site/export_fields.py
Джерело: out/fields/<oblast>_fields_window.geojson і <oblast>_fields_stats.csv (робить fields_map.py)."""
import csv
import json
import math
import os

import numpy as np

SRC = os.path.join("out", "fields")
DST = os.path.join("site", "fields_windows.json")
WINDOWS = {  # область -> підпис і пілотна точка моделі (якщо є)
    "poltava": dict(title="Полтавська · Карлівка", model_point="karlivka_pl"),
    "volyn": dict(title="Волинська", model_point=None),
    "vinnytsia": dict(title="Вінницька · Калинівка", model_point="kalynivka_vn"),
    "mykolaiv": dict(title="Миколаївська · Арбузинка", model_point="arbuzynka_mk"),
    "odesa": dict(title="Одеська · Березівка", model_point="berezivka_od"),
}
TOL_M = 4.0  # допуск спрощення; межі в даних — сходинки по 3 м


def rdp(xy, tol):
    keep = np.zeros(len(xy), bool); keep[0] = keep[-1] = True
    stack = [(0, len(xy) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = xy[i], xy[j]; seg = b - a; L = math.hypot(*seg)
        p = xy[i + 1:j] - a
        d = np.abs(seg[0] * p[:, 1] - seg[1] * p[:, 0]) / L if L > 0 else np.hypot(p[:, 0], p[:, 1])
        k = int(d.argmax())
        if d[k] > tol:
            m = i + 1 + k; keep[m] = True; stack += [(i, m), (m, j)]
    return xy[keep]


def simplify(coords, lat0):
    c = np.array(coords, float)
    kx = 111320 * math.cos(math.radians(lat0)); ky = 110540
    xy = np.column_stack([c[:, 0] * kx, c[:, 1] * ky])
    s = rdp(xy, TOL_M)
    if len(s) < 4:
        s = xy
    return [[round(x / kx, 5), round(y / ky, 5)] for x, y in s]


out = {}
for ob, meta in WINDOWS.items():
    gj = os.path.join(SRC, f"{ob}_fields_window.geojson")
    if not os.path.exists(gj):
        print("немає", gj); continue
    fc = json.load(open(gj, encoding="utf-8"))
    v0 = v1 = 0; feats = []
    for f in fc["features"]:
        p = f["properties"]; g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        new = []
        for poly in polys:
            rings = []
            for r in poly:
                v0 += len(r); s = simplify(r, p["lat"]); v1 += len(s); rings.append(s)
            new.append(rings)
        feats.append(dict(type="Feature",
                          geometry=dict(type="Polygon", coordinates=new[0]) if len(new) == 1 else dict(type="MultiPolygon", coordinates=new),
                          properties=dict(id=int(p["fid"]), ha=p["area_ha"], modis=p["modis_px"], hls=p["hls_px"],
                                          pw=[p["power_lon"], p["power_lat"]], smap=[p["smap_row"], p["smap_col"]],
                                          pilot=p.get("pilot") or "")))
    # розподіл площ по всій області
    areas = np.array([float(r["area_ha"]) for r in csv.DictReader(open(os.path.join(SRC, f"{ob}_fields_stats.csv"), encoding="utf-8"))])
    edges = [0, 1, 2, 5.37, 10, 21.5, 50, 100, 250, 1e9]  # 5,37 га = 1 піксель MODIS, 21,5 = 4 пікселі
    hist = [int(((areas >= a) & (areas < b)).sum()) for a, b in zip(edges[:-1], edges[1:])]
    out[ob] = dict(**meta, features=feats,
                   stats=dict(n=int(len(areas)), median=round(float(np.median(areas)), 1),
                              lt_modis=round(100 * float((areas < 5.37).mean()), 1),  # піксель MOD13Q1 231,66 м = 5,37 га
                              total_kha=round(float(areas.sum()) / 1000, 1), edges=edges[:-1], hist=hist))
    pil = [x for x in feats if x["properties"]["pilot"]]
    print(f"{ob}: {len(feats)} полів у вікні, вершин {v0:,} -> {v1:,}; пілот: {[x['properties']['id'] for x in pil]}")
json.dump(out, open(DST, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("->", DST, round(os.path.getsize(DST) / 1e6, 2), "МБ")
