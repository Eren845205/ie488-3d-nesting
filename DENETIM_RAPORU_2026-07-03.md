# Denetim Raporu — 2026-07-03 (Deneme4 sonrası sistematik tarama)

> Tetikleyici: Deneme4 (ilk gerçek dış-müşteri maili) canlıda 3 hatayı arka arkaya
> açığa çıkardı (adet-parser formatı, voxelize kabuk-guard'ı, auto-mod seçimi).
> Kullanıcı tespiti: "ilk örneklemde 3 hata çıktıysa popülasyonda daha fazlası vardır."
> 4 paralel reviewer (opus) ile ortak hata sınıfı tarandı:
> **"Plan1/2/3'e göre kalibre edilmiş varsayım × yeni veri ailesi"** —
> format vekilleri (girdi biçimi varsayımları) + geometri vekilleri (bbox varsayımları).
>
> Aynı gün kapatılanlar (bu rapora girmedi): parser tire-ailesi + .txt eki + toleranslı
> eşleştirme + checksum; voxelize boş-grid guard taşıma; gözcü NFV-kalite politikası;
> P0 kesin-sonuç tanımı (poller) + hata görünürlüğü (geçmiş).

## Önceliklendirilmiş bulgular

### DALGA 1 — Veri/emek kaybını durduranlar (üretim güvenliği) — AÇIK, ilk sırada önerilir
| # | Sev | Bulgu | Yer |
|---|-----|-------|-----|
| 1 | CRITICAL | /adet-gir: sıfır-sonuçlu koşuda pending kaydı + STL byte'ları DİSKTEN SİLİNİYOR, geçmişe iz yok — operatör emeği + kaynak veri imha, telafi imkânsız | app.py:2601-2611 |
| 2 | CRITICAL | Manuel /otonom (sync+async): nesting_produced_output kapısı YOK — sıfır-sonuçlu koşu maili kalıcı "işlendi" yapar (idempotency ortak → gözcü de almaz) | app.py:1799-1800 |
| 3 | HIGH | Kısmî başarı yutması: 3 partiden 1'i başarılıysa iş "bitti" sayılır; başarısız partiler hiçbir yerde görünmez (eksik teslimat) | mail_poller.py + app.py:619 |
| 4 | HIGH | Sıralama tersliği: mark_processed geçmiş-yazımından ÖNCE kalıcılaşıyor; geçmiş yazımı sessizce başarısız olabilir = "görünmez iş" | mail_poller.py:203, app.py:680 |
| 5 | MEDIUM | /adet-gir başarılı işte de geçmişe yazmıyor (denetim izi eksik) | app.py:2511-2611 |
| 6 | MEDIUM | /sonuc ekranı hata durumunu göstermiyor (geçmiş "hata" derken sonuç ekranı normal görünüyor) | sonuc.html + LAST_RESULT |

**Fix yönleri (R1 raporundan):** #1 `nesting_produced_output` kapısı → sıfır-sonuçta pending KORU + `?hata=nesting` + geçmişe hata kaydı · #2 mark döngüsünü poller'daki kapıyla hizala · #3 kısmî başarı için ayrı durum ("kismi") + başarısız parti notları hata_ozeti'ne + mark yalnız tam başarıda · #4 geçmiş-yaz-ÖNCE-mark sıralaması + yazım hatası görünür uyarı · #5 /adet-gir başarıda `kaynak="manuel"` geçmiş kaydı · #6 /sonuc'a hata banner'ı.

**Bugün kapananlar (bu dalganın poller ayağı):** gözcü yolunda kesin-sonuç kapısı + durum="hata" + "hata:" dedup öneki + UI hata rozeti (27 test).

### DALGA 2 — Sipariş kaybettiren girdi formatları (R2)
| # | Sev | Bulgu | Yer |
|---|-----|-------|-----|
| 7 | HIGH | HTML-only gövde ham HTML olarak parser'a gidiyor — `<p>Ad - 62</p>` çözülmez; Outlook kurumsal mailleri düşer | mail_ingest.py:582-588 |
| 8 | HIGH | ZIP içi Türkçe dosya adı cp437 mojibake (Windows Explorer UTF-8 bayrağı koymaz) — yalnız Türkçe adlı parçalar sessizce düşer = kısmî sipariş | zip_stl_extractor.py:82-93 |
| 9 | HIGH | ZIP yolunda kardeş .xlsx/.csv adet listesi okunmuyor (yalnız .txt) | mail_ingest.py:995, :821 |
| 10 | HIGH | Yalnız İLK zip işleniyor; 2. zip / RAR / iç-içe zip sessizce kayıp | mail_ingest.py:696-702 |
| 11 | HIGH | Türkçe Excel CSV'si: `;` ayraç + cp1254 + ondalık virgül desteklenmiyor → sipariş boş | order_attachment_parser.py:200,210 |
| 12 | MEDIUM | Tire kalıbı imza/adres yanlış-pozitifi ("Blok B - 3") → sinyal kapısı gereksiz açılır | quantity_text_parser.py:61 |
| 13 | MEDIUM | "N parça" beyanı serbest cümleden yakalanıyor → doğru sipariş gereksiz quantity_conflict | quantity_text_parser.py:69 |
| 14 | MEDIUM | RFC2047-kodlu ek adı/konu çözülmüyor ("Sipariş.zip" → uzantı bulunamaz) | mail_ingest.py:401,699 |
| 15 | LOW | Birden çok .txt'te ilki alınıyor (disclaimer.txt tuzağı) | mail_ingest.py:821 |

### DALGA 3 — Müşteriye giden rakamları bozanlar (R3 + R4)
| # | Sev | Bulgu | Yer |
|---|-----|-------|-----|
| 16 | CRITICAL | Otomatik plaka adet-körü: yalnız en büyük TEK parçadan türer; 588 küçük parça → 36mm plaka → 4.3 METRE yükseklik senaryosu | plate.py:30-45 |
| 17 | HIGH | Fiyat hacmi: STL parçalarda 0 (hacim bileşeni tamamen kayıp!), kutuda bbox=katı (kabukta ~8× fazla) — mesh.volume kullanılmıyor | demo_pipeline.py:372-383 |
| 18 | HIGH | Kullanılan plaka boyutu hiçbir sonuç yüzeyinde görünmüyor (rapor/geçmiş/GLB) → Magics yükseklik kıyası doğrulanamaz | stl_order_loader.py:254, sonuc.html |
| 19 | MEDIUM | Doluluk metriği yüzey-şişirilmiş voxel'den → pitch-bağımlı, kabukta şişer → haksız doluluk-indirimi | bin3d.py:221-227 |
| 20 | — | KULLANICI KURALI (2026-07-03): plaka verilmediyse algoritma EN İYİ plakayı kendisi seçsin — aday merdiveni (taban ×1/×1.25/×1.5/×2) + kaba koşu + W·D·H hacim ölçütü; #16'yı da kapatır | tasarım hazır, görevde |

**Bugün kapananlar (bu dalganın fiyat-hacmi ayağı):** #17 STL fiyat-hacmi=0 → KAPANDI 2026-07-03: STL gerçek mesh hacmi (`true_fill*bbox`) artık `_parts_real_volume_mm3` üzerinden fiyat girdisine (`hacim_m3`) VE parti gruplamaya (`Order.total_volume_cm3`) yansıyor — kod davranışı zaten böyleydi, bu karar bilinçli kabul edildi ve testle kilitlendi (`test_reporting_wave_f0`).

### DALGA 4 — Motor fiziği + performans (R3 + R4; ÖLÇ-ÖNCE)
| # | Sev | Bulgu | Yer |
|---|-----|-------|-----|
| 21 | CRITICAL | Kapalı/erişilemez kaviteye yerleştirme denetimi YOK — parçalar mekanik iç içe kilitlenebilir (baskı sonrası ayrılamaz); Magics bu kısıtı uygular → kıyas da adaletsiz | extreme_point.py:229, parallel_decode.py:80 |
| 22 | HIGH | quality=max için zaman bütçesi YOK — 588 parça poller'ı saatlerce kilitleyebilir (canlı tekrar ÖNCESİ çözülmeli) | nfv_solve.py:113, parallel_decode.py |
| 23 | HIGH | RAM guard TOPLAM RAM'e bakıyor (available değil) + parça-sayısı-körü → AX24 yanlış tetiklenip OOM | nfv_solve.py:40-45, capabilities.py |
| 24 | HIGH | RAM ön-kontrolü yalnız NFV'de; tuner/coarse yolları guard'sız (1mm+500mm karışık set = ~4GB grid → OOM) | demo_pipeline.py:656-691 |
| 25 | HIGH | min_feature=bbox-min her katmanda: kabuk parça kaba pitch'te "katı blok"a şişer → coarse plan yanlış optimize (bugünkü fix'in yan etkisi; kalıcı çözüm cidar-kalınlığı türevi) | coarse_to_fine.py:40, pitch.py:48 |
| 26 | MEDIUM | fine_settle kabuk duvarını fine pitch'te delikli voxelize edebilir → settle gerçek çakışma sokabilir | fine_settle.py:118 |
| 27 | MEDIUM | Auto-mod kararı eldeki fill_ratio (kabuk!) sinyalini kullanmıyor (gözcüde bypass edildi; manuel ekranda hâlâ yanlış) | adaptive_params.py:122-160 |
| 28 | MEDIUM | Devoxelizasyon çakışma-garantisi örnekleme-tabanlı (voxel⊇mesh ispatsız); margin=0 | voxelize.py:260-330 |
| 29 | LOW | pitch docstring 2.0↔kod 0.5; min_feature_mm None-filtresiz (TypeError) | pitch.py:182,48 |

### Sağlam doğrulananlar (tekrar dokunma)
GPU fallback zinciri her kademede garantili (R4-H5 PASS) · zip-bomb/path-traversal korumaları ·
.txt kodlama fallback'i · MAX_QTY clamp · belirsiz-eşleşme reddi · idempotency çekirdeği.

## Zorunlu canlı probe'lar (Deneme4 üzerinde, live-runtime kuralı)
1. `solve_nfv(quality="max")` 588 parça: uçtan uca süre + tepe RAM (#22/#23 doğrulaması) — CANLI TEKRARDAN ÖNCE.
2. Kullanılan plaka boyutu logu → Magics 250.24mm kıyası aynı plakada mı (#18).
3. Sonuç GLB'de 3-5 kabuk çifti erişilebilirlik el-kontrolü (#21 kanıtı).
