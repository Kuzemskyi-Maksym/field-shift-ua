"""Техніка для збирання (D27): групи техніки культур (model/machinery.yaml) і «наявна техніка» поля з історії HLS.

Лише позначки та вибір серед уже порахованих кандидатів оптимізатора — модель і №164 не змінюються.
"""
from functools import lru_cache
from pathlib import Path

import yaml

YAML = Path(__file__).resolve().parent / "machinery.yaml"
RENT_NOTE = "це обмеження, а не заборона: техніку можна взяти в оренду або замовити послугу збирання"


@lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(open(YAML, encoding="utf-8"))


def crop_group(crop: str) -> str | None:
    """Група техніки культури; None — збирання не потрібне (пар). Культура без групи → other_unknown."""
    cfg = load()
    if crop in cfg.get("no_harvest", []):
        return None
    for g, v in cfg["groups"].items():
        if crop in v["crops"]:
            return g
    return "other_unknown"


def needs(seq) -> list[str]:
    """Групи техніки, потрібні послідовності (порядок першої появи)."""
    return [g for g in dict.fromkeys(crop_group(c) for c in seq) if g]


def owned(hist: list[dict], plan_start_year: int) -> tuple[set, list[str]]:
    """Наявна техніка = групи культур поточної практики з HLS за останні history_years років до плану.
    Підтверджена культура (confirmed_crop) — її група; «not_sunflower» — культура невідома, групу не додаємо (прапорець)."""
    cfg = load()
    last = plan_start_year - 2                         # останній сезон історії (2025 для плану з 2027)
    first = last - cfg["history_years"] + 1
    got, flags = set(), []
    for r in hist:
        if not first <= r["year"] <= last:
            continue
        cc = r.get("confirmed_crop")
        if cc and cc != "not_sunflower":
            g = crop_group(cc)
            if g:
                got.add(g)
            continue
        key = f"{r['c']}_{r.get('sub') or ''}" if r["c"] == "S" else r["c"]
        m = cfg["hls_map"].get(key)
        if cc == "not_sunflower" and m and m.get("group") == "sunflower_header":
            flags.append(f"{r['year']}: «це був не соняшник» — культура невідома, техніку за цей рік не враховано")
            continue
        if m and m.get("group"):
            got.add(m["group"])
            flags.append(f"{r['year']}: {m['flag']}")
    base = cfg.get("combine_base")
    if base and base["group"] not in got and any(
            first <= r["year"] <= last and (r["c"] in base["classes"] or crop_group(r.get("confirmed_crop") or "")
                                             in ("grain_header", "corn_header", "sunflower_header"))
            for r in hist):
        got.add(base["group"])
        flags.append(base["flag"])
    return got, list(dict.fromkeys(flags))


def badge(seq, have: set) -> dict:
    """Позначка стратегії: які групи потрібні і які з них нові для поля."""
    G = load()["groups"]
    need = needs(seq)
    new = [g for g in need if g not in have]
    return dict(groups=need, new=new, new_uk=[G[g]["name_uk"] for g in new],
                text=("потрібна нова техніка: " + ", ".join(G[g]["name_uk"] for g in new)) if new else None,
                sources={g: G[g].get("source_url") or G[g]["source"] for g in need})
