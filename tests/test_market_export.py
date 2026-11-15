"""Етап 1 модуля ринку (D23): експорт за країнами з Держстату → site/market.json (market_export)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import market_export as ME  # noqa: E402


@pytest.fixture(scope="module")
def mx():
    return ME.build()


def test_every_mapped_product_present(mx):
    for crop, prods in ME.CROP_PRODUCTS.items():
        for p in prods:
            assert p in mx["products"], (crop, p)
        if not prods:
            assert mx["crop_notes"][crop] == "немає даних експорту"


def test_shares_not_above_100(mx):
    for p, b in mx["products"].items():
        assert all(0 <= t["share_pct"] <= 100 for t in b["top"]), p
        assert b["top_share_pct"] <= 100 + 1e-6, p
        assert len(b["top"]) <= ME.TOP
        assert [t["share_pct"] for t in b["top"]] == sorted((t["share_pct"] for t in b["top"]), reverse=True)


def test_price_not_computed_for_zero_volume(mx):
    assert ME.price_usd_t(100.0, 0) is None and ME.price_usd_t(100.0, float("nan")) is None
    assert ME.price_usd_t(180.0, 1000.0) == 180.0                 # тис. дол. × 1000 / т = дол./т
    d = ME.load()
    z = d[(d.volume_t == 0) & (d.area != "_T")]
    assert len(z) > 0                                              # у даних є нульові обсяги — перевіряємо реальні рядки
    for r in z.itertuples():
        b = mx["products"][r.product]
        for t in b["top"]:
            if t["area"] == r.area and b["year"] == r.year:
                assert t["price_usd_t"] is None


def test_units_wheat_and_sunflower_insight(mx):
    """Перевірка одиниць з ТЗ: пшениця 2024 ≈ 20,7 млн т; соняшник — майже лише олія/шрот."""
    w = mx["products"]["wheat"]
    assert w["year"] == 2024 and abs(w["total"]["volume_mt"] - 20.7) < 0.1
    s, o = mx["products"]["sunflower_seed"]["total"]["value_musd"], mx["products"]["sunflower_oil"]["total"]["value_musd"]
    assert s < 0.05 * o and "олійному заводу" in mx["crop_notes"]["sunflower"]
    d = pd.read_csv(ME.SRC)
    t = d[(d["product"] == "wheat") & (d.area == "_T") & (d.year == 2024)].iloc[0]
    assert w["total"]["value_musd"] == round(t.value_kusd / 1000, 1)
    assert all(b["source"] for b in mx["products"].values())
