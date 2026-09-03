# PARALLELLİK TASARIMI — NFV decode süper bilgisayarda (2026-06-23)

> **Bağlam:** Tek-thread FFT bu geometride ~optimal (bit-pack NO-GO, `8cd33f7`); banka
> edilen 3.5× (kademeli z-dilim + xy-bbox) ulaşılabilir tek-thread kazancın çoğu. ~50s ve
> ötesi + fine doğrulama (B) için gerçek kol = **PARALLELLİK** (donanım sizde var). Bu doküman
> NFV'yi nerede/nasıl paralelleştireceğimizi planlar. **Henüz uygulanmadı — tasarım.**

## 1. NFV decode'un paralellik haritası (kodtan, `c3_speed2.py` / `nfv_decode`)

```
for part in largest_first(parts):          # ◀ DIŞ: zorunlu SIRALI (greedy: her parça
    for oi, orient in part.orientations:   #   öncekinin occupancy'sine bağlı)
        o = blb_nfv(ob, orient)            # ◀ İÇ: BAĞIMSIZ (her orient ayrı fftconvolve,
    best = min(key over orients)           #   aynı read-only occupancy) → PARALLEL
    ob.place(best)                         # ◀ tek yazım, sıralı
```

| Seviye | Paralel mi? | Beklenen kazanç | Tip |
|---|---|---|---|
| **A. Oryantasyon (iç döngü)** | ✅ embarrassingly | ~n_or× (4-8×) | tek-decode latency |
| **B. Multi-start (seed/sıra)** | ✅ embarrassingly | kalite + core doygunluğu | kalite araması |
| **C. Konfig/pitch sweep** | ✅ trivially | job sayısı× | cluster job-array |
| D. Tek fftconvolve içi | kısmi (`scipy.fft.set_workers`) | marjinal (denendi) | — |
| Greedy sıralı zincir | ❌ (veri bağımlılığı) | — | — |

## 2. Kol A — Oryantasyon-paralel (TEK decode'u hızlandırır, ÜRETİM için kritik)

**Ne:** Bir parçanın 4-8 oryantasyonunun `blb_nfv` (fftconvolve) çağrıları aynı **read-only**
occupancy üzerinde bağımsız → paralel koştur, sonra `key` ile en iyiyi seç.

**Teknik seçim — THREAD (process değil):**
- `scipy.fft`/`fftconvolve` transform sırasında **GIL'i bırakır** → ThreadPoolExecutor ile
  gerçek paralellik, **occupancy kopyalanmaz** (paylaşımlı read-only). Process pool olsa her
  task'a devasa occupancy pickle'lanır (fine pitch'te 100+MB) = öldürücü overhead.
- `ThreadPoolExecutor(max_workers=n_or)`; her future bir orient'in BLB'sini döner; ana thread
  `key` ile birleştirir. Yerleştirme (`ob.place`) tek thread'de sıralı kalır.

**Beklenen:** n_or=4 → ~3-4× (FFT GIL-free oranında); 281s → ~75-95s. Fine doğrulamayı (B)
pratikleştiren ilk kol.

**Determinism:** `key` karşılaştırması sırasız birleştiğinden sonuç sıradan BAĞIMSIZ (min
deterministik) → **paralel sonuç == seri sonuç BİREBİR** (kalite-koruma testi şart).

## 3. Kol B — Multi-start paralel (kalite araması, opsiyonel)

**Ne:** Farklı yerleşim **sırası**/oryantasyon-önceliği/seed ile K bağımsız decode, en iyiyi al.
**Uyarı (handoff §14):** Plan2'de greedy 556 zaten iyi, SA 556→556 (metaheuristic gereksiz
çıkmıştı). Yani multi-start'ın marjı dar — AMA fine pitch'te veya başka veride sıra-duyarlılık
(Faz1: spread %9.7) marj açabilir. **Önce ölç (B sonrası), sonra yatırım.**

**Teknik:** PROCESS pool / MPI / job-array — her decode bağımsız süreç (occupancy paylaşımı
yok, kopya sorunu yok çünkü ayrı işler). K×core'a ölçeklenir. Bellek = K × occupancy.

## 4. Kol C — Sweep paralel (cluster, bedava)

Pitch/konfig/plan başına bağımsız job (B'nin 1.5+1.0mm koşuları, Plan1/2/3, A/B testleri).
HPC **job-array** (SLURM `--array`) veya basit `multiprocessing.Pool` over config listesi.
Hiç kod değişikliği gerektirmez — mevcut scriptleri parametreyle paralel başlat.

## 5. Süper bilgisayar haritası

```
Cluster (SLURM job-array)
 ├─ Job 1: pitch=1.0 ┐
 ├─ Job 2: pitch=1.5 ├─ Kol C (sweep, node başına 1 decode)
 ├─ Job k: plan3     ┘
 └─ Her node içinde:
      Kol B: K multi-start decode  (process pool, node core'larına böl)
       └─ Her decode içinde:
            Kol A: orient-thread (n_or thread, FFT GIL-free)
             └─ scipy.fft.set_workers (Kol D, marjinal)
```
İç içe: node-arası (C) → node-içi süreç (B) → decode-içi thread (A). Oversubscribe etme
(toplam thread ≈ core); A ile B aynı node'da yarışırsa B'yi azalt.

## 6. Fine doğrulama (B) ile bağ

0.5mm fine FFT tek-thread'de saatler + bellek riski. **Kol A (orient-thread) tek başına**
fine decode'u ~3-4× kısar; **Kol C** ile 0.5mm'yi süper bilgisayarda tek-seferlik node'a atarız.
Yani B'nin "süper bilgisayar tek-seferlik" yolu = Kol A + Kol C. (Şu an B 1.5/1.0mm yerel koşuyor.)

## 7. Doğrulama / riskler (KALİTE-KORUMA — sizin §7 kuralınız)
- **Birebir testi:** paralel decode == seri decode (Plan2 556 / B sonucu) BİREBİR. Kol A
  deterministik birleştiğinden geçmeli; geçmezse race/tie-break hatası, DUR.
- **Oversubscription:** thread×process > core → yavaşlama. Ölç, ayarla.
- **Bellek (multi-start):** K × occupancy fine'da patlayabilir → K'yı belleğe göre sınırla.
- **scipy thread-safety:** fftconvolve thread-safe (yeni dizi döner); paylaşılan occupancy
  yalnız okunur, yazım tek-thread → güvenli.

## 8. Önerilen uygulama sırası
1. **Kol A (orient-thread)** — en yüksek ROI, tek-decode'u 3-4× kısar, üretim+B için kritik,
   birebir-korunur. İLK.
2. **Kol C (sweep)** — bedava, B'nin fine koşularını ve Plan1/3'ü cluster'a dağıtır.
3. **Kol B (multi-start)** — yalnız B/fine'da sıra-marjı ölçülürse (handoff §14: kaba'da gereksiz).

**Not:** Hepsi DENEY katmanında prototiplenir (`scripts/`), birebir-doğrulanır, sonra (A)
üretime opt-in bağlanırken paralel yol da taşınır. Rollback tag `checkpoint-2026-06-22-faz1-2`.
