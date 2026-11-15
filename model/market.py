"""Ринок (ТЗ A4): чиста ціна в точці збуту з урахуванням доставки, найкраща точка, точка беззбитковості.

Дані заповнюють люди; модуль лише перевіряє формат. Немає файлів/полів → модуль вимкнено з прапорцем
(«логістику не враховано»), не помилка. Без мережі.

  data/market/buyers.csv:   buyer_id,type,name,lat,lon,crop,price_uah_t,basis,date,source
  data/market/transport.yaml: tariff_uah_t_km, fixed_uah_t, road_factor (кожне — {value, source})
  data/raw/prices*.csv:     crop,price_uah_t,basis,date,source[,snapshot,note] — одна ціна на культуру, якщо buyers.csv немає;
                            basis: EXW (з господарства — чиста ціна) | avg_domestic (середня внутрішня, базис у джерелі
                            не вказано — прапорець) | CPT_port (у порту — потрібна логістика; «як є» лише для чутливості).
                            Колонка snapshot: в одному розрахунку — лише ОДИН зріз (змішувати не можна).
Усі суми — «валовий дохід», без витрат на виробництво.
"""
from __future__ import annotations

import math
from datetime import date
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
MARKET = ROOT / "data" / "market"
BUYER_COLS = ["buyer_id", "type", "name", "lat", "lon", "crop", "price_uah_t", "basis", "date", "source"]
BUYER_TYPES = {"elevator", "port", "processor", "feed_mill"}
BASES = {"EXW", "CPT", "FCA"}
PRICE_COLS = ["crop", "price_uah_t", "basis", "date", "source"]
PRICE_BASES = {"EXW", "avg_domestic", "CPT_port"}
BASIS_FLAG = {"avg_domestic": "середня внутрішня ціна, базис у джерелі не вказано",
              "CPT_port": "ціна CPT порт узята «як є», без вирахування логістики — завищує чисту ціну (лише чутливість)"}
SAME_SOURCE = {"те саме", "те ж саме", "same"}
PRICES = ROOT / "data" / "raw" / "prices.csv"
EARTH_R_KM = 6371.0088   # середній радіус Землі (IUGG), для haversine


class MarketFormatError(ValueError):
    pass


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def _has_source(v) -> bool:
    return isinstance(v, str) and v.strip() != "" and not v.strip().upper().startswith("TODO")


def validate_buyers(df: pd.DataFrame) -> pd.DataFrame:
    miss = [c for c in BUYER_COLS if c not in df.columns]
    if miss:
        raise MarketFormatError(f"buyers.csv: немає колонок {miss}")
    errs = []
    for i, r in df.iterrows():
        if r.type not in BUYER_TYPES:
            errs.append(f"рядок {i}: type '{r.type}' не з {sorted(BUYER_TYPES)}")
        if r.basis not in BASES:
            errs.append(f"рядок {i}: basis '{r.basis}' не з {sorted(BASES)}")
        if not (-90 <= float(r.lat) <= 90 and -180 <= float(r.lon) <= 180):
            errs.append(f"рядок {i}: координати поза межами")
        if not float(r.price_uah_t) > 0:
            errs.append(f"рядок {i}: ціна ≤ 0")
        if not _has_source(r.source):
            errs.append(f"рядок {i}: немає source")
    if errs:
        raise MarketFormatError("\n".join(errs))
    return df


@dataclass
class Market:
    enabled: bool
    buyers: pd.DataFrame | None = None
    prices: pd.DataFrame | None = None
    transport: dict | None = None
    flags: list = field(default_factory=list)
    snapshot: str | None = None
    cpt_port_as_is: bool = False
    fallback: "Market | None" = None          # запасний зріз (те саме джерело/рік, напр. DSSU_2025 для DSSU_2025_<обл.>)

    def single_price(self, crop: str) -> tuple[float | None, list[str]]:
        """Остання за датою ціна культури: EXW → avg_domestic (прапорець) → CPT_port лише з cpt_port_as_is (прапорець).
        Примітка рядка (note) завжди йде в прапорці."""
        if self.prices is None:
            return None, []
        s = self.prices[self.prices.crop == crop].sort_values("date")
        order = ["EXW", "avg_domestic"] + (["CPT_port"] if self.cpt_port_as_is else [])
        for b in order:
            r = s[s.basis == b]
            if not r.empty:
                row = r.iloc[-1]
                fl = [f"ціна {crop}: {row.price_uah_t:g} грн/т, {b}, {row.date}" + (f", зріз {self.snapshot}" if self.snapshot else "")]
                if b in BASIS_FLAG:
                    fl.append(f"{crop}: {BASIS_FLAG[b]}")
                note = row["note"] if "note" in row.index else None
                if isinstance(note, str) and note.strip():
                    fl.append(f"{crop}: {note.strip()}")
                return float(row.price_uah_t), fl + list(row["_flags"] if "_flags" in row.index else [])
        if not s.empty:
            return None, [f"{crop}: є лише ціна CPT_port — без логістики (buyers.csv/transport.yaml) чисту ціну не рахуємо"]
        if self.fallback is not None:
            p, fl = self.fallback.single_price(crop)
            if p is not None:
                return p, [f"{crop}: немає в зрізі {self.snapshot} → fallback на {self.fallback.snapshot}"] + fl
        return None, []

    def net_prices(self, crop: str, lat: float, lon: float) -> list[dict]:
        """Усі точки для культури, відсортовані за чистою ціною (грн/т, валова)."""
        if not self.enabled:
            return []
        t = self.transport
        out = []
        for _, b in self.buyers[self.buyers.crop == crop].iterrows():
            d = haversine_km(lat, lon, b.lat, b.lon) * t["road_factor"]
            # EXW — покупець забирає з господарства: доставку не віднімаємо; CPT/FCA — доставка на коштах продавця
            net = float(b.price_uah_t) - (0.0 if b.basis == "EXW" else t["tariff_uah_t_km"] * d + t["fixed_uah_t"])
            out.append(dict(buyer_id=b.buyer_id, type=b.type, name=b["name"], dist_road_km=round(d, 1),
                            price_uah_t=float(b.price_uah_t), net_price_uah_t=round(net, 1), basis=b.basis,
                            date=str(b.date), source=b.source))
        return sorted(out, key=lambda x: -x["net_price_uah_t"])

    def breakeven_port_km(self, crop: str, lat: float, lon: float) -> float | None:
        """Відстань до порту (по дорозі), за якої найкращий порт зрівнюється з найкращим місцевим елеватором."""
        pts = self.net_prices(crop, lat, lon)
        ports = [p for p in pts if p["type"] == "port"]
        elev = [p for p in pts if p["type"] == "elevator"]
        if not ports or not elev:
            return None
        p, e, t = ports[0], elev[0], self.transport
        return round((p["price_uah_t"] - t["fixed_uah_t"] - e["net_price_uah_t"]) / t["tariff_uah_t_km"], 1)

    def channel(self, crop: str, lat: float, lon: float) -> dict:
        """Найкраща точка продажу + 2 альтернативи; або одна ціна prices.csv; або нічого — з прапорцями."""
        pts = self.net_prices(crop, lat, lon)
        if pts:
            be = self.breakeven_port_km(crop, lat, lon)
            return dict(type="sale", buyer_id=pts[0]["buyer_id"], net_price_uah_t=pts[0]["net_price_uah_t"],
                        alternatives=pts[1:3], breakeven_port_km=be, flags=[])
        p, pf = self.single_price(crop)
        if p is not None:
            return dict(type="sale", buyer_id=None, net_price_uah_t=p, alternatives=[],
                        flags=["логістику не враховано — одна ціна на культуру"] + pf)
        return dict(type="sale", buyer_id=None, net_price_uah_t=None, alternatives=[],
                    flags=pf + [f"немає ціни для {crop} — дохід не рахується"])


def validate_prices(df: pd.DataFrame) -> pd.DataFrame:
    miss = [c for c in PRICE_COLS if c not in df.columns]
    if miss:
        raise MarketFormatError(f"prices.csv: немає колонок {miss}")
    errs = []
    for i, r in df.iterrows():
        if r.basis not in PRICE_BASES:
            errs.append(f"рядок {i}: basis '{r.basis}' не з {sorted(PRICE_BASES)}")
        try:
            if not float(r.price_uah_t) > 0:
                errs.append(f"рядок {i}: ціна ≤ 0")
        except (TypeError, ValueError):
            errs.append(f"рядок {i}: ціна '{r.price_uah_t}' не число")
        try:
            date.fromisoformat(str(r.date))
        except ValueError:
            errs.append(f"рядок {i}: дата '{r.date}' не YYYY-MM-DD")
        if not _has_source(r.source):
            errs.append(f"рядок {i}: немає source")
    if errs:
        raise MarketFormatError("prices.csv:\n" + "\n".join(errs))
    return df


def load_prices(prices_path: Path, snapshot: str | None = None, known_crops: set | None = None) -> tuple[pd.DataFrame | None, list[str]]:
    """Читає ціни; якщо є колонка snapshot — бере рівно ОДИН зріз. «те саме» в source → перше явне джерело зрізу (прапорець).
    Невідомі crop_id (не з crops.yaml) — відкидаються з прапорцем."""
    flags = []
    df = pd.read_csv(prices_path)
    if df.empty:
        return None, flags
    if "snapshot" in df.columns:
        snaps = sorted(df.snapshot.dropna().unique())
        if snapshot is None:
            if len(snaps) > 1:
                raise MarketFormatError(f"{prices_path.name}: кілька зрізів {snaps} — вкажіть один (змішувати не можна)")
            snapshot = snaps[0]
        if snapshot not in snaps:
            raise MarketFormatError(f"{prices_path.name}: зрізу '{snapshot}' немає; є {snaps}")
        df = df[df.snapshot == snapshot].copy()
    df["_flags"] = [[] for _ in range(len(df))]
    explicit = [s for s in df.source if isinstance(s, str) and s.strip().lower() not in SAME_SOURCE]
    for i in df.index:
        s = df.at[i, "source"]
        if isinstance(s, str) and s.strip().lower() in SAME_SOURCE:
            if not explicit:
                raise MarketFormatError(f"{prices_path.name}: рядок {i}: «{s}» без явного джерела в зрізі")
            df.at[i, "source"] = explicit[0]
            df.at[i, "_flags"] = [f"джерело ціни «{s}» → підставлено джерело зрізу {snapshot}"]
    if known_crops is not None:
        unk = sorted(set(df.crop) - set(known_crops))
        if unk:
            flags.append(f"ціни для невідомих crop_id {unk} відкинуто (у crops.yaml інші id)")
            df = df[df.crop.isin(known_crops)]
    return validate_prices(df), flags + ([f"ціни: зріз {snapshot}"] if snapshot else [])


def load_market(path: Path = MARKET, prices_path: Path = PRICES, snapshot: str | None = None,
                cpt_port_as_is: bool = False, known_crops: set | None = None,
                fallback_snapshot: str | None = None) -> Market:
    m = _load_market(path, prices_path, snapshot, cpt_port_as_is, known_crops)
    if fallback_snapshot and fallback_snapshot != m.snapshot:
        m.fallback = _load_market(path, prices_path, fallback_snapshot, cpt_port_as_is, known_crops)
        m.flags.append(f"ціни: зріз {m.snapshot}, відсутні культури — fallback на {fallback_snapshot}")
    return m


def snapshots(prices_path: Path) -> list[str]:
    df = pd.read_csv(prices_path)
    return sorted(df.snapshot.dropna().unique()) if "snapshot" in df.columns else []


def _load_market(path: Path, prices_path: Path, snapshot: str | None, cpt_port_as_is: bool,
                 known_crops: set | None) -> Market:
    flags = []
    prices, pflags = (None, [])
    if prices_path.exists():
        prices, pflags = load_prices(prices_path, snapshot, known_crops)
        if snapshot is None and prices is not None and "snapshot" in prices.columns:
            snapshot = prices.snapshot.iloc[0]
    if cpt_port_as_is:
        pflags.append(BASIS_FLAG["CPT_port"])
    extra = dict(snapshot=snapshot, cpt_port_as_is=cpt_port_as_is)
    bf, tf = path / "buyers.csv", path / "transport.yaml"
    if not bf.exists() or not tf.exists():
        return Market(False, prices=prices, flags=pflags + ["логістику не враховано (немає buyers.csv / transport.yaml)"], **extra)
    buyers = validate_buyers(pd.read_csv(bf))
    with open(tf, encoding="utf-8") as f:
        tr = yaml.safe_load(f) or {}
    t = {}
    for k in ("tariff_uah_t_km", "fixed_uah_t", "road_factor"):
        v = tr.get(k) or {}
        if not isinstance(v, dict) or not isinstance(v.get("value"), (int, float)) or not _has_source(v.get("source")):
            flags.append(f"transport.yaml: {k} — TODO або без source")
        elif k in ("tariff_uah_t_km", "road_factor") and float(v["value"]) <= 0:
            flags.append(f"transport.yaml: {k} має бути > 0")
        else:
            t[k] = float(v["value"])
    if flags or buyers.empty:
        return Market(False, prices=prices, flags=pflags + ["логістику не враховано"] + flags + (["buyers.csv порожній"] if buyers.empty else []), **extra)
    return Market(True, buyers, prices, t, pflags, **extra)
