"""stl_order_loader.py — Siparis STL byte'larindan NestingInstance kurucusu.

Posta/zip yoluyla gelen siparis dosyalarini (STL bytes + adet eslemesi)
NestingInstance'a donusturur.  numune_loader.py'nin dosya-sistemi bagimliligi
yerine saf bellek-temelli giris kabul eder.

Kullanim:
    from src.nesting3d.instances.stl_order_loader import build_instance_from_order

    result = build_instance_from_order(
        stl_map={"parca_a": <bytes>, "parca_b": <bytes>},
        quantities={"parca_a": 3, "parca_b": 7},
    )
    instance = result.instance
    # result.skipped_no_qty — STL var ama mailde adeti yok
    # result.skipped_no_stl — mailde ad var ama zip'te STL yok

Tasarim kararlari:
    - Esleme anahtari: stl_map anahtari == quantities anahtari (birerbir).
    - Sadece HEM stl_map HEM quantities'te bulunan parcalar instance'a girer.
    - format.py _make_mesh: source="stl" icin stl_path ZORUNLU (bossa ValueError).
      Bu nedenle her STL bytes'i gecici dosyaya yazilir; stl_path o gecici yola set
      edilir.  Gecici dosya fonksiyon scope'u bitince silindi (NamedTemporaryFile
      delete=True, context manager ile).
    - bbox boyutlari PartSpec'e ek meta olarak (width_mm/depth_mm/height_mm)
      atanir — pitch.py ve features.py bu alanlari kullanir.
    - Bozuk/bos mesh: skipped_no_stl'e eklenir + logging.warning.
    - Determinizm: giris sozlugu sirasi Python 3.7+'de ekleme sirasini korur;
      sorted() ile alfabetik isleme tutarlilik saglar.
"""

from __future__ import annotations

import io
import logging
import tempfile
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import trimesh

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cikti dataclass
# ---------------------------------------------------------------------------

@dataclass
class StlOrderResult:
    """build_instance_from_order cikti paketi."""

    instance: NestingInstance
    skipped_no_qty: list[str] = field(default_factory=list)
    """STL var ama mailde adeti yok -> atlanmis parca adlari."""
    skipped_no_stl: list[str] = field(default_factory=list)
    """Mailde ad var ama zip'te STL yok -> atlanmis parca adlari."""


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------

def _bbox_from_bytes(name: str, stl_bytes: bytes) -> Optional[tuple[float, float, float]]:
    """STL bytes'indan bounding-box extents (w, d, h) mm dondur.

    Hata durumunda None dondurur (cagiran skipped_no_stl'e ekler).
    """
    try:
        mesh = trimesh.load(
            io.BytesIO(stl_bytes),
            file_type="stl",
            force="mesh",
        )
    except Exception as exc:
        logger.warning("STL yuklenemedi '%s': %s", name, exc)
        return None

    if mesh.is_empty or len(mesh.faces) == 0:
        logger.warning("Bos veya okunamayan mesh: '%s'", name)
        return None

    mesh.apply_translation(-mesh.bounds[0])
    e = mesh.extents
    return float(e[0]), float(e[1]), float(e[2])


def _write_temp_stl(stl_bytes: bytes) -> str:
    """STL bytes'ini gecici dosyaya yaz, dosya yolunu dondur.

    Cagiran kod dosyayi kullandiktan sonra silmekle yukumludur.
    """
    tmp = tempfile.NamedTemporaryFile(
        suffix=".stl",
        delete=False,
    )
    try:
        tmp.write(stl_bytes)
        tmp.flush()
        tmp.close()
        return tmp.name
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise


def _write_persist_stl(persist_dir: Path, name: str, stl_bytes: bytes) -> str:
    """STL bytes'ini KALICI dizine '<ad>.stl' olarak yaz, yolunu dondur.

    persist_dir verildiginde dosya SILINMEZ — nesting voxelize edene kadar
    yasamasi gerekir (pipeline kullanimi). name guvenligi: basename alinir.
    """
    safe = os.path.basename(name) or "part"
    persist_dir.mkdir(parents=True, exist_ok=True)
    path = persist_dir / f"{safe}.stl"
    path.write_bytes(stl_bytes)
    return str(path)


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def build_instance_from_order(
    stl_map: dict[str, bytes],
    quantities: dict[str, int],
    *,
    container_w_mm: float = 335.0,
    container_d_mm: float = 335.0,
    container_h_mm: Optional[float] = None,
    persist_dir: Optional[Union[str, Path]] = None,
) -> StlOrderResult:
    """Siparis STL byte'lari + adet eslemesinden NestingInstance kur.

    Args:
        stl_map:       {uzantisiz_ad: stl_bytes} — zip extractor ciktisi.
        quantities:    {parca_adi: adet} — quantity parser ciktisi.
        container_w_mm: Konteyner genisligi (mm). Default 335.
        container_d_mm: Konteyner derinligi (mm). Default 335.
        container_h_mm: Konteyner yuksekligi (mm). None = open-dimension.
        persist_dir:   Verilirse STL'ler bu KALICI dizine yazilir ve SILINMEZ
                       (stl_path gecerli kalir — nesting/voxelize sonrasi
                       kullanim icin). None ise gecici dosya + fonksiyon
                       donusunde silinir (geriye uyum; sadece bbox/meta gecerli).

    Returns:
        StlOrderResult — instance + atlanan parca listeleri.
    """
    skipped_no_qty: list[str] = []
    skipped_no_stl: list[str] = []
    parts: list[PartSpec] = []
    temp_files: list[str] = []
    persist_path = Path(persist_dir) if persist_dir is not None else None

    # CASE-INSENSITIVE eşleşme: mail metnindeki ad (örn "Part282115_07D4113")
    # ile zip'teki dosya adı (örn "part282115_07D4113") büyük/küçük harf farkı
    # olsa da eşleşsin. Orijinal STL dosya adı görünür ad olarak korunur.
    _stl_lower = {k.lower(): k for k in stl_map}
    _qty_lower = {k.lower(): k for k in quantities}
    all_lower = sorted(set(_stl_lower) | set(_qty_lower))

    try:
        for low in all_lower:
            stl_key = _stl_lower.get(low)
            qty_key = _qty_lower.get(low)
            has_stl = stl_key is not None
            has_qty = qty_key is not None
            name = stl_key or qty_key  # tercihen STL dosya adı

            if has_stl and not has_qty:
                skipped_no_qty.append(name)
                logger.warning("Parca '%s': STL mevcut ama adet yok — atlanıyor.", name)
                continue

            if has_qty and not has_stl:
                skipped_no_stl.append(name)
                logger.warning("Parca '%s': Adet mevcut ama STL yok — atlanıyor.", name)
                continue

            # Her iki haritada da var — isle
            stl_bytes = stl_map[stl_key]
            qty = quantities[qty_key]

            bbox = _bbox_from_bytes(name, stl_bytes)
            if bbox is None:
                skipped_no_stl.append(name)
                logger.warning("Parca '%s': Bozuk mesh — skipped_no_stl'e eklendi.", name)
                continue

            w, d, h = bbox

            if persist_path is not None:
                stl_path = _write_persist_stl(persist_path, name, stl_bytes)
            else:
                stl_path = _write_temp_stl(stl_bytes)
                temp_files.append(stl_path)

            parts.append(
                PartSpec(
                    id=name,
                    name=name,
                    qty=qty,
                    source="stl",
                    stl_path=stl_path,
                    width_mm=w,
                    depth_mm=d,
                    height_mm=h,
                )
            )

    finally:
        # Sadece gecici dosyalar silinir; persist_dir dosyalari korunur.
        for tmp_path in temp_files:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    container = ContainerSpec(
        width_mm=container_w_mm,
        depth_mm=container_d_mm,
        height_mm=container_h_mm,
    )

    n_distinct = len(parts)
    total_qty = sum(p.qty for p in parts)

    instance = NestingInstance(
        container=container,
        parts=parts,
        meta={
            "family": "mail_order",
            "n_distinct_parts": n_distinct,
            "total_qty": total_qty,
        },
    )

    return StlOrderResult(
        instance=instance,
        skipped_no_qty=skipped_no_qty,
        skipped_no_stl=skipped_no_stl,
    )
