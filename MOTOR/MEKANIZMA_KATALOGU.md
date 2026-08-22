# MEKANİZMA KATALOĞU — İnsan-Kaynaklı Strateji Çıkarımları + Açıklarımız

> Kuruluş: 2026-08-20 (Eren talebi: "her veriden çıkardığımız sonuçlar —
> mühendislerin bizde olmayan stratejileri, kendi eksiklerimiz — ayrı bir
> yerde not alınsın; ML'in otomatik kısmı bunlara göre yönlendirilsin").
>
> **Amaç:** ML'in AKSİYON-UZAYININ insan tarafı. Her girdi bir mekanizma/
> strateji çıkarımıdır; yaşam döngüsü: GÖZLEM → PROTOTİP → KAPI → ÜRETİM →
> **ML-KOLU** (M4 portföyüne girer, seçici haritalar). Deney kanıtları
> YONTEM §3'te kalır (buraya link); beyanlar HOCA_CEVAPLARI'nda. Burası
> KESİT: "elimizde hangi silahlar var / eksik ne / hangisi ne durumda".
>
> **Runbook kuralı:** her yeni veri/referans analizi + her açık-ayrıştırma
> raporu sonunda bu katalog güncellenir (yeni girdi VEYA durum ilerletme).

## A. Referanstan/insandan öğrenilen mekanizmalar

| # | Mekanizma | Kaynak-kanıt | Geometrik tetik (A11) | Durum | Bağlı iş |
|---|---|---|---|---|---|
| MK-01 | **Düz-KANOPİ**: delikli büyük parça diğerlerinin üstüne düz; dik parçalar deliklerden | Hoca 110,41 görüntüleri (2026-08-03) | delikli/düşük-footprint-doluluk büyük parça + no-go geçişi | **ÜRETİMDE** (kanopi-zinciri v28, nfv-kalite yolu) | K-62 |
| MK-02 | **Hedefli TİLT + zemin-PİN**: baseplate eğik + parça-pinleme | plan1 krizi + Magics eğik basma gözlemi | no-go'lu plakaya düz pozu sığmayan yükseklik-sürücü | ÜRETİM-KABLO (şerhli-GO) | K-56 |
| MK-03 | **KAFES/çubuk-arası interleave**: aşan-çubuk kolonları + kanallara kitle-plaka + kalan NFV | fsm610 516 z-anatomisi (çubuk-üstü yığılma teşhisi) | tekrar-kitle payı≥0,5 + plaka-aşan parça | **✅ DAĞILIMSAL KAPI PASS (2026-08-20 gece, köşe-fix sonrası 12-seed @2,0): 12/12 LEGAL (min cl 2,011) + tetik 24/24 + 2W/10T/0L (yfp SIFIR) + yükseklikler fix-öncesiyle birebir — kablo kararı EREN'DE.** fsm610: kısıt-uyumlu mod **400,00 LEGAL (teorik taban+0,4; kısıtlı-eski 691'e −%42)** = tek-plaka şampiyonu; **plan-skoru v2 (ölü-bant; 2026-08-21 gece) kısıtsız ekseni de 458,4→400,00 LEGAL'e indirdi** (12-seed v2-A/B PASS + sentetik 12/12 bit-özdeş; YONTEM v2 kaydı). M4 portföyüne KOL eklendi (kafes + kafes_duruskoru, tetikli). **🔌 ÜRETİMDE (2026-08-22, Eren "Devam et" onayı): `kafes_zincir.kafes_zinciri_uretim` kanopi-deseni kablo (tetik yoksa sıfır maliyet; kabul=TAM A2+ref'ten iyi; kare-plaka sözleşmesi; orientation-kilitte güvenli atlama; 9 birim test + CANLI duman: tetikli mass 416,5→414,5 KABUL / tetiksiz sıfır-dokunuş)**; plan1 v28 baseline 136,20 (köşe-fix bedeli Eren-onaylı) | K-66-d; kalan: duruş-koru modunun üretim tetiği (S3 yaw teyidi sonrası) |
| MK-04 | **ŞİNDİL diyagonal yuvalama**: tek-tip çanak-parça sabit (Δy,Δz) adımla iç-içe dizi (%65 z-tasarrufu gözlendi) | PLAN8 anatomisi (**126** braket — 2026-08-21 tam-dekod düzeltmesi; Δy≈16/Δz≈15-17, 4 kolon) | yüksek-tekrar + **ölçülen şindil Δz < 0,7×h** (araç: k67_yuvalama_derinligi; saniyelik) | **ÖLÇÜM-ARACI HAZIR + GERÇEK-VERİ KANITLI (2026-08-20 gece: fsm braketi Δy=21/Δz=11, %86; xy-hizalı yuvalanmıyor — şindil şart, YONTEM §3 K-67)** → sırada dizim prototipi (kolon-alan maliyeti) | K-67 |
| MK-05 | **TEK-TİP PLAN bölme politikası**: plan-başına tek model; yükseklik-sürücüler ayrı planda | PLAN8 (plakada yalnız braket ✓ 2026-08-21 tam-dekod; "≥8 plan BU işe ait" çıkarımı ŞERHLİ — PLAN8 muhtemelen işler-arası sayaç, S1 cevabı bekler) | çok-parti gereken işte model-bazlı atama | TASARIM (U1 Katman-2) | U1 |
| MK-06 | **PROFİL iç-içe yuvalama**: tf-düşük açık profillerin (çubuk tf 0,098) birbirine kenetlenmesi | çubuk geometrisi + "516'da sömürülmedi" teşhisi; engel: pitch-2 dilation mühürü | tf<~0,15 açık-profil çifti | HİPOTEZ — ince-pitch ister (lab 64GB işi) + iç-içe sözleşme teyidi | K-66 devamı |

## B. Kendi payımıza düşen açıklar (teşhisli eksikler)

| # | Açık | Kanıt | Durum |
|---|---|---|---|
| AC-01 | Karar katmanı sensörlere bakmıyordu (mod-yönlendirici körlüğü) | fsm610 %21 kaybı | K-65 kablo + KARAR-6 polarite + M14 (model→üretim) İLERLİYOR |
| AC-02 | Heightmap yolunda clearance-uygulama zafiyeti (1,004/0,131<2) | fsm610 iki koşu | AÇIK — teşhis sırada (K-45 kuantizasyon bağlantısı şüphesi) |
| AC-03 | Batching'de yükseklik fizibilite kapısı yok (691 tek-parti raporu) | fsm610 | U1 v1 TASARIM HAZIR (LB hakemi + doğru-mod-önce + bölme son çare) |
| AC-04 | Pitch/dilation ince boşlukları mühürlüyor (profil-yuvalama kör noktası) | K-66 teşhisi; kafes v1 INVALID dersi (K-38 yeniden) | KISMİ — kuantize-adım fix'i kodda; ince-pitch donanım bekler |
| AC-05 | Kıyas-şartı doğrulanmadan referans sayısı hedef alındı ("%45 geride" yanılgısı) | PLAN8 öz-ölçümü | KAPANDI — ders: referans DOSYASI önce ölçülür (A10+A4) |
| AC-06 | **Köşegen clearance sızıntısı**: L1-dilation çekirdeği HAM-pin yanında köşegen cebi korumuyordu (parça pin köşesine <2mm oturabiliyordu; settle cebe indirebiliyordu) | k66 seed2 teşhisi (1,256mm; minimal repro 1,088) + YONTEM §3 köşe-fix kaydı | **KAPANDI (kod; commit onay bekler)** — parça-tarafı `kose_doldur` çekirdeği (L1∪S_diag, yalnız pinli+pin_3d); eksen 1×-margin sözleşmesi testli korunur; yeniden-doğrulama: fsm 400,00 birebir ✓ · plan1 v28 132,00→**136,20 LEGAL (Eren 2026-08-21: yeni baseline KABUL)** |
| AC-07 | **Pin-köşe dolgu bedeli**: AC-06 fix'i pinli-plan1'de +4,2mm + söküm 7-cert'e çıkardı (köşegen cebi tamamen mühürleniyor; daha hassas — köşe-yarıçaplı/mesafe-alanı — dolgu 4,2mm'in bir kısmını geri kazanabilir, garanti yok) | plan1 v28 replay kıyası (YONTEM §3 PLAN1-REPLAY kaydı) | BACKLOG (Eren 2026-08-21 "plan1'e bakarız sonra"); korrektlik önce — fix geri alınmaz |

## C. ML'e akış kuralı

Katalogdaki her mekanizma ÜRETİM/KAPI durumuna gelince: (1) M4 portföyüne
KOL olarak eklenir → etiketleri birikir; (2) seçici (mod_yarismasi
kazananı) onun "ne zaman kazandığını" haritalar — el-tetik yalnız adaylık
filtresi kalır; (3) zarf-dışı sınıflarda çekimserlik korunur. Böylece
"manuel çıkarım → otomatik genelleme" hattı: İNSAN mekanizmayı bulur ve
buraya yazar; ML kullanım haritasını öğrenir ve sınırını veriyle inceltir.
