"""tests/test_quantity_text_parser.py — Adet-metni parser testleri.

Gercek hoca maili uzerinden dogrulama.
"""

from src.runtime.quantity_text_parser import parse_quantities


# Hocanin gercek ornek maili (yazi kismi)
GERCEK_MAIL = """Merhabalar Hocam,

Plan1

ENG-500053_L-Bracket 22 adet
811793-1 20 adet
TAPER-GAUGE-1 10 adet
bobbin_1_v2 12 adet
bobbin_2_v2 12 adet
bobbin_3_v2 6 adet
811791-1 19 adet
pyramid_with_doors 5 adet
MTShoe 1 adet
M18_toShopVac_Adapter 2 adet
part262835 2 adet
baseplate_v2 1 adet

Iyi calismalar,
Saygilarimla."""


def test_gercek_mail_tum_parcalar():
    q = parse_quantities(GERCEK_MAIL)
    assert q == {
        "ENG-500053_L-Bracket": 22,
        "811793-1": 20,
        "TAPER-GAUGE-1": 10,
        "bobbin_1_v2": 12,
        "bobbin_2_v2": 12,
        "bobbin_3_v2": 6,
        "811791-1": 19,
        "pyramid_with_doors": 5,
        "MTShoe": 1,
        "M18_toShopVac_Adapter": 2,
        "part262835": 2,
        "baseplate_v2": 1,
    }


def test_gercek_mail_parca_sayisi_ve_toplam():
    q = parse_quantities(GERCEK_MAIL)
    assert len(q) == 12
    assert sum(q.values()) == 22 + 20 + 10 + 12 + 12 + 6 + 19 + 5 + 1 + 2 + 2 + 1


def test_selamlama_baslik_imza_atlanir():
    q = parse_quantities(GERCEK_MAIL)
    assert "Merhabalar Hocam," not in q
    assert "Plan1" not in q
    assert "Saygilarimla." not in q


def test_bos_metin_bos_dict():
    assert parse_quantities("") == {}
    assert parse_quantities("Sadece selamlama, adet yok.") == {}


def test_ad_korunur_ozel_karakterler():
    # tire, alt cizgi, harf-rakam karisik adlar bozulmadan korunur
    q = parse_quantities("M18_toShopVac_Adapter 2 adet\n811793-1 20 adet")
    assert q["M18_toShopVac_Adapter"] == 2
    assert q["811793-1"] == 20


def test_ekleme_sirasi_korunur():
    q = parse_quantities("alfa 3 adet\nbeta 5 adet\ngama 1 adet")
    assert list(q.keys()) == ["alfa", "beta", "gama"]


def test_ayni_ad_toplanir():
    q = parse_quantities("braket 3 adet\nbraket 2 adet")
    assert q["braket"] == 5


def test_sifir_ve_negatif_atlanir():
    q = parse_quantities("bos 0 adet\ngecerli 4 adet")
    assert "bos" not in q
    assert q["gecerli"] == 4


def test_buyuk_kucuk_harf_adet():
    q = parse_quantities("parca 7 ADET\nbaska 3 Adet")
    assert q["parca"] == 7
    assert q["baska"] == 3


def test_determinizm():
    assert parse_quantities(GERCEK_MAIL) == parse_quantities(GERCEK_MAIL)
