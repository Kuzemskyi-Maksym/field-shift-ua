#!/usr/bin/env python3
"""ECOSTRESS (МКС, ECO_L3T_JET.002 ETdaily) проти денного ETa моделі на 5 пілотних полях → reports/ecostress.md + графік,
out/ecostress/model_vs_eco.csv, site/ecostress.json (блок у картці пілотного поля).

Культура на полі в рік Y — з HLS (out/hls/<обл>_ndvi_seasons.csv, поле NASA Harvest пілота):
W → пшениця озима, S late → кукурудза, S early → соняшник, інше (?, S без підтипу) → рік пропускаємо.
Модель: та сама, що в оптимізаторі (FAO-56 водний баланс, календар D17), один рік погоди Y (рядок погоди з блоком 1 = Y),
послідовність (культура Y, чорний пар) — після збирання голий ґрунт до 31.07 наступного року. Старт вологи — умовність
симулятора (ПВ 1 січня року Y−1). Нічого не калібруємо під ECOSTRESS.

  python appeears_ecostress.py process        # спершу: out/ecostress/pilots_et_daily.csv
  python scripts/ecostress_compare.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model import simulate as M  # noqa: E402

ECO = ROOT / "out" / "ecostress"
REP = ROOT / "reports" / "ecostress.md"
PNG = ROOT / "reports" / "ecostress.png"
SITE = ROOT / "site" / "ecostress.json"
FIELDS = {  # model_id у ECOSTRESS → (поле моделі, область HLS, fid HLS, назва)
    "berezivka_od": ("berezivka_od", "odesa", "f16903", "Березівка"),
    "arbuzynka_mk": ("arbuzynka_mk", "mykolaiv", "f3297", "Арбузинка"),
    "karlivka_pl": ("karlivka_pl", "poltava", "f20905", "Карлівка"),
    "kalynivka_vn": ("kalynivka_vn", "vinnytsia", "f1821", "Калинівка"),
    "volyn_f3735": ("volyn:f3735", "volyn", "f3735", "Волинь #3735"),
}
CROP = {("W", ""): "winter_wheat", ("S", "late"): "maize", ("S", "early"): "sunflower"}
CROP_UK = {"winter_wheat": "пшениця озима", "maize": "кукурудза", "sunflower": "соняшник"}
CRIT = dict(r=0.5, bias=0.5, mae=1.0)   # орієнтири читання, зафіксовані до розрахунку (не підгонка)


def hls_crops(ob, fid):
    d = pd.read_csv(ROOT / "out" / "hls" / f"{ob}_ndvi_seasons.csv")
    d = d[d.field == fid]
    out = {}
    for r in d.itertuples():
        sub = "" if pd.isna(r.sub) else str(r.sub)
        out[int(r.y)] = (str(r.c), sub, CROP.get((str(r.c), sub if r.c == "S" else "")))
    return out


def model_year(fld, crop, Y):
    """Денне ETa моделі для календарного року Y (365 днів, 29.02 немає) або (None, причина)."""
    sim = M.SequenceSimulator(fld, K=2, allow_stubs=True, keep_daily=True)
    res, why = sim.run((crop, "black_fallow"))
    if res is None:
        return None, why
    s = M.YEARS.index(Y)                         # рядок погоди s: блок 1 = YEARS[s] = Y
    T = np.full(3 * 365, np.nan)
    for y in res:
        st, eta = y.daily
        T[st:st + eta.shape[1]] = eta[s]
    return T[365:730], None


def stats(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    n = len(a)
    if n == 0:
        return dict(n=0, r=None, bias=None, mae=None)
    r = float(np.corrcoef(a, b)[0, 1]) if n >= 3 and a.std() > 0 and b.std() > 0 else None
    return dict(n=n, r=None if r is None else round(r, 2), bias=round(float((a - b).mean()), 2),
                mae=round(float(np.abs(a - b).mean()), 2))


def fmt_r(r):
    return "—" if r is None else f"{r:.2f}"


def main():
    eco = pd.read_csv(ECO / "pilots_et_daily.csv")
    eco["date"] = pd.to_datetime(eco.date, utc=True)
    eco["y"] = eco.date.dt.year
    rows, site, skipped = [], {}, []
    for mid, (fid_model, ob, fid, name) in FIELDS.items():
        fld = M.field_profile(fid_model, True)
        crops = hls_crops(ob, fid)
        e = eco[eco.model_id == mid]
        site[fid_model] = dict(name=name, years={})
        for Y in sorted(e.y.unique()):
            ey = e[e.y == Y]
            if Y not in M.YEARS:
                skipped.append(f"{name} {Y}: немає погоди POWER у моделі (2001–2025) — {len(ey)} прольотів")
                continue
            c, sub, crop = crops.get(Y, ("немає", "", None))
            hl = f"{c}{(' ' + sub) if sub else ''}"
            if crop is None:
                skipped.append(f"{name} {Y}: HLS «{hl}» — культуру не визначено, {len(ey)} прольотів")
                continue
            T, why = model_year(fld, crop, Y)
            if T is None:
                skipped.append(f"{name} {Y}: модель не рахує ({why})")
                continue
            pts = []
            for r in ey.itertuples():
                md = r.date.strftime("%m-%d")
                if md == "02-29":
                    continue
                d0 = M.doy0(md)
                rows.append(dict(field=name, model_id=mid, date=r.date.strftime("%Y-%m-%d"), y=Y, doy0=d0, crop=crop, hls=hl,
                                 eco=round(float(r.et_daily_mm), 3), model=round(float(T[d0]), 3), daytime=bool(r.daytime),
                                 solar_hour=r.solar_hour, apr_sep=4 <= r.date.month <= 9))
                pts.append([d0, round(float(r.et_daily_mm), 2), int(bool(r.daytime))])
            day = [p for p in pts if p[2]]
            st = stats([T[p[0]] for p in day], [p[1] for p in day])
            site[fid_model]["years"][str(Y)] = dict(crop=crop, crop_uk=CROP_UK[crop], hls=hl,
                                                    model=[round(float(v), 2) for v in T], eco=pts, n=st["n"], r=st["r"])
    x = pd.DataFrame(rows)
    x.to_csv(ECO / "model_vs_eco.csv", index=False)
    d = x[x.daytime]
    season = d[d.apr_sep]

    def table(sub):
        out = []
        for name, g in sub.groupby("field", sort=False):
            s = stats(g.model, g.eco)
            out.append(f"| {name} | {s['n']} | {fmt_r(s['r'])} | {g.eco.mean():.2f} | {g.model.mean():.2f} | {s['bias']:+.2f} | {s['mae']:.2f} |")
        s = stats(sub.model, sub.eco)
        out.append(f"| **усі поля** | {s['n']} | {fmt_r(s['r'])} | {sub.eco.mean():.2f} | {sub.model.mean():.2f} | {s['bias']:+.2f} | {s['mae']:.2f} |")
        return out

    def by_crop(sub):
        out = []
        for crop, g in sub.groupby("crop"):
            s = stats(g.model, g.eco)
            out.append(f"| {CROP_UK[crop]} | {s['n']} | {fmt_r(s['r'])} | {g.eco.mean():.2f} | {g.model.mean():.2f} | "
                       f"{s['bias']:+.2f} | {s['mae']:.2f} |")
        return out

    def by_month(sub):
        out = []
        for m, g in sub.groupby(pd.to_datetime(sub.date).dt.month):
            out.append(f"| {m:02d} | {len(g)} | {g.eco.mean():.2f} | {g.model.mean():.2f} | {(g.model - g.eco).mean():+.2f} |")
        return out

    s_all, s_sea, allp = stats(d.model, d.eco), stats(season.model, season.eco), stats(x.model, x.eco)
    plot(x)
    H = ("| Поле | n | r (Пірсон) | ECOSTRESS, мм/добу | модель ETa, мм/добу | середня різниця (модель − ECO) | MAE |\n"
         "|---|---|---|---|---|---|---|")
    L = ["# ECOSTRESS (МКС) проти ETa моделі — 5 пілотних полів", "",
         "_Згенеровано `python scripts/ecostress_compare.py`. Нічого не калібрували під ECOSTRESS._", "",
         "## Дані", "",
         "- **ECOSTRESS:** ECO_L3T_JET.002, шар `ETdaily` (70 м; медіана 4 моделей ET — PT-JPL-SM, STIC, MOD16, BESS — апскейл "
         "до денного ET від сходу до заходу сонця, мм/добу; ECOSTRESS Collection 2 Tiled User Guide, розд. 5.4). Хмари — "
         "ECO_L2T_LSTE.002 `cloud` (=1 відкинуто). Поле × дата — медіана 5 точок HLS усередині поля (`appeears_ecostress.py process`).",
         "- **Модель:** денне ETa симулятора (FAO-56, той самий, що в оптимізаторі; календар D17), погода POWER того ж року, культура "
         "з HLS цього поля: W → пшениця озима, S late → кукурудза, S early → соняшник; «?» і S без підтипу — пропуск. "
         "Після збирання — голий ґрунт (Annex 7). Модель — ET за добу, ECOSTRESS — від сходу до заходу (нічне ET мале).", "",
         "## 1. Нулі в ETdaily: не заповнення, але й не «ET голого поля»", "",
         "- 1031 з 5437 значень точок (19 %) = 0,0; від'ємних і NaN немає.",
         "- **Fill value ETdaily = NaN, не 0**: AppEEARS `/api/product/ECO_L3T_JET.002` (FillValue NaN, ValidMin/ValidMax порожні) і "
         "каталог Earthdata ECO_L3T_JET v002 («Daily Evapotranspiration (ET) estimate, Fill Value = NaN»). User Guide нуля як коду "
         "не описує. Отже 0 — валідне значення продукту → **повернуто** (`process`: фільтр `> 0` → `≥ 0`).",
         "- Звідки нулі (дані, не документація): у квітні–вересні при прольоті 08:00–17:00 місцевого сонячного часу нулів 0–2 %, "
         "до 08:00 і після 17:00 — 13–57 %; узимку нулі в будь-яку годину (листопад 88 %, січень 69 %). ETdaily — апскейл "
         "миттєвого ET з моменту прольоту на світловий день, тож проліт на світанку/в сутінках дає ≈0 незалежно від поля. "
         "Це артефакт часу прольоту МКС, а не реальне ET голого поля.",
         "- Тому нулі лишаються в `pilots_et_daily.csv`, додано `solar_hour` і `daytime` (08–17 сонячного часу); **порівняння з "
         f"моделлю — лише денні прольоти** ({len(d)} з {len(x)} пар поле×дата). Для повноти — усі прольоти: n {allp['n']}, "
         f"r {fmt_r(allp['r'])}, різниця {allp['bias']:+.2f}, MAE {allp['mae']:.2f} мм/добу.",
         "- Дублікати тайлів (той самий проліт у двох тайлах MGRS) об'єднано медіаною.", "",
         "## 2. Модель проти ECOSTRESS (денні прольоти, увесь рік)", "", H, *table(d), "",
         "## 3. Сезон квітень–вересень (денні прольоти)", "", H, *table(season), "",
         "За культурою (квітень–вересень):", "",
         "| Культура | n | r | ECOSTRESS | модель | різниця | MAE |", "|---|---|---|---|---|---|---|", *by_crop(season), "",
         "За місяцем (усі поля, денні прольоти):", "", "| Місяць | n | ECOSTRESS | модель | різниця |", "|---|---|---|---|---|",
         *by_month(d), "",
         "![ECOSTRESS проти моделі](ecostress.png)", "",
         "## Висновок", "", verdict(s_all, s_sea, season), "",
         "## Що не порівнювали", "", *[f"- {s}" for s in skipped], "",
         "## Обмеження", "",
         "- Погода моделі — клітинка POWER ~50 км, ECOSTRESS — піксель 70 м: локальні дощі не збігаються день у день.",
         "- Культура — з класу HLS (W / S early / S late), не підтверджена фермером; сорт, дата сівби, густота — модельні.",
         "- ETdaily ECOSTRESS — теж модель (ансамбль 4 алгоритмів), не вимір; розкид між ними (ETinstUncertainty) — медіанно ~36 Вт/м².",
         "- Після збирання модель вважає поле голим до 31.07 наступного року; восени на полі може бути наступна озима.", ""]
    REP.write_text("\n".join(L), encoding="utf-8", newline="\n")
    SITE.write_text(json.dumps(dict(ecostress=dict(fields=site, metrics=dict(daytime=s_all, apr_sep=s_sea))),
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"ok {REP.name}, {PNG.name}, {SITE.name} ({SITE.stat().st_size // 1024} КБ); день n={s_all['n']} r={s_all['r']} "
          f"різн={s_all['bias']} MAE={s_all['mae']}; квіт–вер n={s_sea['n']} r={s_sea['r']} різн={s_sea['bias']} MAE={s_sea['mae']}")


def verdict(a, s, season):
    by = season.groupby("crop").apply(lambda g: (g.model - g.eco).mean())
    ok = s["r"] is not None and s["r"] >= CRIT["r"] and abs(s["bias"]) <= CRIT["bias"] and s["mae"] <= CRIT["mae"]
    parts = [f"Денні прольоти, увесь рік: r = {fmt_r(a['r'])}, модель − ECOSTRESS = {a['bias']:+.2f} мм/добу, MAE {a['mae']:.2f}. "
             f"Квітень–вересень: r = {fmt_r(s['r'])}, різниця {s['bias']:+.2f}, MAE {s['mae']:.2f} мм/добу."]
    crit = f"r ≥ {CRIT['r']}, |різниця| ≤ {CRIT['bias']}, MAE ≤ {CRIT['mae']} мм/добу (орієнтири, зафіксовані до розрахунку)"
    parts.append(("Модель узгоджується з ECOSTRESS за орієнтирами " + crit + ".") if ok else
                 ("**Модель розходиться з ECOSTRESS** за орієнтирами " + crit + "."))
    parts.append("Різниця за культурою (квіт–вер, модель − ECO): " + ", ".join(f"{CROP_UK[c]} {v:+.2f}" for c, v in by.items()) + ".")
    parts.append("Не підганяли: Kc, фази, ґрунт і погода — як в оптимізаторі.")
    return " ".join(parts)


def plot(x):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(dict.fromkeys(x.field))
    fig, ax = plt.subplots(len(names), 2, figsize=(13, 2.6 * len(names)), gridspec_kw=dict(width_ratios=[3, 1]))
    for i, n in enumerate(names):
        g = x[x.field == n].copy()
        g["d"] = pd.to_datetime(g.date)
        a = ax[i, 0]
        a.scatter(g.d, g.model, s=14, marker="_", color="#264", label="модель ETa у дні прольоту", zorder=2)
        a.scatter(g.d[g.daytime], g.eco[g.daytime], s=12, color="#c63", label="ECOSTRESS (денний проліт)", zorder=3)
        a.scatter(g.d[~g.daytime], g.eco[~g.daytime], s=10, facecolors="none", edgecolors="#c63", alpha=.5,
                  label="ECOSTRESS (світанок/сутінки)", zorder=3)
        a.set_ylabel(f"{n}\nмм/добу")
        a.set_ylim(0, max(8, float(np.nanmax([g.eco.max(), g.model.max()])) + .5))
        if i == 0:
            a.legend(fontsize=7, loc="upper left", ncol=3)
        b = ax[i, 1]
        dd = g[g.daytime]
        b.scatter(dd.eco, dd.model, s=10, c=np.where(dd.apr_sep, "#c63", "#999"))
        m = max(6, float(np.nanmax([dd.eco.max(), dd.model.max()])) + .5) if len(dd) else 6
        b.plot([0, m], [0, m], color="#555", lw=.8)
        b.set_xlim(0, m)
        b.set_ylim(0, m)
        s = stats(dd.model, dd.eco)
        b.set_title(f"n={s['n']} r={fmt_r(s['r'])} MAE={s['mae']}", fontsize=8)
        b.set_xlabel("ECOSTRESS", fontsize=8)
        b.set_ylabel("модель", fontsize=8)
    fig.suptitle("ECOSTRESS ETdaily проти ETa моделі, мм/добу (праворуч — денні прольоти; помаранчеві — квітень–вересень)", fontsize=10)
    fig.tight_layout()
    fig.savefig(PNG, dpi=110)


if __name__ == "__main__":
    main()
