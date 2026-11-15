#!/usr/bin/env python3
"""ТЗ A10.3: чутливість топ-3 стратегій на 5 пілотних полях → reports/sensitivity.md.

Варіанти: Ky пшениці озимої 1.05; калібрування Yx C; TAW з SoilGrids wv для всіх полів; без поправки Kc на клімат.
Ціна ±20% і коефіцієнт «дорога/пряма» ±1 — не застосовні, доки немає data/market (дохід не рахується) — фіксуємо це.
prev_effect вкл/викл — значень із джерелом немає (усі 1.0) → результат ідентичний за побудовою.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.optimize import PILOT_FIELDS, optimize_field  # noqa: E402

VARIANTS = {
    "база": dict(),
    "Ky пшениці озимої 1.05": dict(sim_kwargs=dict(ky_override={"winter_wheat": 1.05})),
    "калібрування Yx C": dict(calib="C"),
    "TAW: SoilGrids wv для всіх полів": dict(sim_kwargs=dict(taw_source="wv_all")),
    "без поправки Kc на клімат": dict(sim_kwargs=dict(kc_climate=False)),
}
NAMES = ("max_income", "min_risk", "balanced")


def main():
    rows = []
    for f in PILOT_FIELDS:
        base = None
        for vn, kw in VARIANTS.items():
            o = optimize_field(f, allow_stubs=True, write=False, rank="yield_index", **kw)
            st = {s["name"]: s for s in o["strategies"]}
            rec = dict(field=f, variant=vn, seconds=o["run"]["seconds"])
            for n in NAMES:
                s = st.get(n)
                rec[n] = " → ".join(s["sequence_uk"]) if s else None
                rec[f"{n}_idx50"] = s["metrics"]["yield_index_p50"] if s else None
                ww = [y for y in (s["per_year"] if s else []) if y["crop"] == "winter_wheat" and y["yield_t_ha"]]
                rec[f"{n}_ww_t_ha"] = ww[0]["yield_t_ha"]["typical"] if ww else None
            if base is None:
                base = rec
            rec["top3_changed"] = [n for n in NAMES if rec[n] != base[n]]
            rec["next_season"] = o["next_season"]["crop_uk"]
            rows.append(rec)
            print(f, vn, rec["top3_changed"], flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(ROOT / "out" / "strategies" / "sensitivity.csv", index=False)
    md = ["# Чутливість топ-3 стратегій (ТЗ A10.3)", "",
          "5 полів: 4 пілоти + volyn:f3735; `--allow-stubs --rank yield_index` (демо механіки, D11); план 2027–2030. «Змінились» — послідовність стратегії інша, ніж у базі.", "",
          "## Не застосовно зараз", "",
          "- **Ціна ±20%**, **коефіцієнт дорога/пряма ±1**: `data/market/*` порожні → дохід не рахується, ранжування за індексом врожаю (docs/decisions.md D7). Перевірити, щойно R-ролі внесуть ціни.",
          "- **prev_effect вкл/викл**: у `rules.yaml` немає жодного множника з джерелом → усі 1.0, результат ідентичний за побудовою.",
          "", "## Зведення: які стратегії змінились", "",
          "| Поле | Варіант | Змінились | Наступний сезон | balanced | idx P50 balanced | пшениця т/га (typical, balanced) |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['field']} | {r['variant']} | {', '.join(r['top3_changed']) or '—'} | {r['next_season']} | {r['balanced']} | "
                  f"{r['balanced_idx50']} | {r['balanced_ww_t_ha']} |")
    md += ["", "## Повні топ-3 по варіантах", ""]
    for f in PILOT_FIELDS:
        md += [f"### {f}", "", "| Варіант | max_income | min_risk | balanced |", "|---|---|---|---|"]
        for r in rows:
            if r["field"] == f:
                md.append(f"| {r['variant']} | {r['max_income']} | {r['min_risk']} | {r['balanced']} |")
        md.append("")
    ch = d[d.variant != "база"]
    base_next = d[d.variant == "база"].set_index("field").next_season
    md += ["## Висновок", "",
           f"- Варіантів, де змінилась хоча б одна з 3 стратегій: {int((ch.top3_changed.str.len() > 0).sum())} з {len(ch)}.",
           f"- Наступний сезон змінився: {int((ch.next_season.fillna('—') != ch.field.map(base_next).fillna('—')).sum())} з {len(ch)}.",
           "- Калібрування Yx (A/C) змінює т/га, але не Ya/Yx і не вибір у демо-режимі; з цінами (режим money) калібрування впливатиме на вибір — перевірити, коли будуть ціни."]
    (ROOT / "reports" / "sensitivity.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()
