# 04_MOTOR_TUNING — Bayesian Optimization ile Config-Tuning Tasarımı

> Taslak §6(B) verdikti doğrulandı ve korundu: **deterministik motorun
> knob'larını dürüst cross-dataset benchmark'a karşı optimize etmek, daha süslü
> bir sınıflandırıcıdan daha yüksek kaldıraçtır.** Bu dosya onu uygulanabilir
> tasarıma indirir. Ön-şart: `02_EVAL_KAPISI.md` Faz-0 (eval CLI) hazır olmalı
> — objective fonksiyonu odur.

---

## 1. Knob envanteri (ilk tur adayları)

| Knob | Tip | Bugünkü değer/kural | Not |
|---|---|---|---|
| `fine_pitch` | sürekli {0.5, 0.75, 1.0} | 0.5 (kabuk) | R6: pitch değişimi riskli — anchor'lar pitch-bağımlı |
| coarse pitch tarifesi | kural parametreleri | adaptif (parça sayısına) | H-15b: coarse-tune %90 maliyetti |
| `budget` (tuner) | tamsayı | 25 | süre↔kalite ana takası |
| `n_orientations` | {4, 8, 24} | aile-bağımlı (K-18 AX24) | kabukta n=8'in 4..7 pozları voxelize düşürebiliyor (K-22 yan bulgu) |
| wall_aware tetik eşikleri | süreklİ | F5 family_routing sabitleri | en taze kural — duyarlılığı bilinmiyor |
| settle iterasyonları | tamsayı | default | K-18 +settle kazançları ölçülü |
| clearance dilation politikası | ayrık | m=z=ceil(1mm/pitch) | ölçüm-kalibreli; DEĞİŞTİRME (hoca kuralı) — yalnız kayıt |

**İlk iş knob SEÇİMİ değil DUYARLILIK taramasıdır:** her knob için 1-boyutlu
ucuz süpürme (diğerleri sabit, 3-5 değer × dev-suite) → hangi knob'lar
legal-height'ı gerçekten oynatıyor? Etkisiz knob BO uzayına girmez (küçük uzay
= az-örneklemde daha iyi posterior).

## 2. Objective (overfit'e yapısal direnç)

```
maximize   min_{s ∈ dev-setler} [ iyileşme_%(s) ]        (worst-case iyileşme)
kısıt      hiçbir sette INVALID yok
           süre(s) <= 1.25 × mevcut(s)   (hız bütçesi; ayrı pazarlıklı)
raporla    ortalama iyileşme + set-bazlı dağılım (A5)
```

- **Neden worst-case:** ortalama, tek setteki büyük kazançla iki setteki
  bozulmayı gizler (A5). `min` hedefi tek-sete-overfit'i matematiksel olarak
  cezalandırır — bu, taslağın "BO knob-overfit'e karşı korur" iddiasının
  gerçekleşme mekanizmasıdır (BO kendi başına korumaz; objective korur).
- Held-out ASLA objective'e girmez (A3). BO bittiğinde kazanan config TEK KEZ
  held-out'ta doğrulanır (bakış kaydıyla).

## 3. Bütçe gerçeği ve yöntem seçimi

- Bir dev-suite değerlendirmesi ≈ 15-40 dk (deneme4 wall_aware ~6-10 dk +
  plan'lar ~3-4 dk × 3 + numune-dışı). → günde ~20-40 deneme. Bu, BO'nun
  (az-örneklemli pahalı-değerlendirme) tam tasarım noktası.
- **Yöntem:** TPE veya GP-EI. Bağımlılık kararı: çekirdek `src/` sklearn'süz
  kalır (mevcut yasak); **`scripts/` katmanında Optuna KABUL** (dev-time
  bağımlılık, ürüne girmez). İstenmezse basit alternatif: Latin-hypercube
  başlangıç + yerel rafine (elle, stdlib) — knob sayısı ≤4 ise yeterli.
- Determinizm: her deneme seed=42 tek koşu; kazanan adayın 3-seed medyan
  doğrulaması (02_ §6) PASS şartı.

## 4. Süreç (runbook)

1. Duyarlılık taraması (§1) → aktif knob listesi + aralıklar → YONTEM_HARITASI
   aday kaydı (H-xx/K-xx).
2. BO koşusu `scripts/tune_bo.py` (Faz-3'te yazılır): her deneme = eval CLI
   çağrısı; tüm denemeler `data/tuning/trials.jsonl`'e (config + set-bazlı
   legal_height + süre) — bu log kendisi değerli veri (duyarlılık arşivi).
3. Kazanan config → `02_` §2 kapı koşusu (resmî) → PASS ise config değişikliği
   commit + anchor güncelleme (A8) → §3 kaydı.
4. Kaybedenler dahil özet YONTEM_HARITASI'na (NO-GO bilgisi birikir).

## 5. Tuzaklar (bu projede kanıtlı)

- **Pitch anchor'ları:** pitch değişen her deneme frozen anchor'larla
  karşılaştırılamaz — kıyas her zaman AYNI pitch'te (R6 dersi).
- **Kuantizasyon vergisi:** dilation tamsayı-voxel — pitch ile clearance
  etkileşir (`clearance_decompose` bulgusu); pitch knob'u clearance şartını
  bozamaz (INVALID kısıtı yakalar).
- **RAM zarfı:** 6GB istemci hedefi — `peak_ram_mb` kısıt olarak izlenir
  (K-21 koşu-1: RAM taşması disk takasıyla sonucu anlamsızlaştırdı).
- **Süre atfı:** bileşen-toplamı tahmini yerine uçtan-uca ölçüm (H-15 dersi,
  sentez-oranı ~1.0 şartı).
