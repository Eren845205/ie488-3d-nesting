# Deneme4 "Adil Fotoğraf" Raporu — 2026-07-04 (Sprint 1 çıktısı)

> Amaç: Magics'e görünen %54 açığın ne kadarı gerçek algoritma açığı, ne kadarı ölçüm/koşul farkı?
> Veri: Mert Coşkun (FSM), 13 tip / 588 adet, çoğu 0.8–1.35mm cidarlı kabuk. Magics referansı: **250.24mm** (plakası BİLİNMİYOR).

## Tek tabloda durum

| Koşu | Yükseklik | Süre | Tepe RAM | Not |
|---|---|---|---|---|
| Magics (hoca) | **250.24** | ? | ? | plaka/ayar bilinmiyor — mail ile soruldu, cevap bekleniyor |
| Üretim NFV quality=max (gözcü politikası) | 386.4 | 6.1 dk | 0.87GB | eski baseline'ın BİREBİR tekrarı (Sprint 1 regresyon kanıtı) |
| Eski en iyi: heightmap fast @2.9mm | 377.3 | 35s | — | kabuklar katı-blok şişiyor |
| **K-19: heightmap @0.5mm cidar-pitch** | **282.0** | **131 dk** | 0.80GB | **YENİ — Magics açığı %54 → %12.7** (`scripts/k19_cidar_pitch_olcum.py`, YONTEM_HARITASI K-19) |

## Adil-fotoğraf enstrümantasyonu (üretim koşusu, yeni F0 alanları)

- **Plaka:** 301.6 × 301.6mm, **plate_auto=True** — yani plaka siparişten TÜRETİLDİ. Magics'in 250.24'ü hangi plakada bilinmiyor → 282 vs 250 kıyası hâlâ elma-armut olabilir; hoca cevabı şart.
- **Çift-eksen doluluk:** voxel-doluluk %38.3'e karşı **gerçek mesh-hacim doluluğu %9.4** (3.306 cm³ / 588 parçanın tamamı watertight ölçüldü, hacim-eksik=0). Şişkin-voxel metriği 4× abartıyormuş — bundan sonra iki eksen birden raporlanıyor.
- **Zaman bütçesi / RAM guard:** tetiklenmedi (budget_exceeded=False, ram_guard=-).
- **Erişilebilirlik (F2 v1, pitch 1.25mm):** **506/588 parça +Z'de kilitli, tek grup** (analiz 1.3s). İki bileşen:
  1. **Gerçek kilitleme:** NFV cavity-packing sökülebilirliği gözetmiyor; Magics interlocking'i ÖNLÜYOR → bizim 386.4 kısmen "Magics kurallarında illegal" bir istif. Kıyasta bunun düzeltilmesi gerekir.
  2. **Çözünürlük şişmesi:** 1.25mm voxel'de kabuklar arası sub-mm boşluklar kapalı görünür (kanıt: `scripts/f2_pitch_sensitivity.py` — 1mm kanal pitch 2.0'da kilitli, 0.5'te serbest). Gerçek kilit sayısı için ince-pitch yeniden analiz gerekir (F3 işi).
- **Mekanizma notu:** K-19'un 282.0'ı heightmap yolu — heightmap yüzey-üstüne-bırakma gereği ters-sırayla +Z sökülebilir istif üretir (kapalı kaviteye parça sokamaz). Yani **282.0 muhtemelen "legal", 386.4 kısmen "illegal"** — doğrulaması F3'te ince-pitch erişilebilirlik koşusuyla.

## %54 açığın ayrışımı (bugünkü en iyi bilgiyle)

1. **~%41 puan = kaba pitch'in kabuk körlüğü** (K-19 kanıtladı: 377.3→282.0).
2. **Kalan %12.7'nin bilinmeyen payı = plaka farkı** (bizim 301.6 türetilmiş; hoca cevabı gelince netleşir).
3. **Karşı yönde düzeltme:** bizim NFV sayıları sökülebilirlik kısıtı olmadan üretiliyor (506 kilit uyarısı) — Magics'le kural-eşit kıyas için erişilebilirlik kısıtı/onarımı gerekebilir (F2 v2 / F4).
4. **Henüz kullanılmayan kaldıraç:** 200×özdeş düğme için kule-şablonu/telescoping (F4) — 282'nin üstüne binebilir.

## Sprint 1 kapanış durumu

- 7 commit: `afa7be6` (Deneme4 kayıt) · `167edd4` (F1 aile) · `43963b8` (F2 erişilebilirlik) · `1772cf3` (F0 çekirdek) · `b182867` (F0 rapor + STL-fiyat kararı) · `381e520` (K-19 kaydı) · bu rapor.
- Tam suite **2397 passed, 0 regresyon**; donmuş kıyas: plan2 çapası **740/556 BİREBİR**, plan1/plan3/boxy bantta; deneme4 ilk donmuş referans: kutuluk 0.470 / heightmap 380.0 / NFV-greedy 344.0 (@2.0mm, 4 poz).
- Aile tanıma gerçek-veri: deneme4→thin_shell (0.87) ✓ · plan2/3→thin_shell (0.56-0.58) · plan1/numune→mixed_scale (0.53-0.59) · boxy→solid_bulk (0.69). Düşük-güven bandı F5 kalibrasyonuna girdi.

## Sonraki adımlar (Sprint 2)

1. **F3:** cidar-pitch üretime bağlama — tetik `family∈{thin_shell,tube}` + zaman bütçesi + cross-dataset ≤%1 kapısı (K-19p, YONTEM_HARITASI §5).
2. **F4-A/B:** kule-şablonu ölçümü (özdeş-parça fast-path) — süre problemini de çözmeye aday (131dk → hedef dakikalar).
3. **İnce-pitch erişilebilirlik yeniden-analizi:** gerçek kilit sayısı + K-19 layout'unun kilitsizlik doğrulaması.
4. **Hoca cevabı gelince:** gerçek plakayla yeniden koşu → Magics kıyası "adil" ilan edilir.
