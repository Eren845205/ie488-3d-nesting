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
