"""Plate data class — build platform parameters.

Fields follow PLAN.md §7:
  width_mm   : platform width in millimetres (default 220.0 — Ender-3 / Prusa MK4)
  height_mm  : platform height in millimetres (default 220.0)
  margin_mm  : minimum gap between parts and between parts and plate edge (default 1.0)

This is a pure data class (no behaviour).  Collision detection helpers and
placement logic live in Blok 2+ modules (bl.py, bfd.py).
"""

from dataclasses import dataclass, field


@dataclass
class Plate:
    width_mm: float = 220.0
    height_mm: float = 220.0
    margin_mm: float = 1.0
