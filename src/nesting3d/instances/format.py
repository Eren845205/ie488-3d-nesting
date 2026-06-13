"""format.py — Ortak instance format: parça listesi + konteyner tanımı.

Bu modül Faz 2.1 (PLAN_DEMO1.md) kapsamındadır.  A11 geçmiş-veri
sayısallaştırmasının hedef formatı BUDUR — alanlar buraya dökülecek.

JSON Şema (version: "1.0"):
{
  "version": "1.0",
  "container": {
    "width_mm":  float,   # X boyutu (mm)
    "depth_mm":  float,   # Y boyutu (mm)
    "height_mm": float    # Z boyutu (mm; open-dimension'da None/null)
  },
  "parts": [
    {
      "id":       str,           # benzersiz parça kimliği (örn. "box_01")
      "name":     str,           # model adı (aynı modelin farklı adetleri paylaşır)
      "qty":      int,           # adet (>= 1)
      "source":   "box" | "stl", # voxel hattına giriş tipi
      -- source=="box" için:
      "width_mm":  float,        # X (mm)
      "depth_mm":  float,        # Y (mm)
      "height_mm": float,        # Z (mm)
      -- source=="stl" için:
      "stl_path": str            # dosya yolu (mutlak VEYA instance JSON'una göre göreli)
    },
    ...
  ],
  "meta": {                      # isteğe bağlı ek bilgi
    ...
  }
}

Minimum gereklilik: container + en az 1 parça, her parça için id/name/qty/source
ve kaynak'a özgü boyut/yol alanları.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import trimesh


# ---------------------------------------------------------------------------
# Dataclass'lar
# ---------------------------------------------------------------------------

@dataclass
class ContainerSpec:
    """Konteyner boyut tanımı.

    height_mm=None: open-dimension modu (yükseklik minimize edilir).
    """

    width_mm: float   # X
    depth_mm: float   # Y
    height_mm: Optional[float] = None  # Z; None = open-dimension

    def to_dict(self) -> dict:
        return {
            "width_mm": self.width_mm,
            "depth_mm": self.depth_mm,
            "height_mm": self.height_mm,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ContainerSpec":
        return cls(
            width_mm=float(d["width_mm"]),
            depth_mm=float(d["depth_mm"]),
            height_mm=float(d["height_mm"]) if d.get("height_mm") is not None else None,
        )


@dataclass
class PartSpec:
    """Tek parça kaydı.

    source="box": width_mm/depth_mm/height_mm alanları dolu, stl_path None.
    source="stl": stl_path dolu, boyut alanları None.
    """

    id: str
    name: str
    qty: int
    source: str  # "box" | "stl"

    # box fields
    width_mm: Optional[float] = None
    depth_mm: Optional[float] = None
    height_mm: Optional[float] = None

    # stl field
    stl_path: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "name": self.name,
            "qty": self.qty,
            "source": self.source,
        }
        if self.source == "box":
            d["width_mm"] = self.width_mm
            d["depth_mm"] = self.depth_mm
            d["height_mm"] = self.height_mm
        else:
            d["stl_path"] = self.stl_path
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PartSpec":
        required = ["id", "name", "qty", "source"]
        for field_name in required:
            if field_name not in d:
                raise ValueError(
                    f"PartSpec.from_dict: zorunlu alan eksik: '{field_name}'. "
                    f"Mevcut anahtarlar: {list(d.keys())}"
                )
        return cls(
            id=d["id"],
            name=d["name"],
            qty=int(d["qty"]),
            source=d["source"],
            width_mm=float(d["width_mm"]) if d.get("width_mm") is not None else None,
            depth_mm=float(d["depth_mm"]) if d.get("depth_mm") is not None else None,
            height_mm=float(d["height_mm"]) if d.get("height_mm") is not None else None,
            stl_path=d.get("stl_path"),
        )


@dataclass
class NestingInstance:
    """Tam nesting problemi: parça listesi + konteyner.

    Bu dataclass hem JSON serileştirme hem de solver pipeline girişi olarak
    kullanılır.  A11 geçmiş-veri sayısallaştırması da bu yapıya dökülecektir.
    """

    container: ContainerSpec
    parts: List[PartSpec]
    meta: dict = field(default_factory=dict)
    version: str = "1.0"

    # ------------------------------------------------------------------
    # Serileştirme
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "container": self.container.to_dict(),
            "parts": [p.to_dict() for p in self.parts],
            "meta": self.meta,
        }

    def to_json(self, path: Union[str, Path], *, indent: int = 2) -> None:
        """Instance'ı JSON dosyasına yaz."""
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=indent),
            encoding="utf-8",
        )

    @classmethod
    def from_dict(cls, d: dict) -> "NestingInstance":
        required = ["container", "parts"]
        for field_name in required:
            if field_name not in d:
                raise ValueError(
                    f"NestingInstance.from_dict: zorunlu alan eksik: '{field_name}'. "
                    f"Mevcut anahtarlar: {list(d.keys())}"
                )
        parts = []
        for i, p in enumerate(d["parts"]):
            try:
                parts.append(PartSpec.from_dict(p))
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"NestingInstance.from_dict: parts[{i}] ayrıştırma hatası: {exc}"
                ) from exc
        return cls(
            container=ContainerSpec.from_dict(d["container"]),
            parts=parts,
            meta=d.get("meta", {}),
            version=d.get("version", "1.0"),
        )

    @classmethod
    def from_json(cls, path: Union[str, Path]) -> "NestingInstance":
        """JSON dosyasından instance yükle."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(raw)


# ---------------------------------------------------------------------------
# Voxel köprüsü (Faz 2.4)
# ---------------------------------------------------------------------------

def to_voxel_parts(
    instance: NestingInstance,
    pitch: float,
    *,
    n_orientations: int = 4,
    margin: int = 0,
    method: str = "slice",
) -> list:
    """Kutu instance'larini trimesh box mesh -> VoxelPart listesine dönüştür.

    Yalnızca source="box" parçalar desteklenir (source="stl" için stl_path
    dosyası okunur — dosya yoksa FileNotFoundError).  Her model (aynı name)
    bir kez voxelize edilir; adetler expand_quantities ile açılır.

    Kabul kriteri (PLAN_DEMO1.md 2.4): 20 mm kutu @ pitch=5 -> 64 voxel
    (4x4x4 = 64).  method="slice" (default) bu kriteri karşılar:
    ceil(20/5)=4 per side -> 4*4*4=64.

    Returns:
        List[VoxelPart] — solver pipeline'ına doğrudan verilecek liste.
    """
    from src.nesting3d.voxelize import expand_quantities

    # Aynı name'in birden fazla PartSpec'i varsa qty'leri birleştir
    name_to_qty: dict = {}
    name_to_mesh: dict = {}
    for p in instance.parts:
        if p.name not in name_to_mesh:
            name_to_mesh[p.name] = _make_mesh(p)
        name_to_qty[p.name] = name_to_qty.get(p.name, 0) + p.qty

    combined = [
        (name, name_to_mesh[name], name_to_qty[name])
        for name in name_to_mesh
    ]

    return expand_quantities(
        combined,
        pitch,
        n_orientations=n_orientations,
        margin=margin,
        method=method,
    )


def _make_mesh(part: PartSpec) -> trimesh.Trimesh:
    """PartSpec'ten trimesh mesh oluştur."""
    if part.source == "box":
        if None in (part.width_mm, part.depth_mm, part.height_mm):
            raise ValueError(f"Parça '{part.id}': box source için boyutlar zorunlu.")
        mesh = trimesh.creation.box(
            extents=(part.width_mm, part.depth_mm, part.height_mm)
        )
        mesh.apply_translation(-mesh.bounds[0])
        return mesh
    elif part.source == "stl":
        if not part.stl_path:
            raise ValueError(f"Parça '{part.id}': stl source için stl_path zorunlu.")
        mesh = trimesh.load(part.stl_path, force="mesh")
        mesh.apply_translation(-mesh.bounds[0])
        return mesh
    else:
        raise ValueError(f"Parça '{part.id}': bilinmeyen source='{part.source}'.")
