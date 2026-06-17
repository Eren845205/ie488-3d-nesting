# PLAN_OGRENME.md — Kendini-Optimize Eden Öğrenme Döngüsü: Overfit-Güvenli + Root-Cause Akıllı

> ## 🔴 POLİTİKA DEĞİŞİKLİĞİ (2026-06-17): OTOMATİK retrain İPTAL — MANUEL + ÖNERİ
>
> **Kullanıcı kararı:** Öğrenme döngüsü **otomatik/periyodik ÇALIŞMAZ.** Bu
> belgedeki "otomatik, periyodik döngü", "scheduler periyodik tetikler" (Ö1.5),
> "should_retrain → otomatik tetik" niyetleri **artık geçerli değildir.**
>
> **Gerekçe:** Uygulama kendini sessizce yanlış eğitip (overfit) bozarsa
> sorumluluk üreticide (bizde) kalır — kabul edilemez. Hoca/müşteri bu davranışı
> istemeyebilir. Bu riski taşımıyoruz/taşımamalıyız.
>
> **Yürürlükteki model:**
> - Gerçek eğitim (`run_retrain` / artefakt yazma) YALNIZ kullanıcının açık
>   komutuyla: `python -m scripts.retrain_selection`.
> - Hiçbir scheduler/cron/queue retrain'e BAĞLANMAZ. `should_retrain` bir
>   "yeterli yeni veri birikti mi" SİNYALİDİR — otomatik tetik değil.
> - Sistem kullanıcıya **ÖNERİ** sunar (read-only, eğitmez):
>   `python -m scripts.retrain_selection --suggest` → `src/nesting3d/selection/advisor.py`.
>   "Şu kadar veri toplandı, overfit riski şu, şu çözücüler eksik, şu yönde
>   geliştir; karar senin."
> - Tüm güvenlik altyapısı (stratified split, LOO-CV kapısı, monoton garanti,
>   overfit bloğu) **kuruludur ve durur** — ama kapı yalnız MANUEL retrain
>   anında devreye girer.
>
> Aşağıdaki orijinal "otomatik" plan metni REFERANS olarak korunmuştur; tetik
> mekanizması kısımları (Ö1.3 CLI hariç) **uygulanmaz.**

> Tarih: 2026-06-15. Kaynaklar: `APP_YOL_HARITASI.md` (§6 intro monoton-kabul
> ilkesi, **§6.3** kullanıldıkça-akıllanan üç-seviye, **§6.3.1** algoritma-seçim
> modeli + "neden"in mekanistik seviyesi + sentetik karşı-deney, §6.6 Ajan-3
> hipotez rolü), `PLAN_DEMO1.md` (Faz 2.8 telemetri temeli, Faz 5 portföy,
> tek-konfig kuralı), `PLAN_LLM.md` (hipotez ajanı L katmanı, FakeProvider
> deseni), mevcut kod `src/nesting3d/selection/` + `instances/features.py` +
> `telemetry.py` + `scripts/build_selection_model.py` + `instances/synthetic.py`.
>
> **Kapsam ÇİZGİSİ:** bu plan §6.3.1'deki algoritma-seçim modelini, §6.3
> seviye-2/3'teki güvenlik kapısını ve §6.6 Ajan-3 hipotez döngüsünü tekrar
> tasarlamaz — onların MANTIĞI yukarıdaki referanslarda. Burası YALNIZCA o
> mantığı **otomatik, periyodik, overfit-güvenli bir döngüye** bağlayan
> mekanizma: retrain işi + sistem-seviyesi best-so-far kapısı + root-cause
> hipotez-deney motoru + drift öz-teşhis. Çelişki bayrakları §son'da.
>
> **Faz konumu:** §6.3 "Seviye 2 demo sonrası ~1-2 hafta" işi. Mekanizma çoğu
> KURULU (envanter §1); eksik olan **otomasyon + kapı + nedensellik**. Demo-1'i
> (PLAN_DEMO1) GEREKTİRMEZ ama ondan beslenir (telemetri benchmark'tan akar).

---

## Hedef (Goal)

Sistemin her koşudan **root-cause** (neyin NEDEN işe yaradığı) öğrenip bunu
genel motora **soyut, genellenmiş** bir kural olarak — motorun kalıcı kodunu
DEĞİŞTİRMEDEN, yalnız meta-katmanda — entegre eden; hold-out doğrulaması ve
sistem-seviyesi best-so-far kapısı sayesinde öğrenirken **asla kötüleşemeyen**;
ve aptal-retrain ezberini yapısal olarak yasaklayan kapalı bir öğrenme
döngüsü kurmak.

## Neden (Why)

- §6.3 kullanıcı vizyonu: "kullanıldıkça akıllanan sistem". Seviye-1 (veri
  birikimi) KURULU; Seviye-2 (birikimden otomatik ayar) ve Seviye-3'ün güvenli
  hâli (öz-teşhis) henüz OTOMATİK değil — elle `build_selection_model.py`
  çağrılıyor, kapı manuel, "neden" hiç sorulmuyor.
- **Kritik kullanıcı şartı (overfit korkusu):** genel motoru geçmiş veriye göre
  özelleştirmek motoru patlatır. Bu plan overfit'i bir "dikkat" değil **yapısal
  imkânsızlık** olarak kurar (§0 değişmezleri) — aptal retrain bu mimaride
  fiziksel olarak gerçekleşemez.
- §6.3.1 farkı: sıradan algorithm-selection ezber yapar ("X müşteri verisinde
  GA kazandı"). Buradaki AKILLI kısım §6.3.1 madde 4: gözlem → hipotez (neden) →
  **sentetik karşı-deney** → doğrulanırsa genel kural. Bir kural karşı-deneyden
  geçmeden genel sisteme GİREMEZ → nedensel, ezber değil.

---

## 0. Tasarım değişmezleri (öğrenme anayasası — her fazda geçerli)

> Bu 7 madde overfit'i "umut" değil **invariant** yapar. Her faz adımının
> "overfit'e nasıl direniyor" kolonu bu maddelere atıf verir.

1. **DEĞİŞMEZ-A — Genel motor SABİT, öğrenme META-katmanda:** taban çözücüler
   (DBLF/SA/GA/tabu/ALNS) ve voxel/clearance hattı öğrenmeden ETKİLENMEZ;
   tek satır kodu öğrenme tarafından yazılmaz. Öğrenme YALNIZCA `selection/`
   meta-katmanını (hangi çözücüyü seç + hangi tuning) üretir. **Özelleşme
   motorun kalıcı koduna sızarsa = motor patlar = RED.** (§6.3 Seviye-3 sınırı:
   sistem kendi KODUNU değiştirmez.)

2. **DEĞİŞMEZ-B — Soyut özellik, veri kimliği DEĞİL:** model girdi olarak yalnız
   `FEATURE_NAMES` (20 soyut özellik, `features.py`) görür — instance_id /
   müşteri adı / dosya yolu ASLA özellik değildir. Öğrenilen kural "X müşteri"
   değil "repeat_part_ratio > θ → GA" tipinde genellenebilir olmalı. (§6.3.1
   madde 1.)

3. **DEĞİŞMEZ-C — Hold-out zorunlu:** parametre/kural tune'da öğrenilir,
   GÖRÜLMEYEN hold-out'ta sınanır. Hold-out bölünmesi deterministik ve sabit
   (`build_selection_model._split`). Overfit varsa hold-out ifşa eder — tune
   skoru yüksek, hold-out düşük çelişkisi otomatik raporlanır.

4. **DEĞİŞMEZ-D — Sistem-seviyesi best-so-far kapısı (monoton):** yeni öğrenilmiş
   artefakt SADECE hold-out'ta yürürlükteki (kayıtlı) artefaktı GEÇERSE varsayılan
   olur; geçmezse eski artefakt KALIR + ret loglanır. **Sistem öğrenmeden
   KÖTÜLEŞEMEZ** (SA'nın best-so-far garantisinin sistem-seviyesi izdüşümü;
   §6.3 Seviye-2 güvenlik kapısı). Ayrıca runtime'da `selector.select_and_solve`
   zaten DBLF-monoton (selector kötü seçse bile sonuç DBLF'den kötü olamaz) —
   bu iki kapı bağımsız ve üst üste binmiş.

5. **DEĞİŞMEZ-E — Karşı-deney olmadan kural genelleşmez (nedensellik kapısı):**
   bir hipotez ("GA tekrar-parçada kazanıyor ÇÜNKÜ permütasyon çeşitliliği")
   sentetik üreticide o ÖZELLİĞİ değiştirip kazananın değiştiğini GÖSTERMEDEN
   genel kural olamaz. Korelasyon ezberdir; nedensellik karşı-deneyden geçer.
   Geçemeyen hipotez ATILIR + loglanır. (§6.3.1 madde 4.)

6. **DEĞİŞMEZ-F — Sentetik dağılımdan öğren (birkaç gerçek veriye saplanma):**
   eğitim verisi öncelikle sentetik üreticinin (`synthetic.py`) GENİŞ, DENGELİ
   dağılımından gelir; gerçek müşteri verisi yalnız rafine eder, domine ETMEZ.
   Sınırsız + dengeli sentetik = tek-instance ezberinin panzehiri. (§6.3.1
   madde 5: "veri kıtlığı YOK".)

7. **DEĞİŞMEZ-G — Yorumlanabilirlik + kara-kutu yasağı:** öğrenilen her kural
   okunabilir (`explain()`), debug edilebilir, sklearn-siz. "Neden işe yaradığı"
   sorusunun cevabı kod içinde görünür olmalı — kara kutu, ezberin saklandığı
   yerdir. (mevcut `model.py`/`prefilter.py` zaten bu disiplinde.)

---

## 1. Mevcut durum envanteri (gerçek koda dayalı — ne KURULU, ne EKSİK)

> Bu döngünün altyapısının çoğu Demo-1 fazında oracle-kaliteyle kuruldu. Plan
> bunları YENİDEN YAZMAZ; otomasyon + kapı + nedensellik EKLER.

### KURULU (çalışıyor — dokunulmaz veya hafif sarılır)

| Bileşen | Dosya | Rol döngüde |
|---|---|---|
| 20 soyut özellik çıkarıcı | `src/nesting3d/instances/features.py` (`FEATURE_NAMES`, `extract_features`) | DEĞİŞMEZ-B'nin somut hâli; gözlem tarafı |
| Telemetri (append-only JSONL) | `src/nesting3d/telemetry.py` (`append_run`, `load_telemetry`); veri `data/telemetry/runs.jsonl` | Gözlem deposu; her koşu bir satır |
| Eğitim tablosu (telemetri→instance-başı etiket) | `src/nesting3d/selection/dataset.py` (`build_training_table`, `is_easy`/`winner`) | Ham gözlem → öğrenilebilir tablo |
| Kolay-instance ön-filtresi (konservatif kural) | `src/nesting3d/selection/prefilter.py` (`EasyInstancePrefilter`) | Renau&Hart 2024; yanlış-kolay = sadece kayıp |
| Algoritma-seçim modeli (1-NN, yorumlanabilir) | `src/nesting3d/selection/model.py` (`AlgorithmSelector`) | §6.3.1 seçim modeli; düşük güven → portföy |
| Seçim orkestratörü (DBLF-monoton garanti) | `src/nesting3d/selection/selector.py` (`select_and_solve`) | Runtime karar yolu; DEĞİŞMEZ-D ikinci kapı |
| Artefakt kaydet/yükle (JSON, fit'siz) | `src/nesting3d/selection/persistence.py` | Kapı için "yürürlükteki artefakt" mekanizması |
| Model kur + hold-out değerlendir | `scripts/build_selection_model.py` (`_split`, `_evaluate`, SBS/VBS) | DEĞİŞMEZ-C; manuel çalışıyor |
| Sentetik üreticiler (5 aile, seed'li) | `src/nesting3d/instances/synthetic.py` (`random_boxes`, `few_large_many_small`, `high_qty_repeat`, `thin_plates`, `long_rods`) | DEĞİŞMEZ-F; karşı-deney hammaddesi |

### EKSİK (bu planın kapsamı)

1. **Otomatik retrain döngüsü YOK** — `build_selection_model.py` elle çağrılıyor;
   periyodik/tetikli iş yok.
2. **Güvenlik kapısı OTOMATİK değil** — script hold-out skorunu BASIYOR ama
   "yeni artefakt eskiyi geçti mi → ata, yoksa eskiyi koru" kararı + reddedilen
   adayın logu KOD olarak yok. Bugün insan bakıp elle `--save` ediyor (monoton
   garanti uygulanmıyor — yeni model kötü olsa da kaydedilebilir).
3. **Root-cause hipotez-deney YOK** — telemetri ve kurallar var ama "neden"
   sorusu hiç sorulmuyor; karşı-deney üreticisi (DEĞİŞMEZ-E) yok.
4. **Drift sentinel / öz-teşhis YOK** — "şu ailede sistematik zayıfım" raporu
   (§6.3 Seviye-3) üretilmiyor; telemetri kapsamı/kalitesi izlenmiyor.

---

## Faz Ö1 — Otomatik retrain + sistem-seviyesi güvenlik kapısı

> §6.3 Seviye-2'nin otomasyonu. Mekanizma çoğu hazır (`build_selection_model` +
> `persistence`); eksik olan **monoton kapının KOD hâli** + tetikleyici. Bu faz
> tek başına "sistem öğrenirken kötüleşemez" garantisini yürürlüğe koyar.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| Ö1.1 | **Aday-vs-yürürlük kapısı (KALP):** `evaluate_candidate(telemetry, current_artifact_path) -> GateDecision` — telemetriden aday artefakt eğitilir, hold-out'ta hem aday hem yürürlükteki artefakt SBS/VBS metrikleriyle koşulur, `GateDecision(promote: bool, reason, cand_holdout, cur_holdout, delta)` döner. Promote ANCAK `cand_holdout` yürürlüktekini `>= MIN_GAIN_MM` geçerse | `src/nesting3d/selection/gate.py`, `tests/test_selection_gate.py` | Aday eski modelden KÖTÜ hold-out → `promote=False`, yürürlük korunur; aday iyi → `promote=True`; her iki yön testli; deterministik |
| Ö1.2 | **Reddedilen aday logu (kötüleşememe kanıtı):** kapı her kararını append-only JSONL'e yazar (zaman, aday hold-out, yürürlük hold-out, promote, reason). Reddedilen modeller SİLİNMEZ, loglanır — "sistem ne zaman öğrenmeyi reddetti" denetlenebilir | `src/nesting3d/selection/gate.py` (`_log_decision`), `data/telemetry/gate_log.jsonl` | Ret kararı logda; log round-trip testli; sessiz yutma YOK |
| Ö1.3 | **Retrain orkestratörü (tek komut):** `scripts/retrain_selection.py` — telemetri yükle → eğitim tablosu → kapıdan geçir → promote ise `persistence.save_selection_model` ile yürürlük artefaktını ATOMİK değiştir (tmp+rename), değilse dokunma + log. Yeni artefakt eski adı tmp'e taşıyıp versiyonlar (`data/selection_model.v<N>.json` arşivi) | `scripts/retrain_selection.py`, arşiv `data/selection_archive/` | `python -m scripts.retrain_selection` tek komutla kapı kararını uygular; promote yoksa `selection_model.json` byte-aynı kalır |
| Ö1.4 | **Veri-yetersizliği freni (sahte-öğrenme yasağı):** retrain, telemetri `< MIN_INSTANCES_FOR_HOLDOUT` (=10) ise PROMOTE ETMEZ — "veri az, kapı anlamlı değil, yürürlük korundu" loglar. `build_selection_model.py`'deki dürüst-uyarı mantığı kapıya taşınır (kapı seviyesinde zorunlu, sadece basılan uyarı değil) | Ö1.1 içinde guard | n<10 telemetriyle retrain → asla promote; log "veri yetersiz"; mevcut script'in uyarı eşikleri yeniden kullanılır |
| Ö1.5 | **Tetikleyici sözleşmesi (servise hazır kanca):** retrain düz fonksiyon (`run_retrain(telemetry_path, artifact_path) -> GateDecision`), Flask/kuyruk/cron BİLMEZ. PLAN_SERVIS scheduler'ı bunu periyodik (veya "N yeni telemetri satırı biriktiğinde") çağırır — bu plan yalnız saf çağrılabilir sözleşmeyi verir | `src/nesting3d/selection/retrain.py` (`run_retrain`) | Saf fonksiyon; dönüş JSON-serileştirilebilir; PLAN_SERVIS S0 motoru-saf değişmezine uyumlu |

**Bu adım overfit'e nasıl direniyor:**
- Ö1.1 + Ö1.4 birlikte **DEĞİŞMEZ-D**'yi kod hâline getirir: aday model hold-out'ta
  (DEĞİŞMEZ-C, görülmeyen veri) yürürlüktekini geçmeden varsayılan OLAMAZ. Aptal
  retrain (telemetriyi ezberleyen aşırı-uyan model) hold-out'ta düşer → kapı reddeder
  → sistem eski güvenli artefaktta kalır. **Kötüleşme yapısal sıfır.**
- Ö1.2: ret kararları loglandığı için "model ezber yapmaya çalıştı, kapı engelledi"
  görünür — overfit girişimi sessizce gizlenmez, denetlenebilir.
- Ö1.4: az veriyle "öğrendim" yanılsaması yasak; veri-yetersizliği = otomatik fren,
  insan iyimserliğine bırakılmaz.

**Kapattığı madde:** §6.3 Seviye-2 güvenlik kapısı (otomasyon). **Efor: M** (2-3 gün;
mekanizma çoğu hazır, kapı + log + atomik swap yeni).

---

## Faz Ö2 — Root-cause hipotez-deney motoru (AKILLI çekirdek)

> §6.3.1 madde 4 + §6.6 Ajan-3. Bu fazın amacı ezberi nedensellikle ayırmak:
> bir kural genel sisteme **karşı-deneyden geçmeden** giremez (DEĞİŞMEZ-E).
> LLM yalnız HİPOTEZ ÜRETİR; doğrulama deterministik sentetik karşı-deneydir.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| Ö2.1 | **Gözlem özeti (telemetri → yapılandırılmış bulgu):** telemetri + öğrenilmiş seçim modeli kurallarından `ObservationSummary` üretir: hangi özellik ekseninde hangi çözücü domine ediyor (feature-importance benzeri, 1-NN prototip dağılımı + aile-başı kazanan tablosu). Bu, hipotez üretiminin GİRDİSİ | `src/nesting3d/learning/observe.py`, `tests/test_learning_observe.py` | Aynı telemetri → aynı özet (deterministik); "long_rods'ta Ry-pozlu çözücüler kazanıyor" tipi okunabilir bulgu üretir |
| Ö2.2 | **Hipotez üretici (LLM — Ajan-3, ince katman):** `ObservationSummary` → `Hypothesis(feature, direction, claimed_cause, testable_prediction)`. LLM PLAN_LLM gateway'i arkasında (FakeProvider ile testlenir, gerçek API yok); çıktı JSON-şema zorlamalı. **LLM YALNIZ hipotez üretir — kural YAZMAZ, kod DEĞİŞTİRMEZ** | `src/nesting3d/learning/hypothesize.py` (PLAN_LLM `LLMProvider` kullanır), `prompts/hypothesis_*.txt` | FakeProvider ile: özet → şema-geçerli hipotez; şema-dışı çıktı → retry → HumanFallback (PLAN_LLM L0.3); LLM yoksa faz zarif düşer (hipotez=yok, döngü durur, çökmez) |
| Ö2.3 | **Karşı-deney üreticisi (NEDENSELLİK KAPISI — KALP):** hipotezin işaret ettiği ÖZELLİĞİ sistematik değiştiren sentetik instance ailesi üretir (`synthetic.py` üreticileri parametrize edilerek — örn. `repeat_part_ratio`'yu 0.1→0.9 süpür, diğer özellikler sabit). "O özelliği değiştirince kazanan değişiyor mu?" sorusunu deneysel kurar | `src/nesting3d/learning/counter_experiment.py` (synthetic.py'yi sarar, YENİ üretici yazmaz), `tests/test_counter_experiment.py` | Verilen (feature, aralık) → o eksende süpürülmüş, diğer eksenleri sabit-tutulmuş instance serisi; her seri seed'li deterministik; süpürülen özellik gerçekten monoton değişiyor (feature.extract ile doğrulanır) |
| Ö2.4 | **Hipotez doğrulayıcı (deterministik hakem):** karşı-deney instance'larını portföyle koşar (benchmark altyapısı yeniden kullanılır) → `testable_prediction` tutuyor mu? Tutuyorsa `VerifiedRule`, tutmuyorsa `RejectedHypothesis` + neden. **LLM bu adıma KARIŞMAZ — saf kod + metrik** | `src/nesting3d/learning/verify.py`, `tests/test_learning_verify.py` | Sentetik kurgu (kazananı bilinen) → doğru verdict; yanlış hipotez REDDEDİLİR; deterministik; verdict JSON-serileştirilebilir |
| Ö2.5 | **Doğrulanmış kural → seçim modeline besleme (yalnız meta-katman):** `VerifiedRule` selection modeline GENEL bir önsel/ağırlık olarak girer (örn. prefilter eşik adayı veya selector'a ek soyut kural) — ASLA motorun kalıcı koduna değil. Beslenen kural yine Ö1 kapısından geçer (hold-out'ta aklanmazsa girmez) | `src/nesting3d/learning/integrate.py` | Doğrulanmış kural meta-katmana yazılır; motor (`bin3d`/`sa3d`/`dblf`/voxelize) dosyaları DEĞİŞMEZ (test: bu modüller import-zamanı learning'e bağımlı değil); kural Ö1 kapısına tabi |
| Ö2.6 | **Hipotez-deney defteri (bilimsel iz):** her döngü (gözlem → hipotez → karşı-deney → verdict → entegrasyon/ret) append-only loglanır — hangi hipotez denendi, doğrulandı mı, neden reddedildi | `data/learning/hypothesis_log.jsonl` | Tam döngü logda; reddedilen hipotezler kalıcı; round-trip testli |

**Bu adım overfit'e nasıl direniyor:**
- Ö2.3 + Ö2.4 = **DEĞİŞMEZ-E** somut hâli: bir korelasyon ("GA tekrar-parçada
  daha çok kazanmış") ezberdir; ancak `repeat_part_ratio` SÜPÜRÜLDÜĞÜNDE (diğer
  her şey sabitken) kazanan gerçekten değişiyorsa NEDENSELdir. Karşı-deneyden
  geçmeyen hipotez ATILIR — yani sisteme yalnız **nedensel-doğrulanmış** kurallar
  girer, telemetri tesadüfleri değil.
- Ö2.2: LLM'in en tehlikeli yanı (uydurma kural) yapısal kapalı — LLM kural değil
  HİPOTEZ üretir; hipotez deterministik deneyle sınanır. En kötü LLM hatası = boşa
  bir karşı-deney koşusu (kalite riski YOK, §6.6 Ajan-3 koruması).
- Ö2.5: doğrulanmış kural bile DOĞRUDAN yürürlüğe girmez — Ö1 hold-out kapısından
  bir kez daha geçer (çift kapı: nedensellik + best-so-far). Karşı-deney sentetikte
  doğru ama gerçek hold-out'ta zarar veren kural yine reddedilir.
- DEĞİŞMEZ-A: tüm bu döngü meta-katmanda; karşı-deney bile motoru çağırır ama
  motoru DEĞİŞTİRMEZ.

**Kapattığı madde:** §6.3.1 madde 4 ("neden"in mekanistik seviyesi), §6.6 Ajan-3,
§6.3 Seviye-3'ün BİLİMSEL hâli. **Efor: L alt bandı** (4-6 gün; karşı-deney
üreticisi + doğrulayıcı en yoğun kısım, LLM katmanı PLAN_LLM gateway'ine yaslanır).

---

## Faz Ö3 — Telemetri kalitesi/kapsamı + drift sentinel (öz-teşhis)

> §6.3 Seviye-3'ün güvenli hâli: sistem kendi KODUNU değiştirmez ama "şu ailede
> sistematik zayıfım" raporunu kendisi üretir → backlog kendiliğinden oluşur →
> kod değişikliği insan + benchmark kapısından geçer. Döngünün öz-farkındalığı.

| # | İş | Çıktı | Kabul kriteri |
|---|---|---|---|
| Ö3.1 | **Kapsam haritası (özellik-uzayı boşlukları):** telemetrideki instance'ların `FEATURE_NAMES` uzayındaki dağılımını çıkarır; hangi bölgeler SEYREK/BOŞ ("bu özellik kombinasyonunu hiç görmedik") raporlanır. Boşluk = öğrenmenin kör noktası | `src/nesting3d/learning/coverage.py`, `tests/test_learning_coverage.py` | Boş bölge raporu deterministik; "thin_plate_ratio yüksek + n_total_parts yüksek hiç görülmedi" tipi çıktı |
| Ö3.2 | **Sistematik-zayıflık tespiti:** her aile/bölge için selector kararının VBS'e (oracle) göre ortalama kaybı; kayıp eşik üstü olan aileler "sistematik zayıf" işaretlenir — döngünün kendi performans öz-teşhisi | `src/nesting3d/learning/diagnose.py` | "long_rods'ta selector oracle'dan ort. %X geride" tipi rapor; eşik konfigde; deterministik |
| Ö3.3 | **Drift sentinel:** yürürlükteki artefaktın eğitildiği telemetri profili ile GÜNCEL telemetri profili karşılaştırılır; dağılım kayması (yeni aileler, özellik-uzayı kayması) tespit edilince "model bayatladı, retrain öner" sinyali. Sessiz bayatlamaya karşı | `src/nesting3d/learning/drift.py` | Bilinen kaymış telemetriyle drift sinyali; kaymamışla sessiz; deterministik |
| Ö3.4 | **Öz-teşhis raporu → backlog (insan kapısı):** Ö3.1-3.3 tek markdown rapora toplanır: kör noktalar + sistematik zayıflıklar + drift uyarısı + ÖNERİLEN aksiyon (yeni sentetik aile / retrain / motor incelemesi). Aksiyonlar İNSAN onayına gider — sistem kod değiştirmez, backlog üretir | `scripts/learning_selfdiagnose.py`, çıktı `results/selfdiagnose_<tarih>.md` | Tek komutla rapor; öneriler somut + izlenebilir; "kod değiştir" değil "incele/koş" önerir |
| Ö3.5 | **Sentetik kapsam-doldurucu kancası:** Ö3.1'in bulduğu boş bölgeler için sentetik üreticiye hedefli parametre önerisi (o bölgeyi dolduran instance üret) → DEĞİŞMEZ-F'i kapalı döngüye bağlar (kör nokta görülünce sentetik doldurur) | Ö3.4 raporunda öneri olarak | Boş bölge → o bölgeyi hedefleyen üretici parametresi önerilir; öneri Ö2.3 karşı-deney altyapısını yeniden kullanır |

**Bu adım overfit'e nasıl direniyor:**
- Ö3.1 + Ö3.5: overfit'in en sinsi hâli "dar bir bölgede çok veri, gerisi boş" →
  model o bölgeye saplanır. Kapsam haritası bu dengesizliği GÖRÜNÜR yapar; sentetik
  kapsam-doldurucu (DEĞİŞMEZ-F) dengeyi otomatik geri getirir. Birkaç gerçek veriye
  saplanma yapısal engellenir.
- Ö3.2: selector'ın VBS'e göre kaybı izlendiği için "model kendine güveniyor ama
  aslında zayıf" durumu (gizli overfit/underfit) ölçülür — körlük değil.
- Ö3.3: drift sentinel, yürürlükteki kuralın artık temsil etmediği yeni dağılımı
  yakalar; model bayatlayıp sessizce yanlış seçim yapmaya devam edemez.
- Ö3.4: en kritik overfit-koruması — sistem kendi zayıflığını TESPİT eder ama
  KOD DEĞİŞTİRMEZ; düzeltme insan + benchmark kapısından (DEĞİŞMEZ-A + §6.3
  Seviye-3 sınırı). Öz-iyileştirme = öz-teşhis + insan onayı, kör otomasyon değil.

**Kapattığı madde:** §6.3 Seviye-3 güvenli hâli (öz-teşhis), telemetri kalite/kapsam
güvencesi. **Efor: M** (2-3 gün; çoğu telemetri analizi, yeni motor kodu yok).

---

## Bağımlılık sırası (özet)

```
(KURULU: selection/ + features + telemetry + synthetic + build_selection_model)
   │
Faz Ö1 (otomatik retrain + monoton kapı)   ← önce: kapı tüm öğrenmenin emniyeti
   │   [DEĞİŞMEZ-D yürürlüğe girer — bundan sonra sistem kötüleşemez]
   ├─ Faz Ö2 (root-cause hipotez-deney)     ← Ö1 kapısına yaslanır (çift kapı)
   │     [içerik bağımlılığı: PLAN_LLM gateway — FakeProvider ile Ö1'siz de kurulur]
   └─ Faz Ö3 (öz-teşhis + drift)            [Ö2 ile paralel olabilir; Ö1'e bağlı]
```

Ö1 ÖNCE çünkü kapı, Ö2/Ö3'ün ürettiği her kuralın geçtiği emniyettir — kapısız
öğrenme overfit'e açıktır. Ö2 ve Ö3 paralel yürüyebilir (biri nedensellik, biri
öz-farkındalık; kesişimleri yok). Toplam efor: **~L alt bandı** (Ö1+Ö2+Ö3 ≈
1.5-2 hafta tek kişi; §6.3 "demo sonrası ~1-2 hafta" tahminiyle uyumlu).

---

## Riskler ve önlemler

| Risk | Önlem |
|---|---|
| Aday model telemetriyi ezberler (overfit) ama yine de promote edilir | DEĞİŞMEZ-D: Ö1.1 kapısı hold-out'ta (görülmeyen veri) test eder; ezber hold-out'ta düşer → reddedilir; Ö1.2 ret loglanır |
| Az veriyle "öğrendim" yanılsaması | DEĞİŞMEZ-C + Ö1.4: n<10 → asla promote, "veri yetersiz" loglanır; `build_selection_model` dürüst-uyarı eşikleri kapıya taşınır |
| LLM hipotezi uydurma/yanlış kural sokar | DEĞİŞMEZ-E + Ö2.4: LLM yalnız hipotez üretir, kural deterministik karşı-deneyden geçmeden giremez; en kötü = boşa koşu |
| Karşı-deney sentetikte aldatıcı (doğrular ama gerçekte zarar) | Çift kapı: doğrulanmış kural yine Ö1 hold-out kapısından geçer (Ö2.5); sentetik-gerçek tutarsızlığı orada yakalanır |
| Öğrenme motorun kalıcı koduna sızar (motor patlar — en kritik) | DEĞİŞMEZ-A + Ö2.5 testi: motor modülleri (`bin3d`/`sa3d`/`dblf`/`voxelize`) learning'e import-bağımlı OLAMAZ; CI/review taraması |
| Dar bölgede aşırı veri → model o bölgeye saplanır | DEĞİŞMEZ-F + Ö3.1/Ö3.5: kapsam haritası dengesizliği gösterir, sentetik kapsam-doldurucu dengeler |
| Model bayatlar, sessizce yanlış seçer | Ö3.3 drift sentinel: dağılım kayması → retrain öner; selector zaten DBLF-monoton (en kötü kalite kaybı sınırlı) |
| Sistem "kendini geliştirir" derken kontrolsüz kod değiştirir | §6.3 Seviye-3 sınırı + Ö3.4: sistem öz-TEŞHİS üretir, KOD DEĞİŞTİRMEZ; düzeltme insan + benchmark kapısından |
| LLM gateway hazır değilken Ö2 bloke olur | Ö2.2 FakeProvider ile kurulur+testlenir; gerçek hipotez kalitesi PLAN_LLM L katmanına bağlı ama döngü iskeleti API'siz çalışır; LLM yoksa zarif düşüş |
| Retrain runtime'ı bloklar / yarım kalır | Ö1.5 saf fonksiyon + atomik artefakt swap (tmp+rename); PLAN_SERVIS scheduler'ı kuyruğa atar, web'i bloklamaz |

---

## Mevcut desenle / diğer planlarla çelişki + karar bayrakları

- **§B.A — `build_selection_model.py` `--save` bugün monoton DEĞİL (açık
  davranış değişikliği):** mevcut script hold-out skorunu BASIYOR ama `--save`
  verilince modeli KOŞULSUZ kaydediyor — yeni model eskisinden kötü olsa bile
  yürürlük artefaktını ezebilir (DEĞİŞMEZ-D ihlali). Ö1.3 bunu **kapı-zorunlu**
  yapar: promote yoksa artefakt byte-aynı kalır. Mevcut `--save` davranışı
  korunur (manuel kaçış yolu) ama OTOMATİK yol (`retrain_selection.py`) ASLA
  kapısız kaydetmez. Sessiz override değil — bu satır o bayraktır.
- **§B.B — `_evaluate` simülasyonu vs gerçek koşu (kapsam notu):**
  `build_selection_model._evaluate` hold-out'ta seçili çözücüyü GERÇEKTEN
  koşmaz; telemetrideki bilinen height'i kullanır (oracle simülasyon). Ö1 kapısı
  bu hızlı simülasyonu KORUR (telemetri tüm çözücüleri içerdiğinde geçerli);
  ama Ö2.4 doğrulayıcı GERÇEK koşar (karşı-deney instance'ları telemetride yok).
  İki değerlendirme modu bilinçli ayrı: kapı=hızlı simülasyon, nedensellik=gerçek
  koşu. Bayrak: bu ayrım açık tutulur, karıştırılmaz.
- **§B.C — LLM "öğrenme" değil, hipotez (kapsam sınırı):** §5.1 ve §6.3.1
  "eğitme" üç mekanizma — bu plan YALNIZCA istatistiksel seçim modeli +
  hipotez-deney döngüsünü kapsar. "Makale → kod" (§5.1 mekanizma 1) ve geçmiş
  nesting imitation (§5.1 mekanizma 2, A11 BLOKLU) AYRI işler — bu planda DEĞİL.
- **§B.D — kapsam çakışması yok:** seçim modelinin İÇ tasarımı (1-NN, prefilter,
  20 özellik) PLAN_DEMO1 Faz 2.8'de + mevcut kodda; bu plan onları TEKRARLAMAZ,
  yalnız **otomatik döngüye bağlar**. Hipotez ajanının LLM gateway'i PLAN_LLM'de;
  servis tetikleyici PLAN_SERVIS'te. Bu plan o üçünün **öğrenme-döngüsü
  sarmalı**.

---

## BLOKLU — dış girdiye bağlı (ama döngü iskeleti bloklamaz)

> Bu plan girdi BEKLEMEDEN kurulur (sentetik veriyle çalışır — DEĞİŞMEZ-F).
> Aşağıdakiler döngünün GERÇEK-VERİ kalitesini artırır, iskeletini bloklamaz.

| Bekleyen | Soru | Etkilediği (bloke ETMEZ) |
|---|---|---|
| A11 — geçmiş nesting verisi | Format + örnek sayısı | Ö1 retrain gerçek-veri telemetrisiyle ZENGİNLEŞİR (sentetikle kurulur, gerçekle rafine); §5.1 imitation AYRI plan |
| A12 — algoritma/makale listesi | Portföye hangi aileler | Ö2 hipotezleri daha çok çözücü ailesi olunca daha zengin; mevcut 4-çözücü (dblf/sa/ga/tabu) ile döngü tam çalışır |
| A13 — bulut/on-prem LLM | Hipotez ajanı sağlayıcısı | Ö2.2 FakeProvider ile kurulur; gerçek sağlayıcı PLAN_LLM gateway konfig satırı; A13 yalnız o satırı belirler |
| A14 — HPC | Karşı-deney koşu ölçeği | Ö2.3/Ö2.4 karşı-deney serileri HPC'de masif paralelleşir (binlerce instance); yerel ölçekte de çalışır, sadece daha az süpürme noktası |
| PLAN_SERVIS scheduler | Periyodik retrain tetiği | Ö1.5 saf fonksiyon hazır; tetikleyici PLAN_SERVIS S1; manuel `python -m scripts.retrain_selection` ile bağımsız çalışır |
