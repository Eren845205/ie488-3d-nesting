# 03 — Genişletme Sözleşmesi: yeni algoritma/makale ekleme (sistemi BOZMADAN)

> Hoca farklı bir algoritma isteyebilir, mevcudu değiştirmek isteyebilir, yeni
> bir makale entegre etmek gerekebilir. Sistem buna **açık** tasarlandı. Bu dosya
> "nasıl eklenir, neyi bozmamak gerekir" adım adım anlatır.

## Neden eklemek sistemi bozmuyor (mimari garanti)

1. **Ortak `Solver` protokolü** (`src/nesting3d/solvers/base.py`): her algoritma
   tek bir arayüz uygular. Motor çekirdeği (voxelize, decode, bin3d) algoritmadan
   BAĞIMSIZ — yeni algoritma çekirdeğe dokunmaz.
2. **Registry deseni** (`scripts/benchmark.py` `_SOLVER_REGISTRY`): yeni algoritma
   = sözlüğe BİR satır. Mevcut çözücüler etkilenmez.
3. **Ortak decode** (`dblf.place_in_order`): tüm çözücüler aynı decode'u kullanır →
   yeni algoritma "kalite" kıyasında otomatik adil yarışır.
4. **Best-so-far + DBLF tohum:** hiçbir çözücü baseline'ın altına düşemez →
   en kötü yeni algoritma "baseline kadar" olur, kötüleştiremez.
5. **Benchmark kapısı (tek-konfig):** değişiklik benchmark ortalamasını bozarsa
   MERGE EDİLMEZ — kötü değişiklik veriyle yakalanır, sessizce sızamaz.
6. **Instance-Tuner monoton kabul:** tuner menüsüne yeni konfig eklemek de
   güvenli — iyileştirmezse genel sonuç kalır.

## A. Yeni bir ALGORİTMA (çözücü) ekleme — adımlar

> Örnek: hoca "ant colony / PSO / yeni bir metaheuristik ekleyin" dedi.

1. **Oku:** `01_ALGORITMALAR.md` (mevcut çözücüler) + `solvers/base.py` (protokol)
   + örnek olarak `solvers/sa_solver.py` veya `ga_solver.py`.
2. **Yaz:** `src/nesting3d/solvers/<yeni>_solver.py` — bir class, şu imza:
   ```python
   class YeniSolver:
       def solve(self, parts, bin_factory, *, budget=200, seed=42,
                 order_key=None) -> SolveResult: ...
   ```
   - Genotip = sıra + poz listesi; decode = `place_in_order` (ortak).
   - DBLF baseline'ı tohumla + best-so-far (kötüleşme yasak).
   - Determinizm: tüm rastgelelik seed'li `random.Random`/`np.random.Generator`.
3. **Kaydet:** `scripts/benchmark.py` `_SOLVER_REGISTRY`'ye `"<yeni>": YeniSolver`.
   İstersen `benchmark_config.SOLVER_NAMES`'e ekle (portföye girsin).
4. **Test:** `tests/test_solvers_<yeni>.py` — determinizm + DBLF baseline'dan
   kötü değil + SolveResult alanları dolu.
5. **Benchmark kapısı:** `python scripts/benchmark.py` — yeni satır ortalamayı
   iyileştiriyor mu / en az bozmuyor mu? Sonucu `02_PERFORMANS.md`'ye işle.
6. **Belge:** `01_ALGORITMALAR.md`'ye yeni algoritma bölümü ekle.

**Bozmamak için:** mevcut dosyaları DEĞİŞTİRME (yalnız ekle); protokol imzasını
KORU; `models.py` `NUMUNE_*` ve numune 181.5 yoluna dokunma.

## B. Mevcut bir algoritmayı DEĞİŞTİRME — adımlar

> Örnek: SA'nın enerji fonksiyonunu / soğuma şemasını değiştirmek.

1. **Geriye-uyumluluk ZORUNLU:** mevcut default davranış (örn. SA `t0=3.0`)
   BİREBİR korunmalı — numune 181.5 buna bağlı. Yeni davranışı **yeni parametre/
   mod** olarak aç (örn. `t0="auto"` yaptığımız gibi), default'u değiştirme.
2. **Regresyon testi:** mevcut testler (örn. `test_sa3d.py`) yeşil kalmalı.
3. **Benchmark kapısı:** ortalama bozulmamalı.
4. Sonucu 01 + 02'ye işle.

## B'. Bir algoritmayı ÇIKARMA / GERİ-ALMA — adımlar

> Örnek: hoca "şu çözücüyü beğenmedim, kaldır" dedi; ya da bir deneme benchmark
> kapısından geçemedi. "Sistemi bozmadan ekleme" kadar "bozmadan çıkarma" da
> sözleşmeli olmalı.

1. **Önce ÇIKAR, silme:** çözücüyü `benchmark_config.SOLVER_NAMES` / portföy
   listesinden ve `selection/selector.py` `_solver_by_name`'den ÇIKAR (artık
   seçilmez/koşulmaz). Dosyayı (`solvers/<x>_solver.py`) HEMEN silme — önce
   devre dışı bırak, bir süre dursun (geri istenebilir).
2. **Bağ kontrolü:** çıkarılan çözücü başka yerin tohumu/bağımlısı mı? DBLF
   ASLA çıkarılamaz (herkesin decode tabanı + monoton garanti). SA `_neighbour`
   GA/Tabu/ALNS tarafından yeniden kullanılıyor — SA mantığını silmek onları kırar.
3. **Benchmark kapısı:** çıkarınca portföy ortalaması bozuluyor mu? O çözücü bazı
   instance'larda TEK kazanan mıydı (02 tablo)? Bozuyorsa hoca'ya bunu göster,
   kararı birlikte ver.
4. **Telemetri/model etkisi:** çıkarılan çözücü `selection_model.json`'da kazanan
   olarak varsa, model onu hâlâ önerebilir → `_solver_by_name` fallback DBLF'ye
   düşer (zararsız) ama temizlik için telemetriden retrain önerilir (manuel).
5. **Kaydet:** `00_DEGISIKLIK_GUNLUGU.md`'ye ➖ ÇIKARILDI satırı + neden. Tamamen
   reddedildiyse 🧪 bölümüne taşı (tekrar denenmesin). 01'den durumunu güncelle.

**Geri-alma (⏪):** son commit'i `git revert` ile geri al VEYA devre dışı
bıraktığın satırları geri aç. Günlüğe ⏪ satırı düş. Çözücü dosyası hâlâ
duruyorsa geri-alma tek satır (registry'ye tekrar ekle).

## C. Bir MAKALE'yi entegre etme — "makale → KOD" hattı (§5.1 mekanizma 1)

> "Eğitme" = dosyayı modele yüklemek DEĞİL. Makale → okunur → çözücü/operatör
> KODU yazılır → benchmark'tan geçer.

1. Makaleyi `makaleler/` altına koy + `00_OKUMA_LISTESI.md`'ye işle (ne öneriyor,
   hangi aile/operatör).
2. İlgili tekniği bir çözücü veya operatör olarak kodla (A adımları).
3. Benchmark'ta mevcut en iyiyle yarıştır; **geçemezse MERGE EDİLMEZ** (makale
   iddiası ≠ bizim veride iyi). Geçerse 01/02 güncellenir.

## D. Instance-Tuner menüsüne yeni konfig ekleme

`src/nesting3d/tuner.py` `build_menu()`'ye yeni isimli konfig ekle. Monoton kabul
sayesinde güvenli (iyileştirmezse genel sonuç kalır). İleride LLM önericisi bu
menüden seçecek (arayüz pluggable).

## Yapılmaması gerekenler (kırmızı çizgiler)

- ❌ Voxel master poz indeksi 0-11'i yeniden sıralamak (numune dict'leri indekse
  bağlı — yeni poz yalnız SONA eklenir; bkz R1).
- ❌ Numune'ye özel el-ayarını (`NUMUNE_*`) genel motora taşımak (overfit sızması).
- ❌ Benchmark'ı instance-başı elle ayarlamak (tek-konfig kuralı ihlali).
- ❌ Determinizmi bozmak (seed'siz rastgelelik).
- ❌ Mevcut çözücülerin default davranışını sessizce değiştirmek (geriye-uyumluluk).
