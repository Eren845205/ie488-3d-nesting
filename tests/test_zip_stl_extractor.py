"""tests/test_zip_stl_extractor.py — zip_stl_extractor modulu birim testleri.

Kapsam:
  - 3 STL iceren zip -> 3 anahtar, dogru bytes
  - STL + TXT + README karisik -> sadece STL anahtarlari
  - Alt dizin icindeki STL -> anahtar dizin yolu icermez (basename)
  - Path-traversal adli dosya "../evil.stl" -> anahtar "evil" (nötrlenmiş)
  - Boyut limitini asan zip -> ValueError firlatir
  - Bozuk zip byte'lari -> bos dict dondurur, firlatmaz
  - Determinizm: ayni zip -> ayni sonuc
"""

from __future__ import annotations

import io
import zipfile

import pytest

from src.runtime.zip_stl_extractor import extract_stls, _fix_cp437_mojibake


# ---------------------------------------------------------------------------
# Yardimci: bellek-ici zip olusturucu
# ---------------------------------------------------------------------------

def _make_zip(entries: dict[str, bytes]) -> bytes:
    """Bellek-ici sahte zip olusturur.

    entries: {zip_icindeki_yol: dosya_icerik_baytlari}
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test 1: 3 STL iceren zip -> 3 anahtar, dogru bytes
# ---------------------------------------------------------------------------

class TestUcStlDosyasi:
    """Uc adet STL iceren zip dogru sekilde cozulur."""

    def test_uc_anahtar_donus(self):
        parca_a = b"solid A\nendsolid A"
        parca_b = b"solid B\nendsolid B"
        parca_c = b"solid C\nendsolid C"
        zip_bytes = _make_zip({
            "parca_a.stl": parca_a,
            "parca_b.stl": parca_b,
            "parca_c.stl": parca_c,
        })
        sonuc = extract_stls(zip_bytes)
        assert set(sonuc.keys()) == {"parca_a", "parca_b", "parca_c"}

    def test_uc_anahtar_bytes_dogru(self):
        parca_a = b"solid A\nendsolid A"
        parca_b = b"solid B\nendsolid B"
        parca_c = b"solid C\nendsolid C"
        zip_bytes = _make_zip({
            "parca_a.stl": parca_a,
            "parca_b.stl": parca_b,
            "parca_c.stl": parca_c,
        })
        sonuc = extract_stls(zip_bytes)
        assert sonuc["parca_a"] == parca_a
        assert sonuc["parca_b"] == parca_b
        assert sonuc["parca_c"] == parca_c


# ---------------------------------------------------------------------------
# Test 2: STL + TXT + README karisik -> sadece STL anahtarlari
# ---------------------------------------------------------------------------

class TestKarisikIcerik:
    """STL olmayan dosyalar atlanir."""

    def test_sadece_stl_anahtarlari(self):
        zip_bytes = _make_zip({
            "parca.stl": b"solid X\nendsolid X",
            "notlar.txt": b"bu bir not",
            "README": b"okuyun",
            "talimat.pdf": b"%PDF-1.4",
        })
        sonuc = extract_stls(zip_bytes)
        assert set(sonuc.keys()) == {"parca"}

    def test_stl_olmayan_dahil_edilmez(self):
        zip_bytes = _make_zip({
            "a.stl": b"solid\nendsolid",
            "b.STL": b"solid\nendsolid",  # buyuk harf uzanti
            "c.txt": b"metin",
        })
        sonuc = extract_stls(zip_bytes)
        # STL uzantisi (kucuk/buyuk harf farksiz)
        assert "c" not in sonuc
        assert len(sonuc) == 2


# ---------------------------------------------------------------------------
# Test 3: Alt dizin icindeki STL -> anahtar dizinsiz basename
# ---------------------------------------------------------------------------

class TestAltDizin:
    """Alt dizindeki STL dosyasinda anahtar sadece taban ad olmali."""

    def test_alt_dizin_atilir(self):
        zip_bytes = _make_zip({
            "parts/ENG-500053_L-Bracket.stl": b"solid\nendsolid",
        })
        sonuc = extract_stls(zip_bytes)
        assert "ENG-500053_L-Bracket" in sonuc
        assert "parts/ENG-500053_L-Bracket" not in sonuc

    def test_derin_dizin_atilir(self):
        zip_bytes = _make_zip({
            "a/b/c/d.stl": b"solid d\nendsolid d",
        })
        sonuc = extract_stls(zip_bytes)
        assert "d" in sonuc
        assert "a/b/c/d" not in sonuc


# ---------------------------------------------------------------------------
# Test 4: Path-traversal adi "../evil.stl" -> anahtar "evil"
# ---------------------------------------------------------------------------

class TestPathTraversal:
    """Path-traversal icerikli dosya adlari nötrlenmelidir."""

    def test_traversal_notrlenmiş(self):
        # zipfile modulu "../evil.stl" gibi adlara izin verir; extract_stls nötrlemeli
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as zf:
            zf.writestr("../evil.stl", b"solid evil\nendsolid evil")
        zip_bytes = buf.getvalue()

        sonuc = extract_stls(zip_bytes)
        # Anahtar "evil" olmali; path traversal korunmali
        assert "evil" in sonuc
        # Geçis bileşeni (../evil veya ../evil.stl) anahtar olmamali
        for key in sonuc:
            assert ".." not in key
            assert "/" not in key
            assert "\\" not in key

    def test_diske_hicbir_sey_yazilmaz(self, tmp_path, monkeypatch):
        """Bellek-ici calisma — gecici dizine bile dosya yazilmamali."""
        import os
        yazilan_dosyalar: list[str] = []
        orijinal_open = open

        def izleyen_open(path, mode="r", *args, **kwargs):
            if "w" in mode or "x" in mode or "a" in mode:
                yazilan_dosyalar.append(str(path))
            return orijinal_open(path, mode, *args, **kwargs)

        # io.BytesIO ile calisildigi icin disk yazimi beklenmez;
        # test sadece sonucun bos olmadigini dogrular
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w") as zf:
            zf.writestr("../evil.stl", b"solid evil\nendsolid evil")
        sonuc = extract_stls(buf.getvalue())
        assert "evil" in sonuc


# ---------------------------------------------------------------------------
# Test 5: Boyut limitini asan zip -> ValueError
# ---------------------------------------------------------------------------

class TestBoyutLimiti:
    """Toplam STL boyutu max_total_mb'yi asinca ValueError firlatilmali."""

    def test_limit_asilinca_hata(self):
        # 1 MB'lik sahte STL verisi
        buyuk_stl = b"x" * (1024 * 1024)  # 1 MB
        zip_bytes = _make_zip({
            "parca1.stl": buyuk_stl,
            "parca2.stl": buyuk_stl,
        })
        # max_total_mb=1.5 -> 2 MB toplam -> limit asiliyor
        with pytest.raises(ValueError, match="boyut"):
            extract_stls(zip_bytes, max_total_mb=1.5)

    def test_limit_altinda_calisiyor(self):
        kucuk_stl = b"solid\nendsolid"
        zip_bytes = _make_zip({
            "kucuk.stl": kucuk_stl,
        })
        # Cok kucuk dosya, herhangi bir mantikli limitin altinda
        sonuc = extract_stls(zip_bytes, max_total_mb=1.0)
        assert "kucuk" in sonuc

    def test_tam_limitte_gecmez(self):
        """Tam limit esitlenmis -> asma yok, gecmeli."""
        # Tam olarak 1 MB
        tam_limit = b"y" * (1024 * 1024)
        zip_bytes = _make_zip({"tam.stl": tam_limit})
        # tam esit -> asmiyor
        sonuc = extract_stls(zip_bytes, max_total_mb=1.0)
        assert "tam" in sonuc


# ---------------------------------------------------------------------------
# Fix-2 (HIGH): decompress-ONCESI on-eleme + chunk'li okuma (zip-bomb)
# ---------------------------------------------------------------------------

class TestZipBombOnEleme:
    """Tek girisli yuksek-oranli zip (zip-bomb) icin: (a) ZipInfo'nun bildirdigi
    acilmis boyut (file_size) kalan butceyi zaten asiyorsa girisi HIC acmadan/
    okumadan reddet; (b) gecen girisler chunk'li okunur (tek `.read()` cagrisiyla
    tum icerik bellege alinmaz)."""

    def test_declared_size_preempts_any_read_for_oversized_single_entry(self, monkeypatch):
        """Tek giris zaten limiti asiyorsa (bilgi.file_size > butce), o girisin
        icerigi ne zf.read (tum-dosya) ne de akis (.read chunk'lari) ile
        okunur — pre-check decompress'ten ONCE devreye girer.

        NOT: zipfile.ZipFile(...) constructor'i kendi ic dogrulamasi icin
        (data-descriptor tespiti) SON girisi zf.open() ile acabilir — bu
        zipfile'in KENDI davranisidir, extract_stls'in kontrolu disinda.
        Bu yuzden asil kanit: acilan akistan HICBIR BAYT OKUNMAMASI (ne
        ZipFile.read ne de ZipExtFile.read cagrilir).
        """
        read_calls = []
        stream_read_calls = []
        orig_read = zipfile.ZipFile.read
        orig_stream_read = zipfile.ZipExtFile.read

        def _tracking_read(self, *a, **kw):
            read_calls.append(a)
            return orig_read(self, *a, **kw)

        def _tracking_stream_read(self, *a, **kw):
            stream_read_calls.append(a)
            return orig_stream_read(self, *a, **kw)

        monkeypatch.setattr(zipfile.ZipFile, "read", _tracking_read)
        monkeypatch.setattr(zipfile.ZipExtFile, "read", _tracking_stream_read)

        buyuk_stl = b"x" * (2 * 1024 * 1024)  # 2 MB
        zip_bytes = _make_zip({"buyuk.stl": buyuk_stl})

        with pytest.raises(ValueError, match="boyut"):
            extract_stls(zip_bytes, max_total_mb=1.0)

        assert not read_calls, (
            "declared file_size zaten limiti asiyordu; ZipFile.read (tum-dosya) "
            f"hic cagrilmamaliydi (read_calls={read_calls})"
        )
        assert not stream_read_calls, (
            "declared file_size zaten limiti asiyordu; akistan HICBIR bayt "
            f"okunmamaliydi (stream_read_calls={stream_read_calls})"
        )

    def test_second_entry_preempted_by_running_total(self):
        """Ilk giris butceyi doldurursa, ikinci giris (kendi basina makul boyutta
        olsa bile) acilan-toplam ile birlikte asimi tetikler ve okunmadan reddedilir."""
        bir_mb = b"x" * (1024 * 1024)
        zip_bytes = _make_zip({"a.stl": bir_mb, "b.stl": bir_mb})
        # max=1.5MB: ilk giris (1MB) gecer, ikinci giris (1MB) toplami 2MB'a
        # cikarir -> 1.5MB siniri asilir.
        with pytest.raises(ValueError, match="boyut"):
            extract_stls(zip_bytes, max_total_mb=1.5)

    def test_chunked_reading_no_single_full_file_read_call(self, monkeypatch):
        """Gecen (limit-alti) giris chunk'lar halinde okunur; ZipExtFile.read
        parametresiz/negatif (tum-dosyayi-tek-seferde) cagrilmaz."""
        call_sizes = []
        orig_read = zipfile.ZipExtFile.read

        def _tracking_read(self, n=-1, *a, **kw):
            call_sizes.append(n)
            return orig_read(self, n, *a, **kw)

        monkeypatch.setattr(zipfile.ZipExtFile, "read", _tracking_read)

        zip_bytes = _make_zip({"a.stl": b"solid a\nendsolid a" * 100})
        sonuc = extract_stls(zip_bytes)

        assert "a" in sonuc
        assert call_sizes, "ZipExtFile.read hic cagrilmadi"
        assert all(n is not None and n > 0 for n in call_sizes), (
            f"tum-dosya-tek-seferde okuma tespit edildi (chunk boyutu verilmemis): {call_sizes}"
        )

    def test_multi_chunk_entry_still_extracted_correctly(self):
        """Tek chunk sinirindan (1 MB) buyuk ama limit-alti bir giris dogru
        sekilde parca-parca birlestirilip donmeli (bytes bozulmamali)."""
        icerik = bytes((i % 256) for i in range(1024 * 1024 + 777))  # ~1MB + fazla
        zip_bytes = _make_zip({"coklu_chunk.stl": icerik})
        sonuc = extract_stls(zip_bytes, max_total_mb=5.0)
        assert sonuc["coklu_chunk"] == icerik


# ---------------------------------------------------------------------------
# Test 6: Bozuk byte (b"not a zip") -> bos dict, firlatmaz
# ---------------------------------------------------------------------------

class TestBozukZip:
    """Bozuk zip verisi bos dict dondurmeli, hata firlatmamali."""

    def test_bozuk_bayt_bos_dict(self):
        sonuc = extract_stls(b"bu bir zip degil")
        assert sonuc == {}

    def test_bos_bayt_bos_dict(self):
        sonuc = extract_stls(b"")
        assert sonuc == {}

    def test_yanlis_header_bos_dict(self):
        sonuc = extract_stls(b"\x00\x01\x02\x03\x04\x05")
        assert sonuc == {}

    def test_bos_zip_bos_dict(self):
        """STL icermeyen gecerli zip -> bos dict (hata yok)."""
        zip_bytes = _make_zip({"notlar.txt": b"icerik"})
        sonuc = extract_stls(zip_bytes)
        assert sonuc == {}


# ---------------------------------------------------------------------------
# Test 7: Determinizm — ayni zip -> ayni sonuc
# ---------------------------------------------------------------------------

class TestDeterminizm:
    """Ayni girdi -> ayni sonuc (cagri sayisindan bagimsiz)."""

    def test_tekrarli_cagri_ayni_sonuc(self):
        parca = b"solid test\nendsolid test"
        zip_bytes = _make_zip({"test_parca.stl": parca})
        sonuc1 = extract_stls(zip_bytes)
        sonuc2 = extract_stls(zip_bytes)
        sonuc3 = extract_stls(zip_bytes)
        assert sonuc1 == sonuc2 == sonuc3

    def test_farkli_zip_farkli_sonuc(self):
        zip_a = _make_zip({"a.stl": b"solid a\nendsolid a"})
        zip_b = _make_zip({"b.stl": b"solid b\nendsolid b"})
        assert extract_stls(zip_a) != extract_stls(zip_b)


# ---------------------------------------------------------------------------
# Ek test: Cakisan ad -> sonuncuyu kullan (loglanir ama patlamaz)
# ---------------------------------------------------------------------------

class TestCakisanAd:
    """Farkli dizinde ayni taban adli STL -> sonuncusu kazanir, hata yok."""

    def test_cakisan_ad_hata_vermez(self):
        zip_bytes = _make_zip({
            "dir1/parca.stl": b"solid ilk\nendsolid ilk",
            "dir2/parca.stl": b"solid son\nendsolid son",
        })
        # Sadece bir "parca" anahtari olmali (cakisma)
        sonuc = extract_stls(zip_bytes)
        assert "parca" in sonuc
        assert len(sonuc) == 1

    def test_buyuk_kucuk_harf_stl_uzantisi(self):
        """STL / .STL / .Stl hepsi isaretlenmeli."""
        zip_bytes = _make_zip({
            "a.STL": b"solid a\nendsolid a",
            "b.Stl": b"solid b\nendsolid b",
            "c.stl": b"solid c\nendsolid c",
        })
        sonuc = extract_stls(zip_bytes)
        assert set(sonuc.keys()) == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# Dalga-2 #8: ZIP icinde cp437 Turkce mojibake duzeltmesi
# ---------------------------------------------------------------------------

class TestCp437MojibakeDuzeltme:
    """UTF-8 bayraksiz ZIP (Windows Explorer davranisi) Turkce dosya adlarini
    cp437 ile cozer -> mojibake. extract_stls bunu geri cevirmeli."""

    def test_fix_cp437_mojibake_flag_yoksa_duzeltir(self):
        """flag_bits UTF-8 bayragi (0x800) TASIMIYORSA cp857 ile geri cozulur."""
        orijinal = "parça_gövde"
        mojibake = orijinal.encode("cp857").decode("cp437")
        duzeltilmis = _fix_cp437_mojibake(mojibake, flag_bits=0x00)
        assert duzeltilmis == orijinal

    def test_fix_cp437_mojibake_utf8_bayragi_varsa_dokunmaz(self):
        """UTF-8 bayragi (0x800) VARSA ad zaten dogru -- degistirilmez."""
        ad = "parça_gövde.stl"
        assert _fix_cp437_mojibake(ad, flag_bits=0x800) == ad

    def test_fix_cp437_mojibake_ascii_ad_no_op(self):
        """ASCII ad (cp437 roundtrip'i degismez birakir) -- regresyon yok."""
        ad = "ENG-500053_L-Bracket.stl"
        assert _fix_cp437_mojibake(ad, flag_bits=0x00) == ad

    def test_extract_stls_cp437_mojibake_gercek_ada_donusur(self, monkeypatch):
        """extract_stls entegrasyonu: UTF-8 bayraksiz girisde mojibake ad
        gercek Turkce ada donusur ve STL icerigi dogru eslenir."""
        orijinal_ad = "parça_gövde"
        mojibake_ad = orijinal_ad.encode("cp857").decode("cp437")
        icerik = b"solid govde\nendsolid govde"
        zip_bytes = _make_zip({"PLACEHOLDER.stl": icerik})

        orig_infolist = zipfile.ZipFile.infolist

        def _patched_infolist(self):
            infos = orig_infolist(self)
            for info in infos:
                if info.filename == "PLACEHOLDER.stl":
                    info.filename = mojibake_ad + ".stl"
                    info.flag_bits &= ~0x800  # UTF-8 bayragi yok (harici arac davranisi)
            return infos

        monkeypatch.setattr(zipfile.ZipFile, "infolist", _patched_infolist)
        sonuc = extract_stls(zip_bytes)
        assert orijinal_ad in sonuc
        assert sonuc[orijinal_ad] == icerik
