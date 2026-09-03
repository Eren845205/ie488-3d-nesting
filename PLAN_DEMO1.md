# PLAN_DEMO1.md — Demo-1: Algoritma Demosu Fazlı Uygulama Planı

> Tarih: 2026-06-12. Kaynaklar: `APP_YOL_HARITASI.md` (§0.1, §2 R1-R7, §3, §4 Faz 1,
> §5/§5.1, §6.2), `APP_SORULAR.md` (C tablosu), mevcut motor `src/nesting3d/`.
> Kapsam: hocadan yazılı cevap GELMEDEN başlanabilir işler. Bekleyenler en altta
> "BLOKLU" bölümünde.

---

## Hedef (Goal)

Tek-instance'a kalibre mevcut motoru (DBLF + SA, 181.5 mm numune rekoru) KIRMADAN,
çok-çözücülü (DBLF / SA / GA / tabu) bir algoritma portföyüne ve benchmark'la
aklanabilir genel bir motora dönüştürmek — Demo-1'de hocaya "aynı instance'ı N
algoritma koşar, kıyas tablosu basar, en iyiyi raporlar" çekirdeğini göstermek.

## Neden (Why)

- Hoca görüşmesi #2 (§0.1): ilk demo = ALGORİTMA demosu; "sadece SA değil" şartı
  (A6 kısmi cevap) → portföy zorunlu.
- §2 risk listesi: R7 (benchmark yok) kök risk; R1/R2/R4 doğrudan bu planda kapanır.
- Portföy koşucusu aynı zamanda §6 Instance-Tuner menüsünün altyapısıdır.

## Korunacak değişmezler (her fazda geçerli)

1. **Numune regresyonu:** `--scenario numune --orient hybrid` akışı ve 181.5 mm
   sonucu üretebilen konfigürasyon bozulmaz (Faz 0'da resmî regresyon haline gelir).
2. **Master poz indeksleri SABİT:** `voxelize.rotation_matrices` mevcut 0..11
   indeksleri (8 eksen-hizalı + 4 tilt) yeniden SIRALANMAZ — `models.py`
   `NUMUNE_ORIENTATIONS*` dict'leri indekse bağlı. Yeni pozlar yalnız SONA eklenir.
3. **Determinizm:** tüm rastgelelik seed'li `random.Random` / `np.random.Generator`
   üzerinden akar (mevcut SA sözleşmesi GA/tabu'ya da taşınır).
4. **Tek-konfig kuralı (§5):** benchmark kurulduktan sonra motor değişikliği ancak
   benchmark ortalamasını bozmuyorsa merge edilir; numune'yi iyileştirip ortalamayı
   bozan değişiklik RED.
5. **Karantina ayrımı korunur:** `models.py` senaryo verisi motora sızmaz; yeni
   modüller `NUMUNE_*` dict'lerine referans VERMEZ (yalnız `run3d.py` verebilir).

---

## Faz 0 — Regresyon emniyet ağı (kademeli refactor ön şartı)

Mevcut davranışı kilitlemeden hiçbir refactor başlamaz.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 0.1 | Hızlı DBLF regresyon testi: numune senaryosu DBLF baseline yüksekliği (deterministik, SA'sız) altın değer olarak sabitlenir | `tests/test_regression_numune.py` (`@pytest.mark.slow` — slice voxelization dakikalar sürer) | DBLF baseline mm değeri ±0 sapma; mevcut 12 test dosyası yeşil |
| 0.2 | Tam 181.5 mm reprodüksiyon koşusu script'i (SA ~8.5 dk — unit test DEĞİL, manuel/gece koşusu) | `scripts/repro_numune.py` (run3d'yi rekor konfigle çağırır, beklenen değerle karşılaştırıp PASS/FAIL basar) | Tek komutla 181.5 mm (seed 42, kayıtlı konfig) yeniden üretilir |
| 0.3 | `pytest.ini`/`pyproject` marker tanımı: `slow` işaretli testler default koşudan ayrılır | konfig dosyası | `pytest` hızlı, `pytest -m slow` tam |

Kapattığı madde: refactor güvenliği (§4 Faz 1 ön şartı). Efor: **S** (saatler).

---

## Faz 1 — Çözücü portföy altyapısı: ortak arayüz + modülerleştirme

Davranış DEĞİŞMEZ; sadece mimari. Faz 0 regresyonları her adımda yeşil kalmalı.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 1.1 | Ortak çözücü arayüzü: `Solver` protokolü — `solve(parts, bin_factory, *, budget, seed, order_key) -> SolveResult`. `SolveResult` ortak dataclass: placements, bin3d, height_mm, density, time_s, history, meta (solver adı + parametreler) | `src/nesting3d/solvers/__init__.py`, `src/nesting3d/solvers/base.py` | Arayüz birim testli; `SA3DResult` alanları `SolveResult`'a kayıpsız eşlenir |
| 1.2 | DBLF sarmalayıcı: mevcut `dblf.dblf` arayüze adapte edilir (kod taşınmaz, sarılır — `dblf.py` aynen kalır) | `src/nesting3d/solvers/dblf_solver.py` | Numune DBLF baseline'ı bire bir aynı mm |
| 1.3 | SA sarmalayıcı: `sa3d.simulated_annealing_3d` aynı şekilde sarılır | `src/nesting3d/solvers/sa_solver.py` | Aynı seed → bire bir aynı sonuç (Faz 0.2 ile doğrulanır) |
| 1.4 | Ortak genotip + decode sözleşmesi belgelenir: çözüm = sıralı `[(part, orientation_idx)]`, decode = `dblf.place_in_order` (GA/tabu da AYNI decode'u kullanacak — kalite kıyası adil olur) | `solvers/base.py` docstring + `decode()` ortaklaştırması (sa3d'den taşınır, sa3d eskisini import eder) | sa3d testleri yeşil |
| 1.5 | Portföy koşucusu: aynı instance → seçili çözücüler → kıyas tablosu (markdown/CSV) + en iyi sonucun seçimi; çözücü-başı süre/budget raporu | `src/nesting3d/solvers/portfolio.py` | `run_portfolio(parts, bin_factory, solvers, budget)` → tablo + winner; deterministik |
| 1.6 | `run3d.py`'ye `--algo portfolio` + `--solvers dblf,sa,...` bayrakları (geriye uyumlu: `--algo sa` davranışı aynen) | `src/nesting3d/run3d.py` (minimal diff) | Eski CLI çağrıları aynı çıktıyı verir |

Kapattığı madde: §0.1 madde 2 (portföy), §4 Faz 1 "algoritma portföyü", §6
Instance-Tuner altyapısı. Efor: **M** (2-3 gün).

---

## Faz 2 — Benchmark iskeleti (R7 — kök risk; motor değişikliklerinin kapısı)

R1/R2/R3 motor değişiklikleri ANCAK bu faz bitince merge edilir (tek-konfig kuralı
uygulanabilir hale gelir). Bu yüzden Faz 3-4'ten ÖNCE gelir.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 2.1 | Ortak instance formatı: parça listesi (kutu boyutları VEYA STL yolu + adet) + konteyner tanımı, JSON şema. §5.1 adım 2'nin (geçmiş veri sayısallaştırma) hedef formatı da BUDUR — A11 gelince aynı şemaya dökülecek | `src/nesting3d/instances/format.py` (+ şema dokümantasyonu docstring'de) | JSON yükle/kaydet round-trip testi |
| 2.2 | Sentetik instance üreticiler (seed'li): `random_boxes`, `few_large_many_small`, `high_qty_repeat` (yüksek-adetli tekrar parça), `thin_plates` (ince plaka), `long_rods` (uzun çubuk) | `src/nesting3d/instances/synthetic.py` | Aynı seed → aynı instance; her aile için boyut/adet parametreleri belgeli |
| 2.3 | Kutu-tabanlı BR1-BR15 yükleyici (Bischoff-Ratcliff): yayınlanmış veri dosyalarından parse; veri dosyaları repoya `data/br/` altına alınır (kamuya açık OR-Library kaynağı; bulunamazsa yayınlanmış üretici parametrelerinden seed'li yeniden üretim — hangisi kullanıldığı README'de açık yazılır) | `src/nesting3d/instances/br_loader.py`, `data/br/` | BR1 örnek instance yüklenip kutu sayısı/boyutları doğrulanır |
| 2.4 | Kutu hızlı yolu: kutu-tabanlı instance'lar trimesh box mesh → mevcut voxel hattıyla koşulur (ayrı analitik motor YAZILMAZ — Demo-1 kapsamı dışı; A1 cevabı gerektirirse sonra) | `instances/format.py` içinde `to_voxel_parts(instance, pitch)` | 20mm kutu @ pitch 5 = 64 voxel (mevcut test deseni) |
| 2.5 | Benchmark koşucusu: tek komut → tüm instance'lar × seçili çözücüler → tablo (instance, çözücü, yükseklik/doluluk, süre) + ortalama satırı. **Çıplak-motor satırı**: hiçbir elle kısıt/override olmadan koşulan motor skoru her instance'ta ayrı kolon | `scripts/benchmark.py`, çıktı `results/benchmark_<tarih>.md/.csv` | `python scripts/benchmark.py` tek komutla tablo basar; deterministik |
| 2.6 | Tek-konfig + hold-out altyapısı: dondurulmuş parametre seti tek dosyada (`benchmark_config.py`); instance listesi `tune` / `holdout` ikiye bölünmüş ve bölünme sabit | `scripts/benchmark_config.py` | Parametre ayarı yalnız `tune` yarısında yapıldığı README kuralıyla belgeli; koşucu iki yarıyı ayrı raporlar |
| 2.7 | R5 ölçüm satırı: heightmap kaybı göstergesi (yerleşen voxel hacmi / teorik alt sınır) tabloya kolon olarak eklenir — "heightmap kaybı > %X ise tam-3D değerlendir" kararının verisi birikmeye başlar | `scripts/benchmark.py` metrik kolonu | Kolon her satırda dolu |
| 2.8 | **Instance özellik vektörü + telemetri formatı (§6.3.1 temeli — STRATEJİK):** her instance için ~15-25 sayısal özellik çıkaran fonksiyon (parça sayısı, boyut dağılımı istatistikleri, en-boy-yükseklik oranları, hacim varyansı, tekrar-parça oranı, ince-plaka/uzun-çubuk oranı, teorik doluluk alt sınırı); benchmark çıktısı her satırda özellik vektörünü de içerir (CSV kolonları). Böylece algoritma seçim modelinin eğitim verisi İLK koşudan itibaren birikir — sonradan format değiştirme/yeniden koşma maliyeti doğmaz | `src/nesting3d/instances/features.py`, `scripts/benchmark.py` telemetri kolonları | Aynı instance → aynı özellik vektörü (deterministik, birim testli); benchmark CSV'sinde özellik kolonları dolu |

Kapattığı madde: **R7** (doğrudan), **R5** (ölçüm başlangıcı), §5'in tamamı
(set + tek-konfig + hold-out + çıplak-motor + regresyon koşucusu), **§6.3.1
algoritma seçim modelinin veri temeli** (2.8 — telemetri ilk koşudan
birikir; modelin kendisi Demo-1 sonrası, verisi Demo-1 içinde başlar).
Efor: **M** (3-4 gün; 2.8 ile +0.5 gün).

Not (R6 — backlog): pitch otomatik önerisi (`min parça duvar kalınlığı / hedef
çözünürlük` oranından) Demo-1 kapsamına alınmadı; benchmark'ta pitch sabit
konfigde. Faz sonrası küçük iş olarak işaretli.

---## Faz 3 — R1: 24 eksen-hizalı poz

Benchmark kapısı arkasında ilk motor değişikliği.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 3.1 | `rotation_matrices` genişletme: 24 benzersiz eksen-hizalı rotasyonun tamamı. Mevcut 0..7 eksen-hizalı + 8..11 tilt indeksleri AYNEN korunur; eksik 16 eksen-hizalı poz (Ry dahil) indeks 12..27 olarak SONA eklenir. `N_MASTER_POSES` güncellenir; benzersizlik testi (24 eksen-hizalı matris kümesi dedup'lu) | `src/nesting3d/voxelize.py` (minimal diff) | Eski indekslerle üretilen Orientation grid'leri bire bir aynı; yeni set 24 benzersiz eksen-hizalı poz içerir; Faz 0 regresyonları yeşil |
| 3.2 | CLI: `--rotations` choices'a 24 eklenir (ve `n_orientations` → master set eşlemesi belgelenir); default DEĞİŞMEZ | `src/nesting3d/run3d.py` | `--rotations 24` koşar; default çağrılar eski davranışta |
| 3.3 | Benchmark kıyası: 8-poz vs 24-poz tüm benchmark setinde (özellikle `long_rods` / `thin_plates` ailelerinde Ry etkisi beklenir); süre maliyeti (voxelization ~3x, SA decode poz başına) raporlanır | `results/benchmark_r1_*.md` | 24-poz ortalaması ≥ 8-poz; değilse bulgu raporlanır, merge edilmez |

Kapattığı madde: **R1**, §3 madde 1. Efor: **S-M** (1-2 gün; voxelization süresi
artışı koşu maliyetini etkiler).

Not: §3 madde 2 (adaptif poz budama — "tek-başına yüksekliği mevcut tavanı aşan
pozu buda") burada DEĞİL; A12 cevabı ve benchmark verisiyle birlikte ayrı küçük
faz olarak sonra (budama eksen-hizalı 24 pozun maliyetini düşürmek için doğal
devam işi — backlog'a yazıldı).

---

## Faz 4 — Multi-start SA + adaptif t0 (R2, R4)

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 4.1 | Adaptif t0: SA başlamadan ilk N (örn. 50) rastgele komşu decode'unun delta istatistiği toplanır; t0 = hedef erken-kabul oranını veren değer (örn. medyan pozitif delta / ln(1/p0)); `t0="auto"` parametresi — sayısal t0 verilirse eski davranış | `src/nesting3d/sa3d.py` (geriye uyumlu imza) | `t0=3.0` çağrıları bire bir eski sonuç; `t0="auto"` numune'de ±benzer kalite; benchmark'ta farklı ölçekli ailelerde sabit-3'ten kötü değil |
| 4.2 | Multi-start SA resmî bileşen: N seed paralel (Windows uyumlu `multiprocessing`/`concurrent.futures`; süreç-başı seed deterministik türetilir), toplam iterasyon bütçesi tanımlı (N × iters/N veya N × sabit — konfigde), en iyi otomatik seçilir, TÜM seed sonuçları raporlanır (median + best — "şanslı değil tipik" kalite görünür) | `src/nesting3d/solvers/sa_solver.py` (`MultiStartSA`), portföye kayıt | Aynı (seed_base, N, budget) → deterministik aynı sonuç; rapor median/best/std içerir |
| 4.3 | Benchmark kıyası: tek-seed vs multi-start (eşit toplam bütçeyle) — R4'ün "seed alışverişi" iddiası veriyle kapanır | `results/benchmark_multistart_*.md` | Eşit bütçede multi-start median ≥ tek-seed median |

Kapattığı madde: **R2**, **R4**, §3 madde 3. R3 (enerji ağırlığı 0.1·RMS) için
benchmark'ta ağırlık taraması bu fazın koşu altyapısıyla yapılabilir — tarama
deneyi backlog, sonucu iyiyse ayrı merge. Efor: **M** (2-3 gün).

---

## Faz 5 — GA + Tabu Search çözücüleri

A12 (hangi aileler?) cevabı GELMEDEN başlanabilir: GA + tabu en olası adaylar ve
ortak genotip/decode sayesinde A12 farklı aile derse ekleme maliyeti düşük.
A12 cevabı gelirse liste revize edilir — plan bunu varsayım olarak işaretler.

> **A12 kısmi sinyal (2026-06-12):** hoca GA'nın bu tip veri setlerinde daha iyi
> olabileceğini söyledi → varsayım kısmen doğrulandı, revizyon riski küçüldü.
> Uygulama sırası: 5.1 (GA) önce ve özenli (operatör çeşitliliği + popülasyon
> parametreleri benchmark'ta taranır); 5.2 (tabu) sonra. Demo tablosunda GA
> satırının iyi görünmesi hocanın beklentisi açısından önemli.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 5.1 | GA çözücü: birey = ortak genotip (sıra + poz listesi); operatörler: sıra için OX/PMX crossover, poz için uniform crossover; mutasyon = sa3d `_neighbour` hamleleri (yeniden kullanılır); elitizm + best-so-far garantisi; DBLF baseline popülasyona tohumlanır (SA'daki "asla baseline altına düşmez" sözleşmesi korunur) | `src/nesting3d/solvers/ga_solver.py` + birim test | Numune'de DBLF baseline'dan kötü sonuç ÜRETEMEZ; seed'li determinizm; benchmark tablosuna girer |
| 5.2 | Tabu search çözücü: komşuluk = aynı hamle seti; tabu listesi = hamle imzası (örn. (i,j) swap / (i,poz) flip), tenure parametrik; aspirasyon = best'i geçen hamle serbest | `src/nesting3d/solvers/tabu_solver.py` + birim test | Aynı garanti + determinizm; benchmark tablosuna girer |
| 5.3 | Portföy default seti güncellenir: dblf, sa(multi-start), ga, tabu — Demo-1 kıyas tablosu 4 satırlı | `solvers/portfolio.py` konfig | `--algo portfolio` 4 çözücüyü koşup tablo basar |
| 5.4 | Demo koşusu: numune + 2-3 sentetik instance portföyle koşulur, Demo-1 sunum tablosu üretilir | `results/demo1_portfolio.md` | Hocaya gösterilebilir tek tablo: instance × çözücü × kalite × süre |

Kapattığı madde: §0.1 madde 2, §4 Faz 1 "en az 1-2 ek aile", A6/A12 kısmi cevabın
şimdi yapılabilir kısmı. Efor: **M** (3-4 gün).

---

## Faz 6 — Sabit-boyut çoklu-bin sarmalayıcı

Amaç fonksiyonu İKİ varyant olarak kodlanır; HANGİSİNİN default olacağı A2/A3
cevabına bırakılır (her ikisi de koşulabilir durumda teslim edilir).

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 6.1 | `Bin3D`'ye opsiyonel `max_z_voxels` sınırı: `drop_map`'te limiti aşan konumlar geçersiz işaretlenir; `_best_position` None dönebilir → `place_in_order`'a "sığmayanı atla ve raporla" modu (mevcut assert davranışı default kalır — open-dimension çağrılar etkilenmez) | `src/nesting3d/bin3d.py`, `dblf.py` (geriye uyumlu) | Sınırsız çağrılar bire bir eski davranış (Faz 0 regresyonu); sınırlı modda sığmayan parça listesi döner |
| 6.2 | Çoklu-bin sarmalayıcı, varyant O1 — konteyner sayısı min: sıralı doldurma (bin aç → portföy/çözücü ile doldur → sığmayanlar sonraki bin'e), eşitlik kırıcı: son bin doluluk | `src/nesting3d/multibin.py` | Sentetik instance'ta tüm parçalar yerleşir, bin sayısı + bin-başı doluluk raporu |
| 6.3 | Varyant O2 — tek konteyner doluluk max: parça alt-kümesi seçimi (knapsack katmanı: hacim-azalan greedy + çözücü içinde sığmayanı atla) → tek bin'de maksimum doluluk | `multibin.py` (`objective="fill"`) | Aynı instance'ta O1/O2 farklı ve tutarlı sonuç; birim testli |
| 6.4 | CLI + rapor: `--container WxDxH` (verilirse open-dimension yerine multibin), `--objective bins|fill` | `run3d.py` (minimal diff) | Default (bayraksız) davranış değişmez |

Kapattığı madde: §3 madde 4, §4 Faz 1 "sabit konteyner + çoklu-bin". A4 (ağırlık/
istif/this-side-up) cevabı gelince feasibility kancaları 6.1'in geçersiz-konum
mekanizmasına eklenecek — arayüz buna göre tasarlanır (kanca noktası bırakılır,
implementasyon BLOKLU değil ama içerik A4'e bağlı). Efor: **M** (2-3 gün).

---

## Faz 7 — Fiyatlama motoru iskeleti (§6.2) — paralel yürüyebilir

Motor fazlarından bağımsız; Faz 1-6 ile paralel ilerleyebilir. İlke: fiyat hesabı
DETERMİNİSTİK, satır satır izlenebilir.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 7.1 | Normalize kural şeması: girdi alanları (hacim, ağırlık, konteyner sayısı, doluluk, mesafe — A8 ile genişler), kural tipleri (birim fiyat, kademe tablosu, koşullu çarpan, min/max kelepçe), JSON serileştirme | `src/pricing/schema.py` + şema dokümantasyonu | Örnek kural seti JSON round-trip + doğrulama testi |
| 7.2 | Deterministik hesap motoru: nesting sonucu (SolveResult/multibin raporu) + kural seti → fiyat dökümü (satır satır: hangi kural, hangi girdi, ara değer) | `src/pricing/engine.py` + birim testler | Aynı girdi → aynı fiyat; döküm "bu fiyat nereden çıktı"yı tam açıklar |
| 7.3 | İki seviyeli override: (a) kural düzeyi — kural setinde parametre değişikliği yeni versiyon yaratır; (b) teklif düzeyi — tek teklif fiyatı elle ezilir, orijinal + ezilmiş + gerekçe kaydedilir | `src/pricing/overrides.py` | Override'lar iz kaydında; orijinal hesap silinmez |
| 7.4 | Versiyonlama + iz kaydı tasarımı: teklif ↔ kural-seti versiyonu eşlemesi; append-only log (JSON satır dosyası yeterli — DB Demo-1 kapsamı dışı) | `src/pricing/versioning.py` | Teklif kaydından hangi kural versiyonuyla hesaplandığı geri bulunur |
| 7.5 | Excel parser STUB: arayüz + beklenen girdi/çıktı sözleşmesi docstring'de; gövde `NotImplementedError("A8 örnek Excel bekleniyor")` | `src/pricing/excel_parser.py` | Stub import edilebilir; sözleşme belgeli |

Kapattığı madde: §6.2 katman 1-4 (katman 1'in parser gövdesi hariç — BLOKLU).
SaaS yan etkisi gözetilir: kural seti müşteri-başına konfigürasyon dosyası,
kodda sabit değil. Efor: **M** (2-3 gün).

---

## Faz 8 — Çizelgeleme motoru iskeleti (§6.4) — paralel yürüyebilir (eklendi 2026-06-13)

Fiyatlama (Faz 7) deseninin aynısı: mekanizma şimdi, müşteri verisi sonra.
Motor fazlarından bağımsız; `src/scheduling/` yeni paket. A15 bilinmeyenleri
(parti karışım izni, kapasite verileri) KONFİGÜRASYON olarak tasarlanır.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 8.1 | Sipariş + kapasite modeli: Order (müşteri, parça listesi ref, adet/hacim özeti, termin, öncelik sınıfı), Capacity (kaynak sayısı, parti süresi, vardiya takvimi) — JSON round-trip | `src/scheduling/models.py` | Round-trip + doğrulama testli |
| 8.2 | Önceliklendirme kuralları: konfigüre edilebilir ağırlıklı skor (termin yakınlığı/slack + müşteri önceliği + iş büyüklüğü); EDD (earliest due date) default | `src/scheduling/rules.py` | Aynı havuz + aynı konfig → deterministik aynı sıra; ağırlıklar JSON'dan |
| 8.3 | Parti kurucu: sıralı siparişlerden kapasiteye sığan partiler; `allow_mixing` bayrağı (müşteriler arası karışım — A15a cevabına kanca, her iki mod da çalışır) | `src/scheduling/batcher.py` | İki modda da geçerli parti planı; karışım kapalıyken partiler tek-müşterili |
| 8.4 | Termin fizibilite kontrolü: parti planı + kapasite → her siparişin tahmini bitiş tarihi; termin aşımı UYARI listesi ("5 günde yetişmez" sinyali) | `src/scheduling/feasibility.py` | Bilinen senaryolarda doğru aşım tespiti; testli |
| 8.5 | Rapor: öncelik sırası + parti planı + termin uyarıları tek özet (markdown/dict) — ileride agent zincirinin (alım → çizelge → nesting) çıktı sözleşmesi | `src/scheduling/report.py` | Deterministik özet; örnek senaryo testli |

Kapattığı madde: §6.4 halka 2'nin iskeleti; A10 kısmi cevabın (termin-bazlı)
kodlanabilir kısmı. Nesting entegrasyonu (parti → motor çağrısı) Demo-1
sonrası — burada gevşek bağlaşım: parti planı düz veri döner. Efor: **M**.

## Faz 9 — LLM gateway iskeleti (§6.6) — paralel yürüyebilir (eklendi 2026-06-13)

> **Derin plan: `PLAN_LLM.md` (2026-06-13).** Bu faz o planın **L0 çekirdeğinin
> taslağıdır**; 5 rolün tam tasarımı + fazlaması orada (L0-L5). Bayraklı
> revizyonlar (PLAN_LLM §10): 9.1'deki `CloudProvider`/`LocalProvider`
> adlandırması `AnthropicProvider`+`OpenAICompatProvider` olarak revize;
> 9.5 asistan iskeleti L0.8 (topraklama çekirdeği) + L3 (tam rol) olarak bölündü.

Beş LLM rolünün (parser, tuner, hipotez, asistan, rapor — §6.6 tablosu)
ortak altyapısı. Veri-bağımsız; gerçek API çağrısı YOK (testler sahte
sağlayıcıyla). A13 cevabı (bulut/on-prem) tek konfig satırına iner.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| 9.1 | Sağlayıcı soyutlaması: `LLMProvider` arayüzü (complete(prompt, schema) → doğrulanmış dict); `FakeProvider` (test — kayıtlı yanıtlar), `CloudProvider`/`LocalProvider` konfigürasyon iskeleti (gövde stub — endpoint/model konfigden) | `src/llm/provider.py` | FakeProvider ile uçtan uca akış testli; sağlayıcı seçimi konfigden |
| 9.2 | Prompt şablon kayıt defteri: rol-başına şablon (sistem talimatı + few-shot örnek yuvaları + girdi yuvası); şablonlar dosyadan (koda gömülü prompt YOK) | `src/llm/prompts.py` + `prompts/` dizini | Şablon yükle/doldur testli; eksik yuva hatası açık |
| 9.3 | Yapılandırılmış çıktı zorlaması: JSON şema doğrulama + başarısızsa N retry + yine olmazsa `HumanFallback` sonucu (asla sessiz geçiş) | `src/llm/structured.py` | Geçersiz yanıt → retry → fallback zinciri testli |
| 9.4 | Çağrı iz kaydı: her çağrı (rol, şablon versiyonu, süre, token/maliyet alanları, sonuç durumu) append-only JSONL | `src/llm/audit.py` | Kayıt round-trip testli |
| 9.5 | Asistan topraklama iskeleti: `GroundedContext` (yerleşim planı / fiyat dökümü / termin uyarıları gibi sistem çıktılarını paketler); asistan şablonu yalnız bu paketten alıntıyla yanıt kurar (3 kural docstring'de sözleşme) | `src/llm/assistant.py` | FakeProvider ile: bağlamda olmayan soruya "bilgi yok" yanıtı testli |

Kapattığı madde: §6.6 ortak altyapı; §6.1 ince-katman ilkesinin kodu.
Gerçek sağlayıcı gövdeleri (Anthropic API / Ollama) ayrı küçük iş — A13 +
ilk gerçek kullanım fazında. Efor: **M**.

## Bağımlılık sırası (özet)

```
Faz 0 (emniyet ağı)
  └─ Faz 1 (solver arayüzü + portföy koşucusu)
       └─ Faz 2 (benchmark — motor değişikliklerinin KAPISI)
            ├─ Faz 3 (R1: 24 poz)
            ├─ Faz 4 (multi-start SA + adaptif t0)   [3 ile paralel olabilir]
            └─ Faz 5 (GA + tabu + portföy demo)      [4'ten sonra ideal: kıyas adil]
                 └─ Faz 6 (çoklu-bin sarmalayıcı)
Faz 7 (fiyatlama iskeleti) — Faz 1'den itibaren paralel
```

Toplam efor: ~**L alt bandı** (2.5-3.5 hafta tek kişi; Faz 7 paralelliği ile
§4'ün "Demo-MVP ~1-2 hafta" hedefine yaklaşmak için Faz 6 ve 7 demo sonrasına
sarkıtılabilir — Demo-1 minimum çekirdeği Faz 0-5'tir).

---

## Riskler ve önlemler

| Risk | Önlem |
|---|---|
| Refactor sırasında 181.5 mm regresyonu sessizce bozulur | Faz 0 önce; SA tam koşusu yavaş olduğundan hızlı-DBLF altın testi + manuel repro script ikilisi |
| Poz indeksi kayması `NUMUNE_ORIENTATIONS*`'ı sessizce bozar | Değişmez #2: yeni pozlar yalnız sona; Faz 3.1'de eski-indeks grid eşitlik testi |
| BR1-BR15 ham verisi bulunamaz | Yedek yol 2.3'te tanımlı: yayınlanmış parametrelerden seed'li yeniden üretim, kaynak README'de şeffaf |
| GA/tabu, SA'dan belirgin kötü çıkar (demo'da kötü görüntü) | Best-so-far + DBLF tohumlama garantisi: hiçbir çözücü baseline altına düşemez; tablo "en kötü = baseline" gösterir |
| 24 poz voxelization + decode süresini şişirir (~3x) | Faz 3.3 süre kolonu; gerekirse adaptif poz budama (backlog, §3 madde 2) öne çekilir |
| Windows'ta multiprocessing seed/determinizm tuzakları | 4.2 kabul kriteri determinizmi açıkça test eder; süreç-başı seed türetimi merkezi |
| A2 cevabı O1/O2'den farklı bir amaç çıkarır | Faz 6 iki varyantı da kodlar, default'u açık bırakır; amaç fonksiyonu `multibin.py`'de tek noktada |
| Fiyatlama şeması A8 Excel'iyle uyuşmaz | Şema alan listesi genişlemeye açık tasarlanır (ek alan = yeni kural girdisi); motor çekirdeği alan-agnostik |

## Mevcut desenle çelişki bayrağı

- `dblf.place_in_order` bugün "her parça HER ZAMAN yerleşir" sözleşmesiyle assert
  taşıyor (PLAN_3D.md §6.2 kabul kriteri). Faz 6.1 bunu opsiyonel "sığmayanı
  raporla" moduna genişletiyor — açık sözleşme değişikliği, default davranış
  korunarak yapılır. Sessiz override değil; bu satır o bayraktır.
- `run3d.py` `--rotations` choices listesi bugün [1,2,3,4,6,8] — Faz 3.2 listeyi
  genişletir; mevcut default (4) korunur.

---

## BLOKLU — tedarik bekliyor (hocadan)

Bu işler plana ALINMADI; girdi gelince ayrı mini-plan açılır.

| Bekleyen | Soru | Bloke ettiği iş |
|---|---|---|
| A8 — örnek fiyat Excel'i | Excel iç yapısı (tablo mu formül mü, istisnalar) | `src/pricing/excel_parser.py` gövdesi (stub Faz 7.5'te hazır bekler) |
| A9 — mail/ek formatları | Sabit şablon mu serbest metin mi | Faz 2 (otomasyon) mail-ingest + parser tasarımı — Demo-1 kapsamı dışı ama format bilgisi şema tasarımını etkiler |
| A11 — geçmiş nesting verisi | Format (plan/foto/CAD), örnek sayısı | §5.1 öğrenme hattının TAMAMI (toplama → kural çıkarımı) + gerçek-veri benchmark instance'ları (R7'nin en değerli panzehiri). Hazırlık bizde bitik: hedef format = Faz 2.1 instance şeması |
| A12 — makale/algoritma listesi | Portföye hangi aileler girecek | Faz 5 listesinin kesinleşmesi (GA+tabu varsayımla başlıyor — revizyon riski bilinçli alındı) + "makale → kod" hattı (§5.1 mekanizma 1) |
| A14 — HPC erişimi | Sistem/profil/kuyruk + runtime'da kullanılabilirlik | İnce-rotasyon kaba-ince araması (§3 madde 7), masif paralel benchmark sweep'leri, küçük-pitch koşuları. Multi-start SA (Faz 4) yerel paralellikle başlar; HPC gelince N büyütülür |

Ek bekleyenler (BLOKLU değil ama cevabı tasarımı netleştirir): A2/A3 (Faz 6
default amaç + bin selection katmanı), A4 (feasibility kancalarının içeriği),
A1 (kutu mu mesh mi — kutu hızlı yolu zaten Faz 2.4'te açılıyor).
