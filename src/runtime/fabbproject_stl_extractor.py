"""src/runtime/fabbproject_stl_extractor.py — Netfabb .fabbproject cikarici.

Sorumluluk: ham .fabbproject baytlarindan mesh'leri cikarip, ayni-geometri
orneklerini TIP olarak gruplayarak {taban_ad: binary_stl_baytlari} sozlugu
dondurur — zip_stl_extractor.extract_stls ile AYNI sozlesme. Taban ad
"parca{i}_{N}adet" desenindedir; boylece mevcut adet-cozumleme hatti
(dosya-adi kalibi) degismeden calisir.

Format (tersine-muhendislik, 2026-08-21 tam-dekod; YONTEM S2 kaydi +
fsm610 PLAN8 dosyasiyla dogrulandi — braket 75,5x79x48mm birebir):
  dosya : 8 bayt on-ek + "netfabb Project File (c) by FIT 2008" +
          (sikistirilmamis alanlar arasinda) zlib bloklari
  blok  : "tGcm" + ver(u32) + hdr_boyut(u32)=0x58 + nv(u32) +
          face_off(u32)=88+nv*12 + nf(u32) + 0-dolgu (88 bayta kadar) +
          int32 vertex*3 (birim 10nm = mm*100000) + int32 face-indeks*3 +
          ~100 bayt kuyruk
  Yerlestirilmis kopyalarin koordinatlari mesh'e gomuludur (ayri transform
  tablosu yok); bu yuzden tip-gruplama geometri imzasiyla (nv, nf,
  siralanmis-bbox) yapilir ve temsilci mesh min-koseye tasinir.

Guvenlik: acilan toplam bayt max_total_mb'yi asarsa ValueError (zip-bomb
korumasiyla tutarli); diger tum hatalarda bos dict + logging.warning
(pipeline dusurulmez, mail operatore duser).

Kullanim: dogrudan extract_stls_fabbproject(...) veya (onerilen)
zip_stl_extractor.extract_stls(...) — sihir isaretinden otomatik yonlenir.
"""

from __future__ import annotations

import logging
import struct
import zlib
from collections import OrderedDict
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# ASCII isaret dosyanin 8. baytinda baslar (onundeki 8 bayt surume gore
# degisebilir — guvenilir saptama isaretin kendisidir).
_ISARET = b"netfabb Project File"
_ISARET_OFSET = 8

_MESH_MAGIC = b"tGcm"
_HDR = 88
_OLCEK_MM = 100_000.0     # int32 birim: 10nm
_ZLIB_FLG = (0x01, 0x5E, 0x9C, 0xDA)
_TIP_YUVARLA_MM = 0.1     # tip-imzasi bbox yuvarlama adimi


def is_fabbproject(data: bytes) -> bool:
    """Baytlar Netfabb fabbproject isareti tasiyor mu?"""
    return data[_ISARET_OFSET:_ISARET_OFSET + len(_ISARET)] == _ISARET


def _zlib_bloklari(data: bytes, kalan_butce: int):
    """0x78-sihirli konumlardan zlib bloklarini butce-kapali acar.

    Butce asimi ValueError; acilamayan adaylar sessizce gecilir (mesh
    bloklari arasindaki sikistirilmamis alanlar normaldir).
    """
    i, n = 0, len(data)
    gorunum = memoryview(data)  # dilimleme kopyasiz olsun (17MB dosya x cok blok)
    acilan_toplam = 0
    while i < n - 2:
        if data[i] == 0x78 and data[i + 1] in _ZLIB_FLG:
            d = zlib.decompressobj()
            try:
                veri = d.decompress(gorunum[i:],
                                    kalan_butce - acilan_toplam + 1)
            except zlib.error:
                i += 1
                continue
            if d.unconsumed_tail:
                raise ValueError(
                    "fabbproject_stl_extractor: acilan boyut siniri asildi "
                    "(bomb korumasi)")
            if len(veri) > 64:
                acilan_toplam += len(veri)
                yield veri
                kullanilan = n - i - len(d.unused_data)
                i += max(kullanilan, 3)
                continue
        i += 1


def _mesh_coz(blok: bytes):
    """tGcm blogundan (verts_mm, faces) cikar; uymayan blok None."""
    if blok[:4] != _MESH_MAGIC or len(blok) < _HDR:
        return None
    nv, face_off, nf = struct.unpack_from("<III", blok, 12)
    if nv == 0 or nf == 0 or face_off != _HDR + nv * 12:
        return None
    if len(blok) < face_off + nf * 12:
        return None
    verts = struct.unpack_from(f"<{nv * 3}i", blok, _HDR)
    faces = struct.unpack_from(f"<{nf * 3}i", blok, face_off)
    if min(faces) < 0 or max(faces) >= nv:
        logger.warning(
            "fabbproject_stl_extractor: gecersiz yuz indeksi (nv=%d) — "
            "blok atlandi", nv)
        return None
    verts_mm = [v / _OLCEK_MM for v in verts]
    return verts_mm, faces, nv, nf


def _tip_imzasi(verts_mm: List[float], nv: int, nf: int) -> Tuple:
    """Ayni-geometri kopyalarini bulusturan imza (poz-bagimsiz).

    Koordinatlar kopyaya gomulu oldugundan bbox'in SIRALANMIS kenarlari
    kullanilir (eksen-degisimli rotasyonlara dayanikli)."""
    eksen_uz = []
    for e in range(3):
        seri = verts_mm[e::3]
        eksen_uz.append(max(seri) - min(seri))
    yuvarlak = tuple(round(u / _TIP_YUVARLA_MM) for u in sorted(eksen_uz))
    return (nv, nf) + yuvarlak


def _binary_stl(verts_mm: List[float], faces: Tuple[int, ...]) -> bytes:
    """Min-koseye tasinmis binary STL (normaller 0 — okuyucular yeniden
    hesaplar; hassas geometri kaynak dosyada)."""
    mins = [min(verts_mm[e::3]) for e in range(3)]
    n_ucgen = len(faces) // 3
    cikti = bytearray()
    cikti += b"fabbproject cikarimi (netfabb FIT 2008 v1)".ljust(80, b"\x00")
    cikti += struct.pack("<I", n_ucgen)
    for t in range(n_ucgen):
        kayit = [0.0, 0.0, 0.0]
        for k in faces[t * 3:t * 3 + 3]:
            kayit += [verts_mm[k * 3 + e] - mins[e] for e in range(3)]
        cikti += struct.pack("<12f", *kayit)
        cikti += b"\x00\x00"
    return bytes(cikti)


def extract_stls_fabbproject(
    data: bytes,
    *,
    max_total_mb: float = 200.0,
) -> Dict[str, bytes]:
    """Ham .fabbproject baytlarindan tip-gruplu STL sozlugu cikarir.

    Dondurur: {"parca1_126adet": stl_bytes, ...} — gruplar kopya-adedi
    (cok olan once), esitlikte ucgen sayisi buyuk olan once siralanir.
    Bos dict: isaret yok / hic mesh cozulemedi. ValueError: boyut asimi.
    """
    if not is_fabbproject(data):
        logger.warning(
            "fabbproject_stl_extractor: netfabb isareti yok — bos dict")
        return {}
    butce = int(max_total_mb * 1024 * 1024)
    gruplar: "OrderedDict[Tuple, dict]" = OrderedDict()
    try:
        for blok in _zlib_bloklari(data, butce):
            mesh = _mesh_coz(blok)
            if mesh is None:
                continue
            verts_mm, faces, nv, nf = mesh
            imza = _tip_imzasi(verts_mm, nv, nf)
            g = gruplar.get(imza)
            if g is None:
                gruplar[imza] = {"verts": verts_mm, "faces": faces,
                                 "nf": nf, "adet": 1}
            else:
                g["adet"] += 1
    except ValueError:
        raise
    except Exception as hata:  # bozuk govde pipeline'i dusurmesin
        logger.warning(
            "fabbproject_stl_extractor: cozumleme hatasi, bos dict — %s",
            hata)
        return {}
    if not gruplar:
        logger.warning(
            "fabbproject_stl_extractor: hic mesh blogu cozulemedi — bos dict")
        return {}
    sirali = sorted(gruplar.values(),
                    key=lambda g: (-g["adet"], -g["nf"]))
    sonuc: Dict[str, bytes] = {}
    for i, g in enumerate(sirali, 1):
        sonuc[f"parca{i}_{g['adet']}adet"] = _binary_stl(
            g["verts"], g["faces"])
    logger.info(
        "fabbproject_stl_extractor: %d mesh -> %d tip: %s",
        sum(g["adet"] for g in sirali), len(sirali),
        ", ".join(f"parca{i}x{g['adet']}" for i, g in enumerate(sirali, 1)))
    return sonuc
