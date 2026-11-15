"""Оптимізатор сівозміни (ТЗ A1, A6–A9): перебір → фільтри №164/календар/фермер → симуляція 25 років →
критерії → фронт Парето → 3 стратегії (+ «water» для степу) + поточна → calendar + explain → strategies_<field>.json.

Ранжування між культурами — лише за грошима (т/га × ціна) або за кормовою цінністю з джерелом (енергія/протеїн з т/га).
Ya/Yx — частка потенціалу КОЖНОЇ культури окремо, між культурами не порівнюється; режим yield_index — лише демо механіки.
Стратегії будуються лише з культур, для яких є т/га (Yx Держстату); решта — «перспективні, але без даних для т/га».

Без мережі. Дані: кеш POWER/SoilGrids, HLS-історія, Держстат (Yx), ціни/ринок/тваринництво (якщо заповнені).
  python -m model.optimize --field berezivka_od --allow-stubs [--rank auto|money|feed_energy|feed_protein|yield_index]
  python -m model.optimize --pilots --allow-stubs --rank yield_index        # демо механіки без цін
  python -m model.optimize --field berezivka_od --allow-stubs --confirm 2022=winter_wheat
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from model import costs as CO
from model import crops as C
from model import livestock as LV
from model import machinery as MC
from model import market as MK
from model import rules as R
from model import simulate as M

ROOT = Path(__file__).resolve().parents[1]
CFG_YAML = Path(__file__).resolve().parent / "optimize.yaml"
OUT = ROOT / "out" / "strategies"
CONFIRMED = ROOT / "data" / "fields" / "confirmed.yaml"
PILOT_FIELDS = ["berezivka_od", "arbuzynka_mk", "karlivka_pl", "kalynivka_vn", "volyn:f3735"]
WHEAT_AFTER_MAIZE = "пшениця після кукурудзи на зерно — пізня сівба / потрібна інша культура"
DEMO_LABEL = "ранжування без цін — демо механіки"
FALLOW_FORBIDDEN = "чорний пар у цій стратегії заборонений: немає витрат на пар з джерелом"
FALLOW_NO_COST = "витрати на пар не враховано"
CLIMATE_RISK = "маржа близька до нуля в типовий рік і від'ємна в сухий — ризик клімату вищий за вибір культури"
WHY_NOT_REPEAT = "чому не повторювати поточну"
STRATEGY_NAMES = ("max_income", "min_risk", "balanced", "water")
CUR_VIOL = "поточна сівозміна порушує №164 — ризик хвороб і висушення ґрунту"
RANK_MODES = ("auto", "margin", "money", "feed_energy", "feed_protein", "yield_index")
RANK_UNITS = {"margin": "грн/га/рік (маржа = ціна × урожай − витрати на га Держстату, ranking.cost_column; витрати фіксовані)",
              "money": "грн/га/рік (валовий дохід, без витрат)", "feed_energy": "ГДж ОЕ/га/рік",
              "feed_protein": "т сирого протеїну/га/рік", "yield_index": "частка потенціалу Ya/Yx (демо)"}


@lru_cache(maxsize=1)
def load_cfg() -> dict:
    with open(CFG_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


# =====================================================================================
# Історія поля (HLS + підтвердження фермера) і «поточна» стратегія
# =====================================================================================
def hls_field(field_id: str) -> tuple[str, str]:
    """→ (вікно = область, 'f<fid>') поля з рядом HLS. Пілоти — через zones.yaml pilots (той самий полігон, що в портфелі).
    MODIS у точці пілота (site/ndvi_seasons.csv) у моделі більше не використовується — лише на сайті для порівняння."""
    if field_id in M.POINTS:
        z = M._zones()["pilots"][field_id]
        return z["oblast"], f"f{z['fid']}"
    ob, fid = field_id.split(":")
    return ob, fid


def field_history(field_id: str, confirmed: dict | None = None) -> list[dict]:
    """confirmed: {рік: crop_id} з UI (history_confirmed); доповнює/перекриває data/fields/confirmed.yaml."""
    conf = {}
    if CONFIRMED.exists():
        with open(CONFIRMED, encoding="utf-8") as f:
            conf = {int(k): v for k, v in ((yaml.safe_load(f) or {}).get(field_id, {}) or {}).items()}
    conf.update({int(k): v for k, v in (confirmed or {}).items()})
    ob, fid = hls_field(field_id)          # пілот → його полігон NASA Harvest (zones.yaml pilots), як у портфелі
    d = pd.read_csv(ROOT / "out" / "hls" / f"{ob}_ndvi_seasons.csv")
    d = d[d.field == fid]
    rows = [dict(year=int(r.y), c=str(r.c), sub="" if pd.isna(r.sub) else str(r.sub)) for r in d.itertuples()]
    src = f"out/hls/{ob}_ndvi_seasons.csv (HLS 30 м, поле #{fid.lstrip('f')})"
    have = {r["year"] for r in rows}
    for y, c in conf.items():                      # підтверджені роки, яких немає в HLS (напр. 2026)
        if y not in have:
            rows.append(dict(year=y, c="?", sub=""))
    for r in rows:
        r["confirmed_crop"] = conf.get(r["year"])
        r["src"] = src
    return sorted(rows, key=lambda r: r["year"])


def current_variants(hist: list[dict], K: int, rules: dict, plan_start_year: int, max_lag_years: int,
                     max_unknown: int) -> tuple[list[tuple[str, tuple]], list[str]]:
    """Поточна практика = останні K СУЦІЛЬНИХ років історії. Невідомий клас («?») → гілки W/S з прапорцем
    «підтвердіть культуру <рік>». Історія, що закінчується давно, — з прапорцем «історія до <рік>»."""
    g = rules["history"]["current_guess"]
    if len(hist) < K:
        return [], [f"поточну стратегію не визначено: у історії {len(hist)} років < {K}"]
    last = hist[-K:]
    yrs = [r["year"] for r in last]
    if yrs != list(range(yrs[0], yrs[0] + K)):
        return [], [f"поточну стратегію не визначено: роки історії {yrs} не суцільні"]
    flags = [g["flag"], f"поточна — за роками {yrs[0]}–{yrs[-1]}"]
    if yrs[-1] < plan_start_year - 1 - max_lag_years:
        flags.append(f"історія до {yrs[-1]} — поточна практика може бути застарілою")
    elif yrs[-1] < plan_start_year - 1:
        flags.append(f"рік {plan_start_year - 1} ще не в HLS — підтвердіть культуру {plan_start_year - 1}")
    options, unknown = [], []
    for r in last:
        if r.get("confirmed_crop") == "not_sunflower":          # підтверджено «не соняшник» → одна гілка (W), без ліміту
            flags.append(f"{r['year']}: фермер підтвердив «не соняшник»; культура невідома — для поточної взято W")
            options.append([(f"{r['year']}=W (не соняшник)", g["map"]["W"])])
            continue
        if r.get("confirmed_crop"):
            options.append([(None, r["confirmed_crop"])])
            continue
        key = r["c"] if r["c"] in ("W", "F") else f"S_{r['sub']}" if r["c"] == "S" else None
        crop = g["map"].get(key) if key else None
        if crop is None:                           # «?» → гілки W / S
            unknown.append(r["year"])
            options.append([(f"{r['year']}=W", g["map"]["W"]), (f"{r['year']}=S", g["map"]["S_"])])
        else:
            options.append([(None, crop)])
    if len(unknown) > max_unknown:
        return [], flags + [f"поточну стратегію не визначено: невідомих років {unknown} > {max_unknown}"]
    flags += [f"підтвердіть культуру {y} (HLS: клас невідомий; розглянуто W і S)" for y in unknown]
    out = []
    for combo in itertools.product(*options):
        label = ", ".join(l for l, _ in combo if l) or "за класами HLS"
        out.append((label, tuple(c for _, c in combo)))
    return out, flags


# =====================================================================================
# Yx (калібрування A — як v0; див. docs/decisions.md D1)
# =====================================================================================
def yx_table(fld: M.Field, crops: dict, allow_stubs: bool, calib: str, sim_kwargs: dict,
             yield_file: str | None = None) -> tuple[dict, dict]:
    """→ ({crop: Yx або None}, {crop: Ya/Yx [25] одного сезону — для списку «без даних»})."""
    s1 = M.SequenceSimulator(fld, K=1, allow_stubs=allow_stubs, **sim_kwargs)
    obs = M.yields(yield_file)
    out, single = {}, {}
    for c in crops:
        if crops[c]["group"] == "fallow":
            out[c] = None
            continue
        res, _ = s1.run((c,))
        single[c] = None if res is None else res[0].rel_yield
        g = obs[(obs.culture == c) & (obs.oblast == fld.oblast_uk)]
        if g.empty or res is None:
            out[c] = None
            continue
        rel = pd.Series(res[0].rel_yield, index=M.YEARS).loc[g.year].values
        if calib == "C":
            out[c] = float(np.percentile(g.yield_t_ha.values / np.maximum(rel, 1e-6), 90))
        else:
            out[c] = float(g.yield_t_ha.max() / max(rel.max(), 1e-6))
        if not np.isfinite(out[c]):
            out[c] = None
    return out, single


# =====================================================================================
# Режим ранжування і цінність тонни
# =====================================================================================
def unit_values(crops_ranked: list[str], fld, market, livestock) -> dict:
    """{mode: {crop: цінність 1 т або None}} — культури без значення в режимі йдуть у candidates_without_data."""
    money, energy, protein = {}, {}, {}
    for c in crops_ranked:
        ch = market.channel(c, fld.lat, fld.lon)
        fv, _, _ = livestock.feed_value_uah_t(c)
        vals = [v for v in (ch["net_price_uah_t"], fv) if v is not None and v > 0]
        money[c] = max(vals) if vals else None
        f = livestock.feed_values.get(c) if livestock.enabled else None
        energy[c] = f["me"] if f else None                 # МДж/кг = ГДж/т
        protein[c] = f["cp"] / 100 if f else None          # т протеїну / т
    return dict(money=money, feed_energy=energy, feed_protein=protein)


def add_margin(uv: dict, costs: dict) -> dict:
    """margin доступна для культури, якщо є і ціна (money), і витрати на га."""
    uv["margin"] = {c: (p if (p is not None and costs.get(c) is not None and costs[c].value is not None) else None)
                    for c, p in uv["money"].items()}
    return uv


def choose_rank(requested: str, uv: dict) -> tuple[str, list[str]]:
    if requested not in RANK_MODES:
        raise ValueError(f"--rank: {requested} не з {RANK_MODES}")
    if requested == "yield_index":
        return "yield_index", [f"{DEMO_LABEL}: Ya/Yx — частка потенціалу кожної культури окремо; порівняння між культурами некоректне"]
    avail = lambda m: any(v is not None for v in uv[m].values())  # noqa: E731
    if requested == "auto":
        for m in ("margin", "money", "feed_energy", "feed_protein"):
            if avail(m):
                return m, []
        return "none", ["ранжування неможливе: немає цін (data/raw/prices.csv) і кормової цінності з джерелом "
                        "(model/livestock.yaml) — показано лише поточну практику і допустимі культури; "
                        "для демо механіки: --rank yield_index"]
    if not avail(requested):
        raise ValueError(f"--rank {requested}: немає даних для жодної культури")
    return requested, []


# =====================================================================================
# Оцінка послідовності
# =====================================================================================
def evaluate(seq, res, sim: M.SequenceSimulator, yx: dict, mode: str, uv: dict, costs: dict | None = None,
             sf: tuple | None = None) -> dict:
    """sf = (множники [K], прапорці [K]) ефекту насичення соняшником (R.sunflower_multipliers) або None — без ефекту."""
    crops = sim.crops
    K = len(seq)
    mult = list(sf[0]) if sf else [1.0] * K
    rel = np.stack([y.rel_yield * mult[i] if y.rel_yield is not None else np.zeros(M.NY) for i, y in enumerate(res)])     # [K, 25]
    idx = rel.mean(0)
    value, missing, gross, rows = None, [], None, None
    priced = ("margin", "money", "feed_energy", "feed_protein")
    if mode in priced:
        missing = [c for c, y in zip(seq, res) if y.rel_yield is not None and (yx.get(c) is None or uv[mode].get(c) is None)]
    if mode in priced and not missing:
        val = np.zeros((K, M.NY))
        for i, (c, y) in enumerate(zip(seq, res)):
            if y.rel_yield is not None:
                val[i] = yx[c] * y.rel_yield * mult[i] * uv[mode][c]
        if mode == "margin":
            gross = val.mean(0)
            for i, c in enumerate(seq):
                cst = (costs or {}).get(c)
                val[i] = val[i] - (cst.value if cst is not None and cst.value is not None else 0.0)
                # пар: без доходу і без витрат (витрат з джерелом немає) → у сумі 0; per_year маржа пару = null, прапорець
        value = val.mean(0)
        rows = val.copy()                     # [K, 25] — маржа/цінність по роках плану × рядках погоди (лише вихід «гроші»)
        if mode == "money":
            gross = value
    elif mode == "yield_index":
        value = idx
    deficit = np.stack([y.etc_mm - y.eta_mm for y in res if y.rel_yield is not None] or [np.zeros(M.NY)]).mean(0)
    endm = sim.end_moisture(seq)
    v = value if value is not None else idx
    return dict(seq=tuple(seq), res=res, idx=idx, value=value, mode=mode, value_missing=missing, gross=gross, rows=rows,
                mult=mult, mult_flags=list(sf[1]) if sf else [[] for _ in range(K)], sf_effect=sf is not None,
                p50=float(np.percentile(v, 50)), p10=float(np.percentile(v, 10)),
                deficit=float(deficit.mean()), end_moisture=float(endm.mean()),
                legume=sum(crops[c]["n_fixing"] for c in seq) / K,
                drying=sum(crops[c].get("dries_soil", False) for c in seq) / K,
                bare=float(np.mean([y.bare_days for y in res])),
                has_fallow=any(crops[c]["group"] == "fallow" for c in seq))


OBJ = [("p50", +1), ("p10", +1), ("deficit", -1), ("end_moisture", +1), ("legume", +1), ("bare", -1), ("drying", -1)]


def pareto(ev: list[dict]) -> list[int]:
    X = np.array([[s * e[k] for k, s in OBJ] for e in ev])
    keep = []
    for i in range(len(X)):
        dom = np.all(X >= X[i], axis=1) & np.any(X > X[i], axis=1)
        if not dom.any():
            keep.append(i)
    return keep


def balanced_score(ev: list[dict], idxs: list[int], w: dict) -> np.ndarray:
    def norm(k, s):
        x = np.array([ev[i][k] for i in idxs], float) * s
        r = x.max() - x.min()
        return (x - x.min()) / r if r > 0 else np.ones_like(x)
    water = (norm("deficit", -1) + norm("end_moisture", +1)) / 2
    soil = (norm("legume", +1) + norm("bare", -1) + norm("drying", -1)) / 3
    return w["income_p50"] * norm("p50", +1) + w["income_p10"] * norm("p10", +1) + w["water"] * water + w["soil"] * soil


def water_pick(ev: list[dict], idxs: list[int], w: dict) -> int:
    """Стратегія «water»: фронт Парето за (волога на кінець ротації ↑, P10 ↑), бал = w·норм; нічия → P50."""
    X = np.array([[ev[i]["end_moisture"], ev[i]["p10"]] for i in idxs])
    front = [idxs[k] for k in range(len(X)) if not (np.all(X >= X[k], axis=1) & np.any(X > X[k], axis=1)).any()]

    def norm(k):
        x = np.array([ev[i][k] for i in front], float)
        r = x.max() - x.min()
        return (x - x.min()) / r if r > 0 else np.ones_like(x)
    sc = w["end_moisture"] * norm("end_moisture") + w["value_p10"] * norm("p10")
    best = max(range(len(front)), key=lambda k: (round(float(sc[k]), 9), ev[front[k]]["p50"]))
    return front[best]


# =====================================================================================
# Формування JSON (контракт docs/contracts.md = A9 + розширення)
# =====================================================================================
def mmdd(pos_: int) -> str:
    return (date(2001, 1, 1) + timedelta(days=pos_ % 365)).strftime("%m-%d")


def ymd(pos_: int, start_year: int) -> str:
    return f"{start_year - 1 + pos_ // 365}-{mmdd(pos_)}"


def sow_rule_uk(cr: dict) -> str | None:
    r = cr.get("sow_rule")
    if not r:
        return None
    return (f"сівба щороку — перший день після {r['not_before'][3:]}.{r['not_before'][:2]}, коли {r['mean_days']}-денна середня "
            f"температура ґрунту (POWER TSOIL1, 2–10 см) ≥ {r['threshold_c']:g} °C ({r['src']}); дата — медіана, діапазон — P10–P90 25 років")


def q3(x, q):
    return {k: round(float(np.percentile(x, p)), 2) for k, p in q.items()}


def violations_164(seq, history_tail, rules, current: bool) -> dict:
    r = R.check_linear([] if current else list(history_tail), list(seq), rules)
    return dict(count=len(r.violations), list=r.violations)


def strategy_json(name, e, sim, yx, market, livestock, fld, cfg, extra_flags, rules, crop_groups, history_tail,
                  costs: dict | None = None):
    q = cfg["quantiles"]
    seq, res = e["seq"], e["res"]
    per_year, calendar, gaps = [], [], []
    prev_end = -1
    for i, (c, y) in enumerate(zip(seq, res)):
        cr = sim.crops[c]
        fl = list(cr.get("flags", []))
        if y.rel_yield is not None:
            if yx.get(c) is None:
                fl.append(f"{c}: немає даних Держстату для калібрування Yx ({fld.oblast_uk}) — т/га не рахується")
                yth = None
            else:
                yth = q3(yx[c] * y.rel_yield * e["mult"][i], q)
            ytf = {k: round(v * fld.area_ha, 1) for k, v in yth.items()} if (yth and fld.area_ha) else None
            if yth and not fld.area_ha:
                fl.append("площа поля невідома — т на поле не рахується")
            ch = market.channel(c, fld.lat, fld.lon)
            fv, sp, ffl = livestock.feed_value_uah_t(c)
            pick = LV.choose_channel(ch["net_price_uah_t"], fv, sp)
            fl += ch.get("flags", []) + ffl
            if c in cfg.get("crop_logistics_flags", {}):
                fl.append(cfg["crop_logistics_flags"][c])
            vals = [v for v in (ch["net_price_uah_t"], fv) if v is not None and v > 0]
            if ch["net_price_uah_t"] is not None and ch["net_price_uah_t"] <= 0:
                fl.append(f"{c}: чиста ціна ≤ 0 після доставки — продаж невигідний")
            price = max(vals) if vals else None
            rev = {k: round(v * price) for k, v in yth.items()} if (yth and price) else None
            cst = (costs or {}).get(c)
            cost_v = cst.value if cst is not None else None
            if cst is not None:
                fl += cst.flags
            marg = {k: round(v - cost_v) for k, v in rev.items()} if (rev and cost_v is not None) else None
            channel = dict(type=pick["type"], buyer_id=ch.get("buyer_id"), net_price_uah_t=ch["net_price_uah_t"],
                           alternatives=ch.get("alternatives", []), why=pick["why"],
                           breakeven_port_km=ch.get("breakeven_port_km"), feed_value_uah_t=fv, feed_species=sp)
        else:
            yth = ytf = rev = None
            channel = dict(type="none", buyer_id=None, net_price_uah_t=None, alternatives=[], why="пар — без урожаю")
            cost_v, marg = None, None                                        # маржа пару = null (не 0) — D16
            if costs is not None:
                fl.append(f"{FALLOW_NO_COST}: витрат на чорний пар з джерелом немає (у Держстаті немає) — маржа пару = null; "
                          "у маржі послідовності пар = 0 грн (без доходу і без витрат), тобто завищена")
        prev = seq[i - 1] if i else (history_tail[-1] if history_tail else None)
        _, pefl = R.prev_effect(prev, c, rules)
        if e.get("sf_effect") and c == "sunflower":
            pefl = list(e["mult_flags"][i])                      # D20: ефект насичення соняшником замість «не враховано»
        _, pcfl = R.predecessor_class(prev, c, fld.zone, rules, crop_groups)
        fl += pefl + pcfl
        per_year.append(dict(year=i + 1, season=cfg["plan_start_year"] + i, crop=c, crop_uk=cr["name_uk"],
                             rel_yield=q3(y.rel_yield, q) if y.rel_yield is not None else None,
                             prev_effect_mult=round(e["mult"][i], 3),
                             yield_t_ha=yth, yield_t_field=ytf, channel=channel, revenue_uah_ha=rev,
                             cost_uah_ha=round(cost_v) if cost_v is not None else None, margin_uah_ha=marg,
                             flags=list(dict.fromkeys(fl))))
        stub = any(f.startswith("STUB") for f in cr.get("flags", []))
        if y.sow is not None:
            bare = [mmdd(prev_end + 1), mmdd(y.sow - 1)] if y.sow - 1 > prev_end else None
            calendar.append(dict(year=i + 1, crop=c, sow=mmdd(y.sow), harvest=mmdd(y.harvest),
                                 sow_date=ymd(y.sow, cfg["plan_start_year"]), harvest_date=ymd(y.harvest, cfg["plan_start_year"]),
                                 bare=bare, risks=[], stub=stub,
                                 **(dict(sow_range=[mmdd(y.sow_q[0]), mmdd(y.sow_q[1])],
                                         harvest_range=[mmdd(y.harvest_q[0]), mmdd(y.harvest_q[1])],
                                         sow_rule=sow_rule_uk(cr)) if y.sow_q else {}),
                                 flags=[f for f in cr.get("flags", []) if f.startswith("STUB")] +
                                       ["лічильники ризиків (спека в цвітіння, заморозки після сходів) — пороги TODO з джерелом"]))
            prev_end = y.harvest
        else:
            end = prev_end + y.bare_days
            calendar.append(dict(year=i + 1, crop=c, sow=None, harvest=None, bare=[mmdd(prev_end + 1), mmdd(end)],
                                 risks=[], stub=False, flags=["чорний пар: увесь проміжок без культури"]))
            prev_end = end
        gaps += per_year[-1]["flags"]
    cur = name == "current"
    viol = violations_164(seq, history_tail, rules, cur)
    lin = R.check_linear([] if cur else list(history_tail), list(seq), rules)
    gaps += R.cyclic_flag(list(seq), rules) + lin.flags + R.check_constraints(list(seq), None, rules).flags + extra_flags
    gaps.append("самозабезпечення кормом не рахується: немає даних тваринництва і потреби стада (ТЗ A5)")
    if cur and viol["count"]:
        gaps = [CUR_VIOL] + [f"порушення №164: {v}" for v in viol["list"]] + gaps
    money = e["mode"] in ("money", "margin") and e.get("gross") is not None
    marginm = e["mode"] == "margin" and e["value"] is not None
    if e.get("value_missing"):
        gaps.append(f"значення «{RANK_UNITS.get(e['mode'])}» не рахується: немає т/га або ціни для {sorted(set(e['value_missing']))}")
    metrics = dict(income_p50=round(float(np.percentile(e["gross"], 50))) if money else None,
                   income_p10=round(float(np.percentile(e["gross"], 10))) if money else None,
                   margin_p50=round(e["p50"]) if marginm else None, margin_p10=round(e["p10"]) if marginm else None,
                   margin_p90=round(float(np.percentile(e["value"], 90))) if marginm else None,      # для смуги P10–P90 на сайті
                   income_p90=round(float(np.percentile(e["gross"], 90))) if money else None,
                   rank_mode=e["mode"], rank_value_unit=RANK_UNITS.get(e["mode"]),
                   rank_value_p50=round(e["p50"], 3) if e["value"] is not None else None,
                   rank_value_p10=round(e["p10"], 3) if e["value"] is not None else None,
                   yield_index_p50=round(float(np.percentile(e["idx"], 50)), 3),
                   yield_index_p10=round(float(np.percentile(e["idx"], 10)), 3),
                   water_deficit_mm=round(e["deficit"]), end_moisture_frac=round(e["end_moisture"], 2),
                   legume_share=round(e["legume"], 2), bare_days=round(e["bare"]), drying_share=round(e["drying"], 2),
                   violations_164=viol, feed_self_sufficiency=None,
                   margin_excludes_fallow_cost=bool(marginm and e.get("has_fallow")))
    stubs = any(c.get("stub") for c in calendar)
    no_yx = any(p["yield_t_ha"] is None and p["rel_yield"] is not None for p in per_year)
    conf = "low" if (stubs or no_yx or e["mode"] in ("yield_index", "none")) else         ("medium" if (not money or metrics["margin_excludes_fallow_cost"]) else "high")     # пар без витрат → не high
    prof, warns = [], []
    if costs is not None:
        for c in dict.fromkeys(x for x in seq if sim.crops[x]["group"] != "fallow"):
            if costs.get(c) is not None:
                py = cfg["profitability_year"]
                pc = CO.cost_ha(c, fld.oblast_uk, py, "prod_cost_uah_ha", cfg["cost_outlier_factor"], str(ROOT / cfg["costs_file"]))
                line, w = CO.profitability_line(c, sim.crops[c]["name_uk"], fld.oblast_uk, pc, py)
                prof.append(line)
                if w:
                    warns.append(w)
    near0 = (marginm and money and name != "current" and e["p10"] < 0
             and e["p50"] <= cfg.get("near_zero_margin_frac", 0.1) * float(np.percentile(e["gross"], 50)))
    gaps = ([CLIMATE_RISK] if near0 else []) + warns + gaps
    return dict(name=name, sequence=list(seq), sequence_uk=[sim.crops[c]["name_uk"] for c in seq],
                per_year=per_year, metrics=metrics, calendar=calendar,
                explain=dict(why="", data=[], benefits=[], gaps=list(dict.fromkeys(gaps)), agronomist_check=[],
                             profitability=prof),
                confidence=conf)


def why_not_repeat(cur_s: dict, rec_s: dict) -> dict:
    """Порівняльний блок для поточної з порушеннями №164: без числового штрафу, лише факти поточна vs рекомендована."""
    mc, mr = cur_s["metrics"], rec_s["metrics"]
    rows = [dict(metric="violations_164", label="порушення №164", current=mc["violations_164"]["count"],
                 recommended=mr["violations_164"]["count"]),
            dict(metric="end_moisture_frac", label="запас вологи на кінець ротації, частка TAW",
                 current=mc["end_moisture_frac"], recommended=mr["end_moisture_frac"]),
            dict(metric="drying_share", label="частка культур, що сушать ґрунт",
                 current=mc["drying_share"], recommended=mr["drying_share"])]
    lines = [f"порушення №164: поточна {rows[0]['current']} ({'; '.join(mc['violations_164']['list'])}) — "
             f"рекомендована ({rec_s['name']}) {rows[0]['recommended']}",
             f"запас вологи на кінець ротації: поточна {mc['end_moisture_frac']:.0%} TAW — рекомендована {mr['end_moisture_frac']:.0%} TAW",
             f"частка культур-«сушильників»: поточна {mc['drying_share']:.0%} — рекомендована {mr['drying_share']:.0%}"]
    if mc.get("margin_p50") is not None and mr.get("margin_p50") is not None and mc["margin_p50"] > mr["margin_p50"]:
        lines.append("маржа поточної вища, але не враховує наслідків порушень №164 (хвороби, висушення ґрунту) — штраф у маржу не закладено")
    return dict(title=WHY_NOT_REPEAT, compare_with=rec_s["name"], recommended_sequence_uk=rec_s["sequence_uk"],
                rows=rows, lines=lines)


def _why(name, e, cur):
    crit = RANK_UNITS.get(e["mode"], "—")
    t = {"max_income": f"найвищий P50 за критерієм «{crit}» серед послідовностей, що проходять №164 і календар",
         "min_risk": f"найвищий P10 (сухі роки) за критерієм «{crit}»",
         "balanced": f"найкращий зважений бал по фронту Парето («{crit}» P50 і P10, вода, ґрунт; ваги — optimize.yaml)",
         "water": f"степ: найкращий бал за запасом вологи на кінець ротації і P10 «{crit}» (фронт Парето за цими двома; "
                  "ваги water_weights — optimize.yaml); чорний пар дозволено, витрати на пар не враховано",
         "current": "поточна практика поля (припущення за HLS / підтвердження фермера) — точка порівняння",
         "own_machinery": f"найвищий P50 за критерієм «{crit}» серед уже порахованих послідовностей, для яких не потрібна "
                          f"нова техніка збирання (наявна — з культур поточної практики за HLS; {MC.RENT_NOTE})"}[name]
    if e["mode"] == "yield_index":
        t = f"{DEMO_LABEL}. " + t
    b = []
    if cur is not None and name != "current":
        if e["value"] is not None and cur["value"] is not None:
            b.append(f"«{crit}» P50 {e['p50'] - cur['p50']:+.3g} до поточної")
        b.append(f"дефіцит води {e['deficit'] - cur['deficit']:+.0f} мм/сезон до поточної")
        b.append(f"частка бобових {e['legume']:.0%} (поточна {cur['legume']:.0%})")
        b.append(f"волога на кінець ротації {e['end_moisture']:.0%} TAW (поточна {cur['end_moisture']:.0%})")
    return t, b


# =====================================================================================
# Головна функція
# =====================================================================================
# =====================================================================================
# «Ефект у грошах» і пресети — лише нові виходи поверх оцінки (вибір стратегій не змінюється)
# =====================================================================================
PRESETS_YAML = Path(__file__).resolve().parent / "presets.yaml"
MONEY_NOTE = ("P10/P50/P90 — перцентилі за 25 роками погоди; накопичена сума рахується в кожному році погоди окремо, "
              "тому P50 суми ≠ сума P50 по роках")


def _q(x) -> dict:
    return {k: round(float(np.percentile(x, p))) for k, p in (("p10", 10), ("p50", 50), ("p90", 90))}


def money_block(e: dict, area: float | None, start_year: int) -> dict | None:
    """Маржа по роках плану і накопичена, грн/га і грн/поле (area_ha). Лише режим margin."""
    if e.get("mode") != "margin" or e.get("rows") is None:
        return None
    r = e["rows"]
    cum = r.cumsum(0)
    f = (lambda x: _q(x * area)) if area else (lambda x: None)   # noqa: E731
    return dict(area_ha=area, years=[dict(season=start_year + i, margin_ha=_q(r[i]), cumulative_ha=_q(cum[i]),
                                          cumulative_field=f(cum[i])) for i in range(len(r))],
                total_ha=_q(cum[-1]), total_field=f(cum[-1]), excludes_fallow_cost=bool(e.get("has_fallow")), note=MONEY_NOTE)


def vs_current(e: dict, cur: dict | None, area: float | None, start_year: int, cur_viol: int) -> dict | None:
    """Різниця з поточною в тих самих роках погоди: delta 4 роки (P50, P10), рік просідання, рік беззбитковості."""
    if cur is None or e.get("rows") is None or cur.get("rows") is None:
        return None
    d = e["rows"] - cur["rows"]
    cd = d.cumsum(0)
    y50 = [float(np.percentile(d[i], 50)) for i in range(len(d))]
    c50 = [float(np.percentile(cd[i], 50)) for i in range(len(cd))]
    down = [start_year + i for i, v in enumerate(y50) if v < 0]
    be = next((start_year + i for i in range(len(c50)) if all(v >= 0 for v in c50[i:])), None)
    tot = dict(p50=round(c50[-1]), p10=round(float(np.percentile(cd[-1], 10))))
    return dict(delta_vs_current_uah_ha=tot,
                delta_vs_current_uah_field={k: round(v * area) for k, v in tot.items()} if area else None,
                years=[dict(season=start_year + i, delta_ha_p50=round(y50[i]), cum_delta_ha_p50=round(c50[i]),
                            cum_delta_field_p50=round(c50[i] * area) if area else None) for i in range(len(d))],
                drawdown_year=down[0] if down else None, drawdown_years=down, breakeven_year=be,
                current_violates_164=cur_viol > 0,
                rule=("drawdown_year — перший сезон, де маржа стратегії P50 нижча за поточну в той самий рік погоди; "
                      "breakeven_year — перший сезон, з якого накопичена різниця P50 ≥ 0 до кінця плану (null — не окупається)"))


def load_presets() -> dict:
    with open(PRESETS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def eval_presets(K, sim, crops, yx, mode, uv, costs, fld, cfg, rules, base_hist, cur, cur_viol, allow_stubs,
                 sf_fn=None) -> list[dict]:
    """Фіксовані сівозміни без пошуку. Немає параметрів / т/га / ціни / календаря → status no_data, числа null, причини."""
    P = load_presets()
    doc = C.load_yaml()
    status = {s.crop: s for s in C.all_status(doc, fld.zone, allow_stubs)}
    amb = P.get("ambiguous", {})
    name = lambda c: amb[c]["name_uk"] if c in amb else doc["crops"].get(c, {}).get("name_uk") or R.load_rules()["norm164"].get(c, {}).get("name_uk", c)  # noqa: E731
    out = []
    for p in P["presets"]:
        rot = p["rotation"]
        seq = tuple(rot[i % len(rot)] for i in range(K))
        reasons = []
        for c in dict.fromkeys(seq):
            if c in amb:
                vs = amb[c]["variants"]
                blk = [f"{doc['crops'][v]['name_uk']}: " + "; ".join(status[v].reasons) for v in vs if not status[v].ready]
                reasons.append(f"{amb[c]['name_uk']} — {amb[c]['note']}; " + (" | ".join(blk) if len(blk) == len(vs)
                               else "є готовий варіант, але сайт не каже який — не підставляємо"))
            elif c not in doc["crops"]:
                reasons.append(f"{name(c)}: немає в model/crops.yaml (Kc, Ky, фази, календар)")
            elif c not in crops:
                reasons.append(f"{name(c)}: заблоковано параметрами моделі — " + "; ".join(status[c].reasons))
            elif crops[c]["group"] != "fallow" and yx.get(c) is None:
                reasons.append(f"{name(c)}: немає обласної врожайності Держстату ({fld.oblast_uk}) — т/га не рахується")
            elif mode in uv and uv[mode].get(c) is None:
                reasons.append(f"{name(c)}: немає ціни або витрат (режим {mode})")
        rseq = [amb[c]["variants"][0] if c in amb else c for c in seq]          # для №164: одна норма для варіантів
        try:
            viol = violations_164(rseq, base_hist, rules, False)
        except KeyError as ex:
            viol = dict(count=None, list=[f"№164 не перевірено: {ex}"])
        e = None
        if not reasons:
            res, why = sim.run(seq)
            if res is None:
                reasons.append(why[0])
            else:
                e = evaluate(seq, res, sim, yx, mode, uv, costs, sf_fn(seq) if sf_fn else None)
        item = dict(id=p["id"], name_uk=p["name_uk"], src=p["src"], rotation=rot, sequence=list(seq),
                    sequence_uk=[name(c) for c in seq],
                    plan_note=(f"ротація з {len(rot)} полів; роки плану = поля 1–{K}" + (" по колу" if len(rot) < K else "")),
                    status="ok" if e is not None else "no_data", reasons=reasons, violations_164=viol,
                    metrics=None, money=None, vs_current=None)
        if e is not None:
            marg = e["mode"] == "margin" and e["value"] is not None
            item["metrics"] = dict(margin_p10=round(e["p10"]) if marg else None, margin_p50=round(e["p50"]) if marg else None,
                                   margin_p90=round(float(np.percentile(e["value"], 90))) if marg else None,
                                   end_moisture_frac=round(e["end_moisture"], 2), water_deficit_mm=round(e["deficit"]),
                                   margin_excludes_fallow_cost=bool(marg and e["has_fallow"]))
            item["money"] = money_block(e, fld.area_ha, cfg["plan_start_year"])
            item["vs_current"] = vs_current(e, cur, fld.area_ha, cfg["plan_start_year"], cur_viol)
        out.append(item)
    return out


def optimize_field(field_id: str, allow_stubs: bool = False, K: int | None = None, farmer: dict | None = None,
                   soil_texture: str | None = None, sim_kwargs: dict | None = None, calib: str | None = None,
                   rank: str = "auto", history_confirmed: dict | None = None, write: bool = True,
                   prices_snapshot: str | None = None, cpt_port_as_is: bool = False, prices_file: str | None = None,
                   prices_by_oblast: bool | None = None, yield_file: str | None = None,
                   cost_year: int | None = None, cost_column: str | None = None,
                   sunflower_effect: bool | None = None) -> dict:
    t0 = time.time()
    cfg = load_cfg()
    K = K or cfg["years"]
    sim_kwargs = dict(sim_kwargs or {})
    rules = R.load_rules()
    farmer = {**cfg["farmer_defaults"], **(farmer or {})}
    fld = M.field_profile(field_id, allow_stubs)
    sim = M.SequenceSimulator(fld, K=K, allow_stubs=allow_stubs, soil_texture=soil_texture, **sim_kwargs)
    # поточна = спостереження HLS → здійсненна за визначенням: окремий симулятор без календарного відсікання озимих
    sim_cur = M.SequenceSimulator(fld, K=K, allow_stubs=allow_stubs, soil_texture=soil_texture, observed_practice=True, **sim_kwargs)
    crops = sim.crops
    groups = {c: v["group"] for c, v in crops.items()}
    pfile = prices_file or cfg["prices_file"]
    snap = prices_snapshot or (cfg["prices_snapshot"] if not prices_file else None)
    by_ob = cfg["prices_by_oblast"] if prices_by_oblast is None else prices_by_oblast
    fallback = None
    if by_ob:
        ob_snap = cfg["prices_oblast_pattern"].format(oblast=fld.oblast)
        if ob_snap in MK.snapshots(ROOT / pfile):
            snap, fallback = ob_snap, cfg["prices_snapshot"]
    market = MK.load_market(prices_path=ROOT / pfile, snapshot=snap, cpt_port_as_is=cpt_port_as_is,
                            known_crops=set(C.load_yaml()["crops"]), fallback_snapshot=fallback)
    livestock = LV.load_livestock()
    yfile = str(ROOT / (yield_file or cfg["yield_file"]))
    yx, single = yx_table(fld, crops, allow_stubs, calib or cfg["yx_calibration"], sim_kwargs, yfile)

    # ---- культури для стратегій: лише з т/га (+ пар) і, в режимі грошей/корму, з цінністю тонни; решта — окремим списком
    fallow = [c for c in crops if crops[c]["group"] == "fallow"]
    with_yx = [c for c in crops if yx.get(c) is not None]
    cyear = cost_year or cfg["cost_year"]
    ccol = cost_column or cfg["cost_column"]
    costs = {c: CO.cost_ha(c, fld.oblast_uk, cyear, ccol, cfg["cost_outlier_factor"], str(ROOT / cfg["costs_file"]))
             for c in crops if crops[c]["group"] != "fallow"}
    uv = add_margin(unit_values(with_yx, fld, market, livestock), costs)
    mode, rank_flags = choose_rank(rank, uv)
    ranked = [c for c in with_yx if mode not in uv or uv[mode][c] is not None]
    strat_crops = ranked + fallow
    q = cfg["quantiles"]

    def why_out(c):
        if c not in with_yx:
            return f"перспективна, але без даних для т/га: немає Держстату ({Path(yfile).name}) для {fld.oblast_uk} — у стратегіях не бере участі"
        return f"перспективна, але без ціни/цінності в режимі {mode} (зріз {market.snapshot}) — у стратегіях не бере участі"
    no_data = [dict(crop=c, crop_uk=crops[c]["name_uk"],
                    rel_yield_single_season=q3(single[c], q) if single.get(c) is not None else None,
                    price=market.channel(c, fld.lat, fld.lon)["net_price_uah_t"],
                    flags=[why_out(c)] + [f for f in crops[c].get("flags", []) if f.startswith("STUB")])
               for c in crops if c not in strat_crops]
    for s_ in C.all_status(C.load_yaml(), fld.zone, allow_stubs):          # заблоковані параметрами (Ky/календар/Kc)
        if not s_.ready:
            no_data.append(dict(crop=s_.crop, crop_uk=s_.name_uk, rel_yield_single_season=None,
                                price=market.channel(s_.crop, fld.lat, fld.lon)["net_price_uah_t"],
                                flags=["заблоковано параметрами моделі: " + "; ".join(s_.reasons)]))

    hist = field_history(field_id, history_confirmed)
    today = date.fromisoformat(cfg["today"])
    past_sow = {c for c, v in crops.items() if v["season"] == "winter"
                and date(cfg["plan_start_year"] - 1, *map(int, v["calendar"]["sow"].split("-"))) < today}
    branches = R.history_branches(hist, rules, plan_start_year=cfg["plan_start_year"])
    base_hist = branches[0][1]
    sf_on = cfg.get("sunflower_return_effect", False) if sunflower_effect is None else sunflower_effect
    sf_hist = branches[-1][1]            # ефект соняшнику — за гілкою плану (найсуворіша: «можливо соняшник» = соняшник)
    sf_fn = (lambda sq: R.sunflower_multipliers(sf_hist, list(sq), fld.zone, rules)) if sf_on else None  # noqa: E731

    # ---- перебір із відсіканням (№164 за найменш суворою гілкою, календар, фермер)
    cand, n_cal, n_wam, reasons = [], 0, 0, {}

    def rec(prefix):
        nonlocal n_cal, n_wam
        if len(prefix) == K:
            cand.append(prefix)
            return
        for c in strat_crops:
            p = prefix + (c,)
            if c in farmer["forbidden"] or c in farmer["no_machinery_for"]:
                continue
            if not prefix and c in past_sow and c != farmer.get("sown_winter_crop"):
                continue
            if not R.check_linear(base_hist, list(p), rules).ok:
                continue
            res, why = sim.run(p)
            if res is None:
                n_cal += 1
                if prefix and prefix[-1] == "maize" and c == "winter_wheat":
                    n_wam += 1
                reasons[why[0][:60]] = reasons.get(why[0][:60], 0) + 1
                continue
            rec(p)
    if mode != "none" and ranked:
        rec(())
    ev = []
    for seq in cand:
        if not R.check_constraints(list(seq), farmer, rules).ok:
            continue
        res, _ = sim.run(seq)
        e = evaluate(seq, res, sim, yx, mode, uv, costs, sf_fn(seq) if sf_fn else None)
        e["branches_ok"] = [R.check_linear(h, list(seq), rules).ok for _, h in branches]
        ev.append(e)

    # ---- поточна стратегія (варіанти для невідомих років)
    variants, cur_flags = current_variants(hist, K, rules, cfg["plan_start_year"], cfg["current_max_lag_years"],
                                           cfg["current_max_unknown_years"])
    cur, cur_label, cur_alt = None, None, []
    uk = lambda sq: " → ".join(crops[c]["name_uk"] if c in crops else c for c in sq)  # noqa: E731
    for label, seq in variants:
        if not all(c in crops for c in seq):
            cur_flags.append(f"поточна ({label}) {uk(seq)}: є культури без параметрів")
            continue
        res, why = sim_cur.run(seq)
        if res is None:
            cur_flags.append(f"поточна ({label}) {uk(seq)}: {why[0]}")
            continue
        e = evaluate(seq, res, sim_cur, yx, mode, uv, costs, sf_fn(seq) if sf_fn else None)
        e["obs_flags"] = [f for f in why if f.startswith("фактична практика")]      # пізня сівба озимої в поточній
        if cur is None:
            cur, cur_label = e, label
        else:
            cur_alt.append((label, e))

    # ---- стратегії по гілках історії (основна — найсуворіша, остання)
    no_fallow_in = set(cfg.get("fallow_forbidden_in", []))
    with_water = fld.zone in cfg.get("water_strategy_zones", [])

    def pick(ok_idx):
        """max_income/balanced — без пару (немає витрат на пар з джерелом); min_risk — усі; water — лише степ, пар дозволено."""
        if not ok_idx:
            return {}, 0
        front = [ok_idx[i] for i in pareto([ev[i] for i in ok_idx])]
        nf = [i for i in ok_idx if not ev[i]["has_fallow"]]
        front_nf = [nf[i] for i in pareto([ev[i] for i in nf])] if nf else []
        src = lambda n: front_nf if n in no_fallow_in else front  # noqa: E731
        out = {}
        if src("max_income"):
            out["max_income"] = max(src("max_income"), key=lambda i: (ev[i]["p50"], ev[i]["p10"]))
        if src("min_risk"):
            out["min_risk"] = max(src("min_risk"), key=lambda i: (ev[i]["p10"], ev[i]["p50"]))
        if src("balanced"):
            fb = src("balanced")
            out["balanced"] = fb[int(np.argmax(balanced_score(ev, fb, cfg["weights"])))]
        if with_water:
            out["water"] = water_pick(ev, ok_idx, cfg["water_weights"])
        return out, len(front)

    per_branch = []
    for bi, (label, h) in enumerate(branches):
        ok = [i for i, e in enumerate(ev) if e["branches_ok"][bi]]
        p, nf = pick(ok)
        per_branch.append(dict(label=label, n_candidates=len(ok), n_pareto=nf,
                               strategies={k: list(ev[i]["seq"]) for k, i in p.items()}, _pick=p))
    main = per_branch[-1]
    branch_flags = list(rank_flags)
    if len(branches) > 1:
        branch_flags.append(f"попередник не підтверджений: {branches[1][0]} — план розраховано для цієї (суворішої) гілки")
        other = per_branch[0]
        if other["strategies"] != main["strategies"]:
            branch_flags.append(f"якщо {branches[0][0]}: " + "; ".join(f"{k}: {' → '.join(v)}" for k, v in other["strategies"].items()))
        elif main["strategies"]:
            branch_flags.append("гілка «соняшнику не було» дає ті самі стратегії")
    if n_wam:
        branch_flags.append(f"відфільтровано {n_wam} префіксів «кукурудза → пшениця озима»: {WHEAT_AFTER_MAIZE}")
    if no_data:
        branch_flags.append("не брали участі в стратегіях (немає т/га): " + ", ".join(d["crop_uk"] for d in no_data))

    strategies = []
    if cur is not None:
        s = strategy_json("current", cur, sim_cur, yx, market, livestock, fld, cfg, cur.get("obs_flags", []) + cur_flags + rank_flags, rules, groups, base_hist, costs if mode == "margin" else None)
        s["explain"]["why"], s["explain"]["benefits"] = _why("current", cur, None)
        if s["metrics"]["violations_164"]["count"]:
            s["explain"]["why"] = f"{CUR_VIOL}. " + s["explain"]["why"]
        s["assumption"] = cur_label
        s["variants"] = [dict(assumption=l, sequence=list(e["seq"]),
                              sequence_uk=[crops[c]["name_uk"] for c in e["seq"]],
                              violations_164=violations_164(e["seq"], [], rules, True),
                              rank_value_p50=round(e["p50"], 3) if e["value"] is not None else None,
                              yield_index_p50=round(float(np.percentile(e["idx"], 50)), 3)) for l, e in cur_alt]
        strategies.append(s)
    for name in STRATEGY_NAMES:
        if name not in main["_pick"]:
            if name in no_fallow_in and main["_pick"]:
                branch_flags.append(f"стратегія {name} не побудована: без чорного пару немає допустимих послідовностей "
                                    "(немає витрат на пар з джерелом)")
            continue
        e = ev[main["_pick"][name]]
        sflags = [FALLOW_FORBIDDEN] if (name in no_fallow_in and fallow) else []
        if name == "water" and e["has_fallow"] and mode == "margin":
            sflags.append(f"{FALLOW_NO_COST} — маржа послідовності з паром завищена (пар = 0 грн замість від'ємної)")
        s = strategy_json(name, e, sim, yx, market, livestock, fld, cfg, sflags + branch_flags + ([] if cur else cur_flags),
                          rules, groups, base_hist, costs if mode == "margin" else None)
        s["explain"]["why"], s["explain"]["benefits"] = _why(name, e, cur)
        same = [x["name"] for x in strategies if x["sequence"] == s["sequence"] and x["name"] != "current"]
        if same:
            s["explain"]["why"] += f" (збігається зі стратегією {same[0]} — на цьому полі одна послідовність найкраща за кількома критеріями)"
        strategies.append(s)

    # ---- техніка збирання (D27): лише позначки + вибір серед уже порахованих кандидатів; старі стратегії не змінюються
    have, have_flags = MC.owned(hist, cfg["plan_start_year"])
    n_old = len(strategies)
    own_i = None
    if main["_pick"]:
        ok_main = [i for i, e in enumerate(ev) if e["branches_ok"][-1]
                   and not ("max_income" in no_fallow_in and e["has_fallow"])
                   and set(MC.needs(e["seq"])) <= have]
        if ok_main:
            own_i = max(ok_main, key=lambda i: (ev[i]["p50"], ev[i]["p10"]))
    if own_i is not None:
        e = ev[own_i]
        s = strategy_json("own_machinery", e, sim, yx, market, livestock, fld, cfg,
                          ([FALLOW_FORBIDDEN] if ("max_income" in no_fallow_in and fallow) else []) + branch_flags
                          + ([] if cur else cur_flags), rules, groups, base_hist, costs if mode == "margin" else None)
        s["explain"]["why"], s["explain"]["benefits"] = _why("own_machinery", e, cur)
        same = [x["name"] for x in strategies if x["sequence"] == s["sequence"]]
        if same:
            s["explain"]["why"] += f" (збігається зі стратегією {same[0]})"
        strategies.append(s)
    for s in strategies:
        s["machinery"] = dict(MC.badge(s["sequence"], have), owned=sorted(have), owned_flags=have_flags, note=MC.RENT_NOTE)

    # ---- ефект у грошах (нові виходи): маржа по роках / накопичена, на га і на поле; різниця з поточною
    cur_viol = strategies[0]["metrics"]["violations_164"]["count"] if (cur is not None and strategies) else 0
    e_by = {n: ev[i] for n, i in main["_pick"].items()} | ({"current": cur} if cur is not None else {}) \
        | ({"own_machinery": ev[own_i]} if own_i is not None else {})
    for s in strategies:
        s["metrics"]["money"] = money_block(e_by[s["name"]], fld.area_ha, cfg["plan_start_year"])
        if s["name"] != "current":
            s["metrics"]["vs_current"] = vs_current(e_by[s["name"]], cur, fld.area_ha, cfg["plan_start_year"], cur_viol)
    presets = eval_presets(K, sim, crops, yx, mode, uv, costs, fld, cfg, rules, base_hist, cur, cur_viol, allow_stubs, sf_fn)

    if cur is not None and strategies and strategies[0]["name"] == "current" and             strategies[0]["metrics"]["violations_164"]["count"]:
        rec_s = next((s for s in strategies if s["name"] == "balanced"), None)
        if rec_s:
            strategies[0]["explain"]["why_not_repeat"] = why_not_repeat(strategies[0], rec_s)
    zr0 = max(v["zr_m"] for v in crops.values() if v["group"] != "fallow")
    soil = M.S.field_texture(field_id, zr0, soil_texture)
    data_src = [f"погода: NASA POWER, вузол {fld.node} (2001–2025, 25 сценаріїв), висота клітинки POWER",
                f"ґрунт: SoilGrids 2.0, клас {soil.get('texture')} (шари до {zr0} м); " + "; ".join(soil.get("flags", [])),
                f"історія: HLS {hist[0]['year']}–{hist[-1]['year']} ({hist[0]['src']})" if hist else "історія: немає",
                f"Yx: Держстат ({Path(yfile).relative_to(ROOT)}), калібрування A — відхилення від ТЗ A3 (docs/decisions.md D1)",
                f"ціни: {pfile}, зріз {market.snapshot}" + (f" (fallback {fallback})" if fallback else "")
                + (" (CPT_port як є — чутливість)" if cpt_port_as_is else "")
                + "; ринок: data/market/*; корм: model/livestock.yaml",
                "параметри культур: FAO-56/FAO-66 (model/crops.yaml)", "№164: model/rules.yaml"]
    allg = [g for s in strategies[:n_old] for g in s["explain"]["gaps"]]    # own_machinery не змінює перевірки агронома
    agr = []
    if any(g.startswith("STUB: календар") for g in allg):
        agr.append(f"календарі сівби для зони {fld.zone} — заглушки (STUB), потрібні дати R2/R3")
    blocked = [s.name_uk for s in C.all_status(C.load_yaml(), fld.zone, allow_stubs) if not s.ready]
    if blocked:
        agr.append("не розглядались (немає параметрів з джерелом): " + ", ".join(blocked))
    if no_data:
        agr.append(f"немає обласної врожайності Держстату ({fld.oblast_uk}) для: " + ", ".join(d["crop_uk"] for d in no_data))
    if past_sow and not farmer.get("sown_winter_crop"):
        agr.append(f"озимі в році 1 ({', '.join(sorted(past_sow))}) не розглядались: дата сівби вже минула ({cfg['today']}); "
                   "якщо поле засіяне — вкажіть sown_winter_crop")
    if not soil_texture:
        t19 = M.S.field_texture(field_id, zr0).get("taw_mm_per_m")
        wv = M.S.field_texture(field_id, zr0, taw_source="wv_all").get("taw_mm_per_m")
        if t19 and wv and abs(t19 - wv) / t19 > cfg["taw_discrepancy_flag_frac"]:
            agr.append(f"TAW цього поля: FAO-56 Т19 {t19:.0f} мм/м проти SoilGrids wv {wv:.0f} мм/м (до {zr0} м) — перевірити")
    if n_wam:
        agr.append(WHEAT_AFTER_MAIZE)
    if any("бобові після бобових" in g for g in allg):
        agr.append("бобові після бобових у стратегіях — правило-каркас без джерела (rules.yaml), оцінити")
    for s in strategies:
        s["explain"]["data"] = data_src
        s["explain"]["agronomist_check"] = agr
    bal = next((s for s in strategies if s["name"] == "balanced"), None)
    if bal:
        ns = dict(crop=bal["sequence"][0], crop_uk=bal["sequence_uk"][0],
                  why=f"перший рік стратегії «balanced» ({' → '.join(bal['sequence_uk'])}); " + bal["explain"]["why"])
    else:
        ns = dict(crop=None, crop_uk=None,
                  why="рекомендації немає: " + ("; ".join(rank_flags) if mode == "none" else
                                                 "немає культур з т/га" if not ranked else "немає допустимих послідовностей"))
    out = dict(field_id=field_id, area_ha=fld.area_ha, oblast=fld.oblast_uk, zone=fld.zone,
               ranking=dict(mode=mode, unit=RANK_UNITS.get(mode), label=DEMO_LABEL if mode == "yield_index" else None,
                            flags=rank_flags, prices_file=pfile, prices_snapshot=market.snapshot, prices_fallback=fallback,
                            cpt_port_as_is=cpt_port_as_is, yield_file=str(Path(yfile).relative_to(ROOT)),
                            costs_file=cfg["costs_file"], cost_year=cyear, cost_column=ccol,
                            sunflower_return_effect=bool(sf_on)),
               next_season=ns, strategies=strategies, presets=presets, candidates_without_data=no_data,
               history=[dict(year=r["year"], c=r["c"], sub=r["sub"], confirmed_crop=r["confirmed_crop"]) for r in hist],
               history_source=dict(source="HLS 30 м", window=hls_field(field_id)[0], fid=int(hls_field(field_id)[1].lstrip("f")),
                                   file=f"out/hls/{hls_field(field_id)[0]}_ndvi_seasons.csv"),
               history_confirmed={str(r["year"]): r["confirmed_crop"] for r in hist if r["confirmed_crop"]},
               history_branches=[dict(label=b["label"], n_candidates=b["n_candidates"], n_pareto=b["n_pareto"],
                                      strategies=b["strategies"]) for b in per_branch],
               run=dict(seconds=round(time.time() - t0, 1), n_feasible=len(ev), n_calendar_pruned=n_cal,
                        prune_reasons=reasons, crops=list(crops), strategy_crops=strat_crops, plan_years=K,
                        plan_start_year=cfg["plan_start_year"], sim_stats=sim.stats, field_flags=fld.flags,
                        market_flags=market.flags, livestock_flags=livestock.flags,
                        unit_values={m: {c: v for c, v in d.items()} for m, d in uv.items()},
                        yx_t_ha={k: (round(v, 2) if v else None) for k, v in yx.items()}))
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"strategies_{field_id.replace(':', '_')}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--field")
    ap.add_argument("--pilots", action="store_true")
    ap.add_argument("--allow-stubs", action="store_true")
    ap.add_argument("--years", type=int, default=None)
    ap.add_argument("--soil-texture", default=None)
    ap.add_argument("--rank", default="auto", choices=RANK_MODES)
    ap.add_argument("--confirm", action="append", default=[], help="РІК=crop_id, напр. 2022=winter_wheat (повторюваний)")
    ap.add_argument("--prices-snapshot", default=None, help="зріз цін (за замовчуванням optimize.yaml: prices_snapshot)")
    ap.add_argument("--cpt-port-as-is", action="store_true", help="CPT_port «як є» (лише чутливість)")
    ap.add_argument("--prices-file", default=None, help="напр. data/raw/prices_candidates.csv (UUB/EGB)")
    ap.add_argument("--prices-by-oblast", action="store_true", help="зріз DSSU_2025_<oblast> з fallback на DSSU_2025")
    ap.add_argument("--yield-file", default=None, help="напр. data/raw/yield/derzhstat_yield_enterprises.csv")
    ap.add_argument("--cost-year", type=int, default=None)
    ap.add_argument("--cost-column", default=None, choices=["prod_cost_uah_ha", "full_cost_uah_ha"])
    a = ap.parse_args()
    conf = dict(x.split("=") for x in a.confirm)
    fields = PILOT_FIELDS if a.pilots else [a.field]
    for f in fields:
        o = optimize_field(f, a.allow_stubs, a.years, soil_texture=a.soil_texture, rank=a.rank, history_confirmed=conf,
                           prices_snapshot=a.prices_snapshot, cpt_port_as_is=a.cpt_port_as_is, prices_file=a.prices_file,
                           prices_by_oblast=a.prices_by_oblast or None, yield_file=a.yield_file,
                           cost_year=a.cost_year, cost_column=a.cost_column)
        print(f"{f}: {o['run']['seconds']} с, режим {o['ranking']['mode']}, допустимих {o['run']['n_feasible']}, "
              f"наступний сезон: {o['next_season']['crop_uk']}; без даних т/га: {[d['crop'] for d in o['candidates_without_data']]}")
        for s in o["strategies"]:
            m = s["metrics"]
            print(f"   {s['name']:<11} {' → '.join(s['sequence_uk'])}  v50={m['rank_value_p50']} v10={m['rank_value_p10']} "
                  f"def={m['water_deficit_mm']} viol164={m['violations_164']['count']} conf={s['confidence']}"
                  + (f"  [{s.get('assumption')}; +{len(s.get('variants', []))} варіанти]" if s["name"] == "current" else ""))


if __name__ == "__main__":
    main()
