"""tests/test_fabbproject_extract.py — fabbproject_stl_extractor birim testleri.

Kapsam:
  - Sentetik fabbproject (2 tip: kup x3 + tetra x2) -> tip-gruplu STL dict
    ("parca1_3adet" / "parca2_2adet"), ucgen sayilari ve mm olcek dogru
  - extract_stls yonlendirmesi: fabbproject sihir isareti -> ayni sozlesme
  - Bozuk govde (isaret var, icerik cop) -> bos dict, firlatmaz
  - Boyut butcesi asimi -> ValueError (arsiv-bomb korumasiyla tutarli)
  - Gercek PLAN8 dosyasi varsa (yerel): 132 mesh -> 126/4/1/1 gruplari
    (dosya yoksa test SKIP — tasinabilirlik)

Format referansi (FIT 2008 v1; 2026-08-21 tam-dekod, YONTEM S2 kaydi):
  dosya  : 8 bayt on-ek + "netfabb Project File (c) by FIT 2008" + zlib bloklari
  blok   : "tGcm" + ver(u32) + hdr(u32)=88 + nv(u32) + face_off(u32) + nf(u32)
           + 0-dolgu (88'e kadar) + int32 vertex*3 (10nm birim) + int32 face*3
           + 100 bayt kuyruk
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from src.runtime.fabbproject_stl_extractor import (
    extract_stls_fabbproject, is_fabbproject)
from src.runtime.zip_stl_extractor import extract_stls

OLCEK = 100_000  # mm -> 10nm

GERCEK_DOSYA = Path(__file__).resolve().parent.parent / (
    "Veriler/fsm610_2026-08-17/000_17-08-2026.fabbproject")


# ---------------------------------------------------------------------------
# Yardimcilar: sentetik mesh + fabbproject uretici
# ---------------------------------------------------------------------------

def _kup(kenar_mm=10.0, ofset=(0.0, 0.0, 0.0)):
    """8 kose / 12 ucgen birim kup (mm)."""
    k = kenar_mm
    ox, oy, oz = ofset
    v = [(x + ox, y + oy, z + oz)
         for z in (0.0, k) for y in (0.0, k) for x in (0.0, k)]
    f = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6),
         (0, 1, 4), (1, 5, 4), (2, 6, 3), (3, 6, 7),
         (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]
    return v, f


def _tetra(ofset=(0.0, 0.0, 0.0)):
    ox, oy, oz = ofset
    v = [(ox, oy, oz), (5.0 + ox, oy, oz), (ox, 5.0 + oy, oz),
         (ox, oy, 5.0 + oz)]
    f = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
    return v, f


def _tgcm_blok(verts_mm, faces) -> bytes:
    nv, nf = len(verts_mm), len(faces)
    face_off = 88 + nv * 12
    govde = bytearray()
    govde += b"tGcm" + struct.pack("<IIIII", 1, 0x58, nv, face_off, nf)
    govde += b"\x00" * (88 - len(govde))
    for x, y, z in verts_mm:
        govde += struct.pack("<iii", int(round(x * OLCEK)),
                             int(round(y * OLCEK)), int(round(z * OLCEK)))
    for a, b, c in faces:
        govde += struct.pack("<iii", a, b, c)
    govde += b"\x00" * 100  # kuyruk (gercek dosyada 100B)
    return zlib.compress(bytes(govde))


def _fabb_dosya(mesh_listesi) -> bytes:
    """Sentetik .fabbproject baytlari (bloklar arasi dolgu dahil)."""
    b = bytearray()
    b += b"\x99\xe1\x43\x2a\x02\x00\x00\x00"
    b += b"netfabb Project File (c) by FIT 2008\x00\x00"
    for verts, faces in mesh_listesi:
        b += b"\x01\x02\x03"          # sikistirilmamis ara-dolgu
        b += _tgcm_blok(verts, faces)
    return bytes(b)


def _stl_ucgen_sayisi(stl: bytes) -> int:
    assert len(stl) >= 84
    (n,) = struct.unpack_from("<I", stl, 80)
    assert len(stl) == 84 + n * 50
    return n


def _stl_koseler(stl: bytes):
    n = _stl_ucgen_sayisi(stl)
    noktalar = []
    for i in range(n):
        kayit = struct.unpack_from("<12f", stl, 84 + i * 50)
        noktalar += [kayit[3:6], kayit[6:9], kayit[9:12]]
    return noktalar


def _ornek_dosya() -> bytes:
    return _fabb_dosya([
        _kup(ofset=(0, 0, 0)),
        _tetra(ofset=(50, 0, 0)),
        _kup(ofset=(20, 30, 0)),
        _kup(ofset=(100, 100, 100)),
        _tetra(ofset=(70, 0, 0)),
    ])


# ---------------------------------------------------------------------------
# Testler
# ---------------------------------------------------------------------------

class TestSentetikCikarim:
    def test_isaret_tanima(self):
        assert is_fabbproject(_ornek_dosya())
        assert not is_fabbproject(b"PK\x03\x04 bu bir zip")

    def test_tip_gruplama_ve_adet_adlari(self):
        sonuc = extract_stls_fabbproject(_ornek_dosya())
        # kup x3 (12 ucgen) -> parca1; tetra x2 (4 ucgen) -> parca2
        assert set(sonuc.keys()) == {"parca1_3adet", "parca2_2adet"}

    def test_ucgen_sayilari(self):
        sonuc = extract_stls_fabbproject(_ornek_dosya())
        assert _stl_ucgen_sayisi(sonuc["parca1_3adet"]) == 12
        assert _stl_ucgen_sayisi(sonuc["parca2_2adet"]) == 4

    def test_mm_olcek_ve_orijine_tasima(self):
        """Temsilci mesh min-koseye tasinir; kup kenari 10mm okunmali."""
        sonuc = extract_stls_fabbproject(_ornek_dosya())
        noktalar = _stl_koseler(sonuc["parca1_3adet"])
        for eksen in range(3):
            degerler = [p[eksen] for p in noktalar]
            assert min(degerler) == pytest.approx(0.0, abs=1e-4)
            assert max(degerler) == pytest.approx(10.0, abs=1e-4)

    def test_extract_stls_yonlendirmesi(self):
        """Ana giris noktasi fabbproject'i otomatik saptar (zip/rar gibi)."""
        sonuc = extract_stls(_ornek_dosya())
        assert set(sonuc.keys()) == {"parca1_3adet", "parca2_2adet"}


class TestHataYollari:
    def test_bozuk_icerik_bos_dict(self):
        bozuk = _ornek_dosya()[:60] + b"\xff" * 200
        assert extract_stls_fabbproject(bozuk) == {}

    def test_gecersiz_indeks_blogu_atlanir(self):
        """Yuz indeksi nv'yi asan blok atlanir, kalanlar cikar."""
        v, f = _tetra()
        f_bozuk = [(0, 1, 99)] + f[1:]
        dosya = _fabb_dosya([(v, f), (v, f_bozuk)])
        sonuc = extract_stls_fabbproject(dosya)
        assert list(sonuc.keys()) == ["parca1_1adet"]

    def test_boyut_butcesi_valueerror(self):
        with pytest.raises(ValueError):
            extract_stls_fabbproject(_ornek_dosya(), max_total_mb=0.00001)

    def test_zip_yolu_etkilenmez(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.stl", b"solid A\nendsolid A")
        sonuc = extract_stls(buf.getvalue())
        assert set(sonuc.keys()) == {"a"}


class TestGercekPlan8:
    """Gercek PLAN8 dosyasi yerelde varsa tam-dekod dogrulamasi."""

    @pytest.mark.skipif(not GERCEK_DOSYA.exists(),
                        reason="gercek fabbproject yerelde yok")
    def test_plan8_envanteri(self):
        sonuc = extract_stls_fabbproject(GERCEK_DOSYA.read_bytes())
        adetler = sorted(
            (int(ad.rsplit("_", 1)[1][:-4]) for ad in sonuc), reverse=True)
        assert adetler == [126, 4, 1, 1]
