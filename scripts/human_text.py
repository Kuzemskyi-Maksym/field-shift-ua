"""Людський текст для сайту: crop_id → назва з model/crops.yaml (rules.yaml для культур поза моделлю), списки Python → «А → Б».

Лише для текстових полів, що бачить користувач (причини, прапорці, пояснення); id у полях даних (crop, crops…) не чіпаємо.
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def names() -> dict:
    out = {}
    r = yaml.safe_load(open(ROOT / "model" / "rules.yaml", encoding="utf-8"))
    out.update({k: v.get("name_uk", k) for k, v in r["norm164"].items()})
    c = yaml.safe_load(open(ROOT / "model" / "crops.yaml", encoding="utf-8"))["crops"]
    out.update({k: v["name_uk"] for k, v in c.items()})
    out.update({"barley": "Ячмінь"})
    return out


@lru_cache(maxsize=1)
def _ids_re():
    ids = sorted(names(), key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z_])(" + "|".join(map(re.escape, ids)) + r")(?![A-Za-z_])")


def human(s):
    if not isinstance(s, str):
        return s
    N = names()
    s = re.sub(r"\[((?:'[a-z_]+'(?:,\s*)?)+)\]",
               lambda m: " → ".join(N.get(x, x) for x in re.findall(r"'([a-z_]+)'", m.group(1))), s)
    return _ids_re().sub(lambda m: N[m.group(1)].lower() if m.start() > 0 else N[m.group(1)], s)
