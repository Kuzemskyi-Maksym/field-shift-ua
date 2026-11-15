"""Етап 2 модуля ринку (D24): порти, пряма/дорога, кеш OSRM, стоп після двох невдач."""
import io
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import market_ports as MP  # noqa: E402


@pytest.fixture(scope="module")
def mp():
    return MP.build()                     # лише кеш, без мережі


def test_ports_have_source_url():
    p = MP.load_ports()
    assert len(p) == 5 and p.source_url.str.startswith("http").all()
    raw = pd.read_csv(MP.PORTS)
    assert len(raw) == len(p)             # жоден порт не відкинуто


def test_haversine_sanity():
    p = MP.load_ports().set_index("port_id")
    d = MP.haversine_km(p.loc["odesa"].lat, p.loc["odesa"].lon, p.loc["chornomorsk"].lat, p.loc["chornomorsk"].lon)
    assert 15 < d < 30                    # Одеса — Чорноморськ ≈ 20 км по прямій


def test_pilots_road_portfolio_straight(mp):
    f = mp["fields"]
    for pid in MP.PILOTS:
        assert f[pid]["kind"] == "pilot" and f[pid]["nearest"]["distance_type"] == "road", pid
        for r in f[pid]["ports"]:
            assert r["distance_road_km"] >= r["distance_straight_km"], (pid, r)   # дорога не коротша за пряму
    pf = [v for v in f.values() if v["kind"] == "portfolio"]
    assert len(pf) > 200 and all(v["nearest"]["distance_type"] == "straight" for v in pf)
    assert sum(v["kind"] == "window_centre" for v in f.values()) == 5


def test_nearest_falls_back_to_straight_without_full_road():
    ports = MP.load_ports()
    o = dict(lat=47.1, lon=30.67, kind="pilot", road=True)
    r = MP.field_ports(o, ports, {})                        # порожній кеш
    assert r["nearest"]["distance_type"] == "straight" and r["nearest"]["distance_label"] == "по прямій"


def test_fetch_stops_after_two_failures():
    calls = []

    def bad(req, timeout):
        calls.append(req.full_url)
        raise OSError("timeout")
    orig = {"a": dict(lat=47.1, lon=30.6, kind="pilot", road=True), "b": dict(lat=48.0, lon=31.3, kind="pilot", road=True)}
    cache = MP.fetch_osrm(orig, MP.load_ports(), {}, pause_s=0, opener=bad)
    assert len(calls) == 2 and cache == {}


def test_fetch_uses_cache_and_parses():
    ports = MP.load_ports().head(1)
    o = {"a": dict(lat=47.1, lon=30.6, kind="pilot", road=True), "p": dict(lat=47.0, lon=30.0, kind="portfolio", road=False)}

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    calls = []

    def ok(req, timeout):
        calls.append(1)
        return R(json.dumps({"code": "Ok", "routes": [{"distance": 123456}]}).encode())
    c = MP.fetch_osrm(o, ports, {}, pause_s=0, opener=ok)
    assert len(calls) == 1 and list(c.values())[0]["road_km"] == 123.5     # поле портфеля OSRM не питає
    MP.fetch_osrm(o, ports, c, pause_s=0, opener=ok)
    assert len(calls) == 1                                                  # з кешу


# ---- етап 3 (D25): спред порт − елеватор лише в межах одного зрізу ----
def test_basis_maize_from_one_snapshot(mp):
    b = mp["basis"]["maize"]
    assert b["status"] == "ok" and b["snapshot"] == "EGB_2026-07" and b["date"] == "2026-07-08"
    assert b["basis_spread_uah_t"] == b["cpt_port_uah_t"] - b["exw_uah_t"] == 10660 - 9151
    assert "graintrade.com.ua" in b["source"] and "1 509 грн/т" in b["text"]
    others = [c for c, v in mp["basis"].items() if c != "maize"]
    assert all(mp["basis"][c]["status"] == "no_data" and mp["basis"][c]["basis_spread_uah_t"] is None
               and mp["basis"][c]["text"] == MP.NO_BASIS for c in others)


def test_basis_never_mixes_snapshots(tmp_path):
    p = tmp_path / "pr.csv"
    p.write_text("crop,price_uah_t,basis,date,snapshot,source,note\n"
                 "maize,10000,CPT_port,2026-07-08,A,http://a,\n"
                 "maize,9000,EXW,2026-07-08,B,http://b,\n"
                 "soybean,20000,CPT_port,2026-07-08,A,http://a,\n"
                 "soybean,19000,EXW,2026-07-09,A,http://a,\n", encoding="utf-8")
    b = MP.basis_spreads(["maize", "soybean"], p)
    assert b["maize"]["status"] == "no_data" and b["soybean"]["status"] == "no_data"   # різні зрізи / різні дати


# ---- етап 4 (D26): тариф лише з джерелом, за областю відправлення ----
def test_tariffs_sourced_and_only_known_oblasts(mp):
    t = mp["tariffs"]
    assert set(t) == {"chernihiv", "zhytomyr", "kyiv", "sumy", "cherkasy", "kirovohrad", "mykolaiv"}
    for ob, v in t.items():
        assert v["source_url"].startswith("http") and v["quote"] and v["rate_min_uah_t"] <= v["rate_max_uah_t"], ob
    assert t["mykolaiv"]["rate_min_uah_t"] == 800 and t["mykolaiv"]["rate_max_uah_t"] == 950
    assert "800–950 грн/т з ПДВ" in t["mykolaiv"]["text"]
    for pid in ("berezivka_od", "karlivka_pl", "kalynivka_vn", "volyn:f3735"):           # для їхніх областей тарифу немає
        assert mp["fields"][pid]["oblast"] not in t
    assert mp["fields"]["arbuzynka_mk"]["oblast"] == "mykolaiv"
    assert mp["no_tariff_text"] == "вартість доставки не враховано — немає перевіреного тарифу"


def test_crossings_sourced_with_coordinates():
    """Правка 2 (D28): пункти пропуску — лише з координатами й URL Вікіпедії; Рава-Руська без координат не береться."""
    c = MP.load_crossings()
    assert set(c.port_id) == {"yahodyn", "shehyni", "uzhhorod", "chop"}
    assert c.source_url.str.contains("wikipedia.org").all()


def test_three_routes_no_scores(mp):
    for pid in MP.PILOTS:
        R = mp["fields"][pid]["routes"]
        assert [r["route"] for r in R] == ["sea", "danube", "west"], pid
        for r in R:
            assert r["distance_type"] == "road" and r["km"] > 0           # пілоти — дорогою (OSRM, кеш)
            assert not ({"score", "weight", "rank"} & set(r)), r          # жодних ваг і балів
            assert r["risk"] and not any(ch.isdigit() for ch in r["risk"]), r["risk"]   # ризики без цифр
    assert mp["routes_note"].startswith("Ми порівнюємо маршрути за відстанню, тарифом із джерелом і ризиками")
    assert mp["fields"]["odesa:f15245"]["routes"][0]["distance_type"] == "straight"


def test_route_tariff_only_with_source(mp):
    """Тариф є лише для моря з Миколаївської (D26); решта — «немає перевіреного тарифу»."""
    for pid in MP.PILOTS:
        for r in mp["fields"][pid]["routes"]:
            if pid == "arbuzynka_mk" and r["route"] == "sea":
                assert r["tariff_text"].startswith("≈ 800–950 грн/т") and "Укрвантаж" in r["tariff_text"]
            else:
                assert r["tariff_text"] == "немає перевіреного тарифу", (pid, r["route"])
