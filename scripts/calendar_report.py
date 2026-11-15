#!/usr/bin/env python3
"""Календар сівби (D17): перевірки без підгонки → reports/calendar.md.

  1. ярі: динамічна дата сівби (TSOIL1 ≥ поріг, 5-денна середня) — медіана / P10–P90 по 25 роках для кожного поля;
     T2M як проксі — лише для порівняння; кукурудза й соя в Лісостепу/Поліссі — чи потрапляє медіана у явне вікно джерела;
  2. збирання ярих = сівба + Σ фаз FAO-56 Т11 проти HLS senes (S early/late) по областях і зонах, допуск ±15 днів;
  3. озимі: фази з HLS (stage_dates) і чутливість до вікна сівби (Ya/Yx пшениці, один сезон);
  4. соя → озима пшениця: у скількох роках збирання сої не встигає до сівби пшениці;
  5. до / після: next_season, 3 стратегії, маржа, confidence (до = out/strategies у коміті BEFORE_REV).

  python scripts/calendar_report.py            # пише reports/calendar.md
"""
import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model import crops as C  # noqa: E402
from model import simulate as M  # noqa: E402
from model.optimize import OUT, PILOT_FIELDS  # noqa: E402

BEFORE_REV = "ab4d72d"          # останній коміт out/strategies до D17 (календар BASELINE_V0/STUB)
DST = ROOT / "reports" / "calendar.md"
NAMES = {"berezivka_od": "Березівка", "arbuzynka_mk": "Арбузинка", "karlivka_pl": "Карлівка", "kalynivka_vn": "Калинівка",
         "volyn:f3735": "Волинь #3735"}
SPRING = ["maize", "soybean", "sunflower", "spring_wheat", "pea"]
HLS_SUB = {"maize": "late", "soybean": "late", "sunflower": "early", "spring_wheat": "early", "pea": "early"}
TOL = 15
HLS_YEARS = list(range(2016, 2026))


def md(d) -> str:
    return (dt.date(2001, 1, 1) + dt.timedelta(days=int(round(float(d))))).strftime("%d.%m")


def dm(s: str) -> str:
    return f"{s[3:]}.{s[:2]}"


def doy(s: str) -> int:
    return M.doy0(s)


def t2m(node):
    f = M.POWER_DIR / f"tsoil_{node[0]:.3f}_{node[1]:.3f}.csv"
    df = pd.read_csv(f, parse_dates=["date"], index_col="date")
    df = df[~((df.index.month == 2) & (df.index.day == 29))]
    return np.stack([df.T2M[df.index.year == y].values for y in M.YEARS])


def sow_table(fields):
    rows, out, checks = [], {}, []
    for f in fields:
        fld = M.field_profile(f, True)
        crops = C.ready_crops(fld.zone, True)
        temp, proxy = M.load_tsoil(*fld.node)
        air = t2m(fld.node)
        for c in SPRING:
            r = crops[c]["sow_rule"]
            d, _ = M.dynamic_sow_doy(temp, r["threshold_c"], r["not_before"], r["mean_days"])
            a, _ = M.dynamic_sow_doy(air, r["threshold_c"], r["not_before"], r["mean_days"])
            out[(f, c)] = d
            win = r.get("check_window") or {}
            chk = "—"
            if fld.zone in win.get("zones", []):
                lo, hi = map(doy, win["window"])
                ts, ta = lo <= np.median(d) <= hi, lo <= np.median(a) <= hi
                checks.append((f, c, ts, ta))
                chk = f"{dm(win['window'][0])}–{dm(win['window'][1])}: TSOIL1 {'✓' if ts else '✗'}, T2M {'✓' if ta else '✗'}"
            rows.append(f"| {NAMES[f]} | {fld.zone} | {crops[c]['name_uk']} | {r['threshold_c']:g} | **{md(np.median(d))}** | "
                        f"{md(np.percentile(d, 10))}–{md(np.percentile(d, 90))} | {md(np.median(a))} | {chk} |"
                        + (" ⚠ проксі T2M" if proxy else ""))
    return rows, out, checks


def soy_threshold_sens(fields):
    rows = []
    for f in fields:
        fld = M.field_profile(f, True)
        temp, _ = M.load_tsoil(*fld.node)
        v = [md(np.median(M.dynamic_sow_doy(temp, t, "03-01", 5)[0])) for t in (8, 10, 12, 14)]
        rows.append(f"| {NAMES[f]} | " + " | ".join(v) + " |")
    return rows


def harvest_table(fields, sows):
    hls = pd.read_csv(ROOT / "data" / "raw" / "hls_phenology_by_oblast.csv")
    names = C.load_yaml()["crops"]
    rows, zone_acc = [], {}
    idx = [M.YEARS.index(y) for y in HLS_YEARS]
    for f in fields:
        fld = M.field_profile(f, True)
        crops = C.ready_crops(fld.zone, True)
        for c in SPRING:
            hv = sows[(f, c)][idx] + sum(crops[c]["stages_days"])
            h = hls[(hls.oblast == fld.oblast) & (hls.cls == "S") & (hls.subtype == HLS_SUB[c])].iloc[0]
            s_med, s25, s75 = doy(h.senes_median), doy(h.senes_p25), doy(h.senes_p75)
            diff = float(np.median(hv)) - s_med
            zone_acc.setdefault((fld.zone, c), []).append(hv)
            rows.append(f"| {NAMES[f]} ({fld.oblast}) | {names[c]['name_uk']} | S {HLS_SUB[c]} | {md(np.median(hv))} | "
                        f"{md(s_med)} ({md(s25)}–{md(s75)}, n={h.n_field_years}) | {diff:+.0f} | {'✓' if abs(diff) <= TOL else '✗'} |")
    zrows = []
    for (z, c), lst in zone_acc.items():
        hv = np.concatenate(lst)
        hz = hls[(hls.zone == z) & (hls.cls == "S") & (hls.subtype == HLS_SUB[c])]
        s = math.floor(hz.senes_median.map(doy).median() + 0.5)
        diff = float(np.median(hv)) - s
        zrows.append(f"| {z} | {names[c]['name_uk']} | S {HLS_SUB[c]} | {md(np.median(hv))} | {md(s)} "
                     f"({', '.join(sorted(hz.oblast))}) | {diff:+.0f} | {'✓' if abs(diff) <= TOL else '✗'} |")
    return rows, zrows


def winter_tables(fields):
    doc = C.load_yaml()
    st = []
    for z in ("steppe", "forest_steppe", "polissia"):
        cal = doc["crops"]["winter_wheat"]["calendar"][z]
        st.append(f"| {z} | {dm(cal['sow'])} ({cal['src']}, с. {cal['page']}) | {dm(cal['window'][0])}–{dm(cal['window'][1])} | "
                  + " | ".join(dm(d) for d in cal["stage_dates"]) + " |")
    sens = []
    for f in fields:
        fld = M.field_profile(f, True)
        cal = doc["crops"]["winter_wheat"]["calendar"][fld.zone]
        cells = []
        for s in (cal["window"][0], cal["sow"], cal["window"][1]):
            sim = M.SequenceSimulator(fld, K=1, allow_stubs=True)          # новий симулятор: кеш сезону не знає дати сівби
            sim.crops["winter_wheat"] = dict(sim.crops["winter_wheat"], calendar=dict(cal, sow=s))
            res, _ = sim.run(("winter_wheat",))
            r = res[0].rel_yield
            cells.append(f"{np.percentile(r, 50):.2f} / {np.percentile(r, 10):.2f}")
        sens.append(f"| {NAMES[f]} | " + " | ".join(cells) + " |")
    return st, sens


def soy_wheat(fields, sows):
    doc = C.load_yaml()
    rows = []
    for f in fields:
        fld = M.field_profile(f, True)
        crops = C.ready_crops(fld.zone, True)
        hv = sows[(f, "soybean")] + sum(crops["soybean"]["stages_days"])
        cal = doc["crops"]["winter_wheat"]["calendar"][fld.zone]
        ws, we = doy(cal["sow"]), doy(cal["window"][1])
        rows.append(f"| {NAMES[f]} | {md(np.median(hv))} ({md(hv.min())}–{md(hv.max())}) | {md(ws)} | "
                    f"{int((hv >= ws).sum())} з 25 | {int((hv >= we).sum())} з 25 |")
    return rows


def load_before(f):
    p = f"out/strategies/strategies_{f.replace(':', '_')}.json"
    r = subprocess.run(["git", "show", f"{BEFORE_REV}:{p}"], cwd=ROOT, capture_output=True)
    return json.loads(r.stdout.decode("utf-8"))


def k(v):
    return "—" if v is None else f"{v / 1000:.1f}".replace("-", "−")


def before_after(fields):
    rows = []
    for f in fields:
        a = load_before(f)
        b = json.load(open(OUT / f"strategies_{f.replace(':', '_')}.json", encoding="utf-8"))
        for tag, o in (("до", a), ("після", b)):
            st = {s["name"]: s for s in o["strategies"]}

            def cell(n):
                s = st.get(n)
                if not s:
                    return "—"
                m = s["metrics"]
                return f"{' → '.join(s['sequence_uk'])}<br>P50 {k(m['margin_p50'])} / P10 {k(m['margin_p10'])} · {s['confidence']}"
            rows.append(f"| {NAMES[f] if tag == 'до' else ''} | {tag} | **{o['next_season']['crop_uk']}** | "
                        + " | ".join(cell(n) for n in ("max_income", "min_risk", "balanced"))
                        + f" | {o['run'].get('n_calendar_pruned', '—')} |")
    return rows


def main():
    fields = PILOT_FIELDS
    srows, sows, checks = sow_table(fields)
    hrows, zrows = harvest_table(fields, sows)
    wst, wsens = winter_tables(fields)
    meta = json.load(open(M.POWER_DIR / "tsoil_47.000_30.625.meta.json", encoding="utf-8"))
    ok_ts = all(c[2] for c in checks)
    ok_ta = all(c[3] for c in checks)
    miss_ta = sorted({f"{NAMES[f]}: {c}" for f, c, _, ta in checks if not ta})
    L = ["# Календар сівби (D17): джерела, динамічна сівба ярих, перевірка проти HLS", "",
         "_Згенеровано `python scripts/calendar_report.py`. Пороги, вікна й фази — з `data/raw/calendar_sources.yaml` і "
         "`data/raw/hls_phenology_by_oblast.csv`; нічого не підганялось під HLS чи вікна._", "",
         "## 1. Температура ґрунту в POWER", "",
         f"Є: `TSOIL1` (community=AG, daily) — «{meta['definition'].split(': ', 1)[1]}», джерело {', '.join(meta.get('sources') or [])}. "
         "Шар 1,8–9,9 см відповідає «глибині 10 см / загортання насіння» з джерел, тому **проксі T2M не використовується** "
         "(лишається запасним шляхом із прапорцем, якщо для вузла немає `tsoil_*.csv`). Завантажено для 5 вузлів полів: "
         "`python scripts/fetch_power.py --tsoil --node <lat> <lon>`.", "",
         "## 2. Динамічна дата сівби ярих (25 років погоди 2001–2025)", "",
         "Правило: перший день ≥ 01.03, коли 5-денна ковзна середня TSOIL1 ≥ порогу. Колонка T2M — та сама процедура на "
         "температурі повітря (лише для перевірки проксі).", "",
         "| Поле | Зона | Культура | Поріг, °C | Медіана TSOIL1 | P10–P90 | Медіана T2M | Явне вікно джерела |",
         "|---|---|---|---|---|---|---|---|", *srows, "",
         f"**Перевірка (кукурудза, соя; Лісостеп і Полісся):** медіана за TSOIL1 {'потрапляє' if ok_ts else '**не потрапляє**'} "
         "у явні вікна джерел (кукурудза 25.04–05.05, соя 25.04–10.05) "
         + ("на всіх трьох полях. " if ok_ts else "— див. ✗ у таблиці. ")
         + ("Проксі T2M теж потрапив би." if ok_ta else
            f"Проксі T2M дав би сівбу раніше і не потрапив би у вікно ({'; '.join(miss_ta)}) — ще одна причина брати TSOIL1."), "",
         "Чутливість сої до порогу (джерела: 8–10 °C ІСГП, 12–14 °C Юр'єва), медіана дати сівби:", "",
         "| Поле | 8 °C | 10 °C (модель) | 12 °C | 14 °C |", "|---|---|---|---|---|", *soy_threshold_sens(fields), "",
         "## 3. Збирання ярих = сівба + Σ фаз FAO-56 Т11 проти HLS senes", "",
         f"Модель — медіана за роками погоди {HLS_YEARS[0]}–{HLS_YEARS[-1]} (як період HLS); HLS senes = перша дата NDVI<0,35 "
         "після піку (≈ дозрівання). Відповідність культур підтипам HLS (early/late) — з коментаря calendar_sources.yaml "
         f"(«кукурудза/соя?», «соняшник/ярі зернові?»), тобто сама — припущення. Допуск ±{TOL} днів.", "",
         "| Поле (область) | Культура | HLS | Збирання моделі | HLS senes (P25–P75) | Δ, дні | ±15 |",
         "|---|---|---|---|---|---|---|", *hrows, "",
         "По зонах (модель — медіана всіх поле-років зони; HLS — медіана медіан областей):", "",
         "| Зона | Культура | HLS | Збирання моделі | HLS senes | Δ, дні | ±15 |", "|---|---|---|---|---|---|---|", *zrows, "",
         "**Без підгонки.** Дата сівби тепер з джерел і погоди, а довжина сезону — та сама сума фаз FAO-56 Т11 (регіони "
         "США/Середземномор'я); тому розбіжність зі спадом NDVI — це питання довжин фаз, не сівби. NDVI<0,35 — дозрівання, "
         "а не збирання: для кукурудзи з досушуванням у полі (Kc_end 0,35, прим. 11) збирання моделі пізніше за спад NDVI очікувано. "
         "Довжини фаз не змінювали — це окреме рішення (українські довжини фаз або калібрування за HLS).", "",
         "## 4. Озимі: сівба з джерел, фази з HLS", "",
         "stage_dates = [greenup, peak, senes − 25 д, senes] (клас W, медіана медіан областей зони); 25 д — L_late FAO-56 Т11 "
         "Winter Wheat (NDVI не дає початку дозрівання). Прапорець у стратегіях з озимими: «фази озимих з NDVI полів».", "",
         "| Зона | Сівба (opt, джерело) | Вікно | кінець ini | кінець dev | кінець mid | кінець late |", "|---|---|---|---|---|---|---|",
         *wst, "", "Було (BASELINE_V0, усі зони): сівба 01.10; фази 15.03 / 25.04 / 10.06 / 10.07.", "",
         "Чутливість до вікна сівби — Ya/Yx озимої пшениці (один сезон, P50 / P10 по 25 роках), сівба на початку / opt / в кінці вікна:", "",
         "| Поле | початок вікна | opt | кінець вікна |", "|---|---|---|---|", *wsens, "",
         "Фази задані датами, тож дата сівби змінює лише довжину осіннього ini-періоду; агрономічний ефект строку сівби "
         "(перезимівля, кущіння) моделлю не описується.", "",
         "## 5. Соя → озима пшениця", "",
         "Сівба озимих після збирання попередника перевіряється **в кожному з 25 років погоди** (інакше водний баланс "
         "накладав би дві культури). Соя: сівба за TSOIL1 ≥ 10 °C + 137 д фаз FAO-56 (Soybeans, May, Central USA).", "",
         "| Поле | Збирання сої: медіана (мін–макс) | Сівба пшениці (opt) | Років, коли соя пізніше opt | … пізніше кінця вікна |",
         "|---|---|---|---|---|", *soy_wheat(fields, sows), "",
         "Де соя не встигає хоча б в одному році, «соя → озима пшениця» відсікається календарем. Причина — довжина фаз сої "
         "FAO-56 (137 д, США), а не дата сівби. **Питання до агронома:** ранньостиглі сорти сої (00–0) збирають у вересні; "
         "якщо ця ланка потрібна — потрібні українські довжини фаз сої (не підганяли).", "",
         "## 6. До / після (основний варіант: DSSU_2025, повна собівартість 2025)", "",
         f"«До» — `out/strategies` у коміті `{BEFORE_REV}` (календар BASELINE_V0/STUB_NO_SOURCE); «після» — поточний розрахунок. "
         "Клітинка: послідовність; маржа P50 / P10, тис. грн/га/рік; confidence. Останній стовпець — послідовностей, відсічених календарем.", "",
         "| Поле | | next_season | max_income | min_risk | balanced | відсічено календарем |", "|---|---|---|---|---|---|---|",
         *before_after(fields), "",
         "Волинь #3735: історія поля тепер HLS 2016–2025 (`out/hls/volyn_ndvi_seasons.csv`, оновлено в тому ж коміті), "
         "у «до» — 2016–2020; для Волині «до/після» змішує календар і нову історію (поточна практика, хвіст №164).", ""]
    DST.write_text("\n".join(L), encoding="utf-8", newline="\n")
    print(f"ok {DST}")


if __name__ == "__main__":
    main()
