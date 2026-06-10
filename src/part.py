"""Part data class — AABB (bounding-box) representation.

Fields follow PLAN.md §6 CSV schema exactly:
  id          : unique part identifier (ASCII only — no Turkish chars)
  width_mm    : bounding-box width in millimetres (float)
  height_mm   : bounding-box height in millimetres (float)
  qty         : quantity of this part in the job (int); expansion to instances is
                deferred to the loader (Blok 2+)
  rotatable   : if True, the part may be placed at 90-degree rotation {0, 90}
"""

from dataclasses import dataclass


@dataclass
class Part:
    id: str
    width_mm: float
    height_mm: float
    qty: int
    rotatable: bool
