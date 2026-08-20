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
| MK-03 | **KAFES/çubuk-arası interleave**: aşan-çubuk kolonları + kanallara kitle-plaka + kalan NFV | fsm610 516 z-anatomisi (çubuk-üstü yığılma teşhisi) | tekrar-kitle payı≥0,5 + plaka-aşan parça | **KAPI FAIL — kablo BEKLEMEDE**: dağılımsal 12-seed tetik 24/24 + NÖTR-pozitif (12/12 alçak, ~2mm) AMA seed2 clearance 1,642 korrektlik kenarı AÇIK; fsm610 458,40 LEGAL (−%11,2 tek-set) — kazanç ölçekle büyüyor | K-66-d; kapı: çok-seed dağılımsal + sıfır-dokunuş |
| MK-04 | **ŞİNDİL diyagonal yuvalama**: tek-tip çanak-parça sabit (Δy,Δz) adımla iç-içe dizi (%65 z-tasarrufu gözlendi) | PLAN8 anatomisi (118 braket, Δy≈16/Δz≈17, 4 kolon) | yüksek-tekrar + tf düşük + ölçülen yuvalama-derinliği < 0,7×parça-h | GÖZLEM→TASARIM | K-67; adım-çifti kopya-kaydırma taramasıyla ölçülür |
| MK-05 | **TEK-TİP PLAN bölme politikası**: plan-başına tek model; yükseklik-sürücüler ayrı planda | PLAN8 (yalnız braket) + ≥8 plan gerçeği | çok-parti gereken işte model-bazlı atama | TASARIM (U1 Katman-2) | U1 |
| MK-06 | **PROFİL iç-içe yuvalama**: tf-düşük açık profillerin (çubuk tf 0,098) birbirine kenetlenmesi | çubuk geometrisi + "516'da sömürülmedi" teşhisi; engel: pitch-2 dilation mühürü | tf<~0,15 açık-profil çifti | HİPOTEZ — ince-pitch ister (lab 64GB işi) + iç-içe sözleşme teyidi | K-66 devamı |

## B. Kendi payımıza düşen açıklar (teşhisli eksikler)

| # | Açık | Kanıt | Durum |
|---|---|---|---|
| AC-01 | Karar katmanı sensörlere bakmıyordu (mod-yönlendirici körlüğü) | fsm610 %21 kaybı | K-65 kablo + KARAR-6 polarite + M14 (model→üretim) İLERLİYOR |
| AC-02 | Heightmap yolunda clearance-uygulama zafiyeti (1,004/0,131<2) | fsm610 iki koşu | AÇIK — teşhis sırada (K-45 kuantizasyon bağlantısı şüphesi) |
| AC-03 | Batching'de yükseklik fizibilite kapısı yok (691 tek-parti raporu) | fsm610 | U1 v1 TASARIM HAZIR (LB hakemi + doğru-mod-önce + bölme son çare) |
| AC-04 | Pitch/dilation ince boşlukları mühürlüyor (profil-yuvalama kör noktası) | K-66 teşhisi; kafes v1 INVALID dersi (K-38 yeniden) | KISMİ — kuantize-adım fix'i kodda; ince-pitch donanım bekler |
| AC-05 | Kıyas-şartı doğrulanmadan referans sayısı hedef alındı ("%45 geride" yanılgısı) | PLAN8 öz-ölçümü | KAPANDI — ders: referans DOSYASI önce ölçülür (A10+A4) |

## C. ML'e akış kuralı

Katalogdaki her mekanizma ÜRETİM/KAPI durumuna gelince: (1) M4 portföyüne
KOL olarak eklenir → etiketleri birikir; (2) seçici (mod_yarismasi
kazananı) onun "ne zaman kazandığını" haritalar — el-tetik yalnız adaylık
filtresi kalır; (3) zarf-dışı sınıflarda çekimserlik korunur. Böylece
"manuel çıkarım → otomatik genelleme" hattı: İNSAN mekanizmayı bulur ve
buraya yazar; ML kullanım haritasını öğrenir ve sınırını veriyle inceltir.
