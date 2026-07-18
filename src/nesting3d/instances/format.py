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

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import trimesh

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# P0 geo_imza — icerik-tabanli parca kimligi (Eren ilkesi 2026-07-15:
# kimlik ada guvenmez; ayni geometri her kosuda ayni imzayi alir)
# ---------------------------------------------------------------------------

def geo_imza_of_bytes(data: bytes) -> str:
    """Ham dosya iceriginden (orn. STL byte'lari) deterministik imza."""
    return hashlib.sha256(data).hexdigest()


def geo_imza_of_mesh(mesh: "trimesh.Trimesh") -> str:
    """Kanonik mesh imzasi: orijine tasinmis, yuvarlanmis vertex/face dizileri.

    Konum-bagimsiz (orijine kok), float gurultusune dayanikli (1e-6 mm
    yuvarlama). Ayni geometri -> ayni imza; farkli geometri -> farkli.
    """
    v = np.asarray(mesh.vertices, dtype=np.float64)
    kok = v - v.min(axis=0) if len(v) else v
    h = hashlib.sha256()
    h.update(np.round(kok, 6).tobytes())
    h.update(np.asarray(mesh.faces, dtype=np.int64).tobytes())
    return h.hexdigest()


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

    # F1 aile taksonomisi — opsiyonel geometri/aile metasi (geriye uyumlu).
    # None ise dict'e YAZILMAZ; eski kayitlar (bu alanlar yokken) sorunsuz okunur.
    wall_mm: Optional[float] = None      # tahmini cidar kalinligi (2V/A), shell ise
    family: Optional[str] = None         # per-parca aile etiketi (family.py)
    true_fill: Optional[float] = None    # gercek doluluk V/bbox_vol (watertight)

    # P0 parca kimligi (Sokum Konsolu, Eren ilkesi 2026-07-15: kimlik ada
    # guvenmez) — opsiyonel kunye alanlari (wall_mm/family deseni, geriye uyum).
    order_id: Optional[str] = None       # parcanin geldigi siparis
    geo_imza: Optional[str] = None       # icerik hash'i (STL byte sha256 /
    #                                      kanonik mesh-hash); loader doldurur,
    #                                      yoksa to_voxel_parts mesh'ten uretir
    kaynak_ad: Optional[str] = None      # orijinal STL/dosya adi

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
        # Opsiyonel taksonomi alanlari — yalnizca dolu ise yaz (geriye uyum).
        if self.wall_mm is not None:
            d["wall_mm"] = self.wall_mm
        if self.family is not None:
            d["family"] = self.family
        if self.true_fill is not None:
            d["true_fill"] = self.true_fill
        if self.order_id is not None:
            d["order_id"] = self.order_id
        if self.geo_imza is not None:
            d["geo_imza"] = self.geo_imza
        if self.kaynak_ad is not None:
            d["kaynak_ad"] = self.kaynak_ad
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
            wall_mm=float(d["wall_mm"]) if d.get("wall_mm") is not None else None,
            family=d.get("family"),
            true_fill=float(d["true_fill"]) if d.get("true_fill") is not None else None,
            order_id=d.get("order_id"),
            geo_imza=d.get("geo_imza"),
            kaynak_ad=d.get("kaynak_ad"),
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
    z_dilate: int = 0,
    method: str = "slice",
    allowed_orientations: Optional[tuple] = None,
    extra_rot_overrides: Optional[dict] = None,
) -> list:
    """Kutu instance'larini trimesh box mesh -> VoxelPart listesine dönüştür.

    Yalnızca source="box" parçalar desteklenir (source="stl" için stl_path
    dosyası okunur — dosya yoksa FileNotFoundError).  Her model (aynı name)
    bir kez voxelize edilir; adetler expand_quantities ile açılır.

    Kabul kriteri (PLAN_DEMO1.md 2.4): 20 mm kutu @ pitch=5 -> 64 voxel
    (4x4x4 = 64).  method="slice" (default) bu kriteri karşılar:
    ceil(20/5)=4 per side -> 4*4*4=64.

    allowed_orientations: 28-pozluk master sete indeks tuple'ı — TÜM modellere
    aynı poz kısıtı (K-18p: quality=max AX24 eksen-hizalı seti). Verilirse
    n_orientations yok sayılır (voxelize_part önceliği).

    extra_rot_overrides (K-56): {model adı -> [4x4 rot matrisi, ...]} — adı
    eşleşen modelin default setine SONA eklenen ek pozlar (hedefli-tilt;
    master sette olmayan düşük açılar). Anahtar görünen ad (display) veya
    kaynak_ad ile eşleşir. None = bit-özdeş.

    z_dilate: TEK-TARAFLI (+z / üst) dilation voxel sayısı (EVAL-1 NFV dikey-
    clearance fix). 0 (default) -> hiç z-dilation (mevcut çağıranlar BİT-ÖZDEŞ).
    >0 iken her parça grid'i yalnız yukarı büyür → iki parça arası dikey boşluk
    >= z_dilate voxel garanti (taban etkilenmez → plakaya oturur).

    Returns:
        List[VoxelPart] — solver pipeline'ına doğrudan verilecek liste.
    """
    from src.nesting3d.voxelize import expand_quantities

    # P0 gruplama (Eren ilkesi 2026-07-15: kimlik ada guvenmez): anahtar
    # (name, geo_imza). Imza yalniz bugunku YANLIS birlesmeleri AYIRIR
    # (ayni ad + FARKLI geometri iki siparisten gelirse eskiden ilk mesh
    # kazanir, digeri sessizce yanlis geometriyle basilirdi); ayni-geometri
    # gruplari birlestirmeye devam eder -> id'ler/solver girdisi BIT-OZDES.
    # Ayrisan gruplar gorunen adda ayrisir (name, name~2, ...) + ASCII log.
    mesh_cache: dict = {}   # icerik anahtari -> mesh (STL tek kez yuklenir)
    groups: dict = {}       # (name, imza) -> {mesh, qty, display, kovalar}
    name_sayac: dict = {}   # name -> kac farkli imza grubu goruldu

    for p in instance.parts:
        if p.source == "box":
            icerik_key = ("box", p.width_mm, p.depth_mm, p.height_mm)
        else:
            icerik_key = ("stl", p.stl_path)
        if icerik_key not in mesh_cache:
            mesh_cache[icerik_key] = _make_mesh(p)
        mesh = mesh_cache[icerik_key]
        imza = p.geo_imza or geo_imza_of_mesh(mesh)

        key = (p.name, imza)
        if key not in groups:
            n = name_sayac.get(p.name, 0) + 1
            name_sayac[p.name] = n
            display = p.name if n == 1 else f"{p.name}~{n}"
            if n > 1:
                _LOG.warning(
                    "to_voxel_parts: ayni ad '%s' FARKLI geometriyle geldi "
                    "(imza %s...) -> grup '%s' olarak ayristirildi "
                    "(yanlis-geometri birlesme guard'i)",
                    p.name, imza[:8], display)
            groups[key] = {"mesh": mesh, "display": display, "qty": 0,
                           "imza": imza, "kaynak_ad": p.kaynak_ad,
                           "kovalar": []}
        g = groups[key]
        g["qty"] += p.qty
        g["kovalar"].append((p.order_id, int(p.qty)))
        if g["kaynak_ad"] is None and p.kaynak_ad is not None:
            g["kaynak_ad"] = p.kaynak_ad

    combined = [(g["display"], g["mesh"], g["qty"]) for g in groups.values()]
    kimlik_map = {
        g["display"]: {"geo_imza": g["imza"], "kaynak_ad": g["kaynak_ad"],
                       "kovalar": g["kovalar"]}
        for g in groups.values()
    }

    overrides = ({g["display"]: allowed_orientations for g in groups.values()}
                 if allowed_orientations is not None else None)
    extra = None
    if extra_rot_overrides:
        extra = {}
        for g in groups.values():
            rots = extra_rot_overrides.get(g["display"])
            if rots is None and g["kaynak_ad"] is not None:
                rots = extra_rot_overrides.get(g["kaynak_ad"])
            if rots:
                extra[g["display"]] = rots
    return expand_quantities(
        combined,
        pitch,
        n_orientations=n_orientations,
        margin=margin,
        z_dilate=z_dilate,
        method=method,
        orientation_overrides=overrides,
        extra_rot_overrides=extra,
        kimlik_map=kimlik_map,
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
