#!/usr/bin/env python3
"""
Field Shift — карта РЕАЛЬНИХ полів України (NASA Harvest, межі полів 2023) + прив'язка даних NASA до кожного поля.

Джерело меж полів: NASA Harvest, «Ukraine Field Boundary Delineation 2023» (CC BY),
Sadeh et al., Sci Data 12, 833 (2025), https://doi.org/10.1038/s41597-025-05190-7
Понад 5 млн полів, PlanetScope 3 м; точність ~77% за даними фермерів. Шейпфайли по областях.

Що робить скрипт:
  1. Завантажує межі полів області (ZIP із NASA Harvest Portal), кешує в data/fields/.
  2. Рахує для кожного поля площу, центр і «які дані NASA йому належать»:
     клітинка NASA POWER, клітинка SMAP 9 км, скільки пікселів MODIS 250 м і HLS 30 м уміщується в поле.
  3. Знаходить реальне поле під кожною нашою пілотною точкою (якщо точка в цій області).
  4. Малює карту полів у вікні навколо центру (супутник Esri + межі полів, клік — картка поля).
  5. Пише GeoJSON полів вікна для запиту AppEEARS (HLS NDVI 30 м по кожному полю) — наступний крок.

Запуск (потрібен інтернет):
  pip install requests numpy matplotlib pyproj
  python fields_map.py --oblast volyn                          # центр — середина області, радіус 12 км
  python fields_map.py --oblast poltava --center 49.366,35.013 # навколо пілотного поля Карлівка
  python fields_map.py --oblast volyn --center 50.75,25.33 --radius-km 8

Результат: out/fields/<oblast>_fields_map.html, <oblast>_fields_window.geojson, <oblast>_fields_stats.csv,
           <oblast>_appeears_fields.geojson
"""
import argparse
import io
import json
import math
import struct
import sys
import zipfile
from pathlib import Path

try:  # NASA Harvest пакує великі області методом Deflate64 (zip-метод 9), стандартний zipfile його не читає
    import zipfile_deflate64  # noqa: F401  (pip install zipfile-deflate64)
except ImportError:
    zipfile_deflate64 = None

import numpy as np
import requests
from matplotlib.path import Path as MplPath

DATA = Path("data/fields")
OUT = Path("out/fields")
UA = {"User-Agent": "FieldShift-SpaceApps2026/0.1 (education)"}
BASE = "https://data.harvestportal.org/dataset/39597661-59b1-4069-a2aa-5c26e5c9fd8a/resource"
ZIPS = {  # назва області -> (resource id, файл) з data.harvestportal.org (2023)
    "cherkasy": ("641c5dd6-cda4-4918-a8aa-120e49dc96ea", "cherkasy"), "chernihiv": ("d7926261-06e6-4a8d-bedf-de273e22c6f5", "chernihiv"),
    "chernivtsi": ("27442c7a-fdc4-405b-8a2a-df91fdc518d3", "chernivtsi"), "dnipropetrovsk": ("efac5a87-ea98-459c-80cb-7ed0c73e01a9", "dnipropetrovsk"),
    "ivano-frankivsk": ("2949df1a-bece-4e36-ba81-6265c3698b8c", "ivano-frankivsk"), "kharkiv": ("65f00235-7532-4acf-9e4b-6bfea52b080f", "kharkiv"),
    "kherson": ("a4610b82-30c9-48ed-bfb8-b02be19b1783", "kherson"), "khmelnytskyi": ("7c5ed4d3-cb28-4a9c-a779-e060e5e27893", "khmelnytskyi"),
    "kirovohrad": ("e7e59d4f-3079-4e94-94fd-f7d79c48c87c", "kirovohrad"), "kyiv": ("e7681930-4aa7-43ef-bba3-e75ced9ac63b", "kyiv"),
    "lviv": ("26be38d7-23bf-4f5e-a13d-67fe01fd4476", "lviv"), "mykolaiv": ("444ddaf2-23f7-4ca9-949a-dc9dbdb1b0d1", "mykolayiv"),
    "odesa": ("de8a7405-7302-4775-8ff9-05ba653cd09c", "odessa"), "poltava": ("9925eb11-6ccd-4d15-b8ba-114b546c27b9", "poltava"),
    "rivne": ("68dbfe4c-5d79-442e-a8a3-629bba576934", "rivne"), "sumy": ("ee4a8fdd-68b7-4378-b75d-35a879f53785", "sumy"),
    "ternopil": ("2734a120-7b0c-46b7-8d9e-7f9101732d34", "ternopil"), "vinnytsia": ("4128692d-2073-46b3-b78d-cd5fcb8d90c4", "vinnytsa"),
    "volyn": ("1deb907b-d909-4fb3-a66c-f21619d6fd49", "volyn"), "zakarpattia": ("ff9c0db8-b6ef-4a78-b8ef-eaa74e7c83e1", "zakarpattia"),
    "zaporizhzhia": ("6b10228d-8782-45cb-837e-ae85d76399c1", "zaporizhzhya"), "zhytomyr": ("ba75989a-a735-43da-8d6e-4353220e6d1d", "zhytomyr"),
}
PILOTS = {  # наші пілотні точки: (назва, lat, lon, область-ключ)
    "berezivka_od": ("Березівка", 47.103423, 30.671618, "odesa"),
    "arbuzynka_mk": ("Арбузинка", 47.997982, 31.364381, "mykolaiv"),
    "karlivka_pl": ("Карлівка", 49.366228, 35.013165, "poltava"),
    "kalynivka_vn": ("Калинівка", 49.621918, 28.688890, "vinnytsia"),
}


# ---------------------------------------------------------------- читання шейпфайлу без залежностей
def read_shp(shp: bytes):
    """Полігони (тип 5/15/25) зі .shp: список [кільце, ...] на запис; кільце = np.array (N, 2)."""
    file_type = struct.unpack("<i", shp[32:36])[0]
    if file_type % 10 != 5:
        raise SystemExit(f"СТОП: очікував полігони (тип 5), а в .shp тип {file_type}")
    out, pos = [], 100
    while pos + 8 <= len(shp):
        _, clen = struct.unpack(">2i", shp[pos:pos + 8])
        rec = shp[pos + 8: pos + 8 + clen * 2]
        pos += 8 + clen * 2
        stype = struct.unpack("<i", rec[:4])[0]
        if stype == 0:
            out.append([])
            continue
        nparts, npts = struct.unpack("<2i", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44:44 + 4 * nparts])) + [npts]
        pts = np.frombuffer(rec, dtype="<f8", count=2 * npts, offset=44 + 4 * nparts).reshape(-1, 2)
        out.append([pts[parts[i]:parts[i + 1]] for i in range(nparts)])
    return out


def simplify_ring(r, tol_m=1.5, iters=4):
    """Прибирає «сходинки» 3-метрових пікселів: точки, що відхиляються від лінії сусідів < tol_m."""
    if len(r) <= 8:
        return r
    kx = 111320.0 * math.cos(math.radians(float(r[:, 1].mean())))
    for it in range(iters):
        if len(r) <= 8:
            break
        P = (r - r[0]) * (kx, 110540.0)
        a, b, c = P[:-2], P[1:-1], P[2:]
        ac = c - a
        L = np.hypot(ac[:, 0], ac[:, 1])
        d = np.abs(ac[:, 0] * (b[:, 1] - a[:, 1]) - ac[:, 1] * (b[:, 0] - a[:, 0])) / np.where(L > 0, L, 1)
        drop = d < tol_m
        drop[(np.arange(len(drop)) + it) % 2 == 1] = False   # не видаляти дві сусідні точки за прохід
        keep = np.concatenate([[True], ~drop, [True]])
        r = r[keep]
    return r


def read_shp_stream(f, total_bytes=None, simplify=True):
    """Потокове читання .shp з файлоподібного об'єкта (без завантаження гігабайтів у пам'ять)."""
    hdr = f.read(100)
    file_type = struct.unpack("<i", hdr[32:36])[0]
    if file_type % 10 != 5:
        raise SystemExit(f"СТОП: очікував полігони (тип 5), а в .shp тип {file_type}")
    out, done, step, n_in, n_out = [], 100, 200 * 2**20, 0, 0
    while True:
        h = f.read(8)
        if len(h) < 8:
            break
        _, clen = struct.unpack(">2i", h)
        rec = f.read(clen * 2)
        done += 8 + clen * 2
        if total_bytes and done // step != (done - 8 - clen * 2) // step:
            print(f"  читаю поля… {done / 2**20:,.0f} з {total_bytes / 2**20:,.0f} МБ", flush=True)
        if struct.unpack("<i", rec[:4])[0] == 0:
            out.append([])
            continue
        nparts, npts = struct.unpack("<2i", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44:44 + 4 * nparts])) + [npts]
        pts = np.frombuffer(rec, dtype="<f8", count=2 * npts, offset=44 + 4 * nparts).reshape(-1, 2)
        rings = []
        for i in range(nparts):
            r = pts[parts[i]:parts[i + 1]]
            n_in += len(r)
            if simplify:
                r = simplify_ring(r)
            n_out += len(r)
            rings.append(r.copy())
        out.append(rings)
    if simplify and n_in:
        print(f"Спрощення меж: {n_in:,} → {n_out:,} вершин ({100 * n_out / n_in:.0f}%), допуск 1,5 м")
    return out


def read_dbf(dbf: bytes):
    n, hlen, rlen = struct.unpack("<I2H", dbf[4:12])
    fields, p = [], 32
    while dbf[p] != 0x0D:
        name = dbf[p:p + 11].split(b"\x00")[0].decode("latin-1")
        fields.append((name, dbf[p + 11:p + 12].decode(), dbf[p + 16]))
        p += 32
    rows = []
    for i in range(n):
        r = dbf[hlen + i * rlen: hlen + (i + 1) * rlen]
        off, row = 1, {}
        for name, typ, ln in fields:
            v = r[off:off + ln].decode("utf-8", "replace").strip()
            if typ in "NF" and v:
                try:
                    v = float(v)
                except ValueError:
                    pass
            row[name] = v
            off += ln
        rows.append(row)
    return rows


def download(url, zpath):
    """Завантаження з перевіркою місця на диску, прогресом і без «битих» файлів після обриву."""
    import shutil
    part = zpath.with_suffix(".zip.part")
    with requests.get(url, headers=UA, stream=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        free = shutil.disk_usage(zpath.parent).free
        if total and free < total * 1.5:
            raise SystemExit(f"СТОП: на диску вільно {free / 2**20:,.0f} МБ, а файл важить {total / 2**20:,.0f} МБ "
                             f"(+ запас на розпакування). Звільни місце і запусти знову.")
        print(f"Розмір: {total / 2**20:,.0f} МБ" if total else "Розмір невідомий")
        got, step = 0, 50 * 2**20
        try:
            with open(part, "wb") as f:
                for ch in r.iter_content(1 << 20):
                    f.write(ch)
                    got += len(ch)
                    if got // step != (got - len(ch)) // step:
                        print(f"  … {got / 2**20:,.0f} МБ" + (f" з {total / 2**20:,.0f}" if total else ""), flush=True)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
    if not zipfile.is_zipfile(part):
        part.unlink(missing_ok=True)
        raise SystemExit("СТОП: завантажений файл не є ZIP. Спробуй ще раз пізніше.")
    part.replace(zpath)


def save_compact(path, polys, attrs):
    """Компактний кеш у WGS84 (float32, ~0.2 м): у кілька разів менший за ZIP."""
    rings, ring_off, poly_off, n = [], [0], [0], 0
    for p in polys:
        for r in p:
            rings.append(r.astype("<f4"))
            n += len(r)
            ring_off.append(n)
        poly_off.append(len(ring_off) - 1)
    ids = np.array([a.get("Field_ID", i) for i, a in enumerate(attrs)], dtype="i8") if attrs else np.arange(len(polys))
    np.savez_compressed(path, xy=np.vstack(rings) if rings else np.zeros((0, 2), "<f4"),
                        ring_off=np.array(ring_off, "i8"), poly_off=np.array(poly_off, "i8"), ids=ids)


def load_compact(path):
    z = np.load(path)
    xy, ro, po = z["xy"].astype("f8"), z["ring_off"], z["poly_off"]
    polys = [[xy[ro[k]:ro[k + 1]] for k in range(po[i], po[i + 1])] for i in range(len(po) - 1)]
    attrs = [{"Field_ID": int(v)} for v in z["ids"]]
    return polys, attrs


def load_fields(key, delete_zip=False):
    if key not in ZIPS:
        raise SystemExit(f"СТОП: невідома область '{key}'. Доступні: {', '.join(sorted(ZIPS))}")
    rid, fname = ZIPS[key]
    DATA.mkdir(parents=True, exist_ok=True)
    compact = DATA / f"{key}_2023_wgs84.npz"
    if compact.exists():
        polys, attrs = load_compact(compact)
        print(f"{key}: {len(polys):,} полів (з компактного кешу {compact.name})")
        return polys, attrs
    zpath = DATA / f"{fname}_field_boundaries_2023.zip"
    if zpath.exists() and not zipfile.is_zipfile(zpath):
        print(f"{zpath.name} пошкоджений (обірване завантаження) — видаляю і качаю знову")
        zpath.unlink()
    if not zpath.exists():
        url = f"{BASE}/{rid}/download/{fname}_field_boundaries_2023.zip"
        print("Завантажую", url)
        download(url, zpath)
    z = zipfile.ZipFile(zpath)
    methods = {i.compress_type for i in z.infolist()}
    if 9 in methods and zipfile_deflate64 is None:
        raise SystemExit("СТОП: ZIP стиснено методом Deflate64. Встанови підтримку і запусти знову:\n"
                         "  pip install zipfile-deflate64")
    names = z.namelist()
    shp = [n for n in names if n.lower().endswith(".shp")]
    if len(shp) != 1:
        raise SystemExit(f"СТОП: у ZIP {len(shp)} .shp файлів: {names}")
    stem = shp[0][:-4]
    get = lambda ext: next((z.read(n) for n in names if n.lower() == (stem + ext).lower()), None)
    shp_info = z.getinfo(shp[0])
    with z.open(shp_info) as fshp:
        polys = read_shp_stream(fshp, shp_info.file_size)
    attrs = read_dbf(get(".dbf")) if get(".dbf") else [{}] * len(polys)
    prj = (get(".prj") or b"").decode("latin-1")
    z.close()
    print(f"{key}: {len(polys):,} полів; атрибути: {list(attrs[0].keys()) if attrs else []}")
    print("Система координат (.prj):", prj[:120] + ("…" if len(prj) > 120 else ""))
    polys = to_wgs84(polys, prj)
    save_compact(compact, polys, attrs)
    print(f"Компактний кеш: {compact.name}, {compact.stat().st_size / 2**20:,.0f} МБ (ZIP був {zpath.stat().st_size / 2**20:,.0f} МБ)")
    if delete_zip:
        zpath.unlink()
        print("ZIP видалено (--delete-zip), далі працюємо з компактного кешу")
    return polys, attrs


def to_wgs84(polys, prj):
    if not prj or prj.strip().startswith("GEOGCS"):
        sample = np.vstack([r for p in polys[:50] for r in p])
        if np.abs(sample).max() > 180:
            raise SystemExit("СТОП: .prj каже «географічні координати», а значення > 180. Перевір файл.")
        return polys
    from pyproj import CRS, Transformer
    tr = Transformer.from_crs(CRS.from_wkt(prj), "EPSG:4326", always_xy=True)
    print("Перепроєктую у WGS84…")
    out = []
    for p in polys:
        out.append([np.column_stack(tr.transform(r[:, 0], r[:, 1])) for r in p])
    return out


# ---------------------------------------------------------------- геометрія і прив'язка даних
R_EARTH = 6371008.8


def ring_area_m2(r):
    lat0 = np.radians(r[:, 1].mean())
    x = np.radians(r[:, 0]) * R_EARTH * np.cos(lat0)
    y = np.radians(r[:, 1]) * R_EARTH
    return 0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def poly_area_ha(p):
    if not p:
        return 0.0
    areas = [ring_area_m2(r) for r in p]
    outer = max(range(len(areas)), key=lambda i: abs(areas[i]))
    return (abs(areas[outer]) - sum(abs(a) for i, a in enumerate(areas) if i != outer)) / 1e4


def centroid(p):
    r = max(p, key=lambda r: abs(ring_area_m2(r)))
    return float(r[:, 0].mean()), float(r[:, 1].mean())


def power_node(lon, lat):  # сітка MERRA-2 / POWER: 0.625° × 0.5°
    return round(-180 + 0.625 * round((lon + 180) / 0.625), 3), round(-90 + 0.5 * round((lat + 90) / 0.5), 2)


def smap_cell(lon, lat):   # EASE-Grid 2.0 9 км (EPSG:6933), без pyproj: Snyder 1987
    a, e2 = 6378137.0, 0.00669437999014
    e = math.sqrt(e2)
    k0 = math.cos(math.radians(30)) / math.sqrt(1 - e2 * math.sin(math.radians(30)) ** 2)
    s = math.sin(math.radians(lat))
    q = (1 - e2) * (s / (1 - e2 * s * s) - (1 / (2 * e)) * math.log((1 - e * s) / (1 + e * s)))
    x, y = a * k0 * math.radians(lon), a * q / (2 * k0)
    cell, x0, y0 = 9008.055210146, -17367530.44516137, 7314540.830638504
    return int((y0 - y) // cell), int((x - x0) // cell)   # (рядок, стовпець)


def in_poly(p, lon, lat):
    return any(MplPath(r).contains_point((lon, lat)) for r in p[:1]) and not any(
        MplPath(r).contains_point((lon, lat)) for r in p[1:])


# ---------------------------------------------------------------- HTML
HTML = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Поля — {title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{{height:100%;margin:0;font:13px system-ui,sans-serif}}
.box{{background:#fff;padding:10px 12px;border-radius:8px;box-shadow:0 1px 5px #0004;max-width:330px;line-height:1.45}}
.box h3{{margin:0 0 4px;font-size:14px}} .box td{{padding:1px 6px 1px 0}} .muted{{color:#667}}</style></head>
<body><div id="map"></div><script>
const D = {data};
const map = L.map('map', {{preferCanvas:true}});
const esri = s => `https://server.arcgisonline.com/ArcGIS/rest/services/${{s}}/MapServer/tile/{{z}}/{{y}}/{{x}}`;
const sat = L.tileLayer(esri('World_Imagery'), {{maxZoom:19, attribution:'Esri, Maxar, Earthstar'}}).addTo(map);
const gray = L.tileLayer(esri('Canvas/World_Light_Gray_Base'), {{maxZoom:16, attribution:'Esri'}});
const labels = L.tileLayer(esri('Reference/World_Boundaries_and_Places'), {{maxZoom:19}}).addTo(map);
const colorBy = a => a < 5.4 ? '#ff4d4d' : a < 20 ? '#ffb000' : a < 100 ? '#3ad17c' : '#2fa8ff';
const fields = L.geoJSON(D.fields, {{
  style: f => ({{color: f.properties.pilot ? '#ffffff' : colorBy(f.properties.area_ha), weight: f.properties.pilot ? 3 : 1, fillOpacity: f.properties.pilot ? .35 : .12}}),
  onEachFeature: (f, l) => {{ const p = f.properties; l.bindPopup(
    `<b>${{p.pilot ? 'Пілотне поле: ' + p.pilot : 'Поле #' + p.fid}}</b><br>Площа <b>${{p.area_ha.toFixed(1)}} га</b><br>` +
    `Центр ${{p.lat.toFixed(5)}}, ${{p.lon.toFixed(5)}}<hr style="border:0;border-top:1px solid #ddd">` +
    `<table><tr><td>NASA POWER</td><td>вузол ${{p.power_lat}}°, ${{p.power_lon}}° (одна клітинка ~2 900 км²)</td></tr>` +
    `<tr><td>SMAP 9 км</td><td>клітинка ряд ${{p.smap_row}}, ст. ${{p.smap_col}}</td></tr>` +
    `<tr><td>MODIS 250 м</td><td>≈ ${{p.modis_px}} пікс.</td></tr>` +
    `<tr><td>HLS 30 м</td><td>≈ ${{p.hls_px}} пікс.</td></tr></table>` +
    `<span class="muted">${{p.modis_px < 4 ? 'Поле замале для MODIS — для NDVI беремо HLS 30 м.' : 'MODIS NDVI придатний; HLS дасть деталь усередині поля.'}}</span>`); }}
}}).addTo(map);
map.fitBounds(fields.getBounds());
D.pilots.forEach(p => L.circleMarker([p.lat, p.lon], {{radius:6, color:'#fff', weight:2, fillColor:'#111', fillOpacity:1}})
  .bindTooltip(p.name, {{permanent:true, direction:'right'}}).addTo(map));
L.control.layers({{'Супутник (Esri)': sat, 'Сіра карта (Esri)': gray}}, {{'Поля NASA Harvest 2023': fields, 'Підписи': labels}}, {{collapsed:false}}).addTo(map);
const info = L.control({{position:'bottomleft'}});
info.onAdd = () => {{ const d = L.DomUtil.create('div','box'); const s = D.stats;
  d.innerHTML = `<h3>${{D.title}}: реальні поля</h3>` +
  `<div class="muted">Межі: NASA Harvest 2023 (Sadeh et al., 2025), CC BY</div>` +
  `<table><tr><td>Полів в області</td><td><b>${{s.n.toLocaleString('uk-UA')}}</b></td></tr>` +
  `<tr><td>Медіанна площа</td><td><b>${{s.median_ha}} га</b></td></tr>` +
  `<tr><td>Менші за 1 піксель MODIS</td><td><b>${{s.lt_modis_pct}}%</b></td></tr>` +
  `<tr><td>Менші за 4 пікселі MODIS</td><td><b>${{s.lt4_modis_pct}}%</b></td></tr>` +
  `<tr><td>У вікні на карті</td><td>${{D.fields.features.length.toLocaleString('uk-UA')}} полів, радіус ${{D.radius}} км</td></tr></table>` +
  `<div class="muted" style="margin-top:4px">Колір: <span style="color:#ff4d4d">■</span> &lt;5 га (менше пікселя MODIS) ` +
  `<span style="color:#ffb000">■</span> 5–20 <span style="color:#3ad17c">■</span> 20–100 <span style="color:#2fa8ff">■</span> &gt;100 га</div>`;
  return d; }};
info.addTo(map);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oblast", default="volyn")
    ap.add_argument("--center", default=None, help="lat,lon центру вікна (за замовч. середина області)")
    ap.add_argument("--radius-km", type=float, default=12.0)
    ap.add_argument("--max-window", type=int, default=15000, help="обмеження кількості полів на карті")
    ap.add_argument("--delete-zip", action="store_true", help="після створення компактного кешу видалити ZIP (звільняє сотні МБ)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    polys, attrs = load_fields(a.oblast, a.delete_zip)
    keep = [i for i, p in enumerate(polys) if p]
    areas = np.array([poly_area_ha(polys[i]) for i in keep])
    cents = np.array([centroid(polys[i]) for i in keep])
    print(f"Площа: медіана {np.median(areas):.1f} га, P10 {np.percentile(areas, 10):.1f}, P90 {np.percentile(areas, 90):.1f}")
    stats = dict(n=len(keep), median_ha=round(float(np.median(areas)), 1),
                 lt_modis_pct=round(100 * float((areas < 5.37).mean()), 1),
                 lt4_modis_pct=round(100 * float((areas < 4 * 5.37).mean()), 1),
                 total_kha=round(float(areas.sum()) / 1000, 1))
    print("Статистика області:", stats)

    # пілотні поля в цій області
    pilots = []
    for pid, (name, lat, lon, ok) in PILOTS.items():
        if ok != a.oblast:
            continue
        d2 = (cents[:, 0] - lon) ** 2 + (cents[:, 1] - lat) ** 2
        cand = np.argsort(d2)[:200]
        hit = next((j for j in cand if in_poly(polys[keep[j]], lon, lat)), None)
        if hit is None:
            j = int(cand[0])
            print(f"[{name}] точка не всередині поля; найближче поле #{keep[j]} за "
                  f"{math.sqrt(d2[j]) * 111:.2f} км (умовно) — перевір на супутнику")
        else:
            j = int(hit)
            print(f"[{name}] знайдено поле #{keep[j]}, {areas[j]:.1f} га")
        pilots.append(dict(pid=pid, name=name, lat=lat, lon=lon, idx=j))

    # вікно
    if a.center:
        clat, clon = map(float, a.center.split(","))
    elif pilots:
        clat, clon = pilots[0]["lat"], pilots[0]["lon"]
    else:
        clon, clat = float(np.median(cents[:, 0])), float(np.median(cents[:, 1]))
    dx = (cents[:, 0] - clon) * 111.32 * math.cos(math.radians(clat))
    dy = (cents[:, 1] - clat) * 110.57
    win = np.where(dx ** 2 + dy ** 2 <= a.radius_km ** 2)[0]
    if len(win) > a.max_window:
        print(f"У вікні {len(win)} полів — обрізаю до {a.max_window} найближчих (зменш --radius-km)")
        win = win[np.argsort((dx ** 2 + dy ** 2)[win])[:a.max_window]]
    pilot_idx = {p["idx"]: p["name"] for p in pilots}
    win = np.unique(np.concatenate([win, np.array(list(pilot_idx), dtype=int)]))

    feats, rows = [], []
    for j in range(len(keep)):
        lon, lat = cents[j]
        pl, pn = power_node(lon, lat)
        sr, sc = smap_cell(lon, lat)
        rec = dict(fid=int(keep[j]), area_ha=round(float(areas[j]), 2), lon=round(lon, 5), lat=round(lat, 5),
                   power_lon=pl, power_lat=pn, smap_row=sr, smap_col=sc,
                   modis_px=int(areas[j] / 5.366), hls_px=int(areas[j] / 0.09), pilot=pilot_idx.get(j, ""))
        rows.append(rec)
    winset = set(int(x) for x in win)
    for j in sorted(winset):
        p = polys[keep[j]]
        coords = [[[round(float(x), 6), round(float(y), 6)] for x, y in r] for r in p]
        feats.append(dict(type="Feature", properties=rows[j], geometry=dict(type="Polygon", coordinates=coords)))
    fc = dict(type="FeatureCollection", features=feats)

    tag = a.oblast
    (OUT / f"{tag}_fields_window.geojson").write_text(json.dumps(fc), encoding="utf-8")
    with open(OUT / f"{tag}_fields_stats.csv", "w", encoding="utf-8") as f:
        cols = list(rows[0].keys())
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r[c]) for c in cols) + "\n")
    # GeoJSON для AppEEARS (area request): пілотні + найбільші поля вікна, до 50
    sel = sorted(winset, key=lambda j: (rows[j]["pilot"] == "", -rows[j]["area_ha"]))[:50]
    app = dict(type="FeatureCollection", features=[
        dict(type="Feature", properties=dict(id=f"f{rows[j]['fid']}", area_ha=rows[j]["area_ha"]),
             geometry=dict(type="Polygon", coordinates=[[[round(float(x), 6), round(float(y), 6)] for x, y in polys[keep[j]][0]]]))
        for j in sel])
    (OUT / f"{tag}_appeears_fields.geojson").write_text(json.dumps(app), encoding="utf-8")

    data = dict(title=tag.capitalize(), fields=fc, radius=a.radius_km, stats=stats,
                pilots=[dict(name=p["name"], lat=p["lat"], lon=p["lon"]) for p in pilots])
    html = OUT / f"{tag}_fields_map.html"
    html.write_text(HTML.format(title=tag, data=json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    print(f"Вікно: {len(feats):,} полів. Карта: {html.resolve()}")
    print("Для AppEEARS (HLS NDVI по полях):", (OUT / f"{tag}_appeears_fields.geojson").resolve())


if __name__ == "__main__":
    main()
