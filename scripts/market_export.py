#!/usr/bin/env python3
"""Ринок (легкий шар, D23): куди Україна експортує культуру — Держстат SDMX, 2021–2024 → site/market.json, ключ market_export.

Вхід: data/raw/market/derzhstat_export_by_country.csv — product,uktzed,area,country_uk,year,value_kusd,volume_t,source
(вартість — тис. дол. США; обсяг — т; area=_T — усього). Модель стратегій не чіпаємо: це окремий шар для сайту.
Для кожного продукту за останній рік (2024): топ-5 країн за вартістю, частка в _T (%), обсяг (тис. т), середня ціна
(дол./т = value_kusd·1000 / volume_t, лише якщо volume_t > 0), тренд частки топ-1 (2021 → 2024); ряд _T за 2021–2024.
Інші ключі site/market.json (market_ports — етап 2) зберігаються.

  python scripts/market_export.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "market" / "derzhstat_export_by_country.csv"
DST = ROOT / "site" / "market.json"
YEAR = 2024
TOP = 5

# crop_id (model/crops.yaml) → продукти експорту (УКТЗЕД). Ячмінь — обидва; горох — у групі 0713 (усі сушені бобові).
CROP_PRODUCTS = {
    "winter_wheat": ["wheat"], "spring_wheat": ["wheat"],
    "winter_barley": ["barley"], "spring_barley": ["barley"],
    "maize": ["maize"], "soybean": ["soy"], "winter_rapeseed": ["rapeseed"],
    "sunflower": ["sunflower_seed", "sunflower_oil", "sunflower_meal_cake"],
    "pea": ["pulses"],
    "sugar_beet": [],
}
NO_DATA = {"sugar_beet": "немає даних експорту"}
PRODUCT_UK = {
    "wheat": "пшениця", "barley": "ячмінь", "maize": "кукурудза", "soy": "соя (боби)", "rapeseed": "насіння ріпаку",
    "sunflower_seed": "насіння соняшнику", "sunflower_oil": "соняшникова олія",
    "sunflower_meal_cake": "макуха і шрот олійних", "pulses": "сушені бобові (у т. ч. горох)",
}
PRODUCT_NOTE = {
    "sunflower_meal_cake": "код УКТЗЕД 2306 — макуха й інші тверді залишки олійних (крім сої), не лише соняшнику",
    "pulses": "код УКТЗЕД 0713 — усі сушені бобові (горох, сочевиця, нут, квасоля тощо), не лише горох",
}


def load() -> pd.DataFrame:
    d = pd.read_csv(SRC)
    need = {"product", "uktzed", "area", "country_uk", "year", "value_kusd", "volume_t", "source"}
    miss = need - set(d.columns)
    if miss:
        raise ValueError(f"{SRC.name}: немає колонок {sorted(miss)}")
    if d.source.isna().any() or (d.source.astype(str).str.strip() == "").any():
        raise ValueError(f"{SRC.name}: рядки без source")
    return d


def price_usd_t(value_kusd, volume_t):
    """дол./т; при нульовому/відсутньому обсязі — None (не рахуємо)."""
    if volume_t is None or pd.isna(volume_t) or volume_t <= 0 or pd.isna(value_kusd):
        return None
    return round(float(value_kusd) * 1000 / float(volume_t), 1)


def product_block(d: pd.DataFrame, product: str) -> dict:
    p = d[d["product"] == product]
    tot = p[p.area == "_T"].set_index("year")
    cty = p[p.area != "_T"]
    yr = YEAR if YEAR in tot.index else int(tot.index.max())
    t = tot.loc[yr]
    c = cty[cty.year == yr].sort_values("value_kusd", ascending=False)
    top = [dict(country_uk=r.country_uk, area=r.area,
                share_pct=round(100 * r.value_kusd / t.value_kusd, 1) if t.value_kusd > 0 else None,
                value_musd=round(r.value_kusd / 1000, 1), volume_kt=round(r.volume_t / 1000, 1),
                price_usd_t=price_usd_t(r.value_kusd, r.volume_t)) for r in c.head(TOP).itertuples()]
    trend = None
    if top:
        a = top[0]["area"]
        sh = {}
        for y in (int(min(tot.index)), yr):
            v = cty[(cty.year == y) & (cty.area == a)].value_kusd.sum()
            sh[str(y)] = round(100 * v / tot.loc[y].value_kusd, 1) if tot.loc[y].value_kusd > 0 and v > 0 else None
        trend = dict(country_uk=top[0]["country_uk"], share_pct=sh)
    series = [dict(year=int(y), value_musd=round(r.value_kusd / 1000, 1), volume_mt=round(r.volume_t / 1e6, 3),
                   price_usd_t=price_usd_t(r.value_kusd, r.volume_t)) for y, r in tot.sort_index().iterrows()]
    return dict(product=product, name_uk=PRODUCT_UK[product], uktzed=int(p.uktzed.iloc[0]), year=yr,
                total=dict(value_musd=round(t.value_kusd / 1000, 1), volume_mt=round(t.volume_t / 1e6, 3),
                           price_usd_t=price_usd_t(t.value_kusd, t.volume_t)),
                top=top, top_share_pct=round(sum(x["share_pct"] or 0 for x in top), 1), top1_trend=trend, series=series,
                note=PRODUCT_NOTE.get(product), source=str(p.source.iloc[0]))


def sunflower_insight(prods: dict) -> str | None:
    s, o, m = (prods.get(k) for k in ("sunflower_seed", "sunflower_oil", "sunflower_meal_cake"))
    if not (s and o):
        return None
    f = lambda v: f"{v:,.0f}".replace(",", " ")  # noqa: E731
    return (f"Україна експортує соняшник майже лише переробленим: у {s['year']} р. насіння — {f(s['total']['value_musd'])} млн дол., "
            f"олія — {f(o['total']['value_musd'])} млн дол."
            + (f", макуха і шрот олійних (УКТЗЕД 2306) — {f(m['total']['value_musd'])} млн дол" if m else "")
            + ". Тож соняшник фермер зазвичай продає олійному заводу в Україні, а не в порт.")


def build() -> dict:
    d = load()
    prods = {p: product_block(d, p) for p in sorted(d["product"].unique())}
    known = {p for v in CROP_PRODUCTS.values() for p in v}
    missing = known - set(prods)
    if missing:
        raise ValueError(f"немає продуктів у {SRC.name}: {sorted(missing)}")
    notes = dict(NO_DATA)
    ins = sunflower_insight(prods)
    if ins:
        notes["sunflower"] = ins
    return dict(year=YEAR, source=str(d.source.iloc[0]), source_short="Держстат, зовнішня торгівля товарами за країнами (SDMX), 2024",
                units=dict(value="млн дол. США", volume_top="тис. т", volume_total="млн т", price="дол. США за т"),
                crop_products=CROP_PRODUCTS, crop_notes=notes, products=prods)


def main():
    out = json.load(open(DST, encoding="utf-8")) if DST.exists() else {}
    out["market_export"] = build()
    DST.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"ok {DST} ({DST.stat().st_size // 1024} КБ): продуктів {len(out['market_export']['products'])}")


if __name__ == "__main__":
    sys.exit(main())
