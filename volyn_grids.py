#!/usr/bin/env python3
"""
Field Shift — базова візуалізація точок (вузлів сітки) датасетів над Волинською областю.

Що робить:
  1. Завантажує межу Волинської області (geoBoundaries, запасний варіант — Nominatim/OSM).
  2. Для кожного датасету рахує центри клітинок його сітки, що потрапляють в область.
  3. Малює інтерактивну карту (Leaflet) з шаром на кожен датасет + вікно пікселів 250/500 м.
  4. Зберігає CSV з точками — їх же можна використати як координати запитів до API.

Запуск:
  pip install requests numpy matplotlib pyproj
  python volyn_grids.py                # -> out/volyn_grids.html, out/volyn_points_<dataset>.csv
  python volyn_grids.py --oblast "Rivne"   # інша область (назва як у geoBoundaries)

Принцип «діагностуй, не вгадуючи»: якщо межу не знайдено — скрипт друкує доступні назви і зупиняється.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import requests
from matplotlib.path import Path as MplPath

OUT = Path("out")
UA = {"User-Agent": "FieldShift-SpaceApps2026/0.1 (education)"}

# ---------------------------------------------------------------- межа області
def load_boundary(oblast: str):
    """Повертає список кілець [(lon, lat), ...] зовнішніх контурів області."""
    cache = OUT / f"boundary_{oblast.replace(' ', '_')}.geojson"
    if cache.exists():
        geom = json.loads(cache.read_text(encoding="utf-8"))
        return rings_of(geom), "cache"

    # 1) geoBoundaries (ADM1 України)
    try:
        meta = requests.get("https://www.geoboundaries.org/api/current/gbOpen/UKR/ADM1/",
                            headers=UA, timeout=60).json()
        url = meta.get("simplifiedGeometryGeoJSON") or meta["gjDownloadURL"]
        fc = requests.get(url, headers=UA, timeout=120).json()
        names = [f["properties"].get("shapeName", "") for f in fc["features"]]
        hit = [f for f in fc["features"] if oblast.lower() in f["properties"].get("shapeName", "").lower()]
        if len(hit) == 1:
            cache.write_text(json.dumps(hit[0]["geometry"]), encoding="utf-8")
            return rings_of(hit[0]["geometry"]), "geoBoundaries gbOpen UKR ADM1"
        print(f"geoBoundaries: збігів для '{oblast}' = {len(hit)}. Доступні назви:\n  " + "\n  ".join(sorted(names)))
    except Exception as e:
        print("geoBoundaries недоступний:", repr(e))

    # 2) Nominatim (OpenStreetMap)
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": f"{oblast} Oblast, Ukraine", "format": "json",
                                 "polygon_geojson": 1, "limit": 3},
                         headers=UA, timeout=60).json()
        polys = [x for x in r if x.get("geojson", {}).get("type") in ("Polygon", "MultiPolygon")]
        if polys:
            print("Nominatim знайшов:", [x["display_name"] for x in polys])
            geom = polys[0]["geojson"]
            cache.write_text(json.dumps(geom), encoding="utf-8")
            return rings_of(geom), "OpenStreetMap / Nominatim"
    except Exception as e:
        print("Nominatim недоступний:", repr(e))

    sys.exit("СТОП: межу області не отримано. Перевір назву (--oblast) або доступ до мережі.")


def load_all_oblasts():
    """Усі області України (geoBoundaries ADM1). Повертає [(назва, кільця), ...] і FeatureCollection."""
    cache = OUT / "boundary_UKR_ADM1.geojson"
    if cache.exists():
        fc = json.loads(cache.read_text(encoding="utf-8"))
        src = "cache (geoBoundaries gbOpen UKR ADM1)"
    else:
        try:
            meta = requests.get("https://www.geoboundaries.org/api/current/gbOpen/UKR/ADM1/",
                                headers=UA, timeout=60).json()
            url = meta.get("simplifiedGeometryGeoJSON") or meta["gjDownloadURL"]
            fc = requests.get(url, headers=UA, timeout=180).json()
        except Exception as e:
            sys.exit(f"СТОП: не вдалося завантажити межі областей з geoBoundaries ({e.__class__.__name__}). "
                     "Перевір інтернет або поклади файл у out/boundary_UKR_ADM1.geojson.")
        cache.write_text(json.dumps(fc), encoding="utf-8")
        src = "geoBoundaries gbOpen UKR ADM1"
    parts = [(f["properties"].get("shapeName", "?"), rings_of(f["geometry"])) for f in fc["features"]]
    print(f"Областей у межах: {len(parts)}")
    return parts, fc, src


def rings_of(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [p[0] for p in geom["coordinates"]]
    raise ValueError(f"Невідомий тип геометрії: {geom['type']}")


def inside(rings, lon, lat):
    pts = np.column_stack([lon, lat])
    mask = np.zeros(len(pts), bool)
    for ring in rings:
        mask |= MplPath(np.asarray(ring)).contains_points(pts)
    return mask


def bbox(rings, pad=0.0):
    a = np.vstack([np.asarray(r) for r in rings])
    return a[:, 0].min() - pad, a[:, 1].min() - pad, a[:, 0].max() + pad, a[:, 1].max() + pad


# ---------------------------------------------------------------- сітки датасетів
def regular_grid(bb, dlon, dlat, lon0, lat0):
    """Центри регулярної сітки: lon = lon0 + k*dlon, lat = lat0 + k*dlat."""
    w, s, e, n = bb
    lons = lon0 + dlon * np.arange(np.floor((w - lon0) / dlon), np.ceil((e - lon0) / dlon) + 1)
    lats = lat0 + dlat * np.arange(np.floor((s - lat0) / dlat), np.ceil((n - lat0) / dlat) + 1)
    LO, LA = np.meshgrid(lons, lats)
    return LO.ravel(), LA.ravel()


class _Cea6933:
    """Lambert cylindrical equal-area на еліпсоїді WGS84, φs=30° (EPSG:6933), Snyder 1987, рівн. 10-15, 3-12, 3-18."""
    a, e2 = 6378137.0, 0.00669437999014

    def __init__(self, inverse=False):
        e = np.sqrt(self.e2)
        s = np.sin(np.radians(30.0))
        self.k0 = np.cos(np.radians(30.0)) / np.sqrt(1 - self.e2 * s * s)
        self.e, self.inverse = e, inverse
        self.qp = self._q(np.pi / 2)

    def _q(self, phi):
        s, e, e2 = np.sin(phi), self.e, self.e2
        return (1 - e2) * (s / (1 - e2 * s * s) - (1 / (2 * e)) * np.log((1 - e * s) / (1 + e * s)))

    def transform(self, u, v):
        u, v = np.asarray(u, float), np.asarray(v, float)
        if not self.inverse:
            lon, lat = np.radians(u), np.radians(v)
            return self.a * self.k0 * lon, self.a * self._q(lat) / (2 * self.k0)
        x, y = u, v
        beta = np.arcsin(np.clip(2 * y * self.k0 / (self.a * self.qp), -1, 1))
        e2 = self.e2
        phi = (beta + (e2 / 3 + 31 * e2**2 / 180 + 517 * e2**3 / 5040) * np.sin(2 * beta)
               + (23 * e2**2 / 360 + 251 * e2**3 / 3780) * np.sin(4 * beta)
               + (761 * e2**3 / 45360) * np.sin(6 * beta))
        return np.degrees(x / (self.a * self.k0)), np.degrees(phi)


def ease2_9km(bb):
    """Центри EASE-Grid 2.0 Global 9 km (SMAP L3 Enhanced), EPSG:6933."""
    cell = 9008.055210146   # м (NSIDC EASE-Grid 2.0, M09)
    x0, y0 = -17367530.44516137, 7314540.830638504
    try:
        from pyproj import Transformer
        fwd = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
        inv = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)
    except ImportError:          # без pyproj: формули Snyder (1987) для EPSG:6933
        fwd, inv = _Cea6933(), _Cea6933(inverse=True)
    w, s, e, n = bb
    xs, ys = fwd.transform([w, e, w, e], [s, s, n, n])
    c0, c1 = int((min(xs) - x0) // cell) - 1, int((max(xs) - x0) // cell) + 1
    r0, r1 = int((y0 - max(ys)) // cell) - 1, int((y0 - min(ys)) // cell) + 1
    C, R = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
    X, Y = x0 + (C + 0.5) * cell, y0 - (R + 0.5) * cell
    lon, lat = inv.transform(X.ravel(), Y.ravel())
    return np.asarray(lon), np.asarray(lat)


R_SIN = 6371007.181          # MODIS sinusoidal sphere
SIN_X0, SIN_Y0 = -20015109.354, 10007554.677
MODIS_PX = {250: 231.65635826395834, 500: 463.31271652791656}


def modis_pixels_window(lon_c, lat_c, half_km, res):
    """Контури пікселів MODIS (синусоїдальна проєкція) у вікні навколо точки."""
    px = MODIS_PX[res]
    to_xy = lambda lo, la: (R_SIN * np.radians(lo) * np.cos(np.radians(la)), R_SIN * np.radians(la))
    to_ll = lambda x, y: (np.degrees(x / (R_SIN * np.cos(y / R_SIN))), np.degrees(y / R_SIN))
    xc, yc = to_xy(lon_c, lat_c)
    h = half_km * 1000
    i0, i1 = int((xc - h - SIN_X0) // px), int((xc + h - SIN_X0) // px)
    j0, j1 = int((SIN_Y0 - (yc + h)) // px), int((SIN_Y0 - (yc - h)) // px)
    polys = []
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            xa, xb = SIN_X0 + i * px, SIN_X0 + (i + 1) * px
            ya, yb = SIN_Y0 - j * px, SIN_Y0 - (j + 1) * px
            ring = [to_ll(x, y) for x, y in [(xa, ya), (xb, ya), (xb, yb), (xa, yb), (xa, ya)]]
            polys.append([[round(la, 6), round(lo, 6)] for lo, la in ring])
    return polys


# Опис датасетів: (id, назва, роздільність, функція центрів, колір, примітка)
DATASETS = [
    ("power", "NASA POWER (метео, MERRA-2)", "0.5° × 0.625°",
     lambda bb: regular_grid(bb, 0.625, 0.5, -180.0, -90.0), "#d62728",
     "Сітка метеопараметрів POWER; сонячні параметри — інша, грубша сітка. Звірити з docs/methodology."),
    ("smap", "SMAP SPL3SMP_E (EASE-Grid 2.0, 9 км)", "9 км",
     ease2_9km, "#1f77b4", "Вологість поверхні 0–5 см; з 2024 над Україною дані неякісні (ймовірно РЕБ)."),
    ("era5land", "ERA5-Land / AgERA5 / Open-Meteo", "0.1°",
     lambda bb: regular_grid(bb, 0.1, 0.1, 0.0, 0.0), "#2ca02c", "Реаналіз; вузли на кратних 0.1°."),
    ("imerg", "GPM IMERG (опади)", "0.1°",
     lambda bb: regular_grid(bb, 0.1, 0.1, 0.05, 0.05), "#9467bd", "Центри клітинок на x.x5°."),
    ("chirps", "CHIRPS v3 (опади)", "0.05°",
     lambda bb: regular_grid(bb, 0.05, 0.05, 0.025, 0.025), "#ff7f0e", "Центри клітинок на x.x25°."),
]


# ---------------------------------------------------------------- HTML
HTML = """<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Сітки датасетів — {oblast}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{{height:100%;margin:0;font-family:system-ui,sans-serif}}
.info{{background:#fff;padding:8px 10px;border-radius:6px;box-shadow:0 1px 4px #0003;font-size:13px;max-width:320px}}
.info td{{padding:1px 6px}} .sw{{display:inline-block;width:10px;height:10px;border-radius:50%}}</style></head>
<body><div id="map"></div><script>
const D = {data};
const map = L.map('map',{{preferCanvas:true}});
// OSM і CARTO блокують тайли для файлів, відкритих локально (немає Referer), тому — Esri.
const esri = s => `https://server.arcgisonline.com/ArcGIS/rest/services/${{s}}/MapServer/tile/{{z}}/{{y}}/{{x}}`;
const bases = {{
  'Сіра карта (Esri)': L.tileLayer(esri('Canvas/World_Light_Gray_Base'),
     {{maxZoom:16,attribution:'Tiles © Esri, HERE, Garmin, © OpenStreetMap contributors'}}),
  'Топокарта (Esri)': L.tileLayer(esri('World_Topo_Map'),
     {{maxZoom:19,attribution:'Tiles © Esri, HERE, Garmin, © OpenStreetMap contributors'}}),
  'Супутник (Esri)': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
     {{maxZoom:19,attribution:'Tiles © Esri, Maxar, Earthstar Geographics'}})
}};
bases['Сіра карта (Esri)'].addTo(map);
const bnd = L.geoJSON(D.boundary,{{style:{{color:'#222',weight:1.2,fill:false}}}}).addTo(map);
map.fitBounds(bnd.getBounds());
const overlays = {{}};
D.layers.forEach((ly,i) => {{
  const g = L.layerGroup();
  ly.points.forEach(p => L.circleMarker([p[1],p[0]],{{radius:ly.r,color:ly.color,weight:1,fillOpacity:.7}})
     .bindPopup(`<b>${{ly.name}}</b><br>${{ly.res}}<br>lat ${{p[1].toFixed(4)}}, lon ${{p[0].toFixed(4)}}<br><small>${{ly.note}}</small>`).addTo(g));
  overlays[`<span class="sw" style="background:${{ly.color}}"></span> ${{ly.name}} — ${{ly.points.length}}`] = g;
  if (i < 2) g.addTo(map);
}});
D.windows.forEach(w => {{
  const g = L.layerGroup();
  w.polys.forEach(p => L.polygon(p,{{color:w.color,weight:.6,fill:false}}).addTo(g));
  L.marker([w.lat,w.lon]).bindPopup('Демо-поле: вікно пікселів').addTo(g);
  overlays[`▦ ${{w.name}} (вікно ${{w.size}})`] = g;
}});
L.control.layers(bases, overlays, {{collapsed:false}}).addTo(map);
const info = L.control({{position:'bottomleft'}});
info.onAdd = () => {{ const d = L.DomUtil.create('div','info');
  d.innerHTML = `<b>${{D.oblast}}: точки сіток датасетів</b><br><small>Межа: ${{D.boundary_src}}</small><table>` +
    D.layers.map(l=>`<tr><td><span class="sw" style="background:${{l.color}}"></span></td><td>${{l.name}}</td><td>${{l.res}}</td><td><b>${{l.points.length}}</b></td></tr>`).join('') +
    D.dense.map(x=>`<tr><td></td><td>${{x.name}}</td><td>${{x.res}}</td><td>≈${{x.n}}</td></tr>`).join('') +
    `</table><small>Точка = центр клітинки. Щільні сітки (250–500 м) показано вікном навколо демо-поля.</small>`;
  return d; }};
info.addTo(map);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oblast", default="Volyn")
    ap.add_argument("--demo", default=None, help="lat,lon демо-поля для вікна пікселів (за замовч. центр області)")
    ap.add_argument("--window-km", type=float, default=2.0, help="півширина вікна пікселів, км")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    country = a.oblast.lower() in ("all", "ukraine", "україна")
    if country:
        parts, fc, src = load_all_oblasts()
        rings = [r for _, rs in parts for r in rs]
        boundary_geo = fc
        label, tag = "Україна", "ukraine"
    else:
        rings, src = load_boundary(a.oblast)
        parts = [(a.oblast, rings)]
        boundary_geo = {"type": "Feature", "properties": {},
                        "geometry": {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}}
        label, tag = a.oblast, a.oblast.lower()
    bb = bbox(rings, pad=0.7)
    area_km2 = estimate_area_km2(rings)
    print(f"Межа: {src}; bbox {tuple(round(float(v), 3) for v in bbox(rings))}; площа ≈ {area_km2:,.0f} км²")

    layers, per_region = [], {}
    for did, name, res, fn, color, note in DATASETS:
        try:
            lon, lat = fn(bb)
        except ImportError:
            print(f"[{did}] пропущено: потрібен pyproj (pip install pyproj)")
            continue
        region = np.array([""] * len(lon), dtype=object)
        for pname, prings in parts:                 # приналежність точки до області
            region[(region == "") & inside(prings, lon, lat)] = pname
        m = region != ""
        pts = [[round(float(x), 5), round(float(y), 5)] for x, y in zip(lon[m], lat[m])]
        n = len(pts)
        layers.append(dict(id=did, name=name, res=res, color=color, note=note, points=pts,
                           r=7 if n < 50 else 4 if n < 600 else 2 if n < 5000 else 1.5))
        with open(OUT / f"{tag}_points_{did}.csv", "w", encoding="utf-8") as f:
            f.write("lon,lat,region\n" + "".join(
                f"{p[0]},{p[1]},{r}\n" for p, r in zip(pts, region[m])))
        for r in region[m]:
            per_region.setdefault(r, {}).setdefault(did, 0)
            per_region[r][did] += 1
        print(f"[{did}] {name}: {n} точок")
    if country:
        ids = [l["id"] for l in layers]
        with open(OUT / f"{tag}_points_by_region.csv", "w", encoding="utf-8") as f:
            f.write("region," + ",".join(ids) + "\n")
            for r in sorted(per_region):
                f.write(r + "," + ",".join(str(per_region[r].get(i, 0)) for i in ids) + "\n")
        print("Кількість точок по областях:", OUT / f"{tag}_points_by_region.csv")

    if a.demo:
        dlat, dlon = map(float, a.demo.split(","))
    else:
        w, s, e, n = bbox(rings)
        dlon, dlat = (w + e) / 2, (s + n) / 2
    windows = [
        dict(name="MODIS 250 м (NDVI MOD13Q1)", size=f"{2*a.window_km:g}×{2*a.window_km:g} км", color="#17becf",
             lat=dlat, lon=dlon, polys=modis_pixels_window(dlon, dlat, a.window_km, 250)),
        dict(name="MODIS 500 м (ET MOD16A2GF)", size=f"{2*a.window_km:g}×{2*a.window_km:g} км", color="#8c564b",
             lat=dlat, lon=dlon, polys=modis_pixels_window(dlon, dlat, a.window_km, 500)),
    ]
    dense = [dict(name="MODIS NDVI / SoilGrids", res="250 м", n=f"{area_km2 / 0.0537:,.0f}"),
             dict(name="MODIS ET", res="500 м", n=f"{area_km2 / 0.2147:,.0f}")]

    data = dict(oblast=label, boundary_src=src, boundary=boundary_geo,
                layers=layers, windows=windows, dense=dense)
    html = OUT / f"{tag}_grids.html"
    html.write_text(HTML.format(oblast=label, data=json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    print("Готово:", html.resolve())


def estimate_area_km2(rings):
    tot = 0.0
    for ring in rings:
        a = np.asarray(ring)
        lat0 = np.radians(a[:, 1].mean())
        x = np.radians(a[:, 0]) * 6371.0 * np.cos(lat0)
        y = np.radians(a[:, 1]) * 6371.0
        tot += abs(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
    return tot


if __name__ == "__main__":
    main()
