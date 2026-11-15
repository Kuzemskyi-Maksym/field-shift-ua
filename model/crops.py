"""Завантаження і валідація model/crops.yaml.

Культура потрапляє в оптимізацію, лише якщо всі обов'язкові параметри мають число з джерелом.
TODO → «заблоковано» з причинами. Календар зі status: stub → дозволено лише з allow_stubs=True
і з прапорцем у результаті.

CLI:  python -m model.crops [--zone steppe] [--allow-stubs] [--report reports/crops_params.md]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CROPS_YAML = HERE / "crops.yaml"
SOILS_YAML = HERE / "soils.yaml"

TODO = "TODO"
PARAMS = ["kc_ini", "kc_mid", "kc_end", "stages_days", "ky", "zr_m", "p"]
# Межі фізичної правдоподібності — лише перевірка друкарських помилок, не параметри моделі.
SANITY = {"h_m": (0.1, 10.0), "kc_ini": (0.0, 1.3), "kc_mid": (0.3, 1.4), "kc_end": (0.0, 1.3), "ky": (0.2, 2.0),
          "zr_m": (0.1, 3.0), "p": (0.1, 0.8)}


class SchemaError(ValueError):
    pass


@dataclass
class CropStatus:
    crop: str
    name_uk: str
    zone: str
    ready: bool
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def load_yaml(path: Path = CROPS_YAML) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_todo(v) -> bool:
    if isinstance(v, (list, tuple)):
        return any(is_todo(x) for x in v)
    return v is None or (isinstance(v, str) and v.strip().upper().startswith(TODO))


SEASONS = {"winter", "spring", "perennial", "none", "cover"}
STUB_SOURCES = {"BASELINE_V0", "STUB_NO_SOURCE"}   # лише дати календаря і лише з allow_stubs
DYNAMIC = "dynamic"                                  # ярі: дата сівби щороку з температури ґрунту (sow_rule)
HLS_STAGE_FLAG = "фази озимих з NDVI полів (HLS, медіана областей зони), не з агрономічних джерел; L_late 25 д — FAO-56 Т11"


def _mmdd(s) -> tuple[int, int] | None:
    """'MM-DD' → (місяць, день) або None, якщо формат/дата некоректні (рік не високосний)."""
    if not isinstance(s, str) or len(s) != 5 or s[2] != "-":
        return None
    try:
        import datetime as _dt
        d = _dt.date(2001, int(s[:2]), int(s[3:]))
    except ValueError:
        return None
    return d.month, d.day


def _bad_sources(doc: dict) -> set[str]:
    """Джерела, текст яких — TODO, або заглушки: число з таким src не має джерела."""
    return {k for k, v in doc.get("sources", {}).items() if is_todo(v)} | STUB_SOURCES


def is_stub_calendar(cal: dict) -> bool:
    return cal.get("status") == "stub" or cal.get("src") in STUB_SOURCES


def validate_schema(doc: dict) -> None:
    """Помилки формату (не відсутність даних): невідомі/порожні src, неправдоподібні числа, криві дати."""
    errs = []
    srcs = set(doc.get("sources", {}))
    bad = _bad_sources(doc)
    zones = doc.get("zones", [])
    for cid, c in doc.get("crops", {}).items():
        for k in ("name_uk", "season", "group"):
            if k not in c:
                errs.append(f"{cid}: немає {k}")
        if c.get("season") not in SEASONS:
            errs.append(f"{cid}.season='{c.get('season')}' не з {sorted(SEASONS)}")
        for key, p in c.items():
            if isinstance(p, dict) and "value" in p:
                v = p["value"]
                if p.get("src") not in srcs:
                    errs.append(f"{cid}.{key}: src '{p.get('src')}' немає в sources")
                elif not is_todo(v) and p["src"] in bad:
                    errs.append(f"{cid}.{key}={v}: src '{p['src']}' — TODO/заглушка, число без джерела")
                if is_todo(v):
                    if isinstance(v, list):
                        errs.append(f"{cid}.{key}: TODO всередині списку {v} — пиши value: TODO цілком")
                    continue
                if key == "stages_days":
                    if not (isinstance(v, list) and len(v) == 4 and
                            all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in v)):
                        errs.append(f"{cid}.stages_days: очікую 4 додатні цілі, маю {v}")
                elif key in SANITY:
                    lo, hi = SANITY[key]
                    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                        errs.append(f"{cid}.{key}={v} поза [{lo}, {hi}] — друкарська помилка?")
        for z in zones:
            cal = (c.get("calendar") or {}).get(z)
            if cal is None:
                errs.append(f"{cid}: немає calendar.{z}")
                continue
            if cal.get("src") not in srcs:
                errs.append(f"{cid}.calendar.{z}: src '{cal.get('src')}' немає в sources")
            if cal.get("src") in STUB_SOURCES and cal.get("status") != "stub":
                errs.append(f"{cid}.calendar.{z}: src {cal.get('src')} вимагає status: stub")
            sow = cal.get("sow")
            if is_todo(sow) or sow == "none":
                continue
            if cal.get("src") in bad - STUB_SOURCES:
                errs.append(f"{cid}.calendar.{z}: дата без джерела (src '{cal.get('src')}')")
            if cal.get("stage_src") is not None and cal["stage_src"] not in srcs:
                errs.append(f"{cid}.calendar.{z}: stage_src '{cal['stage_src']}' немає в sources")
            if cal.get("window") is not None and (len(cal["window"]) != 2 or None in map(_mmdd, cal["window"])):
                errs.append(f"{cid}.calendar.{z}.window={cal['window']}: очікую 2 дати MM-DD")
            if sow == DYNAMIC:
                r = c.get("sow_rule") or {}
                if c.get("season") != "spring":
                    errs.append(f"{cid}.calendar.{z}: sow: dynamic лише для ярих")
                thr = r.get("threshold_c")
                if isinstance(thr, bool) or not isinstance(thr, (int, float)) or not -5 <= thr <= 30:
                    errs.append(f"{cid}.sow_rule.threshold_c={thr}: очікую число °C")
                if _mmdd(r.get("not_before")) is None:
                    errs.append(f"{cid}.sow_rule.not_before='{r.get('not_before')}' не MM-DD")
                if not isinstance(r.get("mean_days"), int) or not 1 <= r["mean_days"] <= 15:
                    errs.append(f"{cid}.sow_rule.mean_days={r.get('mean_days')}: очікую ціле 1–15")
                if r.get("var") not in ("TSOIL1",):
                    errs.append(f"{cid}.sow_rule.var={r.get('var')}: підтримується лише TSOIL1 (проксі T2M — автоматично з прапорцем)")
                if r.get("src") not in srcs or r.get("src") in bad:
                    errs.append(f"{cid}.sow_rule: src '{r.get('src')}' немає в sources або без джерела")
                continue
            if _mmdd(sow) is None:
                errs.append(f"{cid}.calendar.{z}.sow='{sow}' не MM-DD")
            sd = cal.get("stage_dates")
            if c.get("season") == "winter" and not is_todo(sd):
                ds = [_mmdd(x) for x in (sd or [])]
                if len(ds) != 4 or None in ds:
                    errs.append(f"{cid}.calendar.{z}.stage_dates: очікую 4 дати MM-DD, маю {sd}")
                elif ds != sorted(ds) or not ds[-1] < _mmdd(sow):
                    errs.append(f"{cid}.calendar.{z}.stage_dates {sd}: мають зростати в році після сівби {sow}")
    if errs:
        raise SchemaError("\n".join(errs))


def crop_status(doc: dict, cid: str, zone: str, allow_stubs: bool = False) -> CropStatus:
    if zone not in doc.get("zones", []):
        raise ValueError(f"невідома зона '{zone}', є: {doc.get('zones')}")
    c = doc["crops"][cid]
    st = CropStatus(cid, c["name_uk"], zone, True)
    if c.get("group") == "fallow":
        if is_todo(c.get("kc_method", {}).get("value")):
            st.reasons.append("kc_method: TODO")
    else:
        for k in PARAMS:
            if c.get("season") == "winter" and k == "stages_days":
                continue          # для озимих фази — з calendar.stage_dates (rules_of_choice.winter_calendar)
            if is_todo(c.get(k, {}).get("value")):
                st.reasons.append(f"{k}: TODO ({c.get(k, {}).get('note', 'немає в джерелі')})")
        cal = c["calendar"][zone]
        if is_todo(cal.get("sow")):
            st.reasons.append(f"calendar.{zone}.sow: TODO (R2/R3)")
        else:
            if c.get("season") == "winter" and is_todo(cal.get("stage_dates", TODO)):
                st.reasons.append(f"calendar.{zone}.stage_dates: TODO (озимі — дати фаз від R2/R3)")
            if cal.get("stage_src") == "HLS_PHENO":
                st.flags.append(HLS_STAGE_FLAG)
            if cal.get("sow") == DYNAMIC and (c.get("sow_rule") or {}).get("flag"):
                st.flags.append(f"сівба: {c['sow_rule']['flag']}")
            if is_stub_calendar(cal):
                if allow_stubs:
                    st.flags.append(f"STUB: календар {zone} — заглушка без джерела ({cal.get('src')})")
                    if cal.get("flag"):
                        st.flags.append(f"STUB: {cal['flag']}")
                else:
                    st.reasons.append(f"calendar.{zone}: заглушка {cal.get('src')} (дозволити --allow-stubs)")
        sd = c.get("stages_days", {})
        if c.get("season") != "winter" and not is_todo(sd.get("value")) and sd.get("src") == "FAO56_T11":
            st.flags.append(f"довжини фаз FAO-56 Т11 для іншого регіону ({sd.get('note', '')})")
        for k in PARAMS:
            if c.get(k, {}).get("midpoint"):
                st.flags.append(f"{k}: середина діапазону без примітки FAO")
    st.ready = not st.reasons
    return st


def all_status(doc: dict, zone: str, allow_stubs: bool = False) -> list[CropStatus]:
    return [crop_status(doc, cid, zone, allow_stubs) for cid in doc["crops"]]


def ready_crops(zone: str, allow_stubs: bool = False, path: Path = CROPS_YAML) -> dict:
    """Повертає {crop_id: параметри-числа} лише для готових культур."""
    doc = load_yaml(path)
    validate_schema(doc)
    out = {}
    for st in all_status(doc, zone, allow_stubs):
        if st.ready:
            c = doc["crops"][st.crop]
            out[st.crop] = dict(name_uk=c["name_uk"], season=c["season"], group=c["group"],
                                n_fixing=c.get("n_fixing", False), dries_soil=c.get("dries_soil", False),
                                calendar=c["calendar"][zone], flags=st.flags, sow_rule=c.get("sow_rule"),
                                **{k: c[k]["value"] for k in PARAMS + ["kc_method", "h_m"] if k in c})
    return out


def param_table_md(doc: dict) -> str:
    srcs = doc["sources"]
    rows = ["| Культура | Параметр | Значення | Джерело | Примітка |", "|---|---|---|---|---|"]
    for cid, c in doc["crops"].items():
        for k in PARAMS + ["kc_method"]:
            if k not in c:
                continue
            p = c[k]
            v = p["value"]
            v = "**TODO**" if is_todo(v) else v
            rows.append(f"| {c['name_uk']} | {k} | {v} | {p['src']} | {p.get('note', '')} |")
        for z, cal in c["calendar"].items():
            v = "**TODO**" if is_todo(cal.get("sow")) else cal.get("sow")
            tag = " (stub)" if cal.get("status") == "stub" else ""
            rows.append(f"| {c['name_uk']} | calendar.{z}.sow | {v}{tag} | {cal['src']} | |")
    rows += ["", "**Джерела**", ""] + [f"- `{k}` — {v}" for k, v in srcs.items()]
    return "\n".join(rows)


def status_md(doc: dict, zones: list[str], allow_stubs: bool) -> str:
    out = []
    for z in zones:
        sts = all_status(doc, z, allow_stubs)
        ok = [s for s in sts if s.ready]
        out += [f"### Зона `{z}` (allow_stubs={allow_stubs}): готово {len(ok)} з {len(sts)}", "",
                "| Культура | Статус | Причини / прапорці |", "|---|---|---|"]
        for s in sts:
            why = "; ".join(s.reasons) if s.reasons else "; ".join(s.flags)
            out.append(f"| {s.name_uk} | {'✅ готово' if s.ready else '⛔ заблоковано'} | {why} |")
        ky = [s.name_uk for s in sts if any(r.startswith("ky: TODO") for r in s.reasons)]
        out += ["", f"**Чекають джерела Ky:** {', '.join(ky) if ky else '—'}", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default=None)
    ap.add_argument("--allow-stubs", action="store_true")
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    doc = load_yaml()
    validate_schema(doc)
    zones = [a.zone] if a.zone else doc["zones"]
    text = "\n".join(["# Параметри культур: значення × джерело / TODO", "",
                      "Згенеровано `python -m model.crops --report`. Не редагувати вручну.", "",
                      "## Готовність до оптимізації", "",
                      status_md(doc, zones, False), status_md(doc, zones, True),
                      "## Культура × параметр × джерело", "", param_table_md(doc)])
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text, encoding="utf-8")
        print("Звіт:", a.report)
    else:
        print(status_md(doc, zones, a.allow_stubs))


if __name__ == "__main__":
    main()
