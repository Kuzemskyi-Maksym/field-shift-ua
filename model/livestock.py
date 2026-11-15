"""Тваринництво (ТЗ A5): канал «зерно → корм → приріст → грн» і самозабезпечення кормом.

model/livestock.yaml заповнюють люди; модуль лише перевіряє формат. Немає даних → вимкнено з прапорцем.
Сума — «валовий дохід від м'яса, без витрат на утримання» (виробничі витрати тваринництва, крім корму, — TODO).

Формат livestock.yaml:
  species:
    pig:                                    # pig | broiler | beef | dairy
      feed_conversion_kg_feed_per_kg_gain: {value, source}
      liveweight_price_uah_kg: {value, source}
      carcass_yield: {value, source}
      max_share_in_ration: {crop_id: {value, source}}
  feed_values: {crop_id: {me_mj_kg: {value, source}, cp_pct: {value, source}}}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

LIVESTOCK_YAML = Path(__file__).resolve().parent / "livestock.yaml"
SPECIES = {"pig", "broiler", "beef", "dairy"}
NOTE = "валовий дохід від м'яса, без витрат на утримання"


def _num(v):
    """{value, source} з числом і непорожнім не-TODO source → число, інакше None."""
    if not isinstance(v, dict):
        return None
    x, s = v.get("value"), v.get("source")
    ok = isinstance(x, (int, float)) and not isinstance(x, bool) and isinstance(s, str) and s.strip() \
        and not s.strip().upper().startswith("TODO")
    return float(x) if ok else None


@dataclass
class Livestock:
    enabled: bool
    species: dict = field(default_factory=dict)      # {sp: {fcr, price, carcass, max_share{crop: x}}}
    feed_values: dict = field(default_factory=dict)  # {crop: {me, cp}}
    flags: list = field(default_factory=list)

    def feed_value_uah_t(self, crop: str) -> tuple[float | None, str | None, list[str]]:
        """Найкращий вид тварин для 1 т зерна культури: (грн/т валових, вид, прапорці)."""
        if not self.enabled:
            return None, None, list(self.flags)
        best, who = None, None
        for sp, p in self.species.items():
            if (p["max_share"].get(crop) or 0) <= 0:
                continue
            v = 1000.0 / p["fcr"] * p["price"]          # кг приросту на 1 т корму × грн/кг живої ваги
            if best is None or v > best:
                best, who = v, sp
        if best is None:
            return None, None, [f"{crop}: немає виду тварин із часткою в раціоні > 0"]
        return best, who, [NOTE]

    def self_sufficiency(self, produced_t: dict, need_me_mj: float | None, need_cp_t: float | None) -> dict | None:
        """Частка потреби в енергії (ME) і протеїні (CP), закрита власним зерном. Потреби — вхід фермера."""
        if not self.enabled or not need_me_mj or not need_cp_t:
            return None
        me = sum(t * 1000 * self.feed_values[c]["me"] for c, t in produced_t.items() if c in self.feed_values)
        cp = sum(t * self.feed_values[c]["cp"] / 100 for c, t in produced_t.items() if c in self.feed_values)
        return dict(energy=min(me / need_me_mj, 1.0), protein=min(cp / need_cp_t, 1.0))


def load_livestock(path: Path = LIVESTOCK_YAML) -> Livestock:
    if not path.exists():
        return Livestock(False, flags=["канал «корм» вимкнено (немає model/livestock.yaml)"])
    with open(path, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    flags, species = [], {}
    for sp, p in (d.get("species") or {}).items():
        if sp not in SPECIES:
            raise ValueError(f"livestock.yaml: вид '{sp}' не з {sorted(SPECIES)}")
        fcr = _num(p.get("feed_conversion_kg_feed_per_kg_gain"))
        price = _num(p.get("liveweight_price_uah_kg"))
        carcass = _num(p.get("carcass_yield"))
        shares = {c: _num(v) for c, v in (p.get("max_share_in_ration") or {}).items()}
        if fcr is None or price is None:
            flags.append(f"{sp}: FCR або ціна — TODO/без source")
            continue
        species[sp] = dict(fcr=fcr, price=price, carcass=carcass, max_share={c: v for c, v in shares.items() if v is not None})
    fv = {}
    for c, v in (d.get("feed_values") or {}).items():
        me, cp = _num((v or {}).get("me_mj_kg")), _num((v or {}).get("cp_pct"))
        if me is not None and cp is not None:
            fv[c] = dict(me=me, cp=cp)
    if not species:
        return Livestock(False, flags=["канал «корм» вимкнено (немає видів із джерелами)"] + flags)
    return Livestock(True, species, fv, flags)


def choose_channel(sale_net_uah_t: float | None, feed_uah_t: float | None, feed_species: str | None) -> dict:
    """max(продаж, корм) з поясненням."""
    if feed_uah_t is None and sale_net_uah_t is None:
        return dict(type="sale", why="немає ні ціни продажу, ні даних тваринництва — канал не оцінено")
    if feed_uah_t is None:
        return dict(type="sale", why="канал «корм» недоступний")
    if sale_net_uah_t is None:
        return dict(type="feed", species=feed_species,
                    why=f"ціни продажу немає; корм ({feed_species}) {feed_uah_t:.0f} грн/т ({NOTE})")
    if feed_uah_t > sale_net_uah_t:
        return dict(type="feed", species=feed_species,
                    why=f"корм ({feed_species}) {feed_uah_t:.0f} грн/т > продаж {sale_net_uah_t:.0f} грн/т ({NOTE}; "
                        "вартість решти раціону не врахована — порівняння завищує корм)")
    return dict(type="sale", why=f"продаж {sale_net_uah_t:.0f} грн/т ≥ корм {feed_uah_t:.0f} грн/т ({NOTE})")
