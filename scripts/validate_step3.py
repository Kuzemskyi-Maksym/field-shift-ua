#!/usr/bin/env python3
"""Крок 3: baseline v0 проти нових параметрів (leave-one-year-out, ті самі 48 пар «область × культура × рік»).

Нічого не підганяємо: метрики як є. Варіанти — абляції, щоб видно було, яка зміна що дає.
Калібрування Yx:  A = як baseline v0: max(інших років) / max(rel інших років);
                  B = ТЗ A3: P90 обласної врожайності інших років;
                  C = альтернатива: P90 «потенційного» врожаю obs/rel інших років (для рішення, не підгонка).
  python scripts/validate_step3.py   → reports/step3_validation.md, out/model/step3_validation.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from baseline_model import POINTS  # noqa: E402
from model import simulate as M  # noqa: E402

CROPS = ["winter_wheat", "maize", "sunflower"]
VARIANTS = {
    "нові параметри (повна модель)": {},
    "  без поправки Kc на клімат (рівн. 62/65)": dict(kc_climate=False),
    "  без корекції p (Т22 прим. 2)": dict(p_adjust=False),
    "  Kc голого ґрунту = 0.3 (як v0)": dict(bare_annex7=False),
    "  TAW = 140 мм/м (як v0)": dict(taw_override_mm_m=140.0),
    "  Ky пшениці озимої = 1.05 (чутливість)": dict(ky_override={"winter_wheat": 1.05}),
}


def metrics(v, col):
    err = (v[col] - v.obs).abs() / v.obs
    return dict(MAPE_pct=round(100 * err.mean(), 1), spearman=round(v[col].corr(v.obs, method="spearman"), 2), n=len(v))


def run_variant(opts):
    rows = []
    obs = M.yields()
    for pid in POINTS:
        f = M.field_profile(pid, allow_stubs=True)
        sim = M.SequenceSimulator(f, K=1, allow_stubs=True, **opts)
        for crop in CROPS:
            res, why = sim.run((crop,))
            if res is None:
                raise SystemExit(f"{pid} {crop}: {why}")
            rel = pd.Series(res[0].rel_yield, index=M.YEARS)
            g = obs[(obs.culture == crop) & (obs.oblast == f.oblast_uk)]
            for _, r in g.iterrows():
                others = g[g.year != r.year]
                yxA = others.yield_t_ha.max() / max(rel.loc[others.year].max(), 1e-6)
                yxB = M.yx_p90(crop, f.oblast_uk, exclude_year=r.year)
                yxC = float(np.percentile(others.yield_t_ha.values / np.maximum(rel.loc[others.year].values, 1e-6), 90))
                rows.append(dict(point=pid, crop=crop, oblast=f.oblast_uk, year=r.year, obs=r.yield_t_ha,
                                 rel=round(rel.loc[r.year], 3), predA=yxA * rel.loc[r.year], predB=yxB * rel.loc[r.year], predC=yxC * rel.loc[r.year]))
    return pd.DataFrame(rows)


def main():
    v0 = pd.read_csv(ROOT / "out" / "model" / "validation.csv")
    table = [dict(variant="baseline v0 (out/model/validation.csv)", calib="A", **metrics(v0, "pred_model")),
             dict(variant="кліматологія (середнє інших років)", calib="—", **metrics(v0, "pred_clim")),
             dict(variant="лише опади сезону (регресія)", calib="—", **metrics(v0, "pred_rain"))]
    detail = []
    for name, opts in VARIANTS.items():
        d = run_variant(opts)
        table.append(dict(variant=name, calib="A", **metrics(d, "predA")))
        table.append(dict(variant=name, calib="B (P90, ТЗ)", **metrics(d, "predB")))
        table.append(dict(variant=name, calib="C (P90 obs/rel)", **metrics(d, "predC")))
        detail.append(d.assign(variant=name.strip()))
    T = pd.DataFrame(table)
    D = pd.concat(detail)
    D.to_csv(ROOT / "out" / "model" / "step3_validation.csv", index=False)
    full = D[D.variant == "нові параметри (повна модель)"]
    per_crop = []
    for crop in CROPS:
        a = v0[v0.crop == crop]
        b = full[full.crop == crop]
        per_crop.append(dict(crop=crop, v0_MAPE=metrics(a, "pred_model")["MAPE_pct"], new_MAPE_A=metrics(b, "predA")["MAPE_pct"],
                             new_MAPE_B=metrics(b, "predB")["MAPE_pct"], new_MAPE_C=metrics(b, "predC")["MAPE_pct"], v0_spearman=metrics(a, "pred_model")["spearman"],
                             new_spearman_A=metrics(b, "predA")["spearman"]))
    P = pd.DataFrame(per_crop)
    md = lambda df: "\n".join(["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)] +  # noqa: E731
                              ["| " + " | ".join(str(x) for x in r) + " |" for r in df.itertuples(index=False)])
    rep = ["# Крок 3: baseline v0 проти нових параметрів", "",
           "Leave-one-year-out, ті самі 48 пар «пілот × культура × рік» (Держстат 2015, 2020–2022). Нічого не підганяли.",
           "Калібрування Yx: **A** — як у v0 (max інших років / max їхнього Ya/Yx); **B** — ТЗ A3 (P90 обласної врожайності інших років); **C** — P90 від obs/rel інших років (альтернатива для рішення).",
           "", "## Загальні метрики", "", md(T), "", "## По культурах (повна модель)", "", md(P), "",
           "## Що змінилося відносно v0", "",
           "- Параметри культур: FAO-56 Т11/12/22/24, FAO-66 (Ky пшениці 1.00; Zr — верхня межа, богара).",
           "- TAW: SoilGrids → USDA → FAO-56 Т19 (пілоти: 130–140 мм/м) замість 140 мм/м.",
           "- Kc голого ґрунту з погоди (FAO-56 розд. 11 / Annex 7) замість 0.3; p-корекція; поправка Kc на клімат (рівн. 62/63/65, T2MDEW).",
           "- Старт: профіль на ПВ 1 січня року перед сезоном (v0: 50% TAW за 60 днів до сівби).",
           "- Календар: ті самі заглушки v0 (пшениця, кукурудза, соняшник), довжини фаз кукурудзи — FAO-56 Т11 (Айдахо) замість заглушки v0.",
           "- Погода: вузол POWER (ідентична точці пілота), висота — POWER (клітинка), а не SRTM точки; 29.02 вилучено.",
           "", "## Висновок", "",
           "- Нові параметри з джерелами **не покращили** точність відносно v0 (калібрування A: MAPE 16.5 проти 16.2, Spearman 0.91 проти 0.90) — у межах шуму n = 48.",
           "- Найбільший внесок дає Kc голого ґрунту з погоди: повернення до 0.3 погіршує MAPE (A) на ~2 п.п.",
           "- Калібрування за ТЗ A3 (B: Yx = P90 урожайності) **гірше** (MAPE ~26): P90 фактичних урожаїв уже містить водний стрес, тож Yx·Ya/Yx систематично занижує. Альтернатива C (P90 від obs/rel) — MAPE ~22, теж гірша за A. Це суперечність ТЗ A3 і моделі — потрібне рішення; найкраща на цих даних — A (як у v0).",
           "", "## Рішення (12.11.2026)", "",
           "- **Основне калібрування — A (як v0). Це ВІДХИЛЕННЯ від ТЗ A3** (Yx = P90 обласної врожайності): P90 фактичних урожаїв уже містить водний стрес, тож множення на Ya/Yx занижує прогноз подвійно. Див. docs/decisions.md D1.",
           "- Варіант C лишається у звіті чутливості (найкращий Spearman — для порівняння стратегій важливіший порядок).",
           "", "## Обмеження", "",
           "- n = 48 і лише 4 роки Держстату → різниця в кілька п.п. MAPE статистично не значуща.",
           "- Точка POWER (~50 км) проти середнього по області.",
           ]
    (ROOT / "reports" / "step3_validation.md").write_text("\n".join(rep), encoding="utf-8")
    print(md(T)); print(); print(md(P))


if __name__ == "__main__":
    main()
