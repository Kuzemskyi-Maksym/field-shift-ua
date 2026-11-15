"""Ґрунт поля: SoilGrids (кеш data/raw/soil/soil_fields.csv) → середнє по шарах до Zr → клас USDA → FAO-56 Табл. 19 → TAW.

Без мережі. Дані качає scripts/fetch_soilgrids.py. Ручне задання: texture_override=<клас> → прапорець.
"""
from __future__ import annotations

import operator
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
SOILS_YAML = HERE / "soils.yaml"
SOIL_CSV = HERE.parent / "data" / "raw" / "soil" / "soil_fields.csv"
OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


@lru_cache(maxsize=1)
def load_soils(path: str = str(SOILS_YAML)) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _cond_ok(v: float, spec: str) -> bool:
    for part in spec.split(","):
        m = re.fullmatch(r"\s*(<=|>=|<|>)\s*([\d.]+)\s*", part)
        if not m:
            raise ValueError(f"погана умова '{spec}'")
        if not OPS[m.group(1)](v, float(m.group(2))):
            return False
    return True


def _extra_ok(sand, silt, clay, expr: str) -> bool:
    m = re.fullmatch(r"\s*silt\+([\d.]+)\*clay\s*(<=|>=|<|>)\s*([\d.]+)\s*", expr)
    if not m:
        raise ValueError(f"погана умова '{expr}'")
    return OPS[m.group(2)](silt + float(m.group(1)) * clay, float(m.group(3)))


def usda_classes(sand: float, silt: float, clay: float, soils: dict | None = None) -> list[str]:
    """Усі класи USDA, чиї рядки таблиці NRCS (USTF) задовольняє точка. Очікується рівно один."""
    soils = soils or load_soils()
    out = []
    for name, boxes in soils["usda_texture"]["classes"].items():
        for b in boxes:
            if (_cond_ok(sand, b["sand"]) and _cond_ok(silt, b["silt"]) and _cond_ok(clay, b["clay"])
                    and all(_extra_ok(sand, silt, clay, e) for e in b.get("extra", []))):
                out.append(name)
                break
    return out


def layer_weights(zr_m: float, soils: dict | None = None) -> dict[str, float]:
    """Частки шарів SoilGrids у профілі 0..Zr (за товщиною перекриття)."""
    soils = soils or load_soils()
    sg = soils["soilgrids"]
    zr_cm = zr_m * 100
    w = {}
    for (top, bot), lab in zip(sg["layers_cm"], sg["depth_labels"]):
        ov = max(0.0, min(bot, zr_cm) - top)
        if ov > 0:
            w[lab] = ov
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()}


@lru_cache(maxsize=1)
def _soil_table(path: str = str(SOIL_CSV)) -> pd.DataFrame:
    return pd.read_csv(path)


def wv_taw(field_id: str, zr_m: float, soils: dict | None = None) -> tuple[float | None, float | None]:
    """θ при 33 і 1500 кПа з SoilGrids (wv0033/wv1500; value = об. %, ISRIC FAQ), середнє по шарах до Zr → (θFC, θWP)."""
    soils = soils or load_soils()
    t = _soil_table()
    t = t[t.field_id == field_id]
    w = layer_weights(zr_m, soils)
    out = []
    for prop in ("wv0033", "wv1500"):
        s = t[t.prop == prop].set_index("depth").value.reindex(list(w))
        if s.isna().any():
            return None, None
        out.append(sum(s[d] * wt for d, wt in w.items()) / 100)
    return out[0], out[1]


def field_texture(field_id: str, zr_m: float, texture_override: str | None = None, soils: dict | None = None,
                  taw_source: str = "t19") -> dict:
    """→ {texture, sand, silt, clay, fao_t19, taw_mm_per_m, flags, theta_fc, theta_wp}.

    taw_source: "t19" — FAO-56 Табл. 19, а для класів поза нею — SoilGrids wv0033/wv1500 з прапорцем;
                "wv_all" — SoilGrids wv для всіх полів (лише чутливість)."""
    soils = soils or load_soils()
    flags = []
    if texture_override:
        if texture_override not in soils["usda_texture"]["classes"]:
            raise ValueError(f"невідомий клас '{texture_override}'")
        tex, comp = texture_override, {}
        flags.append(f"текстура задана вручну: {tex}")
    else:
        if not SOIL_CSV.exists():
            return dict(texture=None, fao_t19=None, taw_mm_per_m=None,
                        flags=["немає даних SoilGrids (scripts/fetch_soilgrids.py) — задай --soil-texture"])
        t = _soil_table()
        t = t[t.field_id == field_id]
        if t.empty:
            return dict(texture=None, fao_t19=None, taw_mm_per_m=None, flags=[f"поля {field_id} немає в SoilGrids-кеші"])
        w = layer_weights(zr_m, soils)
        comp = {}
        for prop in ("sand", "silt", "clay"):
            s = t[t.prop == prop].set_index("depth").value
            if s.reindex(list(w)).isna().any():
                return dict(texture=None, fao_t19=None, taw_mm_per_m=None, flags=[f"SoilGrids: пропуск {prop} у шарах до Zr"])
            comp[prop] = sum(s[d] * wt for d, wt in w.items())
        tot = sum(comp.values())
        if abs(tot - 100) > soils["soilgrids"]["sum_tolerance_pct"]:
            flags.append(f"SoilGrids: sand+silt+clay = {tot:.1f}% — нормовано до 100")
        comp = {k: 100 * v / tot for k, v in comp.items()}
        cls = usda_classes(comp["sand"], comp["silt"], comp["clay"], soils)
        if len(cls) != 1:
            return dict(texture=None, fao_t19=None, taw_mm_per_m=None, **comp,
                        flags=[f"клас USDA неоднозначний/не знайдений: {cls} для {comp}"])
        tex = cls[0]
        flags.append(f"текстура SoilGrids 2.0 (центроїд поля, шари до {zr_m} м)")
    missing = tex in soils["usda_texture"]["fao_t19_missing"] or tex not in soils["textures"]
    if (missing or taw_source == "wv_all") and not texture_override:
        fc, wp = wv_taw(field_id, zr_m, soils)
        if fc is None:
            flags.append(f"клас {tex}: TAW недоступний (немає wv SoilGrids)")
            return dict(texture=tex, fao_t19=None, taw_mm_per_m=None, flags=flags, **comp)
        flags.append("TAW з SoilGrids, клас відсутній у FAO табл. 19" if missing else "TAW з SoilGrids wv0033/wv1500 (режим чутливості wv_all)")
        return dict(texture=tex, fao_t19=None, theta_fc=fc, theta_wp=wp, taw_mm_per_m=1000 * (fc - wp), flags=flags, **comp)
    if missing:
        flags.append(f"клас {tex} відсутній у FAO-56 Табл. 19 — TAW: TODO")
        return dict(texture=tex, fao_t19=None, taw_mm_per_m=None, flags=flags, **comp)
    row = soils["textures"][tex]
    fc, wp = sum(row["theta_fc"]) / 2, sum(row["theta_wp"]) / 2
    flags.append("θFC/θWP — середина діапазону Табл. 19")
    return dict(texture=tex, fao_t19=tex, theta_fc=fc, theta_wp=wp, taw_mm_per_m=1000 * (fc - wp), flags=flags, **comp)
