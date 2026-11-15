#!/usr/bin/env python3
"""Маржа на 5 пілотах (D15/D16): основний варіант (повна собівартість 2025), демо «соняшнику не було», чутливість
→ out/strategies/strategies_*.json, demo_not_sunflower_*.json, margin_compare.json; таблиці markdown у stdout
(для reports/margin.md), разом з перевіркою буряку проти Держстату.

  python scripts/margin_report.py > out/strategies/margin_tables.md
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model import costs as CO  # noqa: E402
from model import simulate as M  # noqa: E402
from model.optimize import OUT, PILOT_FIELDS, STRATEGY_NAMES, optimize_field  # noqa: E402

DEMO_FIELDS = ["kalynivka_vn", "karlivka_pl"]   # роки — з HLS поля (D22): S/early і S/'' з 2020 (rules.yaml maybe_sunflower)


def demo_years(f):
    from model import optimize as O
    from model import rules as R
    ms = R.load_rules()["history"]["maybe_sunflower"]
    return [r["year"] for r in O.field_history(f) if r["year"] >= 2020 and r["c"] == ms["c"] and (r["sub"] or "") in ms["sub"]]
SENS = {"(a) витрати на виробництво (prod_cost)": dict(cost_column="prod_cost_uah_ha"),
        "(b) повна собівартість 2024": dict(cost_year=2024),
        "(c) UUB-ціни + ті самі витрати": dict(prices_file="data/raw/prices_candidates.csv", prices_snapshot="UUB_2026-11")}
NAMES = ("current",) + STRATEGY_NAMES


def k(v):
    return "—" if v is None else f"{v / 1000:.1f}"


def row(field, variant, o):
    st = {s["name"]: s for s in o["strategies"]}
    r = dict(field=field, variant=variant, next=o["next_season"]["crop_uk"])
    for n in NAMES:
        s = st.get(n)
        r[n] = " → ".join(s["sequence_uk"]) if s else None
        r[f"{n}_m50"] = s["metrics"]["margin_p50"] if s else None
        r[f"{n}_m10"] = s["metrics"]["margin_p10"] if s else None
        r[f"{n}_fallow_no_cost"] = s["metrics"].get("margin_excludes_fallow_cost") if s else None
    r["prof"] = sorted({x for s in o["strategies"] for x in s["explain"]["profitability"]})
    r["warn"] = sorted({g for s in o["strategies"] for g in s["explain"]["gaps"] if g.startswith("УВАГА")})
    return r


def cell(r, n):
    if r.get(n) is None:
        return "—"
    star = "\\*" if r.get(f"{n}_fallow_no_cost") else ""
    return f"{r[n]} ({k(r[f'{n}_m50'])} / {k(r[f'{n}_m10'])}){star}"


def beet_check():
    out = []
    for f in ("kalynivka_vn", "karlivka_pl", "volyn:f3735"):
        o = optimize_field(f, allow_stubs=True, write=False)
        fld = M.field_profile(f, True)
        res, _ = M.SequenceSimulator(fld, K=1, allow_stubs=True).run(("sugar_beet",))
        yx, price = o["run"]["yx_t_ha"]["sugar_beet"], o["run"]["unit_values"]["money"]["sugar_beet"]
        y = yx * res[0].rel_yield
        d = CO.load_costs()
        r = d[(d.crop == "sugar_beet") & (d.oblast == fld.oblast_uk) & (d.year == 2025)].iloc[0]
        fc = CO.cost_ha("sugar_beet", fld.oblast_uk, 2025, "full_cost_uah_ha").value
        pc = CO.cost_ha("sugar_beet", fld.oblast_uk, 2025, "prod_cost_uah_ha").value
        p = lambda q: float(np.percentile(y, q))  # noqa: E731
        out.append(dict(field=f, oblast=fld.oblast_uk, yx=yx, y10=p(10), y50=p(50), y90=p(90), price=price,
                        prod_ha=pc, full_ha=fc, m_full50=p(50) * price - fc, m_full90=p(90) * price - fc,
                        m_prod50=p(50) * price - pc, ent_y=float(r.yield_ent_t_ha), ent_price=float(r.sale_price_uah_t),
                        ent_prof=float(r.profitability_pct), prod_t=float(r.prod_cost_uah_t), full_t=float(r.full_cost_uah_t),
                        ent_margin=float(r.yield_ent_t_ha * r.sale_price_uah_t - r.full_cost_uah_ha)))
    return out


def year_check(field, crop, year=2025):
    """Маржа моделі саме в погоду року `year` проти Держстату того ж року (урожай, ціна, витрати)."""
    o = optimize_field(field, allow_stubs=True, write=False)
    fld = M.field_profile(field, True)
    res, _ = M.SequenceSimulator(fld, K=1, allow_stubs=True).run((crop,))
    yx, price = o["run"]["yx_t_ha"][crop], o["run"]["unit_values"]["money"][crop]
    y = pd.Series(yx * res[0].rel_yield, index=M.YEARS)
    cost = CO.cost_ha(crop, fld.oblast_uk, year, o["ranking"]["cost_column"]).value
    d = CO.load_costs()
    r = d[(d.crop == crop) & (d.oblast == fld.oblast_uk) & (d.year == year)].iloc[0]
    obs = M.yields(str(ROOT / "data/raw/yield/derzhstat_yield.csv"))
    obs_all = obs[(obs.culture == crop) & (obs.oblast == fld.oblast_uk) & (obs.year == year)].yield_t_ha
    m = y * price - cost
    return dict(field=field, crop=crop, year=year, oblast=fld.oblast_uk, yx=yx, price_model=price, cost_ha=cost,
                y_model_year=float(y[year]), rank_year_of_25=int((y < y[year]).sum()) + 1, y_model_p50=float(y.median()),
                margin_model_year=float(m[year]), margin_model_p50=float(m.median()),
                y_ent=float(r.yield_ent_t_ha), y_all=float(obs_all.iloc[0]) if len(obs_all) else None,
                price_ent=float(r.sale_price_uah_t), full_cost_t=float(r.full_cost_uah_t),
                margin_derzh=float(r.yield_ent_t_ha * r.sale_price_uah_t - r.full_cost_uah_ha), prof=float(r.profitability_pct),
                gap_yield=float((y[year] - r.yield_ent_t_ha) * price),
                gap_price=float((price - r.sale_price_uah_t) * r.yield_ent_t_ha),
                gap_cost=float(r.full_cost_uah_ha - cost))


def main():
    rows, demo = [], []
    for f in PILOT_FIELDS:
        rows.append(row(f, "DSSU_2025, повна собівартість (основне)", optimize_field(f, allow_stubs=True)))
        for v, kw in SENS.items():
            rows.append(row(f, v, optimize_field(f, allow_stubs=True, write=False, **kw)))
    for f, yrs in ((f, demo_years(f)) for f in DEMO_FIELDS):
        if not yrs:                                   # у HLS поля немає «можливо соняшник» з 2020 → демо не має сенсу
            (OUT / f"demo_not_sunflower_{f}.json").unlink(missing_ok=True)
            demo.append(dict(field=f, variant="демо not_sunflower", confirmed=[], skipped="немає S/early з 2020 у HLS поля"))
            continue
        o = optimize_field(f, allow_stubs=True, write=False, history_confirmed={y: "not_sunflower" for y in yrs})
        (OUT / f"demo_not_sunflower_{f}.json").write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
        demo.append(dict(row(f, "демо not_sunflower", o), confirmed=yrs))
    beet = beet_check()
    maize = year_check("arbuzynka_mk", "maize", 2025)
    (OUT / "margin_compare.json").write_text(json.dumps(dict(rows=rows, demo=demo, beet=beet, maize_mykolaiv_2025=maize),
                                                        ensure_ascii=False, indent=1),
                                             encoding="utf-8")

    hdr = "| Поле | next_season | " + " | ".join(NAMES[1:]) + " | поточна |"
    sep = "|" + "---|" * (len(NAMES) + 2)
    print("## Основне\n\n" + hdr + "\n" + sep)
    for r in rows:
        if "основне" in r["variant"]:
            print(f"| {r['field']} | **{r['next']}** | " + " | ".join(cell(r, n) for n in NAMES[1:]) + f" | {cell(r, 'current')} |")
    print("\n## Демо\n\n| Поле | підтверджено | next_season | " + " | ".join(NAMES[1:]) + " | поточна |\n" + "|" + "---|" * (len(NAMES) + 3))
    for r in demo:
        if r.get("skipped"):
            print(f"| {r['field']} | — | {r['skipped']} |" + " |" * len(NAMES))
            continue
        print(f"| {r['field']} | {', '.join(map(str, r['confirmed']))} | **{r['next']}** | "
              + " | ".join(cell(r, n) for n in NAMES[1:]) + f" | {cell(r, 'current')} |")
    print("\n## Чутливість\n\n| Поле | Варіант | next_season | " + " | ".join(NAMES[1:]) + " |\n" + "|" + "---|" * (len(NAMES) + 2))
    for r in rows:
        if "основне" not in r["variant"]:
            print(f"| {r['field']} | {r['variant']} | {r['next']} | " + " | ".join(cell(r, n) for n in NAMES[1:]) + " |")
    print("\n## Буряк\n")
    for b in beet:
        print(json.dumps({kk: (round(v, 1) if isinstance(v, float) else v) for kk, v in b.items()}, ensure_ascii=False))
    print("\n## Кукурудза Миколаївська 2025\n")
    print(json.dumps({kk: (round(v, 2) if isinstance(v, float) else v) for kk, v in maize.items()}, ensure_ascii=False))
    print("\n## Рентабельність\n")
    for r in rows:
        if "основне" in r["variant"]:
            print(f"- **{r['field']}:** " + "; ".join(x.split("рентабельність ", 1)[1].split(" (рентабельність")[0].replace(" за Держстатом, 2025", "") for x in r["prof"]))
            for w in r["warn"]:
                print(f"  - ⚠ {w}")


if __name__ == "__main__":
    main()
