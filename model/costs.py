"""Витрати на виробництво (Держстат SDMX, підприємства): культура × область × рік → грн/га, з правилами заповнення.

data/raw/costs_derzhstat.csv: crop, oblast, year, prod_cost_uah_t, profitability_pct, sale_price_uah_t, yield_ent_t_ha,
prod_cost_uah_ha (= на т × урожайність підприємств того ж року), full_cost_uah_t, full_cost_uah_ha, note, source.

Правила (рішення 12.11.2026, docs/decisions.md D15):
  • пропуск для області → середнє по інших областях того ж року, прапорець «витрати з інших областей»;
  • викид: якщо значення відрізняється від медіани по областях того ж року більш ніж у outlier_factor разів →
    медіана з прапорцем;
  • note рядка (пшениця/ячмінь без поділу на озимі/ярі, горох = зернобобові) — у прапорці.
Витрати на га ФІКСОВАНІ: не залежать від урожаю року симуляції.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
COSTS = ROOT / "data" / "raw" / "costs_derzhstat.csv"
COLUMNS = {"prod_cost_uah_ha", "full_cost_uah_ha"}


@lru_cache(maxsize=4)
def load_costs(path: str = str(COSTS)) -> pd.DataFrame:
    d = pd.read_csv(path)
    miss = ({"crop", "oblast", "year", "profitability_pct", "note", "source"} | COLUMNS) - set(d.columns)
    if miss:
        raise ValueError(f"{Path(path).name}: немає колонок {sorted(miss)}")
    return d


@dataclass
class Cost:
    value: float | None
    flags: list = field(default_factory=list)
    profitability_pct: float | None = None


def cost_ha(crop: str, oblast_uk: str, year: int, column: str = "prod_cost_uah_ha",
            outlier_factor: float = 2.0, path: str = str(COSTS)) -> Cost:
    if column not in COLUMNS:
        raise ValueError(f"column {column} не з {sorted(COLUMNS)}")
    d = load_costs(path)
    y = d[(d.crop == crop) & (d.year == year)]
    if y.empty:
        return Cost(None, [f"витрати {crop} {year}: немає в Держстаті"])
    vals = y.set_index("oblast")[column].dropna()
    vals = vals[vals > 0]
    row = y[y.oblast == oblast_uk]
    prof = None if row.empty or pd.isna(row.profitability_pct.iloc[0]) else float(row.profitability_pct.iloc[0])
    note = (row.note.iloc[0] if not row.empty else y.note.iloc[0])
    flags = [f"витрати {crop}: {note}"] if isinstance(note, str) and note.strip() else []
    label = "повна собівартість" if column == "full_cost_uah_ha" else "витрати на виробництво"
    if vals.empty:
        return Cost(None, flags + [f"{label} {crop} {year}: немає жодної області"], prof)
    med = float(vals.median())
    if oblast_uk in vals.index:
        v = float(vals[oblast_uk])
        if v > outlier_factor * med or v < med / outlier_factor:
            return Cost(med, flags + [f"{label} {crop} {oblast_uk} {year}: {v:.0f} грн/га — викид (>×{outlier_factor:g} від "
                                      f"медіани {med:.0f}), взято медіану по областях"], prof)
        return Cost(v, flags + [f"{label} {crop}: {v:.0f} грн/га ({oblast_uk}, {year}, Держстат, підприємства)"], prof)
    others = vals.drop(oblast_uk, errors="ignore")
    v = float(others.mean())
    return Cost(v, flags + [f"{label} {crop}: {v:.0f} грн/га — витрати з інших областей (середнє {', '.join(others.index)}, {year}); "
                            f"для {oblast_uk} немає даних"], prof)


def profitability_line(crop: str, crop_uk: str, oblast_uk: str, c: Cost, year: int) -> tuple[str, str | None]:
    """→ (рядок для explain, попередження або None)."""
    if c.profitability_pct is None:
        return f"рентабельність «{crop_uk}» в області ({oblast_uk} обл.) за Держстатом, {year}: немає даних", None
    line = (f"рентабельність «{crop_uk}» в області ({oblast_uk} обл.) за Держстатом, {year}: {c.profitability_pct:g}% "
            f"(рентабельність Держстату — за {year} рік; маржа моделі — P50 за 25 роками погоди)")
    warn = None
    if c.profitability_pct < 0:
        warn = (f"УВАГА: «{crop_uk}» збиткова в області ({oblast_uk} обл.) за Держстатом, {year} ({c.profitability_pct:g}%) — "
                f"рентабельність Держстату — за {year} рік, маржа моделі — медіана 25 років погоди; "
                "маржа моделі для цієї культури може бути завищена")
    return line, warn
