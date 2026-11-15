"""D31: пошкодження тваринами — лише якісно, кожна тварина з URL і цитатою; без чисел втрат."""
import re
from pathlib import Path

import yaml

W = Path(__file__).resolve().parents[1] / "data" / "raw" / "wildlife_damage.yaml"


def test_animals_sourced_no_numbers():
    a = yaml.safe_load(open(W, encoding="utf-8"))["animals"]
    assert a
    for k, v in a.items():
        assert v["source_url"].startswith("http") and v["quote"] and v["crops"], k
        assert not re.search(r"\d+\s*%", v["quote"]), k            # жодних відсотків втрат у тому, що йде на сайт
