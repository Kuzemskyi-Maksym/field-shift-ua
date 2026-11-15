"""Ґрунт: класифікація USDA (NRCS SSM 2017 через USTF), шари SoilGrids до Zr, TAW із FAO-56 Табл. 19."""
import pytest

from model import soil as S


def test_usda_partition_complete_and_unique():
    """Кожна точка трикутника (крок 1%) — рівно один клас."""
    for clay in range(0, 101):
        for sand in range(0, 101 - clay):
            c = S.usda_classes(sand, 100 - clay - sand, clay)
            assert len(c) == 1, (sand, 100 - clay - sand, clay, c)


@pytest.mark.parametrize("sand,silt,clay,cls", [
    (92, 5, 3, "sand"), (80, 12, 8, "loamy_sand"), (65, 25, 10, "sandy_loam"), (40, 40, 20, "loam"),
    (20, 65, 15, "silt_loam"), (5, 88, 7, "silt"), (60, 15, 25, "sandy_clay_loam"), (30, 35, 35, "clay_loam"),
    (10, 55, 35, "silty_clay_loam"), (50, 5, 45, "sandy_clay"), (5, 50, 45, "silty_clay"), (20, 20, 60, "clay"),
])
def test_usda_textbook_points(sand, silt, clay, cls):
    assert S.usda_classes(sand, silt, clay) == [cls]


def test_layer_weights_to_zr():
    w = S.layer_weights(1.0)
    assert set(w) == {"0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm"}
    assert abs(sum(w.values()) - 1) < 1e-12 and abs(w["60-100cm"] - 0.40) < 1e-12
    w = S.layer_weights(1.5)
    assert abs(w["100-200cm"] - 50 / 150) < 1e-12


def test_override_flag_and_taw_from_t19_midpoints():
    r = S.field_texture("x", 1.0, texture_override="silt_loam")
    assert "текстура задана вручну: silt_loam" in r["flags"]
    assert abs(r["taw_mm_per_m"] - 1000 * ((0.22 + 0.36) / 2 - (0.09 + 0.21) / 2)) < 1e-9


def test_class_missing_from_t19_blocks_taw():
    r = S.field_texture("x", 1.0, texture_override="clay_loam")
    assert r["taw_mm_per_m"] is None and any("Табл. 19" in f for f in r["flags"])
