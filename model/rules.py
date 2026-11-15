"""Жорсткі правила сівозміни (ТЗ A6): норматив КМУ №164, історія поля з HLS, обмеження фермера.

- check_rot_site   — порт 1:1 функції checkRot із site/template.html (циклічна перевірка сайту).
- check_linear     — ФІЛЬТР оптимізатора: історія поля + план, лінійно, норми з rules.yaml.
- history_branches — гілки історії з HLS: «можливо соняшник» у непідтверджених S/early-роках.
- cyclic_flag      — циклічна перевірка плану нормами rules.yaml; НЕ фільтр, а прапорець.
- check_constraints — обмеження фермера (заборонені культури, техніка, частки).

Усі норми — з model/rules.yaml (з полем source). Числа в коді є лише в порті сайту (джерело — сайт).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
RULES_YAML = HERE / "rules.yaml"


def load_rules(path: Path = RULES_YAML) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# =====================================================================================
# a) Порт checkRot сайту (site/template.html, блок «норматив №164»). Джерело — сайт; таблиці
#    RET/GROUP/LIM скопійовано ДОСЛІВНО, разом з особливостями сайту («Ячмінь» один, без жита/вівса).
#    Перевірка: tests/fixtures/site_presets.json, згенерований справжнім JS (tests/gen_site_presets.js).
# =====================================================================================
SITE_RET = {"Пшениця озима": 2, "Ячмінь": 1, "Гречка": 1, "Просо": 2, "Соя": 3, "Горох": 3, "Ріпак": 3,
            "Буряк цукровий": 3, "Соняшник": 7}
SITE_GROUP = {"Пшениця озима": "g", "Пшениця яра": "g", "Ячмінь": "g", "Кукурудза": "g", "Гречка": "g", "Просо": "g",
              "Соя": "g", "Горох": "g", "Соняшник": "t", "Ріпак": "t", "Буряк цукровий": "t", "Чорний пар": "p"}
SITE_LIM = [("Зернові та зернобобові", lambda c: SITE_GROUP.get(c) == "g", 25, 95),
            ("Технічні, усього", lambda c: SITE_GROUP.get(c) == "t", 5, 30),
            ("Соняшник", lambda c: c == "Соняшник", 5, 9),
            ("Ріпак", lambda c: c == "Ріпак", 3, 5)]


def _js_round(x: float) -> int:
    """Math.round у JS: .5 округлюється вгору (Python round — банківське)."""
    return math.floor(x + 0.5)


def check_rot_site(r: list[str]) -> tuple[list[list], list[dict]]:
    """Повертає (rows, shares) як checkRot: rows = [культура, «повертається», «норма», ok|bad|na]."""
    n = len(r)
    if not n:
        return [], []
    rows = []
    for c in dict.fromkeys(r):                       # [...new Set(r)] — порядок першої появи
        pos = [i for i, x in enumerate(r) if x == c]
        if c == "Кукурудза":
            run = best = 0
            for i in range(2 * n):
                run = run + 1 if r[i % n] == c else 0
                best = max(best, min(run, 2 * n))
            mono = len(pos) == n
            rows.append([c, "щороку" if mono else "не поспіль" if best == 1 else f"{best} роки поспіль",
                         "2–3 роки поспіль", "bad" if mono or best > 3 else "ok"])
            continue
        gaps = [(((pos[(i + 1) % len(pos)] - p + n) % n) or n) - 1 for i, p in enumerate(pos)]
        g, need = min(gaps), SITE_RET.get(c)
        rows.append([c, "щороку" if g == 0 else f"через {g}", "не нормується" if need is None else f"через ≥ {need}",
                     "na" if need is None else "ok" if g >= need else "bad"])
    shares = []
    for name, f, lo, hi in SITE_LIM:
        v = _js_round(100 * sum(1 for x in r if f(x)) / n)
        single = name in ("Соняшник", "Ріпак")
        st = "na" if single and v == 0 else "ok" if lo <= v <= hi else "warn"
        suffix = " (не вирощується)" if st == "na" else " — забагато" if v > hi else " — замало" if v < lo else ""
        shares.append(dict(name=name, value=v, lo=lo, hi=hi, status=st, suffix=suffix))
    return rows, shares


# =====================================================================================
# c) Лінійна перевірка (фільтр) + d) циклічна (прапорець) — норми з rules.yaml
# =====================================================================================
@dataclass
class RuleResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def _norm(rules: dict, crop: str) -> dict:
    n = rules["norm164"].get(crop)
    if n is None:
        raise KeyError(f"культури '{crop}' немає в rules.yaml norm164 — додай норму або kind: none з джерелом")
    return n


def _key(rules: dict, crop):
    """Ключ порівняння: norm_group / run_group; None (невідомий рік) — нічого не збігається.
    Культура без норми (лише в історії, напр. люпин) — ключ = сама культура."""
    if crop is None:
        return None
    n = rules["norm164"].get(crop)
    if n is None:
        return crop
    return n.get("norm_group") or n.get("run_group") or crop


def _plan_flags(rules: dict, plan: list[str]) -> list[str]:
    flags = []
    for c in dict.fromkeys(plan):
        f = _norm(rules, c).get("flag")
        if f:
            flags.append(f)
    return flags


def check_linear(history: list, plan: list[str], rules: dict | None = None) -> RuleResult:
    """history: найстаріший → найновіший рік (crop_id або None = невідомо); plan: роки 1..k.

    Для кожної культури плану: між нею і попереднім посівом тієї ж norm_group щонайменше `years`
    інших років. Кукурудза (run_group): не більше max_consecutive років поспіль у history+plan.
    Невідомі роки історії нічого не порушують, але дають прапорець.
    """
    rules = rules or load_rules()
    if not plan:
        raise ValueError("порожній план")
    seq = list(history) + list(plan)
    h = len(history)
    res = RuleResult(True, flags=_plan_flags(rules, plan))
    for c in dict.fromkeys(x for x in history if x is not None and x not in rules["norm164"]):
        res.flags.append(f"культура історії '{c}' не має норми №164 у rules.yaml — враховано лише як «не та сама культура»")
    unknown = [i for i, x in enumerate(history) if x is None]
    if unknown:
        res.flags.append(f"історія поля невідома в {len(unknown)} з {h} років — №164 перевірено лише за відомими роками")
    for j in range(h, len(seq)):
        c = seq[j]
        n = _norm(rules, c)
        if n["kind"] == "return":
            k = _key(rules, c)
            prev = next((i for i in range(j - 1, -1, -1) if _key(rules, seq[i]) == k), None)
            if prev is not None and j - prev - 1 < n["years"]:
                where = f"рік плану {prev - h + 1}" if prev >= h else f"історія, {h - prev} р. тому"
                res.violations.append(f"№164: {n['name_uk']} у році плану {j - h + 1} — через {j - prev - 1} р. "
                                      f"після посіву ({where}); норма ≥ {n['years']}")
        elif n["kind"] == "maize_run":
            k = _key(rules, c)
            run, i = 0, j
            while i >= 0 and _key(rules, seq[i]) == k:
                run, i = run + 1, i - 1
            if run > n["max_consecutive"]:
                res.violations.append(f"№164: кукурудза {run} роки поспіль у році плану {j - h + 1}; "
                                      f"норма ≤ {n['max_consecutive']}")
    res.ok = not res.violations
    return res


def cyclic_flag(plan: list[str], rules: dict | None = None) -> list[str]:
    """Якщо план повторювати циклічно — чи порушує він №164 (норми rules.yaml). Лише прапорці."""
    rules = rules or load_rules()
    n = len(plan)
    out = []
    keys = [_key(rules, c) for c in plan]
    seen = set()
    for c in plan:
        k = _key(rules, c)
        if k in seen:
            continue
        seen.add(k)
        nm = _norm(rules, c)
        pos = [i for i, x in enumerate(keys) if x == k]
        if nm["kind"] == "return":
            gaps = [(((pos[(i + 1) % len(pos)] - p + n) % n) or n) - 1 for i, p in enumerate(pos)]
            g = min(gaps)
            if g < nm["years"]:
                out.append(f"якщо повторювати цю сівозміну — порушення №164: {nm['name_uk']} повертається через {g} р. "
                           f"(норма ≥ {nm['years']}), роки плану {[p + 1 for p in pos]}")
        elif nm["kind"] == "maize_run":
            run = best = 0
            for i in range(2 * n):
                run = run + 1 if keys[i % n] == k else 0
                best = max(best, min(run, 2 * n))
            if len(pos) == n or best > nm["max_consecutive"]:
                what = "щороку (монокультура)" if len(pos) == n else f"{best} роки поспіль"
                out.append(f"якщо повторювати цю сівозміну — порушення №164: кукурудза {what} "
                           f"(норма ≤ {nm['max_consecutive']}), роки плану {[p + 1 for p in pos]}")
    return out


# =====================================================================================
# Історія з HLS → гілки
# =====================================================================================
def history_branches(hls_years: list[dict], rules: dict | None = None,
                     plan_start_year: int | None = None) -> list[tuple[str, list]]:
    """hls_years: [{year, c: W|S|F|?, sub: early|late|'', confirmed_crop: crop_id|None}], будь-який порядок.

    Підтверджений рік → його культура. Непідтверджений → None (невідомо).
    Непідтверджені роки з c/sub з rules.yaml history.maybe_sunflower → «можливо соняшник».
    Для норми соняшнику обмежує лише останній попередній посів, тож гілок дві:
      «жоден не соняшник» і «соняшник в останньому такому році».
    Повертає [(мітка, історія від найстарішого до найновішого)].
    """
    rules = rules or load_rules()
    ms = rules["history"]["maybe_sunflower"]
    ys = sorted(hls_years, key=lambda r: r["year"])
    if ys:                                   # пропущені роки (і роки до plan_start_year) → невідомі
        last_y = (plan_start_year - 1) if plan_start_year else ys[-1]["year"]
        if ys[-1]["year"] > last_y:
            raise ValueError(f"історія ({ys[-1]['year']}) не раніше за перший рік плану ({plan_start_year})")
        by = {r["year"]: r for r in ys}
        ys = [by.get(y, {"year": y, "c": "?", "sub": "", "missing": True}) for y in range(ys[0]["year"], last_y + 1)]
    NOT_SF = "not_sunflower"           # фермер підтвердив лише «це був не соняшник» — культура невідома
    base = [None if r.get("confirmed_crop") == NOT_SF else (r.get("confirmed_crop") or None) for r in ys]
    maybe = [i for i, r in enumerate(ys)
             if not r.get("confirmed_crop") and r.get("c") == ms["c"] and (r.get("sub") or "") in ms["sub"]]
    if not maybe:
        return [("історія без гілки «можливо соняшник»", base)]
    last = maybe[-1]
    sf_key = _key(rules, "sunflower")
    if any(_key(rules, base[i]) == sf_key for i in range(last + 1, len(base))):
        return [("історія без гілки «можливо соняшник» (пізніший підтверджений соняшник)", base)]
    yrs = ", ".join(str(ys[i]["year"]) for i in maybe)
    with_sf = list(base)
    with_sf[last] = "sunflower"
    return [(f"соняшнику не було (непідтверджені S/early: {yrs})", base),
            (f"соняшник у {ys[last]['year']} (S/early, не підтверджено)", with_sf)]


# =====================================================================================
# e) Обмеження фермера
# =====================================================================================
def check_constraints(plan: list[str], farmer: dict | None = None, rules: dict | None = None) -> RuleResult:
    """farmer: {forbidden: [crop], no_machinery_for: [crop], no_machinery: [machine_id],
                min_share: {crop: %}, max_share: {crop: %}}.  Частки сайту (rules.shares) — за mode."""
    rules = rules or load_rules()
    farmer = farmer or {}
    res = RuleResult(True)
    n = len(plan)
    if not n:
        raise ValueError("порожній план")
    for c in dict.fromkeys(plan):
        if c in farmer.get("forbidden", []):
            res.violations.append(f"фермер заборонив: {c}")
        if c in farmer.get("no_machinery_for", []):
            res.violations.append(f"немає техніки для: {c}")
    needs = rules.get("machinery", {}).get("needs") or {}
    for m in farmer.get("no_machinery", []):
        if m not in needs:
            res.flags.append(f"техніка '{m}': не знаю, яких культур стосується (rules.yaml machinery — TODO)")
            continue
        for c in set(plan) & set(needs[m]):
            res.violations.append(f"немає техніки '{m}' для: {c}")
    for c, lo in (farmer.get("min_share") or {}).items():
        v = 100 * plan.count(c) / n
        if v < lo:
            res.violations.append(f"частка {c} {v:.0f}% < мінімуму фермера {lo}%")
    for c, hi in (farmer.get("max_share") or {}).items():
        v = 100 * plan.count(c) / n
        if v > hi:
            res.violations.append(f"частка {c} {v:.0f}% > максимуму фермера {hi}%")
    sh = rules.get("shares", {})
    for g in (sh.get("groups") or {}).values():
        k = sum(1 for x in plan if x in g["crops"])
        if not k and g["lo"] > 0 and len(g["crops"]) == 1:
            continue                                            # як на сайті: окрема культура не вирощується
        v = 100 * k / n
        if not g["lo"] <= v <= g["hi"]:
            msg = f"частка «{g['name_uk']}» {v:.0f}% поза {g['lo']}–{g['hi']}% (сайт; для одного поля — орієнтир)"
            (res.violations if sh.get("mode") == "filter" else res.flags).append(msg)
    res.ok = not res.violations
    return res


def prev_effect(prev: str | None, crop: str, rules: dict | None = None) -> tuple[float, list[str]]:
    """Множник попередника; без джерела → 1.0 з прапорцем."""
    rules = rules or load_rules()
    v = ((rules.get("prev_effect") or {}).get("values") or {}).get(prev, {}).get(crop)
    if not v or not v.get("source"):
        return 1.0, ["ефект попередника не враховано"]
    return float(v["value"]), []


def sunflower_multipliers(hist: list, seq: list, zone: str, rules: dict | None = None) -> tuple[list[float], list[list[str]]]:
    """Множник урожаю соняшнику за роками між посівами (prev_effect.sunflower_return, джерело KOHAN2016).

    hist — історія поля (crop_id або None — невідомо), від старого до нового; seq — план. → ([K] множників, [K] прапорців).
    gap = років строго між попереднім посівом соняшнику (в історії або плані) і цим."""
    rules = rules or load_rules()
    c = ((rules.get("prev_effect") or {}).get("sunflower_return")) or {}
    K = len(seq)
    if not c.get("source") or c["source"] not in rules.get("sources", {}):
        return [1.0] * K, [[] for _ in range(K)]
    base, loss, F = c["base_t_ha"], {int(k): v for k, v in c["loss_t_ha"].items()}, c["flags"]
    m1, m2 = 1 - loss[1] / base, 1 - loss[2] / base
    full = list(hist) + list(seq)
    mult, flags = [], []
    for i, crop in enumerate(seq):
        if crop != c["crop"]:
            mult.append(1.0)
            flags.append([])
            continue
        h = len(hist) + i
        j = next((k for k in range(h - 1, -1, -1) if full[k] == c["crop"]), None)
        fl = []
        if j is None:
            m = 1.0
            fl.append(f"соняшник: {F['unknown']}")
        else:
            gap = h - j - 1
            if gap >= c["no_effect_gap"]:
                m = 1.0
            elif gap <= 1:
                m = m1
                if gap == 0:
                    fl.append(F["gap0"])
            elif gap == 2:
                m = m2
            else:                                    # 3–5: лінійно між gap 2 (m2) і no_effect_gap (1,0)
                m = m2 + (1 - m2) * (gap - 2) / (c["no_effect_gap"] - 2)
                fl.append(F["interp"])
            fl.insert(0, f"соняшник через {gap} р. після попереднього посіву → урожай ×{m:.2f} (насичення сівозміни, "
                         f"Кохан та ін., 2016, Полтавська ДСГДС)")
            if zone not in c["local_zones"]:
                fl.append(F["zone"])
        mult.append(m)
        flags.append(fl)
    return mult, flags


def predecessor_class(prev: str | None, crop: str, zone: str, rules: dict | None = None,
                      groups: dict | None = None) -> tuple[str | None, list[str]]:
    """good|acceptable|bad з матриці НААН або з group_rules; без джерела → клас лише як прапорець (без штрафу).

    groups: {crop_id: group} з crops.yaml (для group_rules, напр. legume → legume).
    Повертає (клас для штрафу/фільтра або None, прапорці)."""
    rules = rules or load_rules()
    pr = rules.get("predecessors") or {}
    m = pr.get(zone) or {}
    cls = (m.get(prev) or {}).get(crop)
    if cls is not None:
        return cls, []
    flags = []
    g = groups or {}
    for r in pr.get("group_rules") or []:
        if g.get(prev) == r["prev_group"] and g.get(crop) == r["crop_group"]:
            if r.get("source") in (None, "TODO"):
                flags.append(f"попередник: {prev} → {crop} — «{r['class']}» за правилом «{r['note']}», джерело TODO (лише прапорець)")
            else:
                return r["class"], []
    return None, flags or ["матриця попередників НААН не заповнена"]
