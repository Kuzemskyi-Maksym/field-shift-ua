"""Сайт EN/UA: кожен ключ словника site/i18n.json має en і uk; плейсхолдери # (числа) і § (назви) збігаються."""
import json
import re
from pathlib import Path

I18N = Path(__file__).resolve().parents[1] / "site" / "i18n.json"
CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")


def load():
    return json.load(open(I18N, encoding="utf-8"))


def test_every_key_has_en_and_uk():
    s = load()["strings"]
    assert s
    for k, v in s.items():
        assert v.get("en") and v.get("uk"), k
        assert not CYR.search(v["en"]), (k, v["en"])


def test_placeholders_match():
    for k, v in load()["strings"].items():
        assert v["uk"].count("#") == v["en"].count("#"), (k, v)
        assert v["uk"].count("§") == v["en"].count("§"), (k, v)


def test_names_translated():
    n = load()["names"]
    assert n["Кукурудза"] == "Maize" and n["Волинська"] == "Volyn"
    for uk, en in n.items():
        assert en and not CYR.search(en), uk
