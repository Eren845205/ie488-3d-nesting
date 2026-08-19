# -*- coding: utf-8 -*-
"""demo_not_ornegi_seed.py — hoca-demo icin NOTLU ornek siparis tohumlari.

Bekleyen-siparis deposuna iki notlu + adeti-eksik demo siparisi koyar:
  DEMO-NOT-01   : basit not ("braket dik basilsin") — LLM yuksek guvenle
                  orientation_lock cikarir (onay + kosu gosterisi).
  DEMO-KUPON-02 : hocanin GERCEK musteri notu (kupon oryantasyon, ek
                  2026-08-03) — sema-disi kisit turleri; LLM guveni dusurur,
                  operatore birakir (uydurmama gosterisi).

Demo akisi: ana sayfa bildirim kutusu -> /kisit-onay (oneri+onay) ->
/adet-gir (adet) -> kosu -> /sonuc "isteklere gore kosuldu" kutusu.

Yeniden kosmak guvenli (idempotent — ayni order_id ustune yazar).
Kosum: python -m scripts.demo_not_ornegi_seed
Webapp: /demo-not-yukle butonu tohumla_hepsi()'yi cagirir.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

BASIT_ID = "DEMO-NOT-01"
KUPON_ID = "DEMO-KUPON-02"
A2_ID = "DEMO-A2-03"
# Hocanin GERCEK a2 parcasi (Plan7 siparisi; uzerinde fiziksel "XY" label
# var — hoca 2026-08-03 cevabi). data/demo_assets kopyasi gen_plan7'den.
A2_STL = _ROOT / "data" / "demo_assets" / "288101642-a2.stl"

BASIT_GOVDE = (
    "Merhaba,\n"
    "Ekte braket ve kapak parcalarinin STL dosyalari var.\n"
    "Not: braket parcasi dik konumda basilsin lutfen.\n"
    "Adet bilgisini telefonda konustugumuz gibi ayarlayabilirsiniz.\n"
    "Iyi calismalar."
)

# Hoca eki 2026-08-03 (musteri_mail_notu_kupon_oryantasyon.jpg) — korpus g05.
KUPON_GOVDE = (
    "Merhaba,\n"
    "Test kuponu siparisimiz ektedir.\n"
    "Her bir test tipi icin 3 farkli oryantasyonda kupon gerekmektedir. "
    "(Yatay-Dikey-Transverse (45o))\n"
    "Cekme Testleri icin 15 yatay 15 dikey 15 adet transverse oryantasyonda "
    "toplam 45 adet\n"
    "Kupon dizilimlerinde yatay ve 45o olan (transverse) kuponlarin recoater "
    "ve gaz akis yonune dik olarak durmasi bizim icin onem arz etmektedir.\n"
    "Mumkunse eger, tek seferde uretim bizim icin uygun olur.\n"
)


def _kutu(w, d, h):
    import trimesh

    return trimesh.creation.box(extents=(w, d, h)).export(file_type="stl")


def _tohumla_bir(store, *, order_id, customer, konu, govde, stl_map,
                 review_reason, kabartma_tara=False):
    from src.runtime.note_detector import extract_note_candidates

    stl_names = [f"{n}.stl" for n in stl_map]
    scan = extract_note_candidates(govde, None, stl_names)
    if not scan["adaylar"]:
        raise RuntimeError(
            f"{order_id}: not adayi cikmadi — note_detector desenleri "
            "degisti mi?")
    if kabartma_tara:  # KANAL-3: parca ustu kabartma (VL kapaliysa sessiz)
        try:
            from src.runtime.kabartma import kabartma_not_adaylari
            ek = kabartma_not_adaylari(stl_map)
            if ek:
                scan["adaylar"] = list(scan["adaylar"]) + ek
                print(f"  kabartma adayi: {[a['satir'][:70] for a in ek]}")
        except Exception as e:
            print(f"  kabartma taramasi atlandi ({e})")
    sid = store.add(
        order_id=order_id, customer=customer, sender="demo@ornek.com",
        deadline="2026-09-15", priority_class=2, konu=konu,
        stl_map=stl_map, container=None, review_reason=review_reason,
        adet_listesi={}, not_adaylari=scan["adaylar"], govde_metni=govde,
    )
    return sid, scan["adaylar"]


def tohumla_hepsi(store=None):
    """Iki demo tohumunu da yaz; [(order_id, n_not), ...] doner.

    Kalinliklar bilerek >=15mm (2026-08-15 dersi: 4-6mm inceler pitch'i
    1.6'ya dusurdu -> 335 plakada 44M hucre / 15dk kosu; >=15mm ile pitch
    ~6mm -> canli demo kosusu saniyeler mertebesinde).
    """
    if store is None:
        from src.runtime.pending_orders import PendingOrderStore

        store = PendingOrderStore(_ROOT / "data" / "pending_orders")

    sonuc = []
    sid, adaylar = _tohumla_bir(
        store, order_id=BASIT_ID, customer="Demo Musteri A.S.",
        konu="Braket + kapak siparisi (notlu demo)", govde=BASIT_GOVDE,
        stl_map={"braket": _kutu(60.0, 40.0, 16.0),
                 "kapak": _kutu(50.0, 50.0, 15.0)},
        review_reason="adet bilgisi mailde yok (operator girecek)")
    sonuc.append((sid, len(adaylar)))

    sid, adaylar = _tohumla_bir(
        store, order_id=KUPON_ID, customer="Hoca Gercek Ornek (kupon)",
        konu="Test kuponu siparisi (hoca eki 2026-08-03 gercek notu)",
        govde=KUPON_GOVDE,
        stl_map={"kupon_cekme": _kutu(90.0, 18.0, 15.0),
                 "kupon_basma": _kutu(30.0, 30.0, 30.0),
                 "kupon_yorulma": _kutu(80.0, 16.0, 16.0)},
        review_reason="adetler notta oryantasyon-gruplu (operator girecek)")
    sonuc.append((sid, len(adaylar)))

    # 3) Hocanin GERCEK a2 ornegi (Plan7): mail-metin notu korpus g04'ten
    # birebir; STL gercek parca. NOT: parca 4mm ince -> pitch dusuk -> canli
    # KOSU YAVAS olur; demoda bu tohum not-cikarim + onay gosterisi icindir,
    # kosu gosterisini DEMO-NOT-01 ile yapin.
    if A2_STL.exists():
        a2_govde = (
            "Merhaba,\n"
            "Ekte a2 parcasinin STL dosyasi mevcuttur.\n"
            "288101642-a2 6 adet - Konumu değişmeyecek.\n"
            "Iyi calismalar.\n"
        )
        sid, adaylar = _tohumla_bir(
            store, order_id=A2_ID, customer="Hoca Gercek Ornek (Plan7 a2)",
            konu="a2 siparisi (Plan7; parca ustunde XY label — hoca 08-03)",
            govde=a2_govde,
            stl_map={"288101642-a2": A2_STL.read_bytes()},
            review_reason="a2 durus kisitli (operator adet girecek)",
            kabartma_tara=True)
        sonuc.append((sid, len(adaylar)))
    return sonuc


def main():
    for sid, n_not in tohumla_hepsi():
        print(f"tohum yazildi: {sid} (not adaylari: {n_not})")
    print("demo: ana sayfa bildirim kutusu + /adet-gir + /kisit-onay.")


if __name__ == "__main__":
    main()
