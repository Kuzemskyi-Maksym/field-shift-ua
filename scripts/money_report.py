#!/usr/bin/env python3
"""Ефект у грошах (D19/D20) → reports/money.md: «Збалансована» і «Максимум маржі» проти поточної за 4 роки, на поле,
з ефектом насичення соняшником (основне, out/strategies) і без нього (чутливість); меню сценаріїв; портфель вікон.

  python scripts/margin_report.py      # спершу: out/strategies з ефектом
  python scripts/portfolio.py          # site/portfolio.json
  python scripts/money_report.py
"""
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.optimize import OUT, PILOT_FIELDS, optimize_field  # noqa: E402

DST = ROOT / "reports" / "money.md"
NAMES = {"berezivka_od": "Березівка", "arbuzynka_mk": "Арбузинка", "karlivka_pl": "Карлівка", "kalynivka_vn": "Калинівка",
         "volyn:f3735": "Волинь #3735"}
WIN = {"odesa": "Одеська", "mykolaiv": "Миколаївська", "poltava": "Полтавська", "vinnytsia": "Вінницька", "volyn": "Волинська"}


def m(v, sign=True):
    if v is None:
        return "—"
    s = f"{abs(v) / 1e6:.2f}".replace(".", ",")
    return ("−" if v < 0 else "+" if sign and v > 0 else "") + s


def delta_cell(v):
    if not v:
        return "—"
    d = v["delta_vs_current_uah_field"]
    return f"{m(d['p50'])} / {m(d['p10'])} ({'окупається з ' + str(v['breakeven_year']) if v['breakeven_year'] else 'не окупається'})"


def row(f, o):
    st = {s["name"]: s for s in o["strategies"]}
    cur = st.get("current")
    cells = [delta_cell(st[n]["metrics"].get("vs_current")) if n in st else "—" for n in ("balanced", "max_income")]
    cm = cur["metrics"]["money"]["total_field"]["p50"] if cur and cur["metrics"].get("money") else None
    cs = f"{' → '.join(cur['sequence_uk'])} ({cur['metrics']['violations_164']['count']})" if cur else "—"
    return f"| {NAMES[f]} | {o['area_ha']:.1f} | {o['next_season']['crop_uk']} | {cs} | {m(cm, False)} | " + " | ".join(cells) + " |"


def main():
    warnings.filterwarnings("ignore")
    on = {f: json.load(open(OUT / f"strategies_{f.replace(':', '_')}.json", encoding="utf-8")) for f in PILOT_FIELDS}
    assert all(o["ranking"].get("sunflower_return_effect") for o in on.values()), "out/strategies без ефекту — перезапусти margin_report"
    off = {f: optimize_field(f, allow_stubs=True, write=False, sunflower_effect=False) for f in PILOT_FIELDS}
    H = ("| Поле | га | next_season | поточна (порушень №164) | поточна за 4 роки, млн грн P50 | «Збалансована» − поточна, "
         "млн грн P50 / P10 | «Максимум маржі» − поточна, млн грн P50 / P10 |\n|---|---|---|---|---|---|---|")
    mult = []
    for f, o in on.items():
        cur = next((s for s in o["strategies"] if s["name"] == "current"), None)
        if cur:
            mult.append(f"- {NAMES[f]}: {' → '.join(cur['sequence_uk'])} — множники {[y['prev_effect_mult'] for y in cur['per_year']]}; "
                        f"історія: {o['history_branches'][-1]['label']}")
    pre = []
    for f, o in on.items():
        for p in o["presets"]:
            v, tf = p.get("vs_current"), (p.get("money") or {}).get("total_field")
            nums = (f"{m(tf['p10'], False)} / {m(tf['p50'], False)} / {m(tf['p90'], False)} | "
                    f"{m(v['delta_vs_current_uah_field']['p50']) if v else '—'}") if p["status"] == "ok" else "— | —"
            vc = p["violations_164"]["count"]
            pre.append(f"| {NAMES[f]} | {p['name_uk']} | {nums} | {'—' if vc is None else vc} | "
                       + (p["plan_note"] if p["status"] == "ok" else "немає даних: " + "; ".join(p["reasons"])) + " |")
    port = []
    pf = ROOT / "site" / "portfolio.json"
    if pf.exists():
        for ob, w in json.load(open(pf, encoding="utf-8"))["portfolio"]["windows"].items():
            s = w["summary"]
            share = "—" if s["share_viol_164"] is None else f"{100 * s['share_viol_164']:.0f} %"
            port.append(f"| {WIN[ob]} | {s['n_fields']} | {s['n_ok']} | {s['area_ha']:.0f} | {share} | "
                        f"{m(s['potential_p50_uah'])} / {m(s['potential_p10_uah'])} | {s['n_positive_p50']} | "
                        f"{m(s['potential_mi_p50_uah'])} / {m(s['potential_mi_p10_uah'])} | {s['n_positive_mi_p50']} | "
                        f"{s.get('n_mi_new_machinery', '—')} | "
                        f"{m(s['potential_own_p50_uah']) if 'potential_own_p50_uah' in s else '—'} | {s['n_late_winter_current']} |")
    L = ["# Ефект у грошах: стратегії проти поточної практики (D19, D20)", "",
         "_Згенеровано `python scripts/money_report.py`. Різниця за 4 роки плану 2027–2030, грн на поле (площа — полігон NASA Harvest), "
         "P50 і P10 за 25 роками погоди; рахується в кожному році погоди (P50 суми ≠ сума P50). Ціни DSSU_2025, повна собівартість 2025._", "",
         "## Основне: з ефектом насичення сівозміни соняшником (D20)", "",
         "Множник урожаю соняшнику за роками між посівами — Кохан, Лень, Цилюрик (2016), Полтавська ДСГДС, дослід 1999–2016: "
         "×0,80 (0–1 рік), ×0,90 (2 роки), 3–5 років — інтерполяція, ×1,0 (≥ 6). Застосовано до всіх стратегій, поточної, "
         "пресетів і до історії поля з HLS (гілка «можливо соняшник» = соняшник). Для Степу й Полісся — без локального досліду (прапорець).", "",
         H, *[row(f, o) for f, o in on.items()], "",
         "Множники врожаю соняшнику в поточній практиці:", "", *mult, "",
         "## Чутливість: без ефекту (як до D20)", "", H, *[row(f, o) for f, o in off.items()], "",
         "## Як читати", "",
         "- Від'ємна різниця = поточна практика заробляє більше. Це чесний результат моделі; на сайті: «поточна заробляє більше на X грн, "
         "але порушує №164; втрата від хвороб врахована за дослідом Полтавської ДСГДС».",
         "- Ефект зменшує виграш поточної там, де в ній соняшник часто, але не скасовує його.", "",
         "## Меню сценаріїв (з ефектом)", "",
         "| Поле | Сценарій | маржа на полі за 4 роки, млн грн P10 / P50 / P90 | − поточна, P50 | №164 | примітка |",
         "|---|---|---|---|---|---|", *pre, ""]
    if port:
        L += ["## Портфель вікон («Збалансована» − поточна, з ефектом; scripts/portfolio.py)", "",
              "| Вікно | полів з HLS | з результатом | га | поточна порушує №164 | «Збалансована» − поточна, млн грн P50 / P10 | полів з плюсом | "
              "«Максимум маржі» − поточна, млн грн P50 / P10 | полів з плюсом | «Максимум маржі» потребує нової техніки, полів | "
              "«З наявною технікою» − поточна, млн грн P50 | поточна з пізньою озимою |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|", *port, "",
              "Потенціал — сума різниць P50 (P10) полів, не P50 суми: поля вікна мають спільну погоду.",
              "«З наявною технікою» (D27) — найвища маржа серед уже порахованих сівозмін без нової техніки збирання; наявна техніка — "
              "з культур поточної практики за HLS 2021–2025 (`model/machinery.yaml`). Обмеження, а не заборона: техніку можна орендувати.", ""]
        csv = ROOT / "out" / "portfolio" / "portfolio.csv"
        if csv.exists():
            import pandas as pd
            d = pd.read_csv(csv)
            bad = d[d.status != "ok"]
            cal = bad.reason.fillna("").astype(str).str.contains("календар")
            L += [f"**Поля з результатом: {int((d.status == 'ok').sum())} з {len(d)}** (без результату — {len(bad)}, з них календарних "
                  f"{int(cal.sum())}). Поточна практика — спостереження HLS, тож календарем не відсікається (D21): озима після пізньої "
                  "ярої сіється в моделі після збирання попередника (пізніше за рекомендований строк, з прапорцем — урожай поточної "
                  "може бути занижено). Для рекомендацій календарний фільтр лишився.", ""]
    DST.write_text("\n".join(L), encoding="utf-8", newline="\n")
    print(f"ok {DST}")


if __name__ == "__main__":
    main()
