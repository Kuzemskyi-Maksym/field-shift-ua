#!/usr/bin/env python3
"""D30: індикатор умов для ґрунтових шкідників (model/pests.yaml) з NASA POWER TSOIL1 → site/pests.json (ключ pests).

Для пілотів і полів портфеля: днів у квітні–червні з TSOIL1 у вікні [tmin, tmax) за кожен рік 2016–2025 і лінійний тренд
(днів за 10 років). Вузол POWER без TSOIL1 у кеші data/raw/power/tsoil_*.csv → status no_data (нічого не підставляємо).
Рівні «низький/середній/високий» — лише якщо в джерелі є межі (levels); інакше лише дні й тренд. Модель не змінюється.
  python scripts/pest_risk.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.simulate import node_of  # noqa: E402

PESTS = ROOT / "model" / "pests.yaml"
POWER = ROOT / "data" / "raw" / "power"
DST = ROOT / "site" / "pests.json"
PILOTS = ["berezivka_od", "arbuzynka_mk", "karlivka_pl", "kalynivka_vn", "volyn:f3735"]


def days_in_window(lat: float, lon: float, p: dict) -> dict:
    nl, nn = node_of(lat, lon)
    f = POWER / f"tsoil_{nl:.3f}_{nn:.3f}.csv"
    if not f.exists():
        return dict(status="no_data", node=[nl, nn])
    d = pd.read_csv(f, parse_dates=["date"], index_col="date")[p["var"]]
    y0, y1 = p["years"]
    d = d[(d.index.year >= y0) & (d.index.year <= y1) & d.index.month.isin(p["months"])]
    ok = (d >= p["tmin_c"]) & (d < p["tmax_c"])
    per = ok.groupby(ok.index.year).sum().astype(int)
    if len(per) < 5:
        return dict(status="no_data", node=[nl, nn])
    yrs = per.index.values.astype(float)
    slope = float(np.polyfit(yrs, per.values.astype(float), 1)[0]) * 10
    return dict(status="ok", node=[nl, nn], years=[[int(y), int(v)] for y, v in per.items()],
                mean=round(float(per.mean()), 1), trend_days_per_decade=round(slope, 1))


def build() -> dict:
    cfg = yaml.safe_load(open(PESTS, encoding="utf-8"))["pests"]
    import model.simulate as M
    pts = {}
    for pid in PILOTS:
        f = M.field_profile(pid, allow_stubs=True)
        pts[pid] = (f.lat, f.lon)
    pf = json.load(open(ROOT / "site" / "portfolio.json", encoding="utf-8"))["portfolio"]["windows"]
    for ob, w in pf.items():
        st = pd.read_csv(ROOT / "out" / "fields" / f"{ob}_fields_stats.csv", usecols=["fid", "lat", "lon"]).set_index("fid")
        for fid in w["fields"]:
            pts.setdefault(f"{ob}:f{fid}", (float(st.at[int(fid), "lat"]), float(st.at[int(fid), "lon"])))
    out = dict(pests={k: {kk: v[kk] for kk in ("name_uk", "name_en", "tmin_c", "tmax_c", "months", "years", "levels",
                                                 "source", "source_url", "quote", "crops_note")} for k, v in cfg.items()},
               fields={})
    for fid, (lat, lon) in pts.items():
        out["fields"][fid] = {k: days_in_window(lat, lon, v) for k, v in cfg.items()}
    return out


def main():
    out = build()
    DST.write_text(json.dumps(dict(pests=out), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ok = sum(1 for f in out["fields"].values() for v in f.values() if v["status"] == "ok")
    print(f"ok {DST}: полів {len(out['fields'])}, з даними {ok}")


if __name__ == "__main__":
    main()
