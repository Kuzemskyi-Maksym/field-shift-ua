"""Симулятор сівозміни: FAO-56 водний баланс з переносом вологи між сезонами, 25 стартових років погоди.

Фізика сезону — та сама, що в baseline_model.py (ET0 Penman–Monteith імпортовано без змін; бакет FAO-56 розд. 8;
Ya/Yx = 1 − Ky(1 − ΣETa/ΣETc)). Нове відносно baseline v0 (кожне — з джерелом у YAML):
  • параметри культур із model/crops.yaml (FAO-56 Т11/12/22/24, FAO-66);
  • TAW = 1000(θFC−θWP)·Zr, текстура SoilGrids → USDA → FAO-56 Т19 (model/soil.py);
  • Kc голого ґрунту — FAO-56 розд. 11 / Annex 7 (рівн. 7-3, 7-7, 59) з погоди, а не константа 0.3;
  • p = p_T22 + 0.04(5 − ETc) (FAO-56 Т22, прим. 2);
  • Kc_mid / Kc_end — поправка на клімат FAO-56 рівн. 62/65, RHmin за рівн. 63 (POWER T2MDEW, T2M_MAX);
  • волога переноситься між культурами (умовності — soils.yaml: simulation).

Без мережі: погода з data/raw/power (scripts/fetch_power.py), ґрунт з data/raw/soil (scripts/fetch_soilgrids.py).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from baseline_model import KC_BARE as BASELINE_KC_BARE, POINTS, et0_pm  # noqa: E402  — ET0 без змін

from model import crops as C  # noqa: E402
from model import soil as S  # noqa: E402

POWER_DIR = ROOT / "data" / "raw" / "power"
YIELD_CSV = ROOT / "data" / "raw" / "yield" / "derzhstat_yield.csv"
ZONES_YAML = Path(__file__).resolve().parent / "zones.yaml"
YEARS = list(range(2001, 2026))
NY = len(YEARS)
WX_COLS = ["PRECTOTCORR", "ET0", "T2M_MAX", "T2M_MIN", "T2MDEW", "WS2M"]


# =====================================================================================
# Рівняння FAO-56 (коефіцієнти — частина рівнянь, номери вказано)
# =====================================================================================
def e_sat(t):
    """FAO-56 рівн. 11, кПа."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def rh_min_eq63(tdew_mean, tmax_mean):
    """FAO-56 рівн. 63: RHmin = 100·e°(Tdew)/e°(Tmax), середні за фазу."""
    return 100 * e_sat(tdew_mean) / e_sat(tmax_mean)


def kc_climate_eq62(kc_tab, u2, rhmin, h):
    """FAO-56 рівн. 62 (=65 для Kc_end): межі 1≤u2≤6 м/с, 20≤RHmin≤80 %."""
    u = np.clip(u2, 1, 6)
    r = np.clip(rhmin, 20, 80)
    return kc_tab + (0.04 * (u - 2) - 0.004 * (r - 45)) * (h / 3) ** 0.3


def kc_ini_eq73(tw, et0, tew, rew, eso_factor, kc_max):
    """FAO-56 Annex 7, рівн. 7-3/7-4 (векторно)."""
    eso = eso_factor * et0
    t1 = rew / eso
    stage2 = (tew - (tew - rew) * np.exp(-(tw - t1) * eso * (1 + rew / (tew - rew)) / tew)) / (tw * et0)
    return np.minimum(np.where(tw < t1, eso / et0, stage2), kc_max)


def kc_bare(rain, et0, coarse: bool, soils: dict):
    """Kc голого ґрунту для вікна (FAO-56 розд. 11 → Annex 7). rain, et0: [N, L] → [N].

    t_w = L/(n_w + 0.5) (рівн. 7-7), події — дні з P ≥ 0.2·ET0, сусідні дні — одна подія;
    Kc між Fig. 29 (≤10 мм на подію) і Fig. 30a/b (≥40 мм) — лінійно за рівн. 59.
    """
    c = soils["bare_soil_kc"]
    L = rain.shape[1]
    e = np.maximum(et0.mean(axis=1), 0.1)          # захист від ET0≈0 узимку (ділення); див. прапорець «зима»
    wet = rain >= c["min_event_frac_et0"] * et0
    starts = wet & ~np.concatenate([np.zeros((wet.shape[0], 1), bool), wet[:, :-1]], axis=1)
    nw = starts.sum(axis=1)
    pmean = np.where(nw > 0, (rain * wet).sum(axis=1) / np.maximum(nw, 1), 0.0)
    tw = L / (nw + 0.5)
    f29 = c["fig29"]
    rew29 = np.minimum(np.maximum(f29["rew_cor"]["min"], f29["rew_cor"]["coef"] / np.sqrt(e)), f29["rew_cor"]["max"])
    k29 = kc_ini_eq73(tw, e, f29["tew_cor"], rew29, c["eso_factor"], c["kc_ini_max"])
    f30 = c["fig30a"] if coarse else c["fig30b"]
    tew30 = np.minimum(f30["tew_cor"]["max"], f30["tew_cor"]["coef"] * np.sqrt(e))
    rew30 = np.minimum(f30["rew_cor"]["max"], tew30 - 0.01)
    k30 = kc_ini_eq73(tw, e, tew30, rew30, c["eso_factor"], c["kc_ini_max"])
    lo, hi = c["light_depth_mm"], c["large_depth_mm"]
    w = np.clip((pmean - lo) / (hi - lo), 0, 1)
    return k29 + w * (k30 - k29)


# =====================================================================================
# Водний баланс (FAO-56 розд. 8) — спільне ядро для baseline-режиму і сівозміни
# =====================================================================================
def water_balance(kc, et0, rain, taw, p_tab, dr0, p_adjust=True, adj=None):
    """kc, et0, rain: [N, T]; taw, p_tab, dr0: [N] або скаляр. → (etc, eta, ks, dr_end) — [N, T], [N]."""
    N, T = kc.shape
    taw = np.broadcast_to(np.asarray(taw, float), (N,))
    p_tab = np.broadcast_to(np.asarray(p_tab, float), (N,))
    dr = np.array(np.broadcast_to(np.asarray(dr0, float), (N,)))
    etc_all = kc * et0
    eta_all = np.empty_like(etc_all)
    ks_all = np.empty_like(etc_all)
    if p_adjust:
        coef, etc_ref, p_min, p_max = adj["coef"], adj["etc_ref_mm"], adj["p_min"], adj["p_max"]   # soils.yaml, FAO56_T22_FN2
    for t in range(T):
        etc = etc_all[:, t]
        if p_adjust:
            p = np.minimum(np.maximum(p_tab + coef * (etc_ref - etc), p_min), p_max)
        else:
            p = p_tab
        raw = p * taw
        ks = np.where(dr <= raw, 1.0, np.maximum(0.0, (taw - dr) / np.maximum(taw - raw, 1e-9)))   # рівн. 84
        eta = ks * etc
        dr = np.minimum(np.maximum(dr - rain[:, t] + eta, 0.0), taw)                                # надлишок → стік
        eta_all[:, t] = eta
        ks_all[:, t] = ks
    return etc_all, eta_all, ks_all, dr


def kc_curve(T, sow, dev0, dev1, mid1, late1, kc_ini, kc_mid, kc_end):
    """Kc на днях sow..late1 включно (індекси позицій), як baseline_model.season_kc. kc_mid/kc_end: [N] або скаляр."""
    t = np.arange(sow, late1 + 1)
    kc_mid = np.atleast_1d(kc_mid)[:, None]
    kc_end = np.atleast_1d(kc_end)[:, None]
    out = np.full((kc_mid.shape[0], len(t)), float(kc_ini))
    m = (t >= dev0) & (t < dev1)
    out[:, m] = kc_ini + (kc_mid - kc_ini) * ((t[m] - dev0) / max(dev1 - dev0, 1))
    m = (t >= dev1) & (t < mid1)
    out[:, m] = np.broadcast_to(kc_mid, (kc_mid.shape[0], m.sum()))
    m = t >= mid1
    out[:, m] = kc_mid + (kc_end - kc_mid) * ((t[m] - mid1) / max(late1 - mid1, 1))
    return out


# =====================================================================================
# Погода: вузол POWER → 25 років × (K+1) блоків по 365 днів
# =====================================================================================
@lru_cache(maxsize=64)
def load_node(lat: float, lon: float):
    name = f"power_{lat:.3f}_{lon:.3f}"
    df = pd.read_csv(POWER_DIR / f"{name}.csv", parse_dates=["date"], index_col="date")
    with open(POWER_DIR / f"{name}.meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    rs = df["ALLSKY_SFC_SW_DWN"].median()
    if not 3 <= rs <= 30:
        raise ValueError(f"{name}: медіана ALLSKY_SFC_SW_DWN={rs} — не МДж/м²/добу")
    df = df.interpolate(limit=5).ffill().bfill()
    elev = float(meta["returned_geometry"]["coordinates"][2])
    df["ET0"] = et0_pm(df.T2M_MAX.values, df.T2M_MIN.values, df.RH2M.values, df.WS2M.values,
                       df.ALLSKY_SFC_SW_DWN.values, lat, elev, df.index.dayofyear.values)
    df = df[~((df.index.month == 2) & (df.index.day == 29))]
    if "T2MDEW" not in df:
        df["T2MDEW"] = np.nan
    return df, elev


@lru_cache(maxsize=64)
def weather_stack(lat: float, lon: float, K: int):
    """{col: [25, 365·(K+1)]}: рядок s — старт s (рік плану 1 = YEARS[s]), блок 0 — рік перед ним (по колу)."""
    df, _ = load_node(lat, lon)
    by = {y: df[df.index.year == y] for y in YEARS}
    for y, d in by.items():
        if len(d) != 365:
            raise ValueError(f"рік {y}: {len(d)} днів")
    return {c: np.stack([np.concatenate([by[YEARS[(s + b - 1) % NY]][c].values for b in range(K + 1)])
                         for s in range(NY)]) for c in WX_COLS}


@lru_cache(maxsize=64)
def load_tsoil(lat: float, lon: float):
    """→ ([25, 365] температура для правила сівби по роках YEARS, проксі?) — TSOIL1 з tsoil_<вузол>.csv, інакше T2M."""
    f = POWER_DIR / f"tsoil_{lat:.3f}_{lon:.3f}.csv"
    if f.exists():
        df, col, proxy = pd.read_csv(f, parse_dates=["date"], index_col="date"), "TSOIL1", False
    else:
        df, col, proxy = load_node(lat, lon)[0], "T2M", True
    df = df[~((df.index.month == 2) & (df.index.day == 29))]
    s = df[col].interpolate(limit=5).ffill().bfill()
    return np.stack([s[s.index.year == y].values for y in YEARS]), proxy


def dynamic_sow_doy(temp: np.ndarray, threshold: float, not_before: str, mean_days: int, search_end: str = "06-30"):
    """[25, 365] → (doy0 [25], знайдено [25]): перший день ≥ not_before, коли середня за mean_days днів (день і попередні) ≥ поріг."""
    k = np.ones(mean_days) / mean_days
    m = np.stack([np.convolve(r, k, mode="full")[:365] for r in temp])     # m[t] = середнє temp[t-n+1..t]
    m[:, :mean_days - 1] = -np.inf
    a, b = doy0(not_before), doy0(search_end)
    ok = m[:, a:b + 1] >= threshold
    found = ok.any(1)
    return np.where(found, a + ok.argmax(1), b), found


def doy0(mmdd: str) -> int:
    m, d = int(mmdd[:2]), int(mmdd[3:])
    return (date(2001, m, d) - date(2001, 1, 1)).days


def pos(block: int, mmdd: str) -> int:
    return block * 365 + doy0(mmdd)


# =====================================================================================
# Профіль поля
# =====================================================================================
@lru_cache(maxsize=1)
def _zones():
    with open(ZONES_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def node_of(lat, lon):
    """Вузол сітки POWER 0.5° × 0.625° (та сама формула дала 0 розбіжностей з power_lat/lon у *_fields_stats.csv)."""
    return round(round(lat / 0.5) * 0.5, 3), round(round(lon / 0.625) * 0.625, 3)


@dataclass
class Field:
    field_id: str
    lat: float
    lon: float
    node: tuple
    oblast: str
    oblast_uk: str
    zone: str
    area_ha: float | None
    flags: list = field(default_factory=list)


def field_profile(field_id: str, allow_stubs: bool = False) -> Field:
    z = _zones()
    if field_id in POINTS:
        lat, lon = POINTS[field_id][:2]                      # точка пілота (погода й ґрунт — як у baseline)
        ob, pfid = z["pilots"][field_id]["oblast"], z["pilots"][field_id]["fid"]
        st = pd.read_csv(ROOT / "out" / "fields" / f"{ob}_fields_stats.csv", usecols=["fid", "area_ha"])
        area = float(st[st.fid == pfid].area_ha.iloc[0])
    else:
        ob, fid = field_id.split(":")
        st = pd.read_csv(ROOT / "out" / "fields" / f"{ob}_fields_stats.csv", usecols=["fid", "area_ha", "lat", "lon"])
        r = st[st.fid == int(fid.lstrip("f"))].iloc[0]
        lat, lon, area = float(r.lat), float(r.lon), float(r.area_ha)
    o = z["oblasts"][ob]
    flags = ["погода — клітинка POWER ~50 км, клімат району, не поля"]
    if o["zone_src"] in C.STUB_SOURCES:
        if not allow_stubs:
            raise ValueError(f"зона для {ob} — заглушка; потрібен --allow-stubs")
        flags.append(f"STUB: зона '{o['zone']}' за областю (без джерела)")
    flags.append("площа — полігон NASA Harvest")
    return Field(field_id, lat, lon, node_of(lat, lon), ob, o["name_uk"], o["zone"], area, flags)


# =====================================================================================
# Сівозміна
# =====================================================================================
@dataclass
class YearResult:
    year: int
    crop: str
    rel_yield: np.ndarray | None      # [25] Ya/Yx або None (пар)
    etc_mm: np.ndarray
    eta_mm: np.ndarray
    stress_days: np.ndarray
    bare_days: int
    sow: int | None              # позиція; для динамічної сівби — медіана по 25 роках
    harvest: int | None
    flags: list
    sow_q: tuple | None = None   # (P10, P90) позицій сівби — лише динамічна сівба
    harvest_q: tuple | None = None
    daily: tuple | None = None   # (позиція старту сегмента, ETa [25, L] мм/добу) — лише keep_daily (діагностика ECOSTRESS)


class SequenceSimulator:
    """Симуляція послідовностей для одного поля з кешем префіксів (стан після року k залежить лише від культур 1..k)."""

    def __init__(self, fld: Field, K: int, allow_stubs: bool = False, soil_texture: str | None = None,
                 kc_climate: bool = True, p_adjust: bool = True, bare_annex7: bool = True,
                 ky_override: dict | None = None, taw_override_mm_m: float | None = None,
                 taw_source: str = "t19", season_cache: bool = True, keep_daily: bool = False,
                 observed_practice: bool = False):
        self.f, self.K = fld, K
        self.crops = C.ready_crops(fld.zone, allow_stubs)
        self.soils = S.load_soils()
        self.sim = self.soils["simulation"]
        self.wx = weather_stack(*fld.node, K)
        self.T = 365 * (K + 1)
        self.opts = dict(kc_climate=kc_climate, p_adjust=p_adjust, bare_annex7=bare_annex7)
        self.soil_texture = soil_texture
        self.taw_override = taw_override_mm_m
        self.taw_source = taw_source
        self.ky = {c: (ky_override or {}).get(c, v.get("ky")) for c, v in self.crops.items()}
        self.cache: dict[tuple, tuple] = {}
        self.flags = list(fld.flags)
        if not np.isfinite(self.wx["T2MDEW"]).all() and kc_climate:
            self.flags.append("немає T2MDEW — поправку Kc на клімат (рівн. 62/65) не застосовано")
            self.opts["kc_climate"] = False
        self._taw = {}
        self.season_cache = season_cache and not keep_daily
        self.keep_daily = keep_daily
        # фактична практика з HLS (лише «поточна»): спостереження здійсненне → озима після пізнього попередника сіється
        # max(opt, збирання попередника + 1), а не відкидається; рекомендації — з календарним фільтром, як раніше
        self.observed_practice = observed_practice
        self._seasons: dict = {}
        self._kcb: dict = {}
        self.stats = dict(segments=0, season_hits=0)
        self._sow: dict = {}
        self._sow_flags: dict = {}
        self._cs: dict = {}

    # ---- ґрунт
    def taw(self, zr):
        if zr not in self._taw:
            if self.taw_override is not None:
                self._taw[zr] = (self.taw_override * zr, ["TAW задано вручну (чутливість)"], False)
            else:
                r = S.field_texture(self.f.field_id, zr, self.soil_texture, taw_source=self.taw_source)
                coarse = r.get("texture") in self.soils["bare_soil_kc"]["coarse_textures"]
                taw = None if r["taw_mm_per_m"] is None else r["taw_mm_per_m"] * zr
                self._taw[zr] = (taw, r["flags"], coarse)
        return self._taw[zr]

    # ---- календар
    def sow_doy(self, crop) -> np.ndarray:
        """Динамічна сівба: doy0 по роках YEARS [25] (rules_of_choice.spring_dynamic_sow)."""
        if crop not in self._sow:
            r = self.crops[crop]["sow_rule"]
            temp, proxy = load_tsoil(*self.f.node)
            d, found = dynamic_sow_doy(temp, r["threshold_c"], r["not_before"], r["mean_days"])
            fl = []
            if proxy:
                fl.append("температура ґрунту оцінена за температурою повітря (T2M) — TSOIL1 для вузла не завантажено")
            if not found.all():
                fl.append(f"{crop}: поріг {r['threshold_c']} °C не досягнуто до 30.06 у {int((~found).sum())} з {NY} років — сівба 30.06")
            self._sow[crop] = d
            self._sow_flags[crop] = fl
        return self._sow[crop]

    def season(self, crop, k):
        c = self.crops[crop]
        cal = c["calendar"]
        if c["season"] == "winter":
            sow = pos(k - 1, cal["sow"])
            dev0, dev1, mid1, late1 = (pos(k, d) for d in cal["stage_dates"])
        else:
            if cal["sow"] == C.DYNAMIC:     # [25]: рядок s, блок k — погода року YEARS[(s+k−1) mod 25]
                sow = k * 365 + self.sow_doy(crop)[(np.arange(NY) + k - 1) % NY]
            else:
                sow = pos(k, cal["sow"])
            L = c["stages_days"]
            dev0 = sow + L[0]
            dev1 = dev0 + L[1]
            mid1 = dev1 + L[2]
            late1 = mid1 + L[3]
        return sow, dev0, dev1, mid1, late1

    def run(self, seq: tuple) -> tuple[list[YearResult] | None, list[str]]:
        """→ (результати по роках, прапорці) або (None, [причина]) для неможливої послідовності."""
        seq = tuple(seq)
        if seq in self.cache:
            return self.cache[seq][0], self.cache[seq][1]
        if len(seq) == 0:
            st = dict(dr=np.full(NY, np.nan), end=-1, taw=None, p=None)
            self.cache[seq] = ([], [], st)
            return [], []
        prev_res, prev_flags = self.run(seq[:-1])
        if prev_res is None:
            self.cache[seq] = (None, prev_flags, None)
            return None, prev_flags
        state = self.cache[seq[:-1]][2]
        out = self._segment(seq[-1], len(seq), state)
        if isinstance(out, str):
            self.cache[seq] = (None, [out], None)
            return None, [out]
        yr, st, fl = out
        res = prev_res + [yr]
        flags = list(dict.fromkeys(prev_flags + fl))
        self.cache[seq] = (res, flags, st)
        return res, flags

    def _segment(self, crop, k, state):
        w, sim, soils = self.wx, self.sim, self.soils
        start = state["end"] + 1
        flags = []
        if crop not in self.crops:
            return f"культура {crop} не готова (zone={self.f.zone})"
        c = self.crops[crop]
        fallow = c["group"] == "fallow"
        if fallow:
            end = pos(k, sim["fallow_plan_year_end"])
            zr = None
            if state["taw"] is None:
                taw, tf, coarse = self.taw(sim["fallow_first_zr_m"])
                flags += tf + ["пар у 1-й рік: Zr за умовністю simulation.fallow_first_zr_m"]
            else:
                taw, coarse = state["taw"], state["coarse"]
            p_tab = state["p"] if state["p"] is not None else sim["fallow_first_p"]   # p лише для Ks на голому ґрунті
            if state["p"] is None:
                flags.append("пар у 1-й рік: p для Ks голого ґрунту — умовність simulation.fallow_first_p")
            sow = harvest = None
            if end <= start:
                return f"календар: межа пару {sim['fallow_plan_year_end']} у році {k} раніше за кінець попереднього сезону"
        else:
            sow, dev0, dev1, mid1, late1 = self.season(crop, k)
            dyn = np.ndim(sow) > 0                      # динамічна сівба: позиції [25] по роках погоди
            if self.observed_practice and not dyn and c["season"] == "winter" and sow <= state["end"]:
                cal = c["calendar"]
                opt, sow = sow, state["end"] + 1            # сегменти спільні для 25 років → після найпізнішого збирання
                win_end = pos(k - 1, cal["window"][1]) if cal.get("window") else opt
                if sow > win_end:
                    flags.append(f"фактична практика з HLS: озима після пізньої ярої; у моделі сівба пізніша за рекомендовану "
                                 f"(рік {k}: {sow - opt} дн. після оптимуму, поза вікном джерела) — врожай може бути занижено")
                else:
                    flags.append(f"фактична практика з HLS: сівбу озимої зсунуто на {sow - opt} дн. після оптимуму "
                                 f"(рік {k}, після збирання попередника; у межах вікна джерела)")
                if sow >= dev0:
                    return f"календар: озима (рік {k}) — збирання попередника пізніше за початок вегетації"
            if np.min(sow) <= state["end"]:
                return (f"календар: сівба {crop} (рік {k}) раніше за збирання попередньої культури "
                        f"— неможливо з поточними датами" + (" (хоча б в одному з 25 років погоди)" if dyn else ""))
            end = harvest = int(np.max(late1)) if dyn else late1     # сегмент — до найпізнішого збирання; далі — голий ґрунт
            zr, p_tab = c["zr_m"], c["p"]
            taw, tf, coarse = self.taw(zr)
            flags += tf + (self._sow_flags[crop] if dyn else [])
        if taw is None:
            return f"TAW для {crop}: немає даних ґрунту (" + "; ".join(flags) + ")"
        dyn = sow is not None and np.ndim(sow) > 0
        if end >= self.T:
            return f"календар: {crop} виходить за горизонт симуляції"
        # перенос: зберігаємо частку виснаження
        if state["taw"] is None:
            dr0 = np.full(NY, sim["initial_dr_frac"] * taw)
            flags.append("старт ротації: профіль на ПВ 1 січня року перед ротацією (умовність)")
        else:
            dr0 = state["dr"] / state["taw"] * taw
        key = None
        if self.season_cache:
            q = sim["season_cache_round_mm"]
            dr0 = np.clip(np.round(dr0 / q) * q, 0, taw)
            key = (crop, k, start, round(taw, 6), coarse, p_tab, tuple(dr0))
            self.stats["segments"] += 1
            if key in self._seasons:
                self.stats["season_hits"] += 1
                yr, st, fl = self._seasons[key]
                return yr, dict(st), list(dict.fromkeys(flags + fl))
        sl = slice(start, end + 1)
        rain, et0 = w["PRECTOTCORR"][:, sl], w["ET0"][:, sl]
        L = end - start + 1
        if dyn:
            return self._segment_dynamic(crop, k, c, start, end, L, rain, et0, taw, p_tab, coarse, dr0, flags, key,
                                         sow, dev0, dev1, mid1, late1)
        kc = np.zeros((NY, L))
        bare_to = (sow - start) if sow is not None else L        # дні [0, bare_to) — без культури
        cfg = soils["bare_soil_kc"]
        if bare_to > 0:
            if self.opts["bare_annex7"]:
                win = sim["bare_kc_window_days"]
                for a in range(0, bare_to, win):
                    b = min(a + win, bare_to)
                    mk = (start + a, start + b, coarse)
                    if mk not in self._kcb:
                        self._kcb[mk] = kc_bare(rain[:, a:b], et0[:, a:b], coarse, soils)
                    kc[:, a:b] = self._kcb[mk][:, None]
            else:
                kc[:, :bare_to] = BASELINE_KC_BARE
                flags.append("Kc голого ґрунту = KC_BARE baseline v0 (без джерела) — режим порівняння")
        if sow is not None:
            kc_mid = np.full(NY, c["kc_mid"])
            kc_end = np.full(NY, c["kc_end"])
            if self.opts["kc_climate"]:
                h = c.get("h_m")
                if C.is_todo(h) or h is None:
                    flags.append(f"{crop}: немає h — поправку Kc на клімат не застосовано")
                else:
                    mid = slice(dev1, mid1)
                    rh = rh_min_eq63(w["T2MDEW"][:, mid].mean(1), w["T2M_MAX"][:, mid].mean(1))
                    kc_mid = kc_climate_eq62(c["kc_mid"], w["WS2M"][:, mid].mean(1), rh, h)
                    if c["kc_end"] >= 0.45:
                        late = slice(mid1, late1 + 1)
                        rh = rh_min_eq63(w["T2MDEW"][:, late].mean(1), w["T2M_MAX"][:, late].mean(1))
                        kc_end = kc_climate_eq62(c["kc_end"], w["WS2M"][:, late].mean(1), rh, h)
            kc[:, bare_to:] = kc_curve(None, sow, dev0, dev1, mid1, late1, c["kc_ini"], kc_mid, kc_end)
        etc, eta, ks, dr_end = water_balance(kc, et0, rain, taw, p_tab, dr0, self.opts["p_adjust"],
                                             soils["depletion_adjust"])
        st = dict(dr=dr_end, end=end, taw=taw, p=p_tab, coarse=coarse)
        daily = (start, eta) if self.keep_daily else None
        if sow is None:
            yr = YearResult(k, crop, None, etc.sum(1), eta.sum(1), np.zeros(NY, int), L, None, None, flags, daily=daily)
        else:
            s = slice(bare_to, L)
            etc_s, eta_s = etc[:, s].sum(1), eta[:, s].sum(1)
            rel = np.clip(1 - self.ky[crop] * (1 - eta_s / etc_s), 0, 1)
            yr = YearResult(k, crop, rel, etc_s, eta_s, (ks[:, s] < 1).sum(1), bare_to, sow, harvest, flags, daily=daily)
        if key is not None:
            flags.append(f"кеш сезону: стартова волога округлена до {sim['season_cache_round_mm']} мм")
            self._seasons[key] = (yr, st, flags)
        return yr, st, flags

    def _rowmean(self, col, a, b):
        """Середнє w[col] на [a_y, b_y) для кожного рядка (позиції [25])."""
        if col not in self._cs:
            x = self.wx[col]
            self._cs[col] = np.concatenate([np.zeros((NY, 1)), np.cumsum(x, 1)], 1)
        cs, r = self._cs[col], np.arange(NY)
        return (cs[r, b] - cs[r, a]) / np.maximum(b - a, 1)

    def _segment_dynamic(self, crop, k, c, start, end, L, rain, et0, taw, p_tab, coarse, dr0, flags, key,
                         sow, dev0, dev1, mid1, late1):
        """Ярі з динамічною сівбою: власні дати в кожному рядку; до сівби й після збирання — голий ґрунт (Annex 7)."""
        sim, soils = self.sim, self.soils
        kc = np.zeros((NY, L))
        if self.opts["bare_annex7"]:
            win = sim["bare_kc_window_days"]
            for a in range(0, L, win):
                b = min(a + win, L)
                mk = (start + a, start + b, coarse)
                if mk not in self._kcb:
                    self._kcb[mk] = kc_bare(rain[:, a:b], et0[:, a:b], coarse, soils)
                kc[:, a:b] = self._kcb[mk][:, None]
        else:
            kc[:] = BASELINE_KC_BARE
            flags.append("Kc голого ґрунту = KC_BARE baseline v0 (без джерела) — режим порівняння")
        kc_mid = np.full(NY, float(c["kc_mid"]))
        kc_end = np.full(NY, float(c["kc_end"]))
        if self.opts["kc_climate"]:
            h = c.get("h_m")
            if C.is_todo(h) or h is None:
                flags.append(f"{crop}: немає h — поправку Kc на клімат не застосовано")
            else:
                rh = rh_min_eq63(self._rowmean("T2MDEW", dev1, mid1), self._rowmean("T2M_MAX", dev1, mid1))
                kc_mid = kc_climate_eq62(c["kc_mid"], self._rowmean("WS2M", dev1, mid1), rh, h)
                if c["kc_end"] >= 0.45:
                    rh = rh_min_eq63(self._rowmean("T2MDEW", mid1, late1 + 1), self._rowmean("T2M_MAX", mid1, late1 + 1))
                    kc_end = kc_climate_eq62(c["kc_end"], self._rowmean("WS2M", mid1, late1 + 1), rh, h)
        crop_m = np.zeros((NY, L), bool)
        for y in range(NY):
            a, b = sow[y] - start, late1[y] - start
            kc[y, a:b + 1] = kc_curve(None, sow[y], dev0[y], dev1[y], mid1[y], late1[y], c["kc_ini"], kc_mid[y], kc_end[y])[0]
            crop_m[y, a:b + 1] = True
        etc, eta, ks, dr_end = water_balance(kc, et0, rain, taw, p_tab, dr0, self.opts["p_adjust"], soils["depletion_adjust"])
        st = dict(dr=dr_end, end=end, taw=taw, p=p_tab, coarse=coarse)
        daily = (start, eta) if self.keep_daily else None
        etc_s, eta_s = (etc * crop_m).sum(1), (eta * crop_m).sum(1)
        rel = np.clip(1 - self.ky[crop] * (1 - eta_s / etc_s), 0, 1)
        q = lambda x: (int(round(np.percentile(x, 10))), int(round(np.percentile(x, 90))))   # noqa: E731
        yr = YearResult(k, crop, rel, etc_s, eta_s, ((ks < 1) & crop_m).sum(1), int(round(float((~crop_m).sum(1).mean()))),
                        int(round(np.median(sow))), int(round(np.median(late1))), flags, sow_q=q(sow), harvest_q=q(late1), daily=daily)
        if key is not None:
            flags.append(f"кеш сезону: стартова волога округлена до {sim['season_cache_round_mm']} мм")
            self._seasons[key] = (yr, st, flags)
        return yr, st, flags

    def end_moisture(self, seq) -> np.ndarray:
        """Частка доступної вологи (1 − Dr/TAW) на кінець ротації, [25]."""
        self.run(seq)
        st = self.cache[tuple(seq)][2]
        return 1 - st["dr"] / st["taw"]


# =====================================================================================
# Режим baseline v0 — лише для тесту «послідовність з 1 культури = поточний симулятор»
# =====================================================================================
def baseline_season(wx: pd.DataFrame, et0: pd.Series, c: dict, year: int, taw_per_m: float, kc_bare_const: float):
    """Відтворює baseline_model.simulate через спільне ядро water_balance (реальний календар, без 29.02-вилучення)."""
    if c["season"] == "winter":
        sow = pd.Timestamp(f"{year - 1}-{c['sow']}")
        marks = [pd.Timestamp(f"{year}-{d}") for d in c["stage_dates"]]
    else:
        sow = pd.Timestamp(f"{year}-{c['sow']}")
        m, acc = [], sow
        for n in c["stages_days"]:
            acc = acc + pd.Timedelta(days=n)
            m.append(acc)
        marks = m
    start = sow - pd.Timedelta(days=60)
    idx = pd.date_range(start, marks[-1])
    if idx[0] < wx.index[0] or idx[-1] > wx.index[-1]:
        return None
    o = lambda d: (d - start).days   # noqa: E731
    kc = np.full((1, len(idx)), kc_bare_const)
    kc[:, o(sow):] = kc_curve(None, o(sow), *(o(x) for x in marks), c["kc_ini"], c["kc_mid"], c["kc_end"])
    taw = taw_per_m * c["zr"]
    etc, eta, ks, _ = water_balance(kc, et0.reindex(idx).values[None], wx["PRECTOTCORR"].reindex(idx).values[None],
                                    taw, c["p"], 0.5 * taw, p_adjust=False)
    s = slice(o(sow), None)
    rel = float(np.clip(1 - c["ky"] * (1 - eta[0, s].sum() / etc[0, s].sum()), 0, 1))
    return dict(etc_mm=round(etc[0, s].sum()), eta_mm=round(eta[0, s].sum()), rel_yield=round(rel, 3),
                stress_days=int((ks[0, s] < 1).sum()))


# =====================================================================================
# Врожай: Yx = P90 обласної врожайності Держстату (ТЗ A3)
# =====================================================================================
@lru_cache(maxsize=4)
def yields(path: str | None = None) -> pd.DataFrame:
    """Держстат: обласна врожайність, т/га. path=None → усі категорії господарств (YIELD_CSV)."""
    d = pd.read_csv(path or YIELD_CSV, encoding="utf-8")
    return d[d.yield_t_ha.notna() & (d.yield_t_ha > 0)]          # порожні значення Держстату — немає даних, не нуль


def yx_p90(crop: str, oblast_uk: str, exclude_year: int | None = None) -> float | None:
    y = yields()
    s = y[(y.culture == crop) & (y.oblast == oblast_uk)]
    if exclude_year is not None:
        s = s[s.year != exclude_year]
    return None if s.empty else float(np.percentile(s.yield_t_ha, 90))
