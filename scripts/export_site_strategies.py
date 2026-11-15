#!/usr/bin/env python3
"""strategies_<поле>.json (+ demo_not_sunflower_*.json) → site/strategies.json для сайту (FieldPlan, docs/contracts.md).

Модель і сайт незалежні: скрипт лише читає готові out/strategies/*.json; site/build_site.py підхоплює site/strategies.json,
якщо він є.
  python scripts/export_site_strategies.py
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "out" / "strategies"
DST = ROOT / "site" / "strategies.json"
PILOT_FIELDS = ["berezivka_od", "arbuzynka_mk", "karlivka_pl", "kalynivka_vn", "volyn:f3735"]
DEMO = ["kalynivka_vn", "karlivka_pl"]
NAMES = {"berezivka_od": "Березівка", "arbuzynka_mk": "Арбузинка", "karlivka_pl": "Карлівка", "kalynivka_vn": "Калинівка"}


def model_commit() -> str:
    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    h = git("log", "-1", "--format=%h", "--", "model", "out/strategies")
    dirty = git("status", "--porcelain", "--", "model", "out/strategies")
    return h + ("-dirty" if dirty else "")


def crop_kinds() -> dict:
    """crop_id → winter | spring | legume | fallow (колір смуги Ганта)."""
    c = yaml.safe_load(open(ROOT / "model" / "crops.yaml", encoding="utf-8"))["crops"]
    return {k: "fallow" if v.get("group") == "fallow" else "legume" if v.get("n_fixing") else
            "winter" if v.get("season") == "winter" else "spring" for k, v in c.items()}


KINDS = crop_kinds()
W = yaml.safe_load(open(ROOT / "model" / "optimize.yaml", encoding="utf-8"))["weights"]
SNAME = {"current": "Поточна практика", "max_income": "Максимум маржі", "min_risk": "Мінімум ризику",
         "balanced": "Збалансована", "water": "Вода (степ)", "own_machinery": "З наявною технікою"}
WHY = {"balanced": (f"Найкращий баланс маржі, ризику сухого року, вологи й ґрунту (ваги: маржа {W['income_p50']:g}, "
                    f"ризик {W['income_p10']:g}, вода {W['water']:g}, ґрунт {W['soil']:g} — з optimize.yaml)"),
       "max_income": "Найвища маржа в типовий рік",
       "min_risk": "Найвища маржа в сухий рік (P10)",
       "water": "Найбільший запас вологи на кінець ротації при прийнятній маржі в сухий рік",
       "current": "Що росло на полі за HLS — точка порівняння",
       "own_machinery": ("Найвища маржа в типовий рік серед сівозмін, для яких не потрібна нова техніка збирання "
                         "(наявна — з того, що росло на полі за HLS 2021–2025). Це обмеження, а не заборона: "
                         "техніку можна взяти в оренду або замовити послугу збирання")}
# групи прапорців; порядок перевірки: норматив → календар → ціни й витрати → решта = дані
GROUPS = [("норматив", ("№164", "попередник", "частка «", "повертається", "соняшнику не було", "кукурудза → пшениця",
                        "бобові після", "історія поля", "поточна", "підтвердіть", "не нормує")),
          ("календар", ("STUB", "календар", "довжини фаз", "stages_days", "дата", "сівб")),
          ("ціни й витрати", ("ціна", "ціну", "витрат", "собівартість", "рентабельн", "УВАГА", "маржа", "логістик", "канал",
                              "базис", "середнє по", "fcr", "корм", "пар"))]


def k(v) -> str:
    return "—" if v is None else f"{v / 1000:.1f}".replace(".", ",").replace("-", "−")


def human_benefits(benefits: list, m: dict, cur_m: dict | None) -> list:
    """Рядок моделі «‹одиниці› P50 ±N до поточної» → «Маржа в типовий рік (P50): ±X тис. грн/га до поточної»."""
    out = [b for b in benefits if not (b.startswith("«") and "до поточної" in b)]
    if cur_m and m.get("margin_p50") is not None and cur_m.get("margin_p50") is not None:
        d = m["margin_p50"] - cur_m["margin_p50"]
        out.insert(0, f"маржа в типовий рік (P50): {'+' if d >= 0 else ''}{k(d)} тис. грн/га/рік до поточної")
    return out


def gap_groups(gaps: list) -> list:
    out = {g: [] for g, _ in GROUPS} | {"дані": []}
    for x in dict.fromkeys(gaps):
        low = x.lower()
        out[next((g for g, keys in GROUPS if any(kw.lower() in low for kw in keys)), "дані")].append(x)
    return [dict(group=g, items=v) for g, v in out.items() if v]


def money_site(mb: dict | None) -> dict | None:
    """Ефект у грошах: накопичена маржа на полі по роках [сезон, P10, P50, P90] і підсумок за план."""
    if not mb:
        return None
    t3 = lambda d: None if d is None else [d["p10"], d["p50"], d["p90"]]   # noqa: E731
    return dict(years=[[y["season"], *(t3(y["cumulative_field"]) or [None] * 3)] for y in mb["years"]],
                year_ha=[[y["season"], *t3(y["margin_ha"])] for y in mb["years"]],
                total_field=t3(mb["total_field"]), total_ha=t3(mb["total_ha"]), fallow_nc=mb["excludes_fallow_cost"])


def vs_site(v: dict | None) -> dict | None:
    if not v:
        return None
    return dict(d_field=v["delta_vs_current_uah_field"], d_ha=v["delta_vs_current_uah_ha"],
                years=[[y["season"], y["cum_delta_field_p50"], y["delta_ha_p50"]] for y in v["years"]],
                drawdown=v["drawdown_year"], drawdowns=v["drawdown_years"], breakeven=v["breakeven_year"],
                cur_viol=v["current_violates_164"])


def preset_site(p: dict) -> dict:
    m = p.get("metrics") or {}
    return dict(id=p["id"], name=p["name_uk"], seq=p["sequence_uk"], rotation_n=len(p["rotation"]), plan_note=p["plan_note"],
                status=p["status"], reasons=p["reasons"], viol=p["violations_164"]["count"], viol_list=p["violations_164"]["list"],
                moist=m.get("end_moisture_frac"), m=[m.get("margin_p10"), m.get("margin_p50"), m.get("margin_p90")] if m else None,
                money=money_site(p.get("money")), vs=vs_site(p.get("vs_current")))


def binding(field_id: str) -> tuple[str, int]:
    """→ (window = ключ вікна сайту = область, fid NASA Harvest)."""
    if ":" in field_id:
        ob, f = field_id.split(":")
        return ob, int(f.lstrip("f"))
    z = yaml.safe_load(open(ROOT / "model" / "zones.yaml", encoding="utf-8"))["pilots"][field_id]
    return z["oblast"], int(z["fid"])


def field_plan(o: dict, commit: str) -> dict:
    window, fid = binding(o["field_id"])
    cur_m = next((x["metrics"] for x in o["strategies"] if x["name"] == "current"), None)
    S = []
    for s in o["strategies"]:
        m, ex = s["metrics"], s["explain"]
        st = dict(name=s["name"], seq=s["sequence_uk"], crops=s["sequence"], conf=s["confidence"],
                  m=dict(m50=m["margin_p50"], m10=m["margin_p10"], m90=m.get("margin_p90"), i50=m["income_p50"], i10=m["income_p10"],
                         deficit=m["water_deficit_mm"], moist=m["end_moisture_frac"], legume=m["legume_share"],
                         bare=m["bare_days"], drying=m["drying_share"], viol=m["violations_164"]["count"],
                         fallow_nc=m.get("margin_excludes_fallow_cost", False)),
                  years=[dict(crop=y["crop_uk"], crop_id=y["crop"], season=y["season"], y=y["yield_t_ha"],
                              price=y["channel"]["net_price_uah_t"], cost=y["cost_uah_ha"], margin=y["margin_uah_ha"])
                         for y in s["per_year"]],
                  cal=[dict(year=c["year"], crop=c["crop"], kind=KINDS.get(c["crop"], "spring"), sow=c["sow"], harvest=c["harvest"],
                            sow_date=c.get("sow_date"), harvest_date=c.get("harvest_date"), bare=c["bare"],
                            stub=c["stub"], **({"sow_range": c["sow_range"], "harvest_range": c["harvest_range"]}
                                               if c.get("sow_range") else {})) for c in s["calendar"]],
                  why=(f"{WHY.get(s['name'], ex['why'])}. Маржа: P10 {k(m['margin_p10'])} / P50 {k(m['margin_p50'])} / "
                       f"P90 {k(m.get('margin_p90'))} тис. грн/га/рік." if m["margin_p50"] is not None
                       else f"{WHY.get(s['name'], ex['why'])}."),
                  benefits=human_benefits(ex["benefits"], m, cur_m), gap_groups=gap_groups(ex["gaps"]),
                  climate_risk=next((g for g in ex["gaps"][:1] if g.startswith("маржа близька до нуля")), None),
                  prof=ex.get("profitability", []))
        st["money"] = money_site(m.get("money"))
        st["vs"] = vs_site(m.get("vs_current"))
        if m["violations_164"]["count"]:
            st["violations"] = m["violations_164"]["list"]
        if "why_not_repeat" in ex:
            st["why_not_repeat"] = ex["why_not_repeat"]
        if s["name"] == "current":
            st["assumption"] = s.get("assumption")
        if s.get("machinery"):                                   # D27: бейдж техніки (без сирих id груп)
            mc = s["machinery"]
            st["mach"] = dict(new=mc["new_uk"], text=mc["text"], owned_flags=mc["owned_flags"], note=mc["note"])
        S.append(st)
    first = o["strategies"][0]["explain"] if o["strategies"] else {}
    r = o["ranking"]
    nx = dict(o["next_season"])
    bal = next((x for x in S if x["name"] == "balanced"), None)
    if bal and nx.get("crop"):
        nx["why"] = f"Перший рік стратегії «{SNAME['balanced']}» ({' → '.join(bal['seq'])}). {WHY['balanced']}."
        nx["margin_y1"] = bal["years"][0]["margin"]
    return dict(id=o["field_id"], window=window, fid=fid,
                name_uk=NAMES.get(o["field_id"], f"{o['oblast']} · поле #{fid}"),
                oblast=o["oblast"], zone=o["zone"], area_ha=o["area_ha"], next=nx,
                history=[[h["year"], h["c"], h["sub"], h["confirmed_crop"]] for h in o["history"]],
                history_confirmed=o.get("history_confirmed", {}),
                history_src=o.get("history_source"),
                strategies=S, presets=[preset_site(p) for p in o.get("presets", [])], data=first.get("data", []),
                agronomist=first.get("agronomist_check", []),
                no_data=[d["crop_uk"] for d in o["candidates_without_data"]],
                run=dict(prices_snapshot=r["prices_snapshot"], cost_column=r["cost_column"], cost_year=r["cost_year"],
                         ranking_mode=r["mode"], ranking_label=r["label"] or r["unit"], model_commit=commit,
                         sf_effect=bool(r.get("sunflower_return_effect")),
                         plan_start_year=o["run"]["plan_start_year"], plan_years=o["run"]["plan_years"],
                         why_model={x["name"]: x["explain"]["why"] for x in o["strategies"]},      # сирий текст моделі (журі)
                         next_why_model=o["next_season"]["why"]))


ID_KEYS = {"id", "window", "crop", "crops", "crop_id", "kind", "name", "season", "sow", "harvest", "sow_date", "harvest_date",
           "cost_column", "ranking_mode", "model_commit", "prices_snapshot", "why_model", "next_why_model", "metric",
           "compare_with", "status", "group", "history", "history_confirmed"}


def humanize(o, key=None):
    """Видимий текст сайту — без crop_id і списків Python (scripts/human_text.py); поля-ідентифікатори не чіпаємо."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from human_text import human
    if key in ID_KEYS:
        return o
    if isinstance(o, dict):
        return {k: humanize(v, k) for k, v in o.items()}
    if isinstance(o, list):
        return [humanize(v, key) for v in o]
    return human(o)


def main():
    commit = model_commit()
    load = lambda p: json.load(open(p, encoding="utf-8"))  # noqa: E731
    plans = {f: field_plan(load(SRC / f"strategies_{f.replace(':', '_')}.json"), commit) for f in PILOT_FIELDS}
    demo = {f: field_plan(load(SRC / f"demo_not_sunflower_{f}.json"), commit) for f in DEMO
            if (SRC / f"demo_not_sunflower_{f}.json").exists()}
    plans, demo = humanize(plans), humanize(demo)
    DST.write_text(json.dumps(dict(strategies=plans, strategies_demo=demo), ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"ok {DST} {DST.stat().st_size // 1024} КБ; полів {len(plans)}, демо {len(demo)}; model_commit {commit}")


if __name__ == "__main__":
    sys.exit(main())
