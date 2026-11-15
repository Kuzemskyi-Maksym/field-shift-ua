"""D29: найм збирання — ціна лише з ≥ 2 джерел; без даних — no_data; маржа з наймом = стара P50 − площа × ціна × сезони."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import export_site_strategies as E  # noqa: E402


def test_only_crops_with_two_sources():
    assert set(E.HIRE) == {"sunflower"}                 # кукурудза — одне джерело, буряк — жодного
    p = E.HIRE["sunflower"]
    assert p["min"] == 2550 and p["max"] == 4950 and all(s["url"].startswith("http") for s in p["sources"])


def test_hire_block_math_and_no_data():
    s = dict(sequence=["maize", "sunflower", "maize", "sugar_beet"],
             metrics=dict(money=dict(total_field=dict(p10=1.0, p50=1_000_000.0, p90=2.0))))
    h = E.hire_block(s, ["sunflower_header"], 100.0)
    assert h["margin4_p50_lo"] == 1_000_000 - 100 * 4950 and h["margin4_p50_hi"] == 1_000_000 - 100 * 2550
    h = E.hire_block(s, ["sunflower_header", "beet_complex"], 100.0)
    assert h["missing_uk"] == ["бурякозбиральний комплекс"] and "margin4_p50_lo" not in h
