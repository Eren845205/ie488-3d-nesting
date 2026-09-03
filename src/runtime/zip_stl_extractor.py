"""src/runtime/zip_stl_extractor.py — Mail ekinden gelen arsiv icindeki STL cikarici.

Sorumluluk: ham arsiv byte'larindan (.zip VEYA .rar) .stl dosyalarini guvenli
bicimde cikarip {uzantisiz_taban_ad: stl_baytlari} sozlugu olarak dondurur.
Bicim, dosya iceriginin sihir baytlarindan (PK / Rar!) otomatik saptanir —
cagiranin uzanti bilmesi gerekmez.

Guvenlik garantileri
--------------------
- Zip-slip / path traversal: Tum dosya adlarindan dizin bilesenleri atilir;
  sadece basename kullanilir. ZIP yolu diske hic yazmaz (BytesIO); RAR yolu
  yalniz gecici izole dizine acar ve is bitince siler.
- Boyut bombasi: Acilan toplam STL bayt miktari max_total_mb'yi asarsa
  ValueError firlatilir (arsiv-bomb korumasI). RAR yolunda ek olarak acma
  ONCESI arac listelemesinden beyan-boyut toplami kontrol edilir.
- Bozuk arsiv: zipfile.BadZipFile / arac hatasi yakalanir, bos dict
  dondurulur + logging.warning. (Boyut siniri asimi HARIC hata firlatilmaz.)
- RAR icin harici arac gerekir (7-Zip veya Windows 10+ tar.exe/libarchive);
  hicbiri yoksa bos dict + uyari (pipeline dusurulmez, mail operatore duser).

Kullanim
--------
  from src.runtime.zip_stl_extractor import extract_stls

  stl_map = extract_stls(arsiv_bytes)
  # -> {"ENG-500053_L-Bracket": b"...", ...}
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from typing import List, Optional

logger = logging.getLogger(__name__)

# RAR sihir baytlari: v4 "Rar!\x1a\x07\x00", v5 "Rar!\x1a\x07\x01\x00" —
# ortak onek yeterli (bicim ayrimini harici arac yapar).
_RAR_MAGIC = b"Rar!\x1a\x07"

# Fix-2 (HIGH): tek-girisli yuksek-oranli zip (zip-bomb) korumasi. Once ZipInfo'nun
# bildirdigi acilmis boyutla (bilgi.file_size) on-eleme yapilir (hic decompress
# edilmeden reddedilir); gecerse okuma bu boyutta chunk'lar halinde yapilir ve her
# chunk sonrasi biriken toplam kontrol edilir (bildirilen boyut bozuk/yalan olsa
# bile akis erken kesilir).
_CHUNK_SIZE = 1 << 20  # 1 MB


def _fix_cp437_mojibake(name: str, flag_bits: int) -> str:
    """cp437 mojibake'i orijinal Turkce ada cevirir (Dalga-2 #8).

    zipfile UTF-8 bayragi (0x800) TASIMAYAN girisleri her zaman cp437 ile
    cozer (ZIP standardinin eski davranisi). Windows Explorer gibi araclar
    bu bayragi koymadan yerel kod sayfasiyla (Turkce sistemde cp857/cp1254
    ailesi) yazar -> Turkce harfler mojibake olur. Bu fonksiyon zaten-cp437
    cozulmus adi kendi baytlarina geri kodlayip cp857 (sonra utf-8) ile
    yeniden cozmeyi dener; hicbiri anlamli sonuc vermezse (roundtrip hatasi)
    ad DEGISTIRILMEDEN dondurulur (ASCII adlar icin no-op).
    """
    if flag_bits & 0x800:
        return name  # UTF-8 bayragi var -- ad zaten dogru kodlanmis
    try:
        ham = name.encode("cp437")
    except UnicodeEncodeError:
        return name  # cp437'den gelmemis olmali -- dokunma
    for enc in ("cp857", "utf-8"):
        try:
            duzeltilmis = ham.decode(enc)
        except UnicodeDecodeError:
            continue
        return duzeltilmis
    return name


# ---------------------------------------------------------------------------
# RAR yolu — harici arac ile gecici dizine acma (7z / bsdtar)
# ---------------------------------------------------------------------------

def _rar_araci_bul() -> Optional[List[str]]:
    """RAR acabilen harici arac komut govdesini bul (oncelik: 7z, tar).

    7-Zip her RAR surumunu okur; Windows 10+ tar.exe (libarchive) rar/rar5
    okuyucusu tasir. Ikisi de yoksa None (cagiran bos dict dondurur).
    """
    yol = shutil.which("7z")
    if yol:
        return [yol]
    for aday in (r"C:\Program Files\7-Zip\7z.exe",
                 r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if os.path.exists(aday):
            return [aday]
    sistem_tar = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
    if os.path.exists(sistem_tar):
        return [sistem_tar]
    return None


def _rar_beyan_boyut(arac: List[str], rar_path: str) -> Optional[int]:
    """Arac listelemesinden acilmis-boyut toplamini oku (bomba on-elemesi).

    7z: `l -slt` cikti satirlari "Size = N" (giris basina). tar: `-tvf`
    5. kolon. Listeleme basarisiz/parse edilemezse None — cagiran acma
    SONRASI kesin kontrole guvenir (cifte savunmanin ikinci kati).
    """
    ad = os.path.basename(arac[0]).lower()
    try:
        if ad.startswith("7z"):
            p = subprocess.run(arac + ["l", "-slt", rar_path],
                               capture_output=True, timeout=60)
            if p.returncode != 0:
                return None
            metin = p.stdout.decode("utf-8", "replace")
            boyutlar = re.findall(r"^Size = (\d+)\s*$", metin, re.MULTILINE)
            return sum(int(b) for b in boyutlar) if boyutlar else None
        p = subprocess.run(arac + ["-tvf", rar_path],
                           capture_output=True, timeout=60)
        if p.returncode != 0:
            return None
        toplam = 0
        gecerli = False
        for satir in p.stdout.decode("utf-8", "replace").splitlines():
            alanlar = satir.split(None, 8)
            if len(alanlar) >= 5 and alanlar[4].isdigit():
                toplam += int(alanlar[4])
                gecerli = True
        return toplam if gecerli else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _extract_stls_rar(rar_bytes: bytes, max_total_bytes: float) -> dict[str, bytes]:
    """RAR baytlarini gecici dizine acip .stl dosyalarini toplar.

    ZIP yoluyla AYNI sozlesme: basename anahtari, yalniz .stl, cakisma =
    son kazanir + uyari, boyut asimi = ValueError, diger hatalar = bos dict.
    """
    arac = _rar_araci_bul()
    if arac is None:
        logger.warning(
            "zip_stl_extractor: RAR eki icin acici arac yok (7-Zip veya "
            "Windows tar.exe gerekli) — ek atlaniyor, bos dict donduruluyor."
        )
        return {}

    tmp = tempfile.mkdtemp(prefix="rar_stl_")
    try:
        rar_path = os.path.join(tmp, "ek.rar")
        with open(rar_path, "wb") as f:
            f.write(rar_bytes)

        # Kat-1: acma ONCESI beyan-boyut on-elemesi (bomba korumasi).
        beyan = _rar_beyan_boyut(arac, rar_path)
        if beyan is not None and beyan > max_total_bytes:
            raise ValueError(
                f"zip_stl_extractor: RAR beyan acilmis boyutu siniri asiyor — "
                f"{beyan / (1024 * 1024):.2f} MB > "
                f"max {max_total_bytes / (1024 * 1024):.2f} MB (rar-bomb korumasI)"
            )

        cikti_dir = os.path.join(tmp, "acilan")
        os.makedirs(cikti_dir, exist_ok=True)
        ad = os.path.basename(arac[0]).lower()
        if ad.startswith("7z"):
            komut = arac + ["x", "-y", f"-o{cikti_dir}", rar_path]
        else:
            komut = arac + ["-xf", rar_path, "-C", cikti_dir]
        p = subprocess.run(komut, capture_output=True, timeout=300)
        if p.returncode != 0:
            logger.warning(
                "zip_stl_extractor: RAR acilamadi (arac=%s, kod=%d) — bos "
                "dict donduruluyor. stderr: %.200s",
                os.path.basename(arac[0]), p.returncode,
                p.stderr.decode("utf-8", "replace"),
            )
            return {}

        # Kat-2: acma SONRASI kesin boyut kontrolu (listeleme yalan/parse
        # edilememis olsa bile son savunma) + toplama.
        sonuc: dict[str, bytes] = {}
        toplam = 0
        for kok, _dirs, dosyalar in os.walk(cikti_dir):
            for dosya in dosyalar:
                _k, uzanti = os.path.splitext(dosya)
                if uzanti.lower() != ".stl":
                    continue
                yol = os.path.join(kok, dosya)
                boyut = os.path.getsize(yol)
                if toplam + boyut > max_total_bytes:
                    raise ValueError(
                        f"zip_stl_extractor: acilan STL boyutu siniri asildi — "
                        f"toplam {(toplam + boyut) / (1024 * 1024):.2f} MB > "
                        f"max {max_total_bytes / (1024 * 1024):.2f} MB "
                        f"(rar-bomb korumasI, dosya={dosya!r})"
                    )
                anahtar = os.path.splitext(os.path.basename(dosya))[0]
                if anahtar in sonuc:
                    logger.warning(
                        "zip_stl_extractor: cakisan taban ad (RAR), onceki "
                        "uzerine yaziliyor — anahtar=%r, yeni_dosya=%r",
                        anahtar, dosya,
                    )
                with open(yol, "rb") as f:
                    sonuc[anahtar] = f.read()
                toplam += boyut
        return sonuc
    except (OSError, subprocess.TimeoutExpired) as hata:
        logger.warning(
            "zip_stl_extractor: RAR isleme hatasi, bos dict donduruluyor — %s",
            hata,
        )
        return {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extract_stls(
    zip_bytes: bytes,
    *,
    max_total_mb: float = 200.0,
) -> dict[str, bytes]:
    """Ham arsiv (.zip/.rar) byte'larindan .stl dosyalarini cikarir.

    Parametreler
    ------------
    zip_bytes    : Mail ekinden alinan ham zip baytlari.
    max_total_mb : Acilan toplam STL boyutu ust siniri (MB). Asilirsa
                   ValueError firlatilir (zip-bomb korumasI).

    Dondurur
    --------
    dict[str, bytes]
        Anahtar: uzantisiz taban ad (orn. "ENG-500053_L-Bracket").
        Deger  : ilgili STL dosyasinin ham baytlari.
        Bos dict: zip bozuksa veya hic STL yoksa.

    Firlatir
    --------
    ValueError
        Acilan toplam STL boyutu max_total_mb'yi asinca (zip-bomb korumasI).
        Diger hata durumlarinda FIRLATMAZ; bos dict + logging.warning dondurur.

    Notlar
    ------
    - Yalnizca .stl uzantili dosyalar (buyuk/kucuk harf farksiz) islenir.
    - Dizin bilesenleri (subdir/, ../) atilir; sadece basename kullanilir.
    - Cakisan taban ad olursa onceki kayit uzerine yazilir (son kazanir) +
      logging.warning ile bildirilir.
    - Diske hicbir sey yazilmaz.
    """
    max_total_bytes = max_total_mb * 1024 * 1024

    # Bicim saptama: RAR sihir baytlari -> harici arac yolu; Netfabb
    # fabbproject isareti -> mesh-cikarma yolu (tip-gruplu "parca{i}_{N}adet"
    # anahtarlari, ayni sozlesme); aksi halde ZIP yolu (PK olmayan bozuk veri
    # zipfile.BadZipFile ile ayni sekilde bos dict'e duser — eski davranis
    # birebir korunur).
    if zip_bytes[:len(_RAR_MAGIC)] == _RAR_MAGIC:
        return _extract_stls_rar(zip_bytes, max_total_bytes)
    from src.runtime.fabbproject_stl_extractor import (
        extract_stls_fabbproject, is_fabbproject)
    if is_fabbproject(zip_bytes):
        return extract_stls_fabbproject(zip_bytes, max_total_mb=max_total_mb)

    sonuc: dict[str, bytes] = {}

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf:
            toplam_bayt = 0
            for bilgi in zf.infolist():
                # Dizin girisleri (/ ile bitenler) atla
                if bilgi.filename.endswith("/"):
                    continue

                # Dalga-2 #8: cp437 mojibake duzeltmesi (UTF-8 bayraksiz TR ad)
                duzeltilmis_ad = _fix_cp437_mojibake(bilgi.filename, bilgi.flag_bits)

                # Uzanti kontrolu — sadece .stl (buyuk/kucuk harf farksiz)
                _kok, uzanti = os.path.splitext(duzeltilmis_ad)
                if uzanti.lower() != ".stl":
                    continue

                # Zip-slip / path-traversal korumasI: dizin bileseni at
                guvenli_taban = os.path.basename(duzeltilmis_ad)
                if not guvenli_taban:
                    # Ola ki basename bossa (ornek: "/../") atla
                    logger.warning(
                        "zip_stl_extractor: guvensiz dosya adi atlandi — %r",
                        bilgi.filename,
                    )
                    continue

                # Uzantisiz taban ad (anahtar)
                anahtar, _ = os.path.splitext(guvenli_taban)

                # Cakisma kontrolu
                if anahtar in sonuc:
                    logger.warning(
                        "zip_stl_extractor: cakisan taban ad, onceki uzerine yaziliyor — "
                        "anahtar=%r, yeni_dosya=%r",
                        anahtar,
                        bilgi.filename,
                    )

                # Fix-2 (a): decompress-ONCESI on-eleme — ZipInfo'nun bildirdigi
                # acilmis boyut (bilgi.file_size) kalan butceyi zaten asiyorsa bu
                # girisi HIC acma/okuma (zip-bomb: kucuk sikistirilmis boyut, dev
                # acilmis boyut).
                if toplam_bayt + bilgi.file_size > max_total_bytes:
                    raise ValueError(
                        f"zip_stl_extractor: acilan STL boyutu siniri asildi — "
                        f"tahmini toplam {(toplam_bayt + bilgi.file_size) / (1024 * 1024):.2f} MB > "
                        f"max {max_total_mb:.2f} MB (zip-bomb korumasI, dosya={bilgi.filename!r})"
                    )

                # Fix-2 (b): gercek okuma chunk'li — bildirilen boyut yanlis/bozuk
                # olsa bile akis sirasinda gercek bayt sayisi kontrol edilir, tek
                # seferde tum icerik belleğe alinmaz.
                parca_baytlari = bytearray()
                with zf.open(bilgi) as kaynak:
                    while True:
                        chunk = kaynak.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        parca_baytlari.extend(chunk)
                        if toplam_bayt + len(parca_baytlari) > max_total_bytes:
                            raise ValueError(
                                f"zip_stl_extractor: acilan STL boyutu siniri asildi — "
                                f"toplam {(toplam_bayt + len(parca_baytlari)) / (1024 * 1024):.2f} MB > "
                                f"max {max_total_mb:.2f} MB (zip-bomb korumasI, dosya={bilgi.filename!r})"
                            )

                icerik = bytes(parca_baytlari)
                toplam_bayt += len(icerik)
                sonuc[anahtar] = icerik

    except zipfile.BadZipFile as hata:
        logger.warning(
            "zip_stl_extractor: bozuk zip verisi, bos dict donduruluyor — %s", hata
        )
        return {}
    except ValueError:
        # Boyut siniri hatasini yukari ilet (yakalama yok)
        raise

    return sonuc
