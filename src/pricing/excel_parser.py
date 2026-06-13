"""Excel kural seti okuyucu — STUB (PLAN_DEMO1.md 7.5).

Bu modul A8 ornek Excel bekleniyor — Excel'in ic yapisi (tablo mu formul mu,
istisnalar) gorulmeden gercek parser yazilmaz.

Sozlesme (beklenen girdi / cikti)
----------------------------------
Girdi:
    excel_path : str  — Excel dosyasinin tam yolu (.xlsx / .xls)
    sheet_name : str  — Okunacak sayfa adi (varsayilan: "Fiyat Kurallari")

Cikti:
    src.pricing.schema.RuleSet — normalize kural seti nesnesi

Hata durumu:
    NotImplementedError firlatilir (A8 ornek Excel bekleniyor)

Gelecek implementasyon notlari (A8 gelince tamamlanacak)
---------------------------------------------------------
- Excel formatina gore iki ana senaryo bekleniyor:
    (a) Tablo bazli: her satir bir kural (tip, alan, deger sutunlari)
    (b) Formul bazli: Excel formullerinden kural parametreleri cikarilir

- Musteri-ozel istisnalar (indirim / ek ucret) ayri sayfada olabilir;
  conditional_multiplier kuralina eslenir.

- LLM destegi: daginik Excel'in ilk ceviriminde yardimci olabilir;
  sonuc insan onayindan gectikten sonra deterministik kurala donusur
  (bkz. APP_YOL_HARITASI.md §6.2 ve §6.1 basamak 3-4).

Import ornegi (stub haliyle calisir):
    from src.pricing.excel_parser import parse_excel_rule_set
"""

from src.pricing.schema import RuleSet


def parse_excel_rule_set(
    excel_path: str,
    sheet_name: str = "Fiyat Kurallari",
) -> RuleSet:
    """Excel dosyasindan normalize kural seti uretir.

    Parametreler
    ------------
    excel_path : Excel dosyasinin tam yolu (.xlsx / .xls)
    sheet_name : Okunacak sayfa adi

    Donus
    -----
    src.pricing.schema.RuleSet — musteri-ozel normalize kural seti

    Firlatir
    --------
    NotImplementedError
        A8 ornek Excel bekleniyor; dosya yapisi gorulmeden parser yazilmaz.
    """
    raise NotImplementedError(
        "A8 ornek Excel bekleniyor. "
        "Excel ic yapisi (tablo/formul, istisnalar) netlesince "
        "parse_excel_rule_set() tamamlanacak. "
        f"Girdi alindi: excel_path={excel_path!r}, sheet_name={sheet_name!r}"
    )
