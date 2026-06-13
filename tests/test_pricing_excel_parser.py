"""TDD testleri — src/pricing/excel_parser.py (PLAN_DEMO1.md 7.5).

Kapsam: stub import edilebilir, sozlesme belgeli, NotImplementedError firlatir.
"""

import pytest


def test_excel_parser_is_importable():
    """Stub modulu hata vermeden import edilebilmeli."""
    from src.pricing import excel_parser  # noqa: F401


def test_parse_excel_rule_set_is_importable():
    from src.pricing.excel_parser import parse_excel_rule_set  # noqa: F401


def test_parse_excel_raises_not_implemented():
    from src.pricing.excel_parser import parse_excel_rule_set

    with pytest.raises(NotImplementedError):
        parse_excel_rule_set("ornek.xlsx")


def test_parse_excel_error_message_mentions_a8():
    """Hata mesaji A8 referansini icermeli (planlama izlenebilirligi)."""
    from src.pricing.excel_parser import parse_excel_rule_set

    with pytest.raises(NotImplementedError, match="A8"):
        parse_excel_rule_set("ornek.xlsx")


def test_parse_excel_accepts_sheet_name_param():
    """Fonksiyon sheet_name parametresini kabul etmeli."""
    from src.pricing.excel_parser import parse_excel_rule_set
    import inspect

    sig = inspect.signature(parse_excel_rule_set)
    assert "sheet_name" in sig.parameters


def test_parse_excel_sheet_name_has_default():
    """sheet_name icin varsayilan deger olmali."""
    from src.pricing.excel_parser import parse_excel_rule_set
    import inspect

    sig = inspect.signature(parse_excel_rule_set)
    param = sig.parameters["sheet_name"]
    assert param.default is not inspect.Parameter.empty


def test_parse_excel_return_type_annotation_is_rule_set():
    """Donus tipi annotasyonu RuleSet olmali."""
    from src.pricing.excel_parser import parse_excel_rule_set
    from src.pricing.schema import RuleSet
    import inspect

    hints = parse_excel_rule_set.__annotations__
    assert "return" in hints
    assert hints["return"] is RuleSet


def test_parse_excel_docstring_mentions_contract():
    """Docstring sozlesmeyi (girdi/cikti) aciklamali."""
    from src.pricing.excel_parser import parse_excel_rule_set

    doc = parse_excel_rule_set.__doc__ or ""
    assert len(doc.strip()) > 50, "Docstring too short — contract not documented"
