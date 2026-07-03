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


# ---------------------------------------------------------------------------
# Fix-1 (CRITICAL): asiri buyuk adet MAX_QTY'e clamp'lenir (OOM korumasi)
# ---------------------------------------------------------------------------


def test_absurd_qty_clamped_to_max_qty():
    """'bomba 999999999 adet' gibi mail govdesi MAX_QTY'e clamp'lenir."""
    from src.runtime.quantity_text_parser import MAX_QTY
    q = parse_quantities("bomba 999999999 adet")
    assert q["bomba"] == MAX_QTY
    assert q["bomba"] < 999999999


def test_normal_qty_unaffected_by_clamp():
    """MAX_QTY altindaki gercekci adetler clamp'lenmeden aynen gecer (gercek mail: 22)."""
    q = parse_quantities("braket 22 adet")
    assert q["braket"] == 22


# ---------------------------------------------------------------------------
# "Ad - Sayi" formati (hocanin GERCEK Deneme4 maili, 2026-07-03)
# ---------------------------------------------------------------------------

# Birebir gercek mail govdesi (plaintext) — canli yakalanan format.
DENEME4_MAIL = """Merhaba Eren,

Deneme 4’e ait veriler paylasılmaktadır.

588 parça için imalat yüksekliği 250,24 mm’dir.

ASY-0176446 - 62

ASY-0176446-1 - 126

part239392_ROBT UST v27 - 1

part239391_ROBT ALT v27 - 1

01_202201790014_00-K179 Dugme Aksesuari - 12

02_202201790002_T00-K179 Dugme Cift Fonksiyonlu - 12

02_T00-K179 Dugme Cift Fonksiyonlu -26

03_00-K179 Dugme Tek Fonksiyonlu - 200

04_T00-K179 Dugme Fonksiyonsuz - 56

05_00-K179 WBT Dugme - 20

09_00-K179 Dugme Kilidi - 27

10_T00-K179 Kilitli Dugme - 25

17_00-K179 SSB Dugme - 20

İyi çalışmalar,

Saygılarımla."""


def test_deneme4_gercek_mail_tum_parcalar():
    """Canli yakalanan gercek format: '<ad> - <sayi>' (adet kelimesi yok)."""
    q = parse_quantities(DENEME4_MAIL)
    assert q == {
        "ASY-0176446": 62,
        "ASY-0176446-1": 126,
        "part239392_ROBT UST v27": 1,
        "part239391_ROBT ALT v27": 1,
        "01_202201790014_00-K179 Dugme Aksesuari": 12,
        "02_202201790002_T00-K179 Dugme Cift Fonksiyonlu": 12,
        "02_T00-K179 Dugme Cift Fonksiyonlu": 26,
        "03_00-K179 Dugme Tek Fonksiyonlu": 200,
        "04_T00-K179 Dugme Fonksiyonsuz": 56,
        "05_00-K179 WBT Dugme": 20,
        "09_00-K179 Dugme Kilidi": 27,
        "10_T00-K179 Kilitli Dugme": 25,
        "17_00-K179 SSB Dugme": 20,
    }


def test_deneme4_toplam_588():
    q = parse_quantities(DENEME4_MAIL)
    assert sum(q.values()) == 588


def test_dash_ad_icinde_tire_ve_rakam():
    """Ad tire+rakam icerse de SON ayrac dogru bulunur (ASY-0176446-1 - 126)."""
    q = parse_quantities("ASY-0176446-1 - 126")
    assert q == {"ASY-0176446-1": 126}


def test_dash_bosluksuz_sayi():
    """'Fonksiyonlu -26' — ayractan sonra bosluk olmayabilir."""
    q = parse_quantities("02_T00 Dugme -26")
    assert q == {"02_T00 Dugme": 26}


def test_dash_adet_soneki_opsiyonel():
    """'Ad - 26 adet' de calisir (tire + adet birlikte)."""
    q = parse_quantities("braket - 26 adet")
    assert q == {"braket": 26}


def test_dash_pcs_soneki():
    q = parse_quantities("braket - 26 pcs")
    assert q == {"braket": 26}


def test_dash_yaninda_bosluk_yoksa_ad_parcasi():
    """'811793-1' gibi tireli adlar TEK BASINA satirdaysa adet SAYILMAZ
    (tire oncesi bosluk sart — telefon/tarih/parca-no yanlis-pozitifi)."""
    assert parse_quantities("811793-1") == {}
    assert parse_quantities("2026-07-03") == {}
    assert parse_quantities("Tel: 0212-1234567") == {}


def test_dash_boyut_satiri_yanlis_pozitif_degil():
    """Olcu/boyut metni adet uretmez."""
    assert parse_quantities("588 parça için imalat yüksekliği 250,24 mm’dir.") == {}


def test_dash_eski_format_regresyonsuz():
    """Iki format ayni govdede karisik olabilir."""
    q = parse_quantities("braket 3 adet\nkapak - 5")
    assert q == {"braket": 3, "kapak": 5}


def test_dash_clamp_uygulanir():
    from src.runtime.quantity_text_parser import MAX_QTY
    q = parse_quantities("bomba - 999999999")
    assert q["bomba"] == MAX_QTY


# ---------------------------------------------------------------------------
# parse_declared_total — "588 parça" beyani (checksum kaynagi)
# ---------------------------------------------------------------------------


def test_declared_total_deneme4():
    from src.runtime.quantity_text_parser import parse_declared_total
    assert parse_declared_total(DENEME4_MAIL) == 588


def test_declared_total_yoksa_none():
    from src.runtime.quantity_text_parser import parse_declared_total
    assert parse_declared_total("Merhaba, siparis ektedir.") is None
    assert parse_declared_total("") is None


def test_declared_total_parca_ascii():
    from src.runtime.quantity_text_parser import parse_declared_total
    assert parse_declared_total("Toplam 42 parca gonderilmistir.") == 42


# ---------------------------------------------------------------------------
# match_quantities_to_stls — toleransli eslestirme
# ---------------------------------------------------------------------------

from src.runtime.quantity_text_parser import match_quantities_to_stls


def test_match_birebir():
    m, uk, us = match_quantities_to_stls({"braket": 2}, ["braket", "kapak"])
    assert m == {"braket": 2}
    assert uk == []
    assert us == ["kapak"]


def test_match_case_ve_tr_katlama():
    m, uk, us = match_quantities_to_stls(
        {"DÜĞME kilidi": 5}, ["dugme_kilidi"]
    )
    assert m == {"dugme_kilidi": 5}
    assert uk == [] and us == []


def test_match_pcs_soneki_toleransi():
    """Deneme4 gercek tuzagi: mail 'Cift Fonksiyonlu', dosya '...-25pcs'."""
    m, uk, us = match_quantities_to_stls(
        {"02_T00-K179 Dugme Cift Fonksiyonlu": 26},
        ["02_T00-K179 Dugme Cift Fonksiyonlu-25pcs"],
    )
    assert m == {"02_T00-K179 Dugme Cift Fonksiyonlu-25pcs": 26}
    assert uk == [] and us == []


def test_match_birebir_sonekten_ustun():
    """'ASY-0176446' beyani 'ASY-0176446-1' dosyasini CALMAZ — ikisi de birebir."""
    m, uk, us = match_quantities_to_stls(
        {"ASY-0176446": 62, "ASY-0176446-1": 126},
        ["ASY-0176446", "ASY-0176446-1"],
    )
    assert m == {"ASY-0176446": 62, "ASY-0176446-1": 126}
    assert uk == [] and us == []


def test_match_belirsiz_coklu_aday_eslenmez():
    """Iki dosya da sonek adayi ise ESLENMEZ (yanlis parcaya adet yazma)."""
    m, uk, us = match_quantities_to_stls(
        {"braket": 5}, ["braket-1pcs", "braket-2pcs"]
    )
    assert m == {}
    assert uk == ["braket"]
    assert set(us) == {"braket-1pcs", "braket-2pcs"}


def test_match_serbest_metin_soneki_eslenmez():
    """Sonek toleransi adet-ipucu ile sinirli: 'Dugme' != 'Dugme Kilidi'."""
    m, uk, us = match_quantities_to_stls({"Dugme": 5}, ["Dugme Kilidi"])
    assert m == {}
    assert uk == ["Dugme"]


def test_match_deneme4_tam_takim():
    """Gercek Deneme4: 13 mail satiri x 13 dosya — tam kapsama, toplam 588."""
    q = parse_quantities(DENEME4_MAIL)
    stls = [
        "01_202201790014_00-K179 Dugme Aksesuari",
        "02_202201790002_T00-K179 Dugme Cift Fonksiyonlu",
        "02_T00-K179 Dugme Cift Fonksiyonlu-25pcs",
        "03_00-K179 Dugme Tek Fonksiyonlu",
        "04_T00-K179 Dugme Fonksiyonsuz",
        "05_00-K179 WBT Dugme",
        "09_00-K179 Dugme Kilidi",
        "10_T00-K179 Kilitli Dugme",
        "17_00-K179 SSB Dugme",
        "ASY-0176446",
        "ASY-0176446-1",
        "part239391_ROBT ALT v27",
        "part239392_ROBT UST v27",
    ]
    m, uk, us = match_quantities_to_stls(q, stls)
    assert uk == [] and us == []
    assert len(m) == 13
    assert sum(m.values()) == 588
    assert m["02_T00-K179 Dugme Cift Fonksiyonlu-25pcs"] == 26
