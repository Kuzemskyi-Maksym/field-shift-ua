"""Кроки 4–5: формати, вимкнення без даних, ручні приклади."""
import math

import pandas as pd
import pytest
import yaml

from model import livestock as L
from model import market as MK


def test_market_disabled_without_data():
    m = MK.load_market()
    assert not m.enabled and any("логістику не враховано" in f for f in m.flags)
    ch = m.channel("maize", 47.1, 30.6)
    assert ch["net_price_uah_t"] is None and ch["flags"]


def _write_market(tmp_path, transport_ok=True):
    pd.DataFrame([
        dict(buyer_id="E1", type="elevator", name="Елеватор", lat=47.0, lon=30.6, crop="maize", price_uah_t=7000, basis="CPT", date="2026-11-01", source="тест"),
        dict(buyer_id="P1", type="port", name="Порт", lat=46.5, lon=30.7, crop="maize", price_uah_t=8000, basis="CPT", date="2026-11-01", source="тест"),
    ]).to_csv(tmp_path / "buyers.csv", index=False)
    tr = {k: {"value": v, "source": "тест"} for k, v in dict(tariff_uah_t_km=2.0, fixed_uah_t=100.0, road_factor=1.0).items()}
    if not transport_ok:
        tr["road_factor"] = {"value": "TODO", "source": "TODO"}
    (tmp_path / "transport.yaml").write_text(yaml.safe_dump(tr), encoding="utf-8")


def test_net_price_and_breakeven_hand_example(tmp_path):
    _write_market(tmp_path)
    m = MK.load_market(tmp_path)
    assert m.enabled
    lat, lon = 47.0, 30.6                       # поле = елеватор
    pts = m.net_prices("maize", lat, lon)
    d_port = MK.haversine_km(lat, lon, 46.5, 30.7)
    assert pts[0]["buyer_id"] == "P1" if 8000 - 2 * d_port - 100 > 6900 else pts[0]["buyer_id"] == "E1"
    assert math.isclose([p for p in pts if p["buyer_id"] == "E1"][0]["net_price_uah_t"], 7000 - 100)
    # беззбитковість: 8000 − 100 − 2·d = 6900 → d = 500 км
    assert m.breakeven_port_km("maize", lat, lon) == 500.0


def test_transport_todo_disables(tmp_path):
    _write_market(tmp_path, transport_ok=False)
    m = MK.load_market(tmp_path)
    assert not m.enabled and any("road_factor" in f for f in m.flags)


def test_buyers_without_source_rejected(tmp_path):
    _write_market(tmp_path)
    b = pd.read_csv(tmp_path / "buyers.csv"); b.loc[0, "source"] = "TODO"; b.to_csv(tmp_path / "buyers.csv", index=False)
    with pytest.raises(MK.MarketFormatError):
        MK.load_market(tmp_path)


def test_livestock_disabled_by_default():
    ls = L.load_livestock()
    assert not ls.enabled
    v, sp, fl = ls.feed_value_uah_t("maize")
    assert v is None and fl


def test_livestock_hand_example(tmp_path):
    d = {"species": {"pig": {"feed_conversion_kg_feed_per_kg_gain": {"value": 3.0, "source": "тест"},
                             "liveweight_price_uah_kg": {"value": 60.0, "source": "тест"},
                             "carcass_yield": {"value": 0.75, "source": "тест"},
                             "max_share_in_ration": {"maize": {"value": 0.6, "source": "тест"}}}}}
    p = tmp_path / "l.yaml"; p.write_text(yaml.safe_dump(d), encoding="utf-8")
    ls = L.load_livestock(p)
    v, sp, fl = ls.feed_value_uah_t("maize")
    assert v == pytest.approx(1000 / 3 * 60) and sp == "pig"
    assert ls.feed_value_uah_t("sunflower")[0] is None
    ch = L.choose_channel(7000.0, v, sp)
    assert ch["type"] == "feed" and "без витрат на утримання" in ch["why"]
    assert L.choose_channel(25000.0, v, sp)["type"] == "sale"


def test_prices_template_empty_and_validation(tmp_path):
    m = MK.load_market()                                   # data/raw/prices.csv — порожній шаблон
    assert m.prices is None
    good = tmp_path / "p.csv"
    pd.DataFrame([dict(crop="maize", price_uah_t=7000, basis="EXW", date="2026-11-01", source="тест"),
                  dict(crop="maize", price_uah_t=7500, basis="EXW", date="2026-11-10", source="тест"),
                  dict(crop="sunflower", price_uah_t=19000, basis="CPT_port", date="2026-11-10", source="тест")]).to_csv(good, index=False)
    m = MK.load_market(prices_path=good)
    assert m.channel("maize", 47, 30)["net_price_uah_t"] == 7500          # остання за датою EXW
    ch = m.channel("sunflower", 47, 30)
    assert ch["net_price_uah_t"] is None and any("CPT_port" in f for f in ch["flags"])
    for bad in [dict(basis="FOB"), dict(price_uah_t=-1), dict(source="TODO"), dict(date="11/2026")]:
        row = dict(crop="maize", price_uah_t=7000, basis="EXW", date="2026-11-01", source="тест") | bad
        pd.DataFrame([row]).to_csv(good, index=False)
        with pytest.raises(MK.MarketFormatError):
            MK.load_market(prices_path=good)


def test_snapshots_not_mixed_and_avg_domestic(tmp_path):
    p = tmp_path / "pc.csv"
    pd.DataFrame([
        dict(crop="maize", price_uah_t=5000, basis="avg_domestic", date="2026-11-05", snapshot="A", source="джерело A", note="кукурудза"),
        dict(crop="sunflower", price_uah_t=15000, basis="avg_domestic", date="2026-11-05", snapshot="A", source="те саме", note=""),
        dict(crop="maize", price_uah_t=9000, basis="EXW", date="2026-07-08", snapshot="B", source="джерело B", note=""),
        dict(crop="sunflower", price_uah_t=30000, basis="CPT_port", date="2026-07-08", snapshot="B", source="те саме", note=""),
        dict(crop="barley", price_uah_t=9000, basis="CPT_port", date="2026-07-08", snapshot="B", source="те саме", note=""),
    ]).to_csv(p, index=False)
    with pytest.raises(MK.MarketFormatError, match="кілька зрізів"):
        MK.load_market(prices_path=p)
    a = MK.load_market(prices_path=p, snapshot="A", known_crops={"maize", "sunflower"})
    ch = a.channel("sunflower", 47, 30)
    assert ch["net_price_uah_t"] == 15000
    assert any("базис у джерелі не вказано" in f for f in ch["flags"])
    assert any("підставлено джерело зрізу A" in f for f in ch["flags"])
    b = MK.load_market(prices_path=p, snapshot="B", known_crops={"maize", "sunflower"})
    assert b.channel("maize", 47, 30)["net_price_uah_t"] == 9000            # лише зріз B
    assert b.channel("sunflower", 47, 30)["net_price_uah_t"] is None        # CPT_port строго — ні
    assert any("barley" in f for f in b.flags)                             # невідомий crop_id відкинуто
    bb = MK.load_market(prices_path=p, snapshot="B", cpt_port_as_is=True, known_crops={"maize", "sunflower"})
    ch = bb.channel("sunflower", 47, 30)
    assert ch["net_price_uah_t"] == 30000 and any("завищує" in f for f in ch["flags"])


def test_real_candidates_file_main_snapshot():
    m = MK.load_market(prices_path=MK.ROOT / "data" / "raw" / "prices_candidates.csv", snapshot="UUB_2026-11")
    assert m.channel("spring_wheat", 47, 30)["net_price_uah_t"] == pytest.approx(5098.86)
    assert any("ПРАПОРЕЦЬ" in f for f in m.channel("spring_wheat", 47, 30)["flags"])
    assert m.channel("pea", 47, 30)["net_price_uah_t"] is None
