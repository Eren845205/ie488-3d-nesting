# İlerleme Kaydı — 2026-06-11 (hoca feedback oturumu)

> PC kapanışı öncesi durum dökümü. Kod değişiklikleri working tree'de duruyor
> (COMMIT EDİLMEDİ — kullanıcı kararı: final sonuç netleşince push).
> Bu dosya + auto-memory ile oturum kaldığı yerden devam edebilir.

## Hoca feedback'i (WhatsApp Image 2026-06-11 at 16.43.36.jpeg)

1. Parçalar arası **min 1 mm** boşluk (üst üste / yan yana / açılı — her yönde)
2. Çözünürlük artırılacak (en az 1 mm) — VEYA voxel sabit kalıp orijinal
   parçalar yerleştirilecek (seçenek 2 seçildi)
3. Makine: **taban 335×335 mm, max z 600 mm**
4. Orijinal tasarım yüksek çözünürlükte taşınacak (kabartma yazılar kayboluyordu
   → kök neden: `_decimate_display` 4000 üçgene indiriyordu, voxel değil)
5. **Devoxelization tool**: optimizasyon voxel'de, çıktı orijinal mesh'lerle
6. Kullanıcı hedefi: **z ≤ 170 mm** (sözlü, hoca hedefi)

## Yapılan kod değişiklikleri (working tree'de, commit YOK)

- `src/nesting3d/voxelize.py`:
  - `VoxelPart.mesh` artık HER ZAMAN orijinal; decimated kopya `display_mesh`
    alanında (yalnız render)
  - `_surface_cells`: üçgen örnekleme (pitch/2) ile yüzey hücreleri işaretlenir,
    slice iç-hacim grid'iyle birleşir → KONSERVATİF sarma (merkez-içi test ince
    duvarları kaçırıyordu → ölçülen 0.77 mm ihlal bulundu, düzeltildi)
  - `_dilate`: yalnız YATAY (x,y) dilation; dikey boşluk Bin3D.z_clearance'ta
  - `rotation_matrices`: 8-poz master set (0/90/180/270 + yan + ters)
  - `voxelize_part(allowed_orientations=...)` + `expand_quantities(
    orientation_overrides=...)`: parça-bazlı poz kısıtı
- `src/nesting3d/bin3d.py`: `Bin3D(z_clearance=N)` — parça parça ÜSTÜNE
  oturduğunda N hücre dikey boşluk (tek taraflı; çift dilation'ın yarı maliyeti)
- `src/nesting3d/clearance.py` (YENİ): yerleştirilmiş orijinal mesh'lerde
  gerçek min mesafe ölçümü (cKDTree + AABB ön filtre) — scipy requirements'a eklendi
- `src/nesting3d/run3d.py`: numune senaryo default'ları (plate 335, pitch 2.5,
  margin 1, slice), `--max-z 600` + z_ok sütunu, `--check-clearance` (JSON
  rapor), `--rotations` 6/8 seçenekleri, NUMUNE_ORIENTATIONS bağlandı
- `src/nesting3d/models.py`: `NUMUNE_ORIENTATIONS` — plakalar (n3/n6/n7/n8)
  yalnız yatay (0,1,4,5); n5 yalnız (0,1). Gerekçe: dik plaka 178–190 mm →
  ≤170 hedefini imkânsız kılar; n5 yan pozları 249 mm
- `scripts/compare_numune.py`: PLATE 335, clearance satırı raporda
- `tests/test_devox.py` (YENİ) + `tests/test_voxelize3d.py` güncel
- **Test durumu: 92/92 yeşil** (`python -m pytest tests/ -q`)

## Ölçüm sonuçları (48 parça, 335×335, garantili ≥1 mm clearance)

| Koşu | Yükseklik | Clearance | Not |
|---|---|---|---|
| DBLF eski şema (çift dilation) | 265.0 | 3.82 ✓ | |
| DBLF, ilk konservatif grid | 265.0 → ihlalli eskisi 240/0.77✗ | — | ihlali clearance aracı yakaladı |
| DBLF yeni şema (yatay+z_clear, p2.5) | 217.5 | 2.68 ✓ | |
| DBLF p1.5 | 217.5 | 1.50 ✓ | pitch DBLF'e etkisiz |
| SA 2000 iter p2.5 | 192.5 | 3.19 ✓ | results/numune_sa |
| **SA 1000 iter p1.5 (REKOR)** | **190.5** | 1.50 ✓ | results/_exp_p15_sa — ama plakaları DİK dikmiş (n8 dik=190.1 tavanı belirliyor) |
| DBLF rot8 | 260.0 | 2.76 ✓ | 8 poz greedy'yi bozuyor → final sette YOK |
| DBLF dik-yasak p1.5 | 214.5 | 1.60 ✓ | |
| DBLF dik-yasak p1.25 | 211.2 | 1.46 ✓ | |

## KAPANIŞTA ÖLEN koşular — yeniden başlatma komutları

5 paralel final SA (dik yasak + 180/270 pozlar aktif, modeller kodda):

```
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 1000 --pitch 1.5  --seed 42 --export-stl --check-clearance --out results/_final_s42
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 1000 --pitch 1.5  --seed 7  --export-stl --check-clearance --out results/_final_s07
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 1000 --pitch 1.5  --seed 13 --export-stl --check-clearance --out results/_final_s13
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 1000 --pitch 1.5  --seed 99 --export-stl --check-clearance --out results/_final_s99
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 1000 --pitch 1.25 --seed 42 --export-stl --check-clearance --out results/_final_p125_s42
```

Süre: tek koşu solo ~32 dk; 5 paralel ~60-90 dk. Sonuçlar `results/_final_*/summary_3d.md`.

## Analiz notları (yeniden türetilmesin)

- 12 büyük plakanın ham kalınlık toplamı **202.5 mm**; 335 tabana yan yana iki
  plaka sığmaz (178+178=356) → ≤170 ANCAK plaka geçişmesiyle (çıkıntı→delik) olur.
  Arayüz başına ~5 mm geçişme gerekir (toplam ~55 mm).
- Eski 155 mm sonucu: 350 taban + margin'siz + İHLALLİ (0.77 mm) — elma-armut.
- Clearance garanti zinciri: konservatif grid + yatay dilation 1 + z_clearance 1
  → en kötü (çapraz) √2·pitch; p1.5 → 2.1 mm, p1.25 → 1.77 mm. Pitch < 1.0'a
  inilemez (dikey 1 hücre = pitch ≥ 1 mm şartı).
- SA per-iter maliyeti ~pitch⁻²; p1.25 pratik alt sınır (1000 iter ~30 dk solo).
- Makine toz yataklı (parçalar havada nest ediliyor) → her oryantasyon basılabilir.

## EK — 2026-06-11 akşam oturumu (final koşular + hibrit pivot)

**5 final SA koşusu tamamlandı** (dik yasak): s42/p1.5 **198.0** (en iyi),
s13 205.5, s99 205.5, s07 207.0, p1.25/s42 202.5 — hepsi clearance OK,
hiçbiri 190.5 rekorunu geçemedi.

**Tanı bulguları** (`scripts/probe_nesting.py`, YENİ):
- Tam-bindirmede plaka-plaka gerçek geçişme ~0 (yalnız n3 tabanında n6/n8
  4'er mm) → salt-yatık kule tabanı p1.0'da ~206 mm.
- Serbest-ofset "geçişme" değerleri köşe-kaçışı artefaktı; `--start tower`
  (DP-optimal sıra, dblf.tower_order_key) bu yüzden 282 verdi — İPTAL.
- Helly kule alt sınırı DELİKLER yüzünden GEÇERSİZ (SA 198 < 206 kanıtı):
  ≤170 "imkânsız" DENEMEZ, sadece "bulunamadı" denebilir.
- SA'nın 198'i ofset-delik hizalamasından geliyor; yatık yolda taban belirsiz.

**Hibrit pivot** (`--orient hybrid`, NUMUNE_ORIENTATIONS_HYBRID):
plaka dik boyları n3 178.3 / n6 180.9 / n7 187.5 / n8 190.1 → 190.5 rekoru
n8 dik tavanıydı.  Sadece n3+n6'ya dik (2,3) açıldı: beklenen yapı n3 (belki
n6) dik + n7/n8 yatık istif → tavan ~178-181.

**Gece koşuları (4 paralel, 2000 iter, p1.5, ~2-3 saat):**
results/_hyb_s42, _hyb_s07, _hyb_s13 (hibrit) + _flat2k_s42 (yatık derin).
Ölürse yeniden başlat:
```
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 2000 --pitch 1.5 --seed 42 --orient hybrid --export-stl --check-clearance --out results/_hyb_s42
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 2000 --pitch 1.5 --seed 7  --orient hybrid --export-stl --check-clearance --out results/_hyb_s07
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 2000 --pitch 1.5 --seed 13 --orient hybrid --export-stl --check-clearance --out results/_hyb_s13
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 2000 --pitch 1.5 --seed 42 --export-stl --check-clearance --out results/_flat2k_s42
```

**Yeni kod** (working tree, commit YOK): dblf.plates_first_key +
tower_order_key + dblf(order_key), sa3d(order_key), run3d --start/--orient,
models NUMUNE_PLATES + NUMUNE_ORIENTATIONS_HYBRID, scripts/probe_nesting.py,
test_dblf 3 yeni test.  **Testler 95/95.**

## 🏆 FİNAL SONUÇ — 2026-06-12 gece (hibrit koşular bitti)

| Koşu | Yükseklik | Clearance | Not |
|---|---|---|---|
| **Hibrit s13 (REKOR)** | **181.5** | 1.50 ✓ | density 0.229, SA kazancı +33.0 — **resmî sonuç, results/numune_sa** |
| Hibrit s07 | 183.0 | 1.50 ✓ | |
| Hibrit s42 | 184.5 | 1.50 ✓ | |
| Yatık 2000it s42 | 205.5 | 1.64 ✓ | 1000it'ten (198.0) kötü — uzun soğutma farklı yörünge; yatık yol tavanı ~198 |

Hibrit bandı 181.5-184.5: seed'e dayanıklı, yapısal çalışıyor (dik n3/n6 +
yatık n7/n8 istifi).  Eski rekor 190.5 (n8 dik tavanı) **9 mm** iyileştirildi;
≤170 hedefi bu konfigürasyonda ulaşılamadı (dik n3 tavanı ~178-180 yapısal).
Final konfig: pitch 1.5, margin 1, --orient hybrid, 2000 iter, seed 13.
Resmî klasörler: numune_sa = _hyb_s13 kopyası; numune_dblf = aynı konfig DBLF
koşusu; compare_numune.py metinleri pitch 1.5 + hibrit olarak güncellendi.

## EĞİK PLAKA ("ekmek rafı") DENEYİ — 2026-06-12 ~02:30 (SA koşuları BEKLEMEDE)

Hedef <=170 için son koz: plakaları dik değil 20-35° eğik dikmek.
Kod HAZIR ve test edildi (96/96): master sete eğik pozlar (indeks 8-11 =
dikten 20/25/30/35°), `NUMUNE_ORIENTATIONS_TILT` (her plakaya yalnız <170
veren açılar), `run3d --orient tilt`.

Ölçülen eğik tavanlar (p1.5, margin 1, voxel): n3 35°→150.0, n6 35°→148.5,
n7 35°→160.5, n8 35°→157.5 — hepsi 35°'de dizilirse raf tavanı ~160.5 mm.
Raf mekaniği: paralel eğik plakalar merdiven profilleriyle iç içe oturur,
her plakanın alt kenarı tabana değerse (z=0) z_clearance maliyeti yok;
>=1 mm boşluğu yatay dilation verir.

DBLF probu 214.5 (beklenen — greedy eğik pozu hiç seçmez, hibritte de
öyleydi; değer SA'dan gelecek).

**SA koşuları KULLANICI BAŞLATACAK (ayrı session) — hazır komutlar:**
```
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 2000 --pitch 1.5 --seed 42 --orient tilt --export-stl --check-clearance --out results/_tilt_s42
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 2000 --pitch 1.5 --seed 7  --orient tilt --export-stl --check-clearance --out results/_tilt_s07
python -m src.nesting3d.run3d --scenario numune --algo sa --iters 2000 --pitch 1.5 --seed 13 --orient tilt --export-stl --check-clearance --out results/_tilt_s13
```
Süre: 3 paralel ~2-2.5 saat. Değerlendirme: en iyi `_tilt_*` sonucu 181.5
(hibrit rekoru) ile kıyasla; <=170 inerse sunum + resmî klasörler + compare
raporu güncellenir (aynı prosedür: numune_sa'ya kopyala, numune_dblf'i
`--orient tilt` ile yeniden koş, compare_numune.py, make_pptx_numune.py
sabitlerini güncelle).

## Sıradaki adımlar (PC açılınca)

1. 5 final koşuyu yukarıdaki komutlarla yeniden başlat (paralel)
2. En iyi sonucu seç → `results/numune_dblf` + `results/numune_sa`'ya resmi
   koşuları koy → `python scripts/compare_numune.py` ile rapor üret
3. ≤170 çıkmazsa kozlar: daha fazla seed, iters 2000, plaka-önce başlangıç
   sezgisi (DBLF sırasında aynı tip plakaları ardışık + aynı x,y'ye zorla)
4. Kullanıcı onayıyla commit + push → https://github.com/Eren845205/ie488-3d-nesting
   (hazır commit mesajı taslağı bu oturumda yazıldı; konu başlıkları yukarıdaki
   "Yapılan kod değişiklikleri" listesi)
5. Commit DIŞI tutulacaklar: WhatsApp görseli (kişisel), NUMUNE_YERLESIM_SA_Z155.stl
   (eski ihlalli sonuç), APP_SORULAR.md (kullanıcıya sor), SUNUM_NUMUNE.pptx
   (oturum öncesi değişiklik, kullanıcıya sor)
