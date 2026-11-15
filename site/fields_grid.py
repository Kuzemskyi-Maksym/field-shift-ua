#!/usr/bin/env python3
"""Сітка ~11 км по всіх оброблених областях: скільки полів, яка медіана площі, яка частка менша за піксель MODIS.
Джерело: out/fields/*_fields_stats.csv (робить fields_map.py для кожної області). Результат: site/fields_grid.json.
Запуск з папки nasa: python site/fields_grid.py"""
import glob
import json
import os

import numpy as np
import pandas as pd

DLAT, DLON = 0.1, 0.15  # ≈ 11 × 11 км на широті 48–51°
MODIS_HA = 5.37         # піксель MOD13Q1 231,66 м
parts = []
for f in sorted(glob.glob(os.path.join("out", "fields", "*_fields_stats.csv"))):
    ob = os.path.basename(f).replace("_fields_stats.csv", "")
    d = pd.read_csv(f, usecols=["area_ha", "lon", "lat"]); d["ob"] = ob; parts.append(d)
    print(f"{ob}: {len(d):,} полів")
if not parts:
    raise SystemExit("немає out/fields/*_fields_stats.csv — спершу fields_map.py")
d = pd.concat(parts)
d["i"] = np.floor(d.lat / DLAT).astype(int); d["j"] = np.floor(d.lon / DLON).astype(int)
g = d.groupby(["i", "j"])
cells = pd.DataFrame({"n": g.size(), "med": g.area_ha.median(), "small": g.area_ha.apply(lambda a: (a < MODIS_HA).mean()),
                      "ha": g.area_ha.sum()}).reset_index()
lat_c = (cells.i + .5) * DLAT
cell_ha = (DLAT * 111.32) * (DLON * 111.32 * np.cos(np.radians(lat_c))) * 100
cells["share"] = (cells.ha / cell_ha).clip(upper=1)
cells = cells[cells.n >= 5]
out = dict(dlat=DLAT, dlon=DLON, oblasts=sorted(d.ob.unique().tolist()), n=int(len(d)),
           cells=[[int(r.i), int(r.j), int(r.n), round(float(r.med), 1), round(float(r.small), 3), round(float(r.share), 3)]
                  for r in cells.itertuples()])
json.dump(out, open(os.path.join("site", "fields_grid.json"), "w"), separators=(",", ":"))
print(f"разом {len(d):,} полів у {len(cells):,} клітинках -> site/fields_grid.json")
