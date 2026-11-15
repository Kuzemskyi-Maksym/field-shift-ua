#!/usr/bin/env python3
"""ECOSTRESS (МКС) — випаровування ET по 5 пілотних полях через AppEEARS API.

Запуск з папки nasa (поруч має лежати appeears_hls.py — з нього беруться логін і API):
  python appeears_ecostress.py check      # які продукти ECOSTRESS ET і шари є в AppEEARS (нічого не відправляє)
  python appeears_ecostress.py submit     # показує, що саме відправить, питає y/n, відправляє 1 запит
  python appeears_ecostress.py status
  python appeears_ecostress.py download   # CSV -> out/ecostress/
  python appeears_ecostress.py process    # out/ecostress/pilots_et_daily.csv + pilots_et_season.csv

Точки: ті самі 5 точок HLS усередині кожного пілотного поля (out/hls/<oblast>_points.csv, Category = пілотне поле).
Піксель ECOSTRESS 70 м; точки стоять ≥45 м від межі, тож піксель здебільшого в межах поля.
Нічого не вгадуємо: назви продуктів і шарів беремо з API AppEEARS (крок check), а не з пам'яті.
"""
import argparse
import csv
import json
import os
import re
import sys

import appeears_hls as H  # login(), _req(), API

OUT = os.path.join("out", "ecostress")
TASKS = os.path.join(OUT, "tasks.json")
PILOTS = {  # область -> (пілотне поле NASA Harvest, точка моделі)
    "poltava": ("f20905", "karlivka_pl"), "vinnytsia": ("f1821", "kalynivka_vn"),
    "mykolaiv": ("f3297", "arbuzynka_mk"), "odesa": ("f16903", "berezivka_od"), "volyn": ("f3735", "volyn_f3735"),
}
# пріоритет продуктів: новіша версія спершу; ET — L3 JET; хмари — L2 cloud
ET_PRODUCTS = [r"^ECO_L3T_JET\.003$", r"^ECO_L3T_JET\.002$", r"^ECO3ETPTJPL\.001$"]
CLOUD_PRODUCTS = [r"^ECO_L2T_LSTE\.003$", r"^ECO_L2T_LSTE\.002$", r"^ECO2CLD\.001$"]
ET_LAYER = re.compile(r"ETdaily|ETinst$|ETinstUncertainty", re.I)
CLOUD_LAYER = re.compile(r"^cloud$|^CloudMask$|cloud", re.I)


def points():
    rows = []
    for ob, (fid, model_id) in PILOTS.items():
        src = os.path.join("out", "hls", f"{ob}_points.csv")
        if not os.path.exists(src):
            print(f"[{ob}] немає {src}"); continue
        for r in csv.DictReader(open(src, encoding="utf-8")):
            if r["Category"] == fid:
                rows.append(dict(id=r["ID"], category=f"{model_id}|{fid}", latitude=float(r["Latitude"]), longitude=float(r["Longitude"])))
    return rows


def products(rq, H_):
    r = rq.get(f"{H.API}/product", headers=H_, timeout=120)
    r.raise_for_status()
    return {p["ProductAndVersion"]: p for p in r.json()}


def pick(rq, H_, allp, patterns, layer_re):
    for pat in patterns:
        for name in sorted(allp):
            if re.match(pat, name):
                lay = rq.get(f"{H.API}/product/{name}", headers=H_, timeout=60).json()
                chosen = [l for l in lay if layer_re.search(l)]
                if chosen:
                    return name, chosen, sorted(lay)
    return None, [], []


def cmd_check(a):
    rq = H._req(); H_ = H.login(); allp = products(rq, H_)
    eco = {k: v for k, v in allp.items() if k.upper().startswith("ECO")}
    print(f"Продуктів ECOSTRESS в AppEEARS: {len(eco)}")
    for k, v in sorted(eco.items()):
        print(f"  {k:24s} {v.get('Description', '')[:70]} | {v.get('TemporalExtentStart', '')}–{v.get('TemporalExtentEnd', '')}")
    for title, pats, lre in [("ET", ET_PRODUCTS, ET_LAYER), ("хмари", CLOUD_PRODUCTS, CLOUD_LAYER)]:
        name, chosen, all_layers = pick(rq, H_, allp, pats, lre)
        print(f"\n{title}: обрано {name} -> шари {chosen}\n   усі шари: {all_layers}")
    print(f"\nТочок: {len(points())} (5 пілотних полів × 5)")


def cmd_submit(a):
    rq = H._req(); H_ = H.login(); allp = products(rq, H_)
    et, et_l, _ = pick(rq, H_, allp, ET_PRODUCTS, ET_LAYER)
    cl, cl_l, _ = pick(rq, H_, allp, CLOUD_PRODUCTS, CLOUD_LAYER)
    if not et:
        sys.exit("СТОП: не знайшов продукт ECOSTRESS ET. Запусти check і скинь вивід.")
    layers = [{"product": et, "layer": l} for l in et_l] + [{"product": cl, "layer": l} for l in cl_l]
    pts = points()
    print(f"Відправлю: {len(pts)} точок, {a.start}–{a.end}\n  шари: {layers}")
    if not a.yes and input("Відправити? [y/N] ").strip().lower() != "y":
        sys.exit("Скасовано.")
    body = {"task_type": "point", "task_name": "fieldshift_ecostress_pilots",
            "params": {"dates": [{"startDate": a.start, "endDate": a.end}], "layers": layers, "coordinates": pts}}
    r = rq.post(f"{H.API}/task", json=body, headers=H_, timeout=120)
    if r.status_code not in (200, 202):
        sys.exit(f"Помилка HTTP {r.status_code}: {r.text[:500]}")
    os.makedirs(OUT, exist_ok=True)
    tid = r.json()["task_id"]
    json.dump({"task_id": tid, "et_product": et, "cloud_product": cl, "layers": layers}, open(TASKS, "w"), indent=1)
    print("Відправлено, task_id", tid)


def cmd_status(a):
    rq = H._req(); H_ = H.login(); t = json.load(open(TASKS))
    r = rq.get(f"{H.API}/task/{t['task_id']}", headers=H_, timeout=60).json()
    print(t["task_id"], r.get("status"), r.get("progress", ""))


def cmd_download(a):
    rq = H._req(); H_ = H.login(); t = json.load(open(TASKS)); tid = t["task_id"]
    st = rq.get(f"{H.API}/task/{tid}", headers=H_, timeout=60).json().get("status")
    if st != "done":
        sys.exit(f"Ще не готово: {st}")
    for f in rq.get(f"{H.API}/bundle/{tid}", headers=H_, timeout=60).json()["files"]:
        if f["file_name"].endswith(".csv"):
            dst = os.path.join(OUT, os.path.basename(f["file_name"]))
            with rq.get(f"{H.API}/bundle/{tid}/{f['file_id']}", headers=H_, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(dst, "wb") as fh:
                    for ch in r.iter_content(1 << 20): fh.write(ch)
            print(dst)


def cmd_process(a):
    import pandas as pd
    fs = [os.path.join(OUT, f) for f in os.listdir(OUT) if f.endswith(".csv") and "results" in f]
    if not fs:
        sys.exit(f"Немає CSV результатів в {OUT} — спершу download")
    et = cl = None
    for f in fs:
        d = pd.read_csv(f)
        print(f"{os.path.basename(f)}: {len(d)} рядків; колонки: {[c for c in d.columns if c not in ('ID', 'Category', 'Latitude', 'Longitude', 'Date')][:12]}")
        cols_et = [c for c in d.columns if re.search(r"ETdaily$", c)]
        cols_cl = [c for c in d.columns if re.search(r"cloud$", c, re.I)]
        if cols_et: et = (d, cols_et[0])
        if cols_cl: cl = (d, cols_cl[0])
    if et is None:
        sys.exit("Не знайшов колонку ETdaily — скинь назви колонок вище")
    d, c = et
    x = d[["ID", "Category", "Date", c]].rename(columns={c: "et_daily"})
    if cl is not None:
        dc, cc = cl
        x = x.merge(dc[["ID", "Date", cc]].rename(columns={cc: "cloud"}), on=["ID", "Date"], how="left")
        n0 = len(x); x = x[(x.cloud.isna()) | (x.cloud == 0)]
        print(f"Хмарна маска: прибрано {n0 - len(x)} з {n0}")
    else:
        print("ПРАПОРЕЦЬ: хмарної маски немає — значення без фільтра хмар")
    # ETdaily: fill = NaN (AppEEARS /product/ECO_L3T_JET.002, Earthdata catalog), 0 — не fill → нулі лишаємо (≥ 0).
    # Нулі у квітні–вересні — майже лише в прольоти до 08:00 / після 17:00 сонячного часу (ETdaily — інтеграл від сходу до
    # заходу, апскейл з миттєвого ET) → колонка daytime; порівняння з моделлю — лише daytime (reports/ecostress.md).
    x = x[(x.et_daily >= 0) & (x.et_daily < 15)]  # мм/добу; вище 15 — фізично неправдоподібно для богари
    x = x.groupby(["ID", "Category", "Date"], as_index=False).et_daily.median()   # дублікати тайлів (той самий проліт, 2 тайли)
    x["date"] = pd.to_datetime(x.Date.str.replace(" UTC", ""), utc=True)
    g = x.groupby(["Category", "date"]).agg(et_daily_mm=("et_daily", "median"), n_points=("ID", "nunique")).reset_index()
    lon = d.groupby("Category").Longitude.mean()
    g["solar_hour"] = ((g.date.dt.hour + g.date.dt.minute / 60 + g.Category.map(lon) / 15) % 24).round(2)
    g["daytime"] = g.solar_hour.between(8, 17)
    g[["model_id", "fid"]] = g.Category.str.split("|", expand=True)
    g = g.drop(columns="Category")
    g.to_csv(os.path.join(OUT, "pilots_et_daily.csv"), index=False)
    g["y"], g["m"] = g.date.dt.year, g.date.dt.month
    s = g[g.m.between(4, 9) & g.daytime].groupby(["model_id", "y"]).agg(et_mean_mm_day=("et_daily_mm", "mean"), n_obs=("et_daily_mm", "size")).reset_index()
    s.round(2).to_csv(os.path.join(OUT, "pilots_et_season.csv"), index=False)
    print(s.round(2).to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "submit", "status", "download", "process"])
    ap.add_argument("--start", default="07-09-2018", help="MM-DD-YYYY; ECOSTRESS почав роботу в липні 2018")
    ap.add_argument("--end", default="10-31-2026")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    {"check": cmd_check, "submit": cmd_submit, "status": cmd_status, "download": cmd_download, "process": cmd_process}[a.cmd](a)
