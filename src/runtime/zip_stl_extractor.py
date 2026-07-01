"""src/runtime/zip_stl_extractor.py — Mail ekinden gelen zip icindeki STL cikarici.

Sorumluluk: ham zip byte'larindan .stl dosyalarini guvenli bicimde
bellek-ici (diske yazmadan) cikarip {uzantisiz_taban_ad: stl_baytlari} sozlugu
olarak dondurur.

Guvenlik garantileri
--------------------
- Zip-slip / path traversal: Tum dosya adlarindan dizin bilesenleri atilir;
  sadece basename kullanilir. Diskde hicbir dosya olusturulmaz (ZipFile
  io.BytesIO uzerinde calisiyor — diske erisim yok).
- Boyut bombasi: Acilan toplam STL bayt miktari max_total_mb'yi asarsa
  ValueError firlatilir (zip-bomb korumasI).
- Bozuk zip: zipfile.BadZipFile yakalanir, bos dict dondurulur + logging.warning.
  (Boyut siniri asimi HARİC hata firlatilmaz.)

Kullanim
--------
  from src.runtime.zip_stl_extractor import extract_stls

  stl_map = extract_stls(zip_bytes)
  # -> {"ENG-500053_L-Bracket": b"...", ...}
"""

from __future__ import annotations

import io
import logging
import os
import zipfile

logger = logging.getLogger(__name__)

# Fix-2 (HIGH): tek-girisli yuksek-oranli zip (zip-bomb) korumasi. Once ZipInfo'nun
# bildirdigi acilmis boyutla (bilgi.file_size) on-eleme yapilir (hic decompress
# edilmeden reddedilir); gecerse okuma bu boyutta chunk'lar halinde yapilir ve her
# chunk sonrasi biriken toplam kontrol edilir (bildirilen boyut bozuk/yalan olsa
# bile akis erken kesilir).
_CHUNK_SIZE = 1 << 20  # 1 MB


def extract_stls(
    zip_bytes: bytes,
    *,
    max_total_mb: float = 200.0,
) -> dict[str, bytes]:
    """Ham zip byte'larindan .stl dosyalarini bellek-ici cikarir.

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
    sonuc: dict[str, bytes] = {}

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf:
            toplam_bayt = 0
            for bilgi in zf.infolist():
                # Dizin girisleri (/ ile bitenler) atla
                if bilgi.filename.endswith("/"):
                    continue

                # Uzanti kontrolu — sadece .stl (buyuk/kucuk harf farksiz)
                _kok, uzanti = os.path.splitext(bilgi.filename)
                if uzanti.lower() != ".stl":
                    continue

                # Zip-slip / path-traversal korumasI: dizin bileseni at
                guvenli_taban = os.path.basename(bilgi.filename)
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
