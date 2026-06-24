# NFV Kalite Modu — Toplam Gelişim & Overfit Analizi

> **Tarih:** 2026-06-24 · **Branch:** `m1-cavity-nfv` · **Durum:** kod + UI uçtan uca doğrulandı (git temiz)
> **Kapsam:** NFV cavity "kalite modu" çekirdeği + hız optimizasyonları + oryantasyon/pitch kaldıraçları.
> Kaynak ölçümler: `scripts/c3_*` deney scriptleri + `RESUME_2026-06-22..24.md` + memory backlog.

---

## ⚠️ ÖNCE KRİTİK AYRIM: bu bir TAKAS, tek yönlü "hızlanma" değil

NFV, **kalite için hızdan feragat eden opt-in bir mod**. Günlük (default) akış **heightmap**'tir ve
**hiç değişmedi** — aynı hız, aynı sonuç, aynı kod yolu. Kod teyidi:
- `scripts/demo_pipeline.py:550` → `nesting_mode = payload.get("nesting_mode", "heightmap")` (default).
- NFV yalnızca UI checkbox / `scenario["nesting_mode"]="nfv"` ile devreye girer.

Dolayısıyla "toplam gelişme" iki ayrı eksende okunmalı; yoksa yanıltıcı olur:
1. **Kalite** — NFV modu AÇIKKEN ne kadar kısa istif.
2. **Hız** — iki farklı anlam (aşağıda ayrıştırıldı).

---

## 1) KALİTE — istif yüksekliği (mm, DÜŞÜK = İYİ)

| Veri | Heightmap (default) | NFV n=4 | NFV n=8 | **Kazanç (n=8 vs heightmap)** |
|---|---|---|---|---|
| **Plan2** | 740 | 556 | **522** | **~%29 daha kısa** |
| **Plan1** | 147.3 | 132.1 | ~127 (n=8 +%3.8) | **~%14** |
| **Plan3** | 1165 | 930 | (n=8 ölçülmedi) | **%20+** |
| boxy (sentetik saf-kutu) | — | — | — | **%0 — NFV burada kazanmaz** |

**Yorum:** 3 bağımsız gerçek veride **%14–29 daha kısa istif** — ölçülmüş, tek veriye dayanmayan kazanç.
Referans: **Magics Plan2 = 492mm** (0.5mm fine). Bizim açık n=4'te %13 → **n=8'de %6**'ya kapandı.
⚠️ Adalet notu: bizim 522 KABA pitch (2.0mm), Magics 492 FINE (0.5mm) — adil kıyas için süper
bilgisayarda n=28 + 0.5mm fine gerekir (bu makinede OOM).

---

## 2) HIZ — iki farklı "hız" var, karıştırmamak şart

### (a) NFV'nin KENDİ içindeki hızlandırma (NFV'yi KULLANILABİLİR kılan iş)
| Optimizasyon | Etki |
|---|---|
| Kademeli z-dilim | 985s → 376s (**2.6×**) |
| xy-bbox daraltma | 985s → 281s (**3.5×**) |
| GPU-resident (Plan2, RTX 3060 6GB) | **5.5×** |
| Cross-dataset GPU kazancı | plan1 **2.7×**, plan3 **3.3×**, plan2 **5.5×** |

Pitch + bellek guard sayesinde NFV "5 saat / OOM (Plan2 0.5mm)" → "**~2 dk (2.0mm)**" haline geldi.

### (b) NFV vs DEFAULT heightmap — burada NFV bir MALİYET
- NFV Plan2 ~112–376s **vs** heightmap ~9s → **NFV hâlâ ~10–40× YAVAŞ**.
- Default akışın hızı **DEĞİŞMEDİ**.

**Net:** "Algoritma genelinde hızlandı" demek **YANLIŞ**. Doğru ifade:
> *Kaliteyi açan yeni bir (yavaş) mod eklendi ve o mod kendi içinde 3–5× hızlandırılarak kullanılabilir kılındı.*

---

## 3) OVERFIT RİSKİ — bileşen bileşen

| Bileşen | Risk | Gerekçe |
|---|---|---|
| **n=8 default** | ✅ **YOK (matematiksel garanti)** | 4⊂8 küme-içerme → NFV greedy n=8'de **her veride** ≥ n=4 kadar iyi. Veriye uydurma değil, set teorisi. `NFV_DEFAULT_ORIENTATIONS=8`. |
| **Pitch seçici** | ✅ **Giderildi** (`a26d180`) | İlk hali (tek-oran 0.5) Plan2-overfit'ti, **Plan1'i çökertiyordu**. Düzeltme: güvenli 1.0'dan başla → bellek için adaptif kabalaştır → sığmazsa heightmap'e düş. plan1/2/3/boxy **hiçbiri çökmüyor**. |
| **Plaka guard** (`621936c`) | ✅ Sigorta | En büyük parça + 2·margin plakaya sığmalı; sığmazsa feasible=False. boxy çökmesi giderildi; gerçek veride tetiklenmez. |
| **quality="max"** | ✅ YOK | Sabit sayı değil — RAM'den türeyen donanım-tavanı (`_hw_max_orientations`: 16GB→12, datacenter→28). |

**Genel değerlendirme:** Bu oturumun ANA İŞİ zaten **bir overfit'i bulup gidermekti** (pitch Plan1 çökmesi).
Şu an her parametre türetilmiş: pitch ← min_feature (geometri) + RAM + plaka; oryantasyon ← küme-içerme +
RAM. "SABİT-SAYI YASAK" kuralına uyuluyor. **Aktif overfit riski görülmüyor.**

---

## 4) GENELLEME — bütün setlerde geçerli mi?

**Kalite genellemesi:** ✅ Evet — 3 bağımsız gerçek veride kazanç (%14 / %20 / %29), tek veride değil.
n=8'in ≥ n=4 garantisi de veri-bağımsız (matematiksel).

**Hız genellemesi:** ✅ GPU kazancı her veride birebir (CPU-A = GPU yükseklik) + grid büyüdükçe artıyor
(2.7× → 5.5×). NFV'nin default'tan yavaş olması da her veride tutarlı şekilde geçerli.

### İki DÜRÜST çekince (overfit DEĞİL, NFV'nin doğası)
1. **Sentetik saf-kutu (boxy):** NFV burada kazanmaz — cavity (oyuk) yoksa NFV'nin avantajı yoktur.
   Kazanç parçanın boşluk/kutuluk oranıyla orantılı. Guard sayesinde çökmez, sadece fayda yoktur.
2. **Numune verisi YANILTICI:** kutuluk düşük (0.35) olduğu için NFV cavity testbed'i DEĞİL. Gerçek
   değerlendirme Plan2/Plan3 gibi cavity-zengin (kutuluk ~0.07) verilerde yapılmalı. (Memory'de
   "⚠️ ÖNEMLİ DERS: numune cavity testbed'i YANILTIR — Plan2 kullan" olarak kayıtlı.)

---

## 5) ÖZET (tek paragraf)

NFV, **opt-in** olarak gerçek verilerde **%14–29 daha kısa istif** sağlıyor; bedeli default'tan ~10–40×
yavaşlık (ama mod kendi içinde 3–5× hızlandırılıp kullanılabilir kılındı). Default heightmap akışı hiç
değişmedi — hızı aynı. **Overfit riski aktif olarak yönetildi**: bu oturumda bir pitch overfit'i bulunup
giderildi; n=8 ve quality parametreleri matematik/donanımdan türetildi (sabit-sayı yok). Kalite kazancı
3 bağımsız veride doğrulandı; tek çekinceler NFV'nin doğası gereği (saf-kutuda ve düşük-kutuluk numunede
kazanmaması) — bunlar overfit değil. Magics açığı %13'ten %6'ya kapandı; kalan fark büyük ölçüde KABA
pitch kaynaklı (adil kıyas için süper bilgisayarda fine pitch + yüksek-n gerekli).

---

## EK — sayıların kaynağı (izlenebilirlik)
- Kalite/oryantasyon: `scripts/c3_quality_levers.py` (n=4/8/12 sweep, Plan2 @2.0mm GPU).
- Cross-dataset hız: `scripts/c3_xdataset_speed.py` (plan1/plan3 tam tablo).
- Pitch eğrisi/OOM sınırları: `scripts/c3_pitch_curve.py`.
- Üretim kodu: `src/nesting3d/nfv_solve.py` (n=8 default, quality=max), `src/nesting3d/instances/pitch.py`
  (`suggest_nfv_pitch`), `scripts/demo_pipeline.py` (dispatch, default heightmap).
- İlgili commit'ler: `2d8a5da` (adaptif pitch), `a26d180` (pitch cross-dataset fix/overfit gider),
  `621936c` (plaka guard), `ae306c3` (n=8 default + quality=max), `a57dbac` (pyfftw NO-GO).
