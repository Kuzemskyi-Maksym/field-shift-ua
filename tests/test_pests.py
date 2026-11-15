"""D30: пороги шкідників лише з джерела; дні у вікні — з POWER TSOIL1; без даних вузла — no_data."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pest_risk as PR  # noqa: E402


def test_every_pest_has_source_quote_threshold():
    for k, v in yaml.safe_load(open(PR.PESTS, encoding="utf-8"))["pests"].items():
        assert v["source_url"].startswith("http") and v["quote"] and v["tmin_c"] < v["tmax_c"], k
        assert v["levels"] is None or isinstance(v["levels"], dict)


def test_days_bounded_and_no_data():
    p = yaml.safe_load(open(PR.PESTS, encoding="utf-8"))["pests"]["wireworm"]
    r = PR.days_in_window(47.103423, 30.671618, p)            # Березівка, вузол з TSOIL1
    assert r["status"] == "ok" and len(r["years"]) == 10
    assert all(0 <= n <= 91 for _, n in r["years"])          # квітень–червень = 91 день
    assert PR.days_in_window(10.0, 10.0, p)["status"] == "no_data"
