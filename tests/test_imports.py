"""Blok 1 sanity test — import smoke + Part field assignment check."""

from src.part import Part
from src.plate import Plate


def test_part_import_and_fields():
    p = Part(id="p1", width_mm=20.0, height_mm=30.0, qty=1, rotatable=True)
    assert p.id == "p1"
    assert p.width_mm == 20.0
    assert p.height_mm == 30.0
    assert p.qty == 1
    assert p.rotatable is True


def test_plate_import_and_defaults():
    plate = Plate()
    assert plate.width_mm == 220.0
    assert plate.height_mm == 220.0
    assert plate.margin_mm == 1.0
