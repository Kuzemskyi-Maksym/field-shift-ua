#!/usr/bin/env python3
"""Ринок (D24): найближчий порт і відстань поле → порт → site/market.json, ключ market_ports.

Порти — data/raw/market/ports.csv (port_id,name_uk,lat,lon,source_url; без URL порт не береться).
- По прямій (haversine з model/market.py) — для всіх: 5 пілотів, центри 5 вікон, усі поля портфеля.
- Дорогою (OSRM, router.project-osrm.org) — лише 5 пілотів + центри 5 вікон; кеш data/raw/market/osrm_cache.json
  з датою запиту. Мережа — лише з --fetch (збір даних); без нього — тільки кеш. Якщо OSRM двічі поспіль не відповів —
  далі без запитів, лише пряма з підписом «по прямій».
Найближчий порт: за дорогою, якщо для поля є всі дорожні відстані, інакше по прямій (тип відстані — у полі distance_type).
Центр вікна — медіана координат (lat, lon) полів вікна з out/fields/<вікно>_fields_stats.csv.
Етап 3 (D25): basis — CPT_port − EXW з data/raw/prices_candidates.csv лише в межах ОДНОГО snapshot і дати;
культура без обох базисів в одному зрізі → «немає ціни обох базисів з одного джерела» (нічого не підставляємо).
Етап 4 (D26): tariffs — тариф автоперевезення з джерелом за областю відправлення (transport_rates.csv); немає → no_tariff_text.
Інші ключі site/market.json зберігаються.

  python scripts/market_ports.py --fetch     # збір (мережа), потім збірка
  python scripts/market_ports.py             # лише збірка з кешу
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.market import haversine_km  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))

MK = ROOT / "data" / "raw" / "market"
PORTS = MK / "ports.csv"
CACHE = MK / "osrm_cache.json"
DST = ROOT / "site" / "market.json"
WINDOWS = ROOT / "site" / "fields_windows.json"
PORTFOLIO = ROOT / "site" / "portfolio.json"
PRICES = ROOT / "data" / "raw" / "prices_candidates.csv"
TARIFFS = MK / "transport_rates.csv"
NO_TARIFF = "вартість доставки не враховано — немає перевіреного тарифу"
NO_BASIS = "немає ціни обох базисів з одного джерела"
PILOTS = ["berezivka_od", "arbuzynka_mk", "karlivka_pl", "kalynivka_vn", "volyn:f3735"]
OSRM = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
OSRM_SRC = "OSRM (router.project-osrm.org), дані OpenStreetMap"
STRAIGHT_LABEL = "по прямій"
ROAD_LABEL = "дорогою"
BASIS_CROPS = ["winter_wheat", "spring_wheat", "winter_barley", "spring_barley", "maize", "soybean", "winter_rapeseed",
               "sunflower", "pea", "sugar_beet"]   # як CROP_PRODUCTS у market_export.py
# Правка 2 (D28): 3 альтернативні маршрути збуту — без ваг і балів; км, тариф лише з джерелом, ризики текстом без цифр.
CROSSINGS = MK / "border_crossings.csv"
ROUTE_GROUPS = [
    dict(route="sea", name_uk="Морський порт Великої Одеси", ports=["odesa", "chornomorsk", "pivdennyi"],
         risk="морський коридор: воєнні ризики для суден і портів, страхування, черги на під'їздах до портів у сезон"),
    dict(route="danube", name_uk="Дунай (Ізмаїл або Рені)", ports=["izmail", "reni"],
         risk="менші судна й перевалка, рівень води в річці, черги суден на Дунаї"),
    dict(route="west", name_uk="Західний кордон (пункт пропуску до ЄС)", ports=None,
         risk="черги на кордоні, фітосанітарний контроль, обмеження імпорту зерна окремими країнами ЄС; "
              "на залізниці — інша ширина колії, потрібне перевантаження"),
]
ROUTES_NOTE = ("Ми порівнюємо маршрути за відстанню, тарифом із джерелом і ризиками. Зведеної оцінки не даємо — "
               "вибір залежить від умов покупця на дату продажу")


def load_ports() -> pd.DataFrame:
    p = pd.read_csv(PORTS)
    need = {"port_id", "name_uk", "lat", "lon", "source_url"}
    if need - set(p.columns):
        raise ValueError(f"{PORTS.name}: немає колонок {sorted(need - set(p.columns))}")
    return p[p.source_url.astype(str).str.startswith("http")].reset_index(drop=True)


def load_crossings(path: Path = CROSSINGS) -> pd.DataFrame:
    """Пункти пропуску до ЄС: лише з координатами й URL (Вікіпедія). Колонка port_id = crossing_id (той самий кеш OSRM)."""
    if not path.exists():
        return pd.DataFrame(columns=["port_id", "name_uk", "lat", "lon", "source_url", "neighbour_uk", "modes_uk"])
    c = pd.read_csv(path)
    c = c[c.source_url.astype(str).str.startswith("http") & c.lat.notna() & c.lon.notna()]
    return c.rename(columns={"crossing_id": "port_id"}).reset_index(drop=True)


def key(lat, lon, port_id) -> str:
    return f"{lat:.5f},{lon:.5f}->{port_id}"


def origins() -> dict:
    """{id: {lat, lon, kind, road}}: road=True — дозволено OSRM (пілоти й центри вікон)."""
    import model.simulate as M
    out = {}
    for pid in PILOTS:
        f = M.field_profile(pid, allow_stubs=True)
        out[pid] = dict(lat=round(f.lat, 6), lon=round(f.lon, 6), kind="pilot", road=True, oblast=f.oblast)
    win = json.load(open(WINDOWS, encoding="utf-8"))
    for ob, w in win.items():
        st = pd.read_csv(ROOT / "out" / "fields" / f"{ob}_fields_stats.csv", usecols=["fid", "lat", "lon"])
        ids = {int(str(ft["properties"]["id"]).lstrip("f")) for ft in w["features"]}
        s = st[st.fid.isin(ids)]
        out[f"window:{ob}"] = dict(lat=round(float(s.lat.median()), 5), lon=round(float(s.lon.median()), 5),
                                   kind="window_centre", road=True, n_fields=int(len(s)), oblast=ob)
    if PORTFOLIO.exists():
        pf = json.load(open(PORTFOLIO, encoding="utf-8"))["portfolio"]["windows"]
        for ob, w in pf.items():
            st = pd.read_csv(ROOT / "out" / "fields" / f"{ob}_fields_stats.csv", usecols=["fid", "lat", "lon"]).set_index("fid")
            for fid in w["fields"]:
                r = st.loc[int(fid)]
                out.setdefault(f"{ob}:f{fid}", dict(lat=round(float(r.lat), 5), lon=round(float(r.lon), 5), kind="portfolio", road=False, oblast=ob))   # пілот volyn:f3735 лишається пілотом
    return out


def fetch_osrm(orig: dict, ports: pd.DataFrame, cache: dict, pause_s: float = 1.0, opener=urllib.request.urlopen) -> dict:
    """Дописує в cache відсутні дорожні відстані. Дві невдачі поспіль → стоп без ретраїв (решта — по прямій)."""
    fails = 0
    for oid, o in orig.items():
        if not o["road"]:
            continue
        for p in ports.itertuples():
            k = key(o["lat"], o["lon"], p.port_id)
            if k in cache:
                continue
            url = OSRM.format(lon1=o["lon"], lat1=o["lat"], lon2=p.lon, lat2=p.lat)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "field-shift-research/0.1"})
                with opener(req, timeout=20) as r:
                    j = json.loads(r.read().decode("utf-8"))
                if j.get("code") != "Ok" or not j.get("routes"):
                    raise RuntimeError(j.get("code"))
                cache[k] = dict(road_km=round(j["routes"][0]["distance"] / 1000, 1), date=dt.date.today().isoformat(), url=url)
                fails = 0
                print(f"  {oid} → {p.port_id}: {cache[k]['road_km']} км")
            except Exception as e:  # noqa: BLE001 — мережа: будь-яка помилка = невдача
                fails += 1
                print(f"  OSRM не відповів ({oid} → {p.port_id}): {e}")
                if fails >= 2:
                    print("  OSRM двічі поспіль не відповів — далі лише по прямій")
                    return cache
            time.sleep(pause_s)
    return cache


def field_ports(o: dict, ports: pd.DataFrame, cache: dict) -> dict:
    rows = []
    for p in ports.itertuples():
        c = cache.get(key(o["lat"], o["lon"], p.port_id)) if o["road"] else None
        rows.append(dict(port_id=p.port_id, name_uk=p.name_uk,
                         distance_straight_km=round(haversine_km(o["lat"], o["lon"], p.lat, p.lon), 1),
                         distance_road_km=c["road_km"] if c else None, road_date=c["date"] if c else None))
    has_road = all(r["distance_road_km"] is not None for r in rows)
    col = "distance_road_km" if has_road else "distance_straight_km"
    n = min(rows, key=lambda r: r[col])
    out = dict(lat=o["lat"], lon=o["lon"], kind=o["kind"], oblast=o.get("oblast"),
               nearest=dict(port_id=n["port_id"], name_uk=n["name_uk"], km=n[col],
                            distance_type="road" if has_road else "straight",
                            distance_label=ROAD_LABEL if has_road else STRAIGHT_LABEL))
    if o["kind"] == "portfolio":                 # компактно: лише пряма до кожного порту
        out["straight_km"] = {r["port_id"]: r["distance_straight_km"] for r in rows}
    else:
        out["ports"] = rows
    if "n_fields" in o:
        out["n_fields"] = o["n_fields"]
    return out


def routes(o: dict, ports: pd.DataFrame, crossings: pd.DataFrame, cache: dict, tariff_by_oblast: dict) -> list[dict]:
    """3 альтернативи: найближчий пункт у групі (дорогою, якщо є всі дорожні відстані групи, інакше по прямій).
    Тариф — лише морський напрямок (джерело D26: «до портових хабів Одеського регіону») і лише для області з тарифом."""
    out = []
    for g in ROUTE_GROUPS:
        dests = ports[ports.port_id.isin(g["ports"])] if g["ports"] else crossings
        if dests.empty:
            continue
        rows = []
        for p in dests.itertuples():
            c = cache.get(key(o["lat"], o["lon"], p.port_id)) if o["road"] else None
            rows.append(dict(id=p.port_id, name_uk=p.name_uk, straight=round(haversine_km(o["lat"], o["lon"], p.lat, p.lon), 1),
                             road=c["road_km"] if c else None, date=c["date"] if c else None,
                             extra=(f"{p.neighbour_uk}; {p.modes_uk}" if g["route"] == "west" else None)))
        has_road = all(r["road"] is not None for r in rows)
        n = min(rows, key=lambda r: r["road"] if has_road else r["straight"])
        t = tariff_by_oblast.get(o.get("oblast")) if g["route"] == "sea" else None
        out.append(dict(route=g["route"], name_uk=g["name_uk"], point_id=n["id"], point_uk=n["name_uk"], point_note=n["extra"],
                        km=n["road"] if has_road else n["straight"], distance_type="road" if has_road else "straight",
                        distance_label=ROAD_LABEL if has_road else STRAIGHT_LABEL, road_date=n["date"] if has_road else None,
                        tariff_text=(f"≈ {_n(t['rate_min_uah_t'])}"
                                     + ("" if t["rate_min_uah_t"] == t["rate_max_uah_t"] else f"–{_n(t['rate_max_uah_t'])}")
                                     + f" грн/т {t['vat']} ({t['source'].split(' via ')[0]}, {t['period']})"
                                     if t else "немає перевіреного тарифу"),
                        risk=g["risk"]))
    return out


def _n(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def _gen(name: str) -> str:
    """«Кукурудза» → «кукурудзу» для тексту (лише прості випадки; інакше — як є, з малої)."""
    n = name.lower()
    return n[:-1] + "у" if n.endswith("а") else n


def basis_spreads(crops, prices_path: Path = PRICES) -> dict:
    """{crop: {...}} — CPT_port − EXW в межах одного snapshot і однієї дати; source — джерело рядка CPT (явне)."""
    import human_text as H
    d = pd.read_csv(prices_path)
    out = {}
    for c in crops:
        name = H.names().get(c, c)
        best = None
        for (snap, date), g in d[d.crop == c].groupby(["snapshot", "date"]):
            cpt, exw = g[g.basis == "CPT_port"], g[g.basis == "EXW"]
            if len(cpt) == 1 and len(exw) == 1:
                src = [x for x in (cpt.source.iloc[0], exw.source.iloc[0]) if x.strip().lower() not in ("те саме", "те ж саме", "same")]
                if not src:                                   # «те саме» → явне джерело зрізу
                    src = [x for x in d[d.snapshot == snap].source if x.strip().lower() not in ("те саме", "те ж саме", "same")][:1]
                best = dict(status="ok", crop_uk=name, cpt_port_uah_t=float(cpt.price_uah_t.iloc[0]),
                            exw_uah_t=float(exw.price_uah_t.iloc[0]),
                            basis_spread_uah_t=float(cpt.price_uah_t.iloc[0] - exw.price_uah_t.iloc[0]),
                            snapshot=snap, date=date, source=src[0] if src else None)
        if best:
            sp = f"{best['basis_spread_uah_t']:,.0f}".replace(",", " ")
            dd = ".".join(reversed(best["date"].split("-")))
            best["text"] = (f"На ту саму дату порт платив за {_gen(name)} на {sp} грн/т більше, ніж елеватор "
                            f"(Електронна зернова біржа, {dd}). Чи окупиться доставка — залежить від тарифу.")
            out[c] = best
        else:
            out[c] = dict(status="no_data", crop_uk=name, basis_spread_uah_t=None, text=NO_BASIS)
    return out


def tariffs(path: Path = TARIFFS) -> dict:
    """{oblast: {...}} — лише рядки з URL і цитатою (етап 4, D26). Тариф — лише для сайту, у маржу не йде."""
    if not path.exists():
        return {}
    t = pd.read_csv(path)
    t = t[t.source_url.astype(str).str.startswith("http") & t.quote.notna()]
    out = {}
    for r in t.itertuples():
        rng = f"{r.rate_min_uah_t:,.0f}".replace(",", " ") + ("" if r.rate_min_uah_t == r.rate_max_uah_t else
                                                              "–" + f"{r.rate_max_uah_t:,.0f}".replace(",", " "))
        out[r.origin_oblast] = dict(rate_min_uah_t=float(r.rate_min_uah_t), rate_max_uah_t=float(r.rate_max_uah_t),
                                    destination_uk=r.destination_gen_uk, vat=r.vat, period=r.period, source=r.source,
                                    source_url=r.source_url, quote=r.quote,
                                    text=(f"Доставка вантажівкою з {r.origin_uk[:-1]}ої обл. до {r.destination_gen_uk} ≈ {rng} грн/т {r.vat} "
                                          f"({r.source.split(' via ')[0]}, {r.period}). Порт вигідніший, якщо різниця цін більша за цю суму."))
    return out


def build(cache: dict | None = None) -> dict:
    ports = load_ports()
    cache = cache if cache is not None else (json.load(open(CACHE, encoding="utf-8")) if CACHE.exists() else {})
    orig = origins()
    fields = {oid: field_ports(o, ports, cache) for oid, o in orig.items()}
    cross, tar = load_crossings(), tariffs()
    for oid, o in orig.items():
        fields[oid]["routes"] = routes(o, ports, cross, cache, tar)
    return dict(ports=ports.to_dict("records"), crossings=cross.to_dict("records"), routes_note=ROUTES_NOTE,
                road_source=OSRM_SRC, straight_note="по прямій (haversine) — без урахування доріг; реальний шлях довший",
                window_centre_note="центр вікна — медіана координат полів вікна",
                road_note="OSRM дає найкоротший автомаршрут і може вести через сусідні країни (до Рені — можливо, через Молдову); перетин кордону й черги не враховано",
                fields=fields,
                basis=basis_spreads(BASIS_CROPS),
                basis_note="CPT порт − EXW елеватор лише в межах одного зрізу цін і однієї дати; логістику не віднято",
                tariffs=tariffs(), no_tariff_text=NO_TARIFF)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--fetch", action="store_true", help="дозапитати OSRM (мережа) для пілотів і центрів вікон")
    args = a.parse_args()
    cache = json.load(open(CACHE, encoding="utf-8")) if CACHE.exists() else {}
    if args.fetch:
        cache = fetch_osrm(origins(), pd.concat([load_ports(), load_crossings()[["port_id", "name_uk", "lat", "lon", "source_url"]]],
                                                ignore_index=True), cache)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    out = json.load(open(DST, encoding="utf-8")) if DST.exists() else {}
    out["market_ports"] = mp = build(cache)
    DST.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    road = sum(1 for f in mp["fields"].values() if f["nearest"]["distance_type"] == "road")
    print(f"ok {DST}: полів {len(mp['fields'])}, з дорожньою відстанню {road}")


if __name__ == "__main__":
    sys.exit(main())
