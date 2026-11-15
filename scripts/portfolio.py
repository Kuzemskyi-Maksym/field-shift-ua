#!/usr/bin/env python3
"""Портфель вікна: оптимізатор (без змін) для всіх полів з HLS у 5 вікнах → site/portfolio.json, out/portfolio/portfolio.csv.

Поля — out/hls/<вікно>_ndvi_seasons.csv (50 найбільших полів вікна + пілот), id «<вікно>:f<fid>» (як volyn:f3735):
межі/площа — out/fields/<вікно>_fields_stats.csv, ґрунт — data/raw/soil, погода — вузол POWER поля. Поле, де оптимізатор
не дає результату (немає ґрунту, поточної, цін…) — status no_data з причиною (на карті — сіре).

  python scripts/portfolio.py --estimate 10       # час на N полів → оцінка повного прогону
  python scripts/portfolio.py --workers 10        # повний прогін
"""
import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
WINDOWS = ["odesa", "mykolaiv", "poltava", "vinnytsia", "volyn"]
OUT = ROOT / "out" / "portfolio"
SITE = ROOT / "site" / "portfolio.json"


def field_ids():
    ids = []
    for ob in WINDOWS:
        d = pd.read_csv(ROOT / "out" / "hls" / f"{ob}_ndvi_seasons.csv", usecols=["field"])
        ids += [f"{ob}:{f}" for f in sorted(d.field.unique())]
    return ids


def run_one(fid: str) -> dict:
    import warnings
    warnings.filterwarnings("ignore")
    from model import optimize as O
    ob, f = fid.split(":")
    rec = dict(id=fid, window=ob, fid=int(f.lstrip("f")))
    t = time.time()
    try:
        pil = {f"{v['oblast']}:f{v['fid']}": k for k, v in O.M._zones()["pilots"].items()}
        rec["model_id"] = pil.get(fid, fid)      # пілот — той самий розрахунок, що в #plan (точка, ґрунт, HLS поля)
        o = O.optimize_field(rec["model_id"], allow_stubs=True, write=False)
    except Exception as e:                                       # немає ґрунту / профілю тощо — причина, не підстановка
        rec.update(status="no_data", reason=f"{type(e).__name__}: {str(e)[:200]}", seconds=round(time.time() - t, 1),
                   trace=traceback.format_exc(limit=2)[-400:])
        return rec
    st = {s["name"]: s for s in o["strategies"]}
    bal, cur, mi = st.get("balanced"), st.get("current"), st.get("max_income")
    own = st.get("own_machinery")                                # D27: з наявною технікою (нові колонки, старі не змінюються)
    vown = own["metrics"].get("vs_current") if own else None
    down = vown["delta_vs_current_uah_field"] if vown else None
    rec.update(own_uk=own["sequence_uk"] if own else None,
               own_p50_field=down["p50"] if down else None, own_p10_field=down["p10"] if down else None,
               bal_new_machinery=", ".join(bal["machinery"]["new_uk"]) if bal and bal.get("machinery") else None,
               mi_new_machinery=", ".join(mi["machinery"]["new_uk"]) if mi and mi.get("machinery") else None)
    vs = bal["metrics"].get("vs_current") if bal else None
    vmi = mi["metrics"].get("vs_current") if mi else None
    dmi = vmi["delta_vs_current_uah_field"] if vmi else None
    reasons = []
    if not bal:
        reasons.append(o["next_season"]["why"])
    if not cur:
        g = [x for s in o["strategies"][:1] for x in s["explain"]["gaps"]
             if x.startswith("поточна (") or x.startswith("поточну стратегію не визначено")]
        reasons.append("поточну практику з HLS не оцінено" + (": " + "; ".join(g)[:300] if g else ""))
    late = [x for x in (cur["explain"]["gaps"] if cur else []) if x.startswith("фактична практика")]
    if bal and cur and not vs:
        reasons.append("різницю з поточною не пораховано (немає маржі)")
    df = vs["delta_vs_current_uah_field"] if vs else None
    from human_text import human                               # сайт: crop_uk замість id і списків Python
    late = [human(x) for x in late]
    rec.update(status="ok" if (bal and df) else "partial" if bal else "no_data", reason=human("; ".join(reasons)) or None,
               area_ha=o["area_ha"], zone=o["zone"], mode=o["ranking"]["mode"],
               next_season=o["next_season"]["crop"], next_season_uk=o["next_season"]["crop_uk"],
               balanced=bal["sequence"] if bal else None, balanced_uk=bal["sequence_uk"] if bal else None,
               current=cur["sequence"] if cur else None, current_uk=cur["sequence_uk"] if cur else None,
               current_late_winter=late[0] if late else None,
               mi_uk=mi["sequence_uk"] if mi else None,
               mi_p50_field=dmi["p50"] if dmi else None, mi_p10_field=dmi["p10"] if dmi else None,
               mi_breakeven_year=vmi["breakeven_year"] if vmi else None,
               delta_p50_field=df["p50"] if df else None, delta_p10_field=df["p10"] if df else None,
               delta_p50_ha=vs["delta_vs_current_uah_ha"]["p50"] if vs else None,
               breakeven_year=vs["breakeven_year"] if vs else None, drawdown_year=vs["drawdown_year"] if vs else None,
               violations_164_now=cur["metrics"]["violations_164"]["count"] if cur else None,
               conf=bal["confidence"] if bal else None, seconds=round(time.time() - t, 1))
    return rec


def summary(recs):
    out = {}
    for ob in WINDOWS:
        r = [x for x in recs if x["window"] == ob]
        ok = [x for x in r if x["status"] == "ok"]
        cur = [x for x in r if x.get("violations_164_now") is not None]
        out[ob] = dict(n_fields=len(r), n_ok=len(ok), n_no_data=len(r) - len(ok),
                       area_ha=round(sum(x.get("area_ha") or 0 for x in r), 1), area_ok_ha=round(sum(x["area_ha"] for x in ok), 1),
                       n_with_current=len(cur),
                       share_viol_164=round(sum(x["violations_164_now"] > 0 for x in cur) / len(cur), 3) if cur else None,
                       potential_p50_uah=sum(x["delta_p50_field"] for x in ok), potential_p10_uah=sum(x["delta_p10_field"] for x in ok),
                       n_positive_p50=sum(x["delta_p50_field"] > 0 for x in ok),
                       potential_mi_p50_uah=sum(x["mi_p50_field"] for x in ok if x.get("mi_p50_field") is not None),
                       potential_mi_p10_uah=sum(x["mi_p10_field"] for x in ok if x.get("mi_p10_field") is not None),
                       n_positive_mi_p50=sum((x.get("mi_p50_field") or 0) > 0 for x in ok),
                       potential_own_p50_uah=sum(x["own_p50_field"] for x in ok if x.get("own_p50_field") is not None),
                       n_own=sum(x.get("own_p50_field") is not None for x in ok),
                       n_mi_new_machinery=sum(bool(x.get("mi_new_machinery")) for x in ok),
                       n_late_winter_current=sum(bool(x.get("current_late_winter")) for x in ok),
                       next_season_counts={k: int(v) for k, v in pd.Series([x["next_season_uk"] for x in r if x.get("next_season_uk")],
                                                                           dtype=object).value_counts().items()})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--estimate", type=int, default=0, help="прогнати N полів (по вікнах) і оцінити повний час")
    ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()
    ids = field_ids()
    if a.estimate:
        sample = [ids[i] for i in range(0, len(ids), max(1, len(ids) // a.estimate))][:a.estimate]
        t = time.time()
        with ProcessPoolExecutor(min(a.workers, len(sample))) as ex:
            recs = list(ex.map(run_one, sample))
        wall = time.time() - t
        per = [r["seconds"] for r in recs]
        print(f"полів усього: {len(ids)}; проба {len(sample)} полів паралельно ({min(a.workers, len(sample))} процесів) "
              f"за {wall:.0f} с; {sum(per) / len(per):.1f} с/поле в процесі")
        for r in recs:
            print(f"  {r['id']}: {r['status']} {r.get('next_season_uk')} Δ50={r.get('delta_p50_field')} {r.get('seconds')} с {r.get('reason') or ''}")
        print(f"оцінка повного прогону: ≈ {len(ids) / len(sample) * wall / 60:.0f} хв при {a.workers} процесах "
              f"(послідовно ≈ {len(ids) * sum(per) / len(per) / 60:.0f} хв)")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    t, recs = time.time(), []
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(run_one, f) for f in ids]
        for i, fu in enumerate(as_completed(futs), 1):
            recs.append(fu.result())
            if i % 25 == 0:
                print(f"{i}/{len(ids)} за {time.time() - t:.0f} с", flush=True)
    recs.sort(key=lambda r: (WINDOWS.index(r["window"]), r["fid"]))
    pd.DataFrame([{k: v for k, v in r.items() if k != "trace"} for r in recs]).to_csv(OUT / "portfolio.csv", index=False)
    S = summary(recs)
    keep = ("status", "reason", "area_ha", "next_season", "next_season_uk", "balanced_uk", "delta_p50_field", "delta_p10_field",
            "delta_p50_ha", "breakeven_year", "violations_164_now", "conf", "current_uk", "current_late_winter", "mi_uk",
            "mi_p50_field", "mi_p10_field", "mi_breakeven_year",
            "own_uk", "own_p50_field", "own_p10_field", "bal_new_machinery", "mi_new_machinery")
    site = {ob: dict(summary=S[ob], fields={str(r["fid"]): {k: r.get(k) for k in keep} for r in recs if r["window"] == ob})
            for ob in WINDOWS}
    SITE.write_text(json.dumps(dict(portfolio=dict(windows=site, plan_start_year=2027,
                                                   note="різниця balanced − поточна за 4 роки, грн на поле (P50 і P10 за 25 роками "
                                                        "погоди); сума по вікну — сума P50 полів, не P50 суми (поля вікна мають спільну погоду)")),
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"ok {len(recs)} полів за {(time.time() - t) / 60:.1f} хв → {SITE}")
    for ob in WINDOWS:
        print(ob, {k: v for k, v in S[ob].items() if k != "next_season_counts"})


if __name__ == "__main__":
    main()
