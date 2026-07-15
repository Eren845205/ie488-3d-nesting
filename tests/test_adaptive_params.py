"""test_adaptive_params.py — akıllı nesting mod seçimi (predict_nfv_benefit) kalite-güvenlik testleri.

KRİTİK: akıllı mod YANLIŞ seçerse kalite düşer. En tehlikeli hata = cavity-zengin instance'ı
heightmap'e göndermek (false-negative → %14-29 kalite kaybı). Bu testler şüphede-NFV davranışını
ve false-negative=0'ı kalıcı korur. Mekanizma: K-14/K-15 (height-driver formu) + K-12 (NFV>=heightmap).
ÖLÇ-ÖNCE 5-veri kanıtı: scripts/automode_proof.py.
"""
from src.nesting3d.instances.format import NestingInstance, ContainerSpec, PartSpec
from src.nesting3d.adaptive_params import predict_nfv_benefit, ModeDecision


def _inst(parts, plate=(250.0, 250.0)):
    return NestingInstance(container=ContainerSpec(plate[0], plate[1], None), parts=parts)


def _box(pid, w, d, h, qty=1):
    return PartSpec(id=pid, name=pid, qty=qty, source="box",
                    width_mm=w, depth_mm=d, height_mm=h)


def _shell(pid, w, d, h, wall_mm=2.0, true_fill=0.15, qty=1):
    """Kabuk parca proxy'si (STL kaynak + cidar/dusuk-doluluk metasi).

    classify_prelim bunu thin_shell/tube olarak siniflar; true_fill=0.15 ->
    guven ~0.87 (>= WALL_AWARE_CONF_THRESHOLD 0.75). Kompakt (elong<=3) -> thin_shell,
    uzun (elong>3) -> tube.
    """
    return PartSpec(id=pid, name=pid, qty=qty, source="stl",
                    width_mm=w, depth_mm=d, height_mm=h,
                    wall_mm=wall_mm, true_fill=true_fill)


def test_net_kutu_heightmap():
    """Net kutu (mean_aspect_z düşük) → heightmap: cavity yok, NFV kazanmaz (boxy profili)."""
    dec = predict_nfv_benefit(_inst([_box("a", 40, 40, 40, 5)]))
    assert dec.mode == "heightmap"
    assert "kutu" in dec.reason.lower()


def test_ince_plaka_heightmap():
    """İnce-plaka dominant (thin_plate yüksek) → heightmap: düz zaten optimal, NFV uzatır (numune/K-15)."""
    dec = predict_nfv_benefit(_inst([_box("b", 200, 200, 3, 5)]))
    assert dec.mode == "heightmap"
    assert "plaka" in dec.reason.lower()


def test_cavity_aday_nfv():
    """Cavity-aday (orta aspect, ince-değil) → nfv: kalite-güvenli (plan1/2/3 profili)."""
    dec = predict_nfv_benefit(_inst([_box("c", 120, 40, 18, 3), _box("d", 90, 30, 22, 3)]))
    assert dec.mode == "nfv"


def test_false_negative_korumasi():
    """KRİTİK kalite kapısı: cavity-aday (ne net-kutu ne ince-plaka) ASLA heightmap'e gitmemeli.

    Şüphede NFV (varsayılan) — heightmap SADECE bariz kutu/ince-plaka. Bu, cavity-zengin
    instance'ın yanlışlıkla heightmap'e gönderilip %14-29 kalite kaybetmesini önler.
    """
    orta = _inst([_box("e", 100, 50, 25, 2), _box("f", 80, 35, 20, 4), _box("g", 110, 45, 15, 3)])
    dec = predict_nfv_benefit(orta)
    assert dec.mode == "nfv", f"cavity-aday heightmap'e gitti (KALİTE KAYBI RİSKİ): {dec.reason}"


def test_returns_mode_decision():
    """predict_nfv_benefit ModeDecision döndürür (mode + açıklanabilir reason)."""
    dec = predict_nfv_benefit(_inst([_box("a", 40, 40, 40)]))
    assert isinstance(dec, ModeDecision)
    assert dec.mode in ("nfv", "heightmap")
    assert dec.reason  # şeffaflık: gerekçe boş olamaz


def test_deterministik():
    """Aynı instance → aynı karar (saf fonksiyon, rastgelelik yok)."""
    inst = _inst([_box("c", 120, 40, 18, 3), _box("d", 90, 30, 22, 3)])
    d1 = predict_nfv_benefit(inst)
    d2 = predict_nfv_benefit(inst)
    assert d1.mode == d2.mode and d1.reason == d2.reason


# ---------------------------------------------------------------------------
# F5 aile katmanı (2026-07-04): kabuk ailesi → heightmap + wall_aware önerisi.
# Mekanizma: K-12 (NFV>=heightmap) kabukta KIRILIR (K-19) → cidar-pitch yolu.
# ---------------------------------------------------------------------------

def test_kabuk_ailesi_heightmap_wall_aware():
    """Kabuk (thin_shell) + yüksek güven + family_routing=True → heightmap + wall_aware (K-19 yolu).

    Deneme4 senaryosu: ince kabuk artık 'net-kutu' DEĞİL 'kabuk' gerekçesiyle heightmap'e
    gider (doğru mekanizma). Karar makine-okur wall_aware=True taşır (cidar-pitch açılsın).
    Aile katmanı OPT-IN → family_routing=True ile çalışır.
    """
    dec = predict_nfv_benefit(_inst([_shell("sh", 100, 100, 80)]), family_routing=True)
    assert dec.mode == "heightmap"
    assert dec.wall_aware is True
    assert "kabuk" in dec.reason.lower()
    assert "net-kutu" not in dec.reason.lower()  # eski/yanlış gerekçe DEĞİL


def test_tube_ailesi_heightmap_wall_aware():
    """Boru (tube, uzun kabuk) + yüksek güven + family_routing=True → heightmap + wall_aware."""
    dec = predict_nfv_benefit(_inst([_shell("tb", 300, 50, 50)]), family_routing=True)
    assert dec.mode == "heightmap"
    assert dec.wall_aware is True
    assert "kabuk" in dec.reason.lower()


# ---------------------------------------------------------------------------
# rot-sokum dunyasi (Eren karari 2026-07-15; kanit K-46/K-52): thin_shell
# kabuk hukmu TERSINE — d4 NFV ham 231.5 (b+c)-legal + rot-kabul 220.69.
# rot_sokum=True + family_routing=True iken thin_shell NFV'ye gider (rot
# kabul zinciri asagida cozer); tube kanitsiz -> eski yol. Default False
# = BIT-OZDES eski davranis.
# ---------------------------------------------------------------------------

def test_rot_sokum_thin_shell_nfv():
    """d4 senaryosu: rot-sokum dunyasinda thin_shell NFV+rot yoluna gider."""
    dec = predict_nfv_benefit(_inst([_shell("sh", 100, 100, 80)]),
                              family_routing=True, rot_sokum=True)
    assert dec.mode == "nfv"
    assert dec.wall_aware is False  # NFV yolu cidar-pitch kullanmaz
    assert "rot-sokum" in dec.reason.lower()


def test_rot_sokum_tube_eski_yol():
    """tube icin rot-dunyasi kaniti YOK -> heightmap+wall_aware aynen."""
    dec = predict_nfv_benefit(_inst([_shell("tb", 300, 50, 50)]),
                              family_routing=True, rot_sokum=True)
    assert dec.mode == "heightmap" and dec.wall_aware is True


def test_rot_sokum_default_false_bit_ozdes():
    """rot_sokum verilmezse kabuk karari eski davranisla birebir."""
    shell = _inst([_shell("sh", 100, 100, 80)])
    d_eski = predict_nfv_benefit(shell, family_routing=True)
    d_acik = predict_nfv_benefit(shell, family_routing=True, rot_sokum=False)
    assert d_eski.mode == d_acik.mode == "heightmap"
    assert d_eski.reason == d_acik.reason
    assert d_eski.wall_aware is d_acik.wall_aware is True


def test_rot_sokum_family_routing_kapaliyken_etkisiz():
    """rot_sokum yalniz aile katmaninda anlamli; katman kapaliyken v1 kural."""
    dec = predict_nfv_benefit(_inst([_shell("sh", 100, 100, 80)]),
                              rot_sokum=True)  # family_routing default False
    assert dec.mode == "heightmap"
    assert "net-kutu" in dec.reason.lower()


def test_rot_sokum_dusuk_guven_tetiklemez():
    """Dusuk guvenli kabukta aile katmani (dolayisiyla rot flip) tetiklemez."""
    dec = predict_nfv_benefit(_inst([_shell("lo", 100, 100, 80, true_fill=0.45)]),
                              family_routing=True, rot_sokum=True)
    assert "kabuk ailesi" not in dec.reason.lower()
    assert dec.wall_aware is False


def test_family_routing_false_v1_bit_ozdes():
    """OPT-IN kapısı: yüksek-güvenli kabuk fixture'ı bile family_routing=False (DEFAULT) → v1.

    F5 aşama 1 asimetri düzeltmesi: aile katmanı bayrağa bağlı. Bayrak kapalıyken (default)
    aynı kabuk instance'ı v1 kurallarına düşer (mod/gerekçe/wall_aware v1 birebir) — mod-flip
    de wall_aware da ÜRETİLMEZ. v1'de bu kabuk net-kutu profili → heightmap ('net-kutu' gerekçe).
    """
    shell = _inst([_shell("sh", 100, 100, 80)])  # v2'de kabuk tetikler (güven ~0.87)
    v1 = predict_nfv_benefit(shell)                       # default family_routing=False
    v1_explicit = predict_nfv_benefit(shell, family_routing=False)
    assert v1.mode == v1_explicit.mode and v1.reason == v1_explicit.reason
    assert v1.wall_aware is False                         # aile katmanı çalışmadı
    assert "kabuk ailesi" not in v1.reason.lower()
    assert "net-kutu" in v1.reason.lower()                # v1 kural yolu
    # Kontrol: aynı fixture family_routing=True iken kabuk yolunu alır (bayrak fark yaratır).
    v2 = predict_nfv_benefit(shell, family_routing=True)
    assert v2.wall_aware is True and "kabuk" in v2.reason.lower()


def test_kabuk_dusuk_guven_mevcut_kural():
    """Kabuk ama güven < eşik (true_fill 0.45 → ~0.72) + family_routing=True → aile TETİKLEMEZ.

    Konservatif: düşük güvende değişiklik yok (bit-özdeş mevcut kural yolu). Bu instance
    net-kutu profili (mean_aspect_z<4) → heightmap ama 'net-kutu' gerekçesi, wall_aware YOK.
    """
    dec = predict_nfv_benefit(_inst([_shell("lo", 100, 100, 80, true_fill=0.45)]),
                              family_routing=True)
    assert dec.wall_aware is False
    assert "kabuk ailesi" not in dec.reason.lower()


def test_unknown_aile_mevcut_kural():
    """Belirsiz aile (ölçülememiş STL) + family_routing=True → aile katmanı tetiklemez."""
    dec = predict_nfv_benefit(_inst([PartSpec(
        id="u", name="u", qty=1, source="stl",
        width_mm=100, depth_mm=50, height_mm=30)]), family_routing=True)
    assert dec.wall_aware is False
    assert "kabuk ailesi" not in dec.reason.lower()


def test_kutu_aile_katmani_tetiklemez_bit_ozdes():
    """Katı kutular (wall_mm yok) + family_routing=True → aile ASLA tetiklemez → v1 bit-özdeş.

    Kutuluk sinyali olmayan girdilerde aile katmanı açıkken bile v1 ile birebir aynı karar
    (regresyon yok). Bayrak kapalıyken de aynı (aşağıda ayrıca doğrulanır).
    """
    for parts in (
        [_box("a", 40, 40, 40, 5)],                     # net-kutu
        [_box("b", 200, 200, 3, 5)],                    # ince-plaka
        [_box("c", 120, 40, 18, 3), _box("d", 90, 30, 22, 3)],  # cavity-aday
    ):
        d_on = predict_nfv_benefit(_inst(parts), family_routing=True)
        d_off = predict_nfv_benefit(_inst(parts))       # default False
        assert d_on.mode == d_off.mode and d_on.reason == d_off.reason
        assert d_on.wall_aware is False
        assert "kabuk" not in d_on.reason.lower()


def test_mevcut_kural_reason_stringleri_degismedi():
    """BİT-ÖZDEŞLİK: kutu yollarının eski reason string'leri AYNEN korunur (F5 v2 dokunmadı)."""
    d_kutu = predict_nfv_benefit(_inst([_box("a", 40, 40, 40, 5)]))
    assert d_kutu.reason == (
        "net-kutu (mean_aspect_z=1.0 < 4.0): cavity yok, NFV kazanmaz -> hizli heightmap")
    d_plaka = predict_nfv_benefit(_inst([_box("b", 200, 200, 3, 5)]))
    assert d_plaka.reason == (
        "ince-plaka dominant (thin_plate=1.00 > 0.6): duz zaten optimal, NFV uzatir -> heightmap")


def test_wall_aware_conf_thr_override():
    """Eşik parametresi ezilebilir (SABİT-SİHİRLİ-SAYI değil): iki yönde de kontrol."""
    inst = _inst([_shell("sh", 100, 100, 80, true_fill=0.45)])  # güven ~0.72
    # Eşik 0.70'e indirilirse tetikler (0.72 >= 0.70).
    lowered = predict_nfv_benefit(inst, family_routing=True, wall_aware_conf_thr=0.70)
    assert lowered.mode == "heightmap" and lowered.wall_aware is True
    # Eşik 0.95'e çıkarılırsa yüksek-güven kabuk bile tetiklemez.
    inst_hi = _inst([_shell("sh2", 100, 100, 80)])  # güven ~0.87
    raised = predict_nfv_benefit(inst_hi, family_routing=True, wall_aware_conf_thr=0.95)
    assert raised.wall_aware is False


def test_aile_esigi_pitch_tek_kaynak():
    """F5 aile eşiği = F3 WALL_AWARE_CONF_THRESHOLD (çift kaynak yok).

    Eşik pitch.py'den import edildiği için varsayılan davranış tam o değerde döner.
    """
    from src.nesting3d.instances.pitch import WALL_AWARE_CONF_THRESHOLD
    # Güveni eşiğin hemen ÜstÜne getiren true_fill ile tetikleme sınırını doğrula.
    # _fill_conf(tf) = 0.70 + 0.25*(0.5-tf)/0.5. conf=0.75 -> tf=0.40.
    just_below = predict_nfv_benefit(_inst([_shell("b", 100, 100, 80, true_fill=0.42)]),
                                     family_routing=True)
    just_above = predict_nfv_benefit(_inst([_shell("a", 100, 100, 80, true_fill=0.38)]),
                                     family_routing=True)
    assert WALL_AWARE_CONF_THRESHOLD == 0.75
    assert just_below.wall_aware is False   # conf ~0.74 < 0.75
    assert just_above.wall_aware is True    # conf ~0.76 >= 0.75


def test_mode_decision_geriye_uyum():
    """ModeDecision 2-argümanlı yapı bozulmadı; wall_aware default False + getattr deseni."""
    d = ModeDecision("nfv", "gerekce")
    assert d.mode == "nfv" and d.reason == "gerekce"
    assert d.wall_aware is False
    assert getattr(d, "wall_aware", None) is False
    d2 = ModeDecision("heightmap", "kabuk", wall_aware=True)
    assert d2.wall_aware is True
