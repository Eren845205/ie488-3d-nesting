# CLAUDE.md — IE 488 Nesting Motoru (proje kuralları, her oturumda geçerli)

> Eren kararı 2026-07-19: "bunu her seferinde bilerek uyguluyor olman lazım."
> Bu dosya oturum bağlamına OTOMATİK yüklenir — aşağıdakiler hatırlamaya
> bağlı değildir, PAZARLIKSIZ uygulanır.

## Her oturum başı ZORUNLU
1. `STRATEJI/00_ANAYASA.md` oku (A1-A11) — özellikle **A11 tek-veri
   geliştirme yasağı**.
2. **`STRATEJI/RUNBOOK_CALISMA_DISIPLINI.md` = TEK GİRİŞ KAPISI**
   (2026-08-20): dosya haritası §0, durum-bazlı prosedürler P-1..P-10,
   süreç dersleri §D. Her durum (yeni veri, hata, koşu, rapor, eğitim,
   dış iletişim, terfi) ORADAKİ prosedürle yürür; şerh-yaşlanma taraması
   (P-10.2) oturum başında yapılır.
3. Motor işine dokunmadan önce `MOTOR/YONTEM_HARITASI_DATA_BASE.md` §2+§5;
   her deney sonrası §3'e kayıt + **A11 karnesi** (şablon §0'da) +
   `MOTOR/MEKANIZMA_KATALOGU.md` durum güncellemesi.

## A11 — HER geliştirmede bilerek uygulanır
- **Tetik geometrik/aile-koşullu yazılır; kodda veri-adı (plan1, deneme4...)
  YASAK.** Tek sette keşfedilen mekanizmanın tetiği genelleştirilerek kodlanır.
- **Tek-set derinleşme = ŞERHLİ ön-ölçüm.** Aynı oturum içinde genelleme
  kanıtı adımı PLANLANIR ve koşulabiliyorsa KOŞULUR:
  (a) diğer dev-setlerde sıfır-dokunuş/etki ölçümü (4-set kapı veya tekil
  replay'ler), VE/VEYA (b) **sentetik-aile DAĞILIMSAL ölçüm** — B1
  jeneratörleri `src/nesting3d/instances/synthetic.py` (thin_plates,
  random_boxes, long_rods, hollow_tubes, shell_bells...), desen:
  `scripts/k59_dagilim_smoke.py` (tetik-doğruluğu + A/B kazanç dağılımı +
  yanlış-pozitif). "Bir sete bir set daha" genelleme DEĞİLDİR.
- **"Kazanç" ilanı** ancak: 4-set kapı PASS (B2 eşikleri) + tetiksiz
  setlerde sıfır-dokunuş kanıtı + yeni mekanizmalarda dağılımsal
  tetik-doğruluğu. Öncesinde her rapor/kayıt "şerhli" der.
- **Sözleşme değişikliği** (clearance / no-go / plaka semantiği) ayrı sınıf:
  hoca teyidi + TÜM baseline yenileme + A8 gerekçeli anchor.
- **Held-out** (numune, boxy, gelen her yeni gerçek sipariş / kör-test)
  geliştirme döngüsünde AÇILMAZ (A3). Yeni veri gelince İLK İŞ held-out
  sınavıdır ve sonucu bakılan-tarih ile registry'ye loglanır.

## Koşu disiplini
- Koşular `D:\ie488`'den `python -m scripts.detach_run <modul>` ile
  (C'ye büyük dosya yazılmaz); kanıt JSON+log D + OneDrive çift kopya.
- Ölçüm koşuları MÜNHASIR (K-57a): RAM-ağır koşular çakıştırılmaz; RAM
  <4GB boşken NFV-ağır setler (plan3, d4) başlatılmaz.
- Üretim log/print SAF ASCII (cp1254 tuzağı); .bat dosyaları CRLF.

## Rapor disiplini
- Sonuçlar onaysız işlenir (YONTEM + memory); onay yalnız KARAR işlerinde:
  commit/push, üretim default değişikliği, baseline güncelleme, hoca içeriği.
- Her sonuç raporunda A11 statüsü görünür: şerhli mi, hangi kanıt adımları
  bekliyor.

## Yedek disiplini (Eren kararı 2026-08-30 — HER değişiklik öncesi)
- Algoritma/model/kablo/config'e dokunan her değişiklikten ÖNCE
  `python -m scripts.yedekle --etiket <ne_oncesi>` (RUNBOOK P-11). Yedek
  onaysız ve anındadır; commit yedeğin yerine geçmez. Geri dönüş yan
  dizine açılır, yerinde üzerine yazılmaz; sonra test.
