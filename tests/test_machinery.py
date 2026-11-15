"""D27: техніка для збирання — групи з джерелом, наявна техніка з HLS, стратегія «З наявною технікою»."""
import warnings

import pytest
import yaml

from model import machinery as MC

warnings.filterwarnings("ignore")


def test_groups_sourced_and_disjoint():
    cfg = MC.load()
    seen = {}
    for g, v in cfg["groups"].items():
        assert v.get("source"), g
        assert v.get("source_url") or v["source"] == "припущення команди, потребує перевірки агрономом", g
        for c in v["crops"]:
            assert c not in seen, (c, g, seen.get(c))
            seen[c] = g
    crops = yaml.safe_load(open(MC.YAML.parent / "crops.yaml", encoding="utf-8"))["crops"]
    for c in crops:                                   # кожна культура моделі має групу або не потребує збирання
        assert c in seen or c in cfg["no_harvest"], c


def test_owned_from_hls_with_flags():
    hist = [dict(year=2019, c="S", sub="early", confirmed_crop=None),        # поза вікном 2021–2025
            dict(year=2021, c="W", sub="", confirmed_crop=None),
            dict(year=2022, c="S", sub="late", confirmed_crop=None),
            dict(year=2023, c="F", sub="", confirmed_crop=None)]
    have, flags = MC.owned(hist, 2027)
    assert have == {"grain_header", "corn_header"}
    hist.append(dict(year=2024, c="S", sub="early", confirmed_crop=None))
    have, flags = MC.owned(hist, 2027)
    assert "sunflower_header" in have and any("можливо соняшник" in f for f in flags)
    hist[-1]["confirmed_crop"] = "not_sunflower"
    have, flags = MC.owned(hist, 2027)
    assert "sunflower_header" not in have and any("не соняшник" in f for f in flags)
    hist[-1]["confirmed_crop"] = "sugar_beet"
    assert "beet_complex" in MC.owned(hist, 2027)[0]


def test_combine_base_grain_header():
    """Лише ярі (кукурудза/соняшник) за 2021–2025 → зернова жатка вважається наявною (базова комплектація), з прапорцем."""
    hist = [dict(year=y, c="S", sub="late", confirmed_crop=None) for y in range(2021, 2026)]
    have, flags = MC.owned(hist, 2027)
    assert have == {"grain_header", "corn_header"}
    assert any("базова комплектація комбайна" in f for f in flags)
    have, flags = MC.owned([dict(year=2024, c="F", sub="", confirmed_crop=None)], 2027)
    assert have == set() and not flags
    have, _ = MC.owned([dict(year=2024, c="F", sub="", confirmed_crop="sugar_beet")], 2027)
    assert have == {"beet_complex"}


def test_badge():
    b = MC.badge(["maize", "sugar_beet", "maize", "black_fallow"], {"corn_header"})
    assert b["groups"] == ["corn_header", "beet_complex"] and b["new"] == ["beet_complex"]
    assert b["text"] == "потрібна нова техніка: бурякозбиральний комплекс"
    assert MC.badge(["maize"], {"corn_header"})["text"] is None


@pytest.fixture(scope="module")
def volyn():
    from model import optimize as O
    return O.optimize_field("volyn:f3735", allow_stubs=True, write=False)


def test_beet_never_without_warning(volyn):
    """Ментор: буряк не можна радити без бурякозбиральної техніки — кожна стратегія з буряком має бейдж."""
    for s in volyn["strategies"]:
        if "sugar_beet" in s["sequence"] and "beet_complex" not in s["machinery"]["owned"]:
            assert "бурякозбиральний комплекс" in (s["machinery"]["text"] or ""), s["name"]


def test_own_machinery_best_without_new(volyn):
    S = {s["name"]: s for s in volyn["strategies"]}
    own = S["own_machinery"]
    assert own["machinery"]["new"] == []
    for n, s in S.items():                            # серед стратегій без нової техніки own — з найвищою маржею P50
        if n not in ("own_machinery", "current", "water") and not s["machinery"]["new"]:
            assert own["metrics"]["margin_p50"] >= s["metrics"]["margin_p50"] - 1e-6, n
    assert own["metrics"]["vs_current"] is not None
    assert "оренду" in own["machinery"]["note"]
