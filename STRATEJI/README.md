# STRATEJI/ — Algoritma Geliştirme Anayasası ve ML/Genelleme Çerçevesi

> **Sürüm:** v1.0 (2026-07-06, Fable 5) · **Sahibi:** Eren
> **Kaynak:** `ML_GENELLEME_STRATEJI_BULGULAR_2026-07-06.md` (Opus 4.8 ön-taslağı)
> — bu klasör o taslağın koda-karşı-doğrulanmış, düzeltilmiş ve genişletilmiş
> **yürürlükteki** hâlidir. Taslak tarihsel referans olarak kalır; çelişkide
> **bu klasör kazanır.**

---

## Niçin var (kuzey yıldızı)

Bu klasör, algoritma geliştirmeyi **o anki yapay zekânın (model/oturum) anlık
tercihlerinden bağımsız** kılar. Clearance dersi (2026-07-06) motivasyon: 282mm
"kahraman sayı" kısmen config artefaktıydı — ölçüm çerçevesi eksikken "bu daha
iyi" hissi yanıltıcı. Çözüm:

- **Önce:** değişiklik önerilir → "güven bana daha iyi" → oturumun modelinin
  yargısına bağımlı, tekrarlanamaz, overfitting'e açık.
- **Şimdi:** değişiklik önerilir → **sabit, repoda-checkli değerlendirme
  kapısından geçer** (tüm setler + held-out + dürüst metrik). Kabul kriteri
  objektif ve deterministik. Hangi model/oturum olduğu **fark etmez.**

Deterministik olan **kabul kriteri ve değerlendirmedir**; yaratıcı "ne
deneyelim" adımı yargı ister — ama hiçbir iddia kapıdan geçmeden "kazanç"
sayılmaz.

## Klasör haritası

| Dosya | İçerik | Ne zaman okunur |
|---|---|---|
| `00_ANAYASA.md` | Değişmez ilkeler + alınmış kararlar | **Her motor/ML oturumu başında** (kısa) |
| `01_VERI.md` | Veri rejimleri, held-out registry, taksonomi, telemetri v2 | Yeni veri gelince / veri işi yapılırken |
| `02_EVAL_KAPISI.md` | Dürüst metrik tanımı, kapı eşikleri, runbook'lar | Her "iyileştirme iddiası" öncesi/sonrası |
| `03_SECIM_MODELI.md` | ML mevcut durum + karar-yüzeyi kayması + yol haritası | Seçim modeli / öğrenme işlerinde |
| `04_MOTOR_TUNING.md` | Bayesian optimization ile config-tuning tasarımı | Knob-ayarı işine girilince |
| `05_TRANSFER_PLAYBOOK.md` | Başka projelere taşınabilir meta-metodoloji | Yeni proje/iş başlarken |

**İlişki — MOTOR/YONTEM_HARITASI_DATA_BASE.md ile:** YONTEM_HARITASI "ne
denendi, ne oldu" **karar veritabanıdır** (deney günlüğü); STRATEJI/ "nasıl
denenir, ne zaman kabul edilir" **yöntem anayasasıdır**. Her deney yine
YONTEM_HARITASI §3'e işlenir; deneyin kabul kriteri buradan gelir.

## Opus taslağına göre ne değişti (özet)

Doğrulama 2026-07-06, kod okumasıyla (selection/, features.py, family.py,
telemetri, c3_generality):

**Doğrulandı (aynen korundu):**
- Telemetri: 460 satır, 69 instance, 6 sentetik aile (random_boxes 120,
  few_large_many_small 88, high_qty_repeat 80, thin_plates 72, long_rods 72,
  bischoff_ratcliff 28). Model gerçek veriye değil ~69 sentetik instance'a bakıyor.
- gengap: LOO-CV tabanlı overfit kapısı (`OVERFIT_GAP_THRESHOLD=0.2`,
  `MIN_INSTANCES=6`), stratified split, prequential sentinel — sağlam.
- Model: 1-NN + DecisionTree(max_depth=2, min_samples_leaf=2), sklearn'süz,
  yorumlanabilir — küçük-N için doğru temel.
- Öğrenme politikası MANUEL + öneri (retrain.py docstring'i açıkça yasaklıyor).
- İki-rejim veri ekonomisi (sentetik bol/ucuz ≠ gerçek kıt/altın) ve yöntem
  envanteri verdiktleri (boosting/NN hayır, kalibrasyon + kNN evet).

**Bayatladı (güncellendi):**
- "Clearance FIX COMMIT EDİLMEDİ / karar noktası (a)-vs-(b)" → **KAPANDI:**
  (a) uygulandı ve commit'li (`a274628`: `clearance_mm` + HIGH-2 gate + M3 cap,
  2577 test). Gerçek plakada (325) dürüst sayı **329 değil 264mm** (Magics
  250.24'ün +%5.5'i ≈ parite); 329 yanlış-plaka artefaktıydı. (b)
  clearance-aware decompose ile ÖLÇÜLDÜ ve DEĞMEZ bulundu (ödül ≤4mm + garanti
  yok) — `scripts/clearance_decompose.py`.
- "~6 gerçek veri" envanteri → gözcü `otonom_gecmis` sipariş-bazlı kalıcı
  kayıtları (commit `94c3aeb`) **otomatik gerçek-veri kanalı** oldu; her yeni
  mail = registry'ye aday instance (bkz `01_VERI.md`).

**Yeni (taslakta yoktu — en önemli eklemeler):**
1. **Karar-yüzeyi kayması (kritik boşluk):** telemetrideki çözücüler yalnız
   `dblf/sa3d/ga/tabu` — seçim modeli ESKİ metaheuristik portföyü arasında
   seçiyor. Üretimin bugünkü asıl kararları ise **nesting_mode
   (heightmap-vs-NFV)**, **wall_aware tetiği** (bugün F5 kural-tabanlı
   family_routing), **pitch tarifesi**. ML'in hedefi bu yüzeye taşınmalı;
   ayrıntı `03_SECIM_MODELI.md`.
2. **Regret metriği:** seçim modelinin başarısı accuracy ile değil, seçilen
   modun en-iyi-moddan mm cinsinden uzaklığıyla (regret) ölçülmeli — modlar
   arası fark bazen 0.5mm bazen 100mm; accuracy bunu göremez.
3. **Legal-yükseklik** tek başlık metrik olarak formalize edildi
   (yerleşen==N ∧ clearance≥1mm ∧ 0 kilit) — K-19/K-21 derslerinin kurallaşması.
4. **Held-out dürüstlüğü:** Plan1/2/3 + Deneme4 tuning'de KULLANILDI → artık
   held-out İLAN EDİLEMEZLER (development set'tirler). Held-out = Numune + boxy
   + bundan sonra gelen her yeni gerçek sipariş.
5. Transfer playbook (`05_`): Eren'in "farklı işlerde de işimize yarasın"
   isteğinin karşılığı — proje-bağımsız 9 desen.

## Günlük kullanım (özet akışlar — detay 02_EVAL_KAPISI.md)

- **Yeni algoritma fikri:** YONTEM_HARITASI'na aday kaydı → ucuz teşhis
  (ölç-önce) → dev-set kapı koşusu → PASS ise commit + §3 kaydı; FAIL ise
  NO-GO kaydı (o da değerli).
- **Hocadan yeni veri:** `01_VERI.md` registry'ye kayıt → **held-out** etiketi
  → dokunmadan tek final koşusu → sonuç rapora; ASLA tuning döngüsüne sokma.
- **Retrain isteği:** advisor `--suggest` → LOO-CV + gate → manuel
  `python -m scripts.retrain_selection` → promote yalnız gate PASS ile.
