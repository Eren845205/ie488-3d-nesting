# BUSINESS PLAN VE YAPILACAKLAR — İş/Ticarileşme Defteri

> Açılış: 2026-08-17 (hoca görüşmesi sonrası, Eren talebi).
> **Bu dosya bundan sonra business tarafının TEK defteri:** yapılacak işler,
> soru işaretleri, pazarlama/fiyatlandırma fikirleri, müşteri gelişmeleri
> buraya işlenir. Teknik motor işleri YONTEM_HARITASI'nda kalır; app teknik
> yol haritası `APP_YOL_HARITASI.md`'de kalır (fiyat §7, IP §9 oradaki eski
> notlar — güncel business kararları ARTIK BURADA).

---

## §0 — DURUM ÖZETİ (2026-08-17)

- **Pilot + referans site KESİNLEŞTİ:** Hocanın laboratuvarı (FSM).
  Hoca kendisi söyledi: "artık bunu kur, biz kullanalım."
- **Baykar İLGİSİ:** Hoca Baykar yöneticileriyle görüştü; fikri —
  özellikle uygulama fikrini — çok beğenmişler. **Talep var.**
  Baykar = Türkiye'nin en büyük şirketlerinden; hoca zaten Baykar'a
  drone parçaları basıyor → lab referansı Baykar kapısını açan köprü.
- **Gerçek veri geldi:** Hocanın mühendislerinden biri mail ile veri
  gönderdi. Test tamamen UYGULAMA ÜZERİNDEN yapılacak (mailden çekecek,
  kendisi işleyecek) — manuel kısayol YOK. Sonra sonuçlar karşılaştırılacak.

---

## §1 — AKTİF İŞ LİSTESİ (öncelik sırasıyla)

### P1 — Gelen mail-verisinin uçtan uca UYGULAMA testi 🔴 KRİTİK
- [x] ✅ 2026-08-18: uygulama maili KENDİSİ çekti (gözcü→RAR→adet→not→
      kısıt→onay→koşu; 610 parça 94sn). 4 gerçek kırılma bulunup
      düzeltildi (RAR desteği, "isimli parçadan" kalıbı, altçizgi
      ayrımı, max-hizası) — commit onayı bekliyor.
- [x] ✅ Not→kısıt hattı kanıtlı: "rotasyonları değişmeyecek" → 4 parçaya
      durus_koru, motora `orientation_overrides` olarak geçti
      (`kisit_yonlendirme` telemetri izi). Kabartma VL halüsinasyon
      filtresi de canlı çalıştı.
- [x] ✅ Held-out kaydı: STRATEJI/01_VERI.md §2.1 `fsm610` (bakış #1
      kısıtlı 691,2 / #2 kısıtsız 652,8; NFV-max probu koşuda).
- [ ] Sonuçları referansla karşılaştır + hocaya rapor — **BLOKE: S8
      (referans 284mm tek plaka mı? çubuk duruşu?) cevabı + NFV-max
      probu sonucu bekliyor. Mevcut sonuçlar üretilemez (>600 +
      boşluk<2) — bu haliyle hocaya GÖNDERİLMEZ.**

### P2 — Hoca laboratuvarına KURULUM
- [ ] Kurulum sihirbazı hazırla (hedef: hoca/mühendis kendi başına
      kurabilsin; GPU/cupy oto-algılama zaten planda —
      [[project-app-kurulum-gpu-cupy]]: NVIDIA varsa cupy oto-kur,
      fallback'li).
- [ ] **Kurulumdan ÖNCE kod koruma ŞART** (P4) — memory kuralı:
      "korumasız paket ASLA çıkmaz; lisans planı İLK TESLİMATTAN ÖNCE
      uygulanır." Lab kurulumu = ilk teslimat.
- [ ] Lab makinesinde Ollama + model kurulumu (model seçimi P3'e bağlı).
- [ ] Mail hesabı: lab kurulumu hangi mail kutusunu dinleyecek?
      (bizim Gmail mi, hocanın/labın hesabı mı — App Password/OAuth işi)
- [ ] Topoloji: fabrika-içi TEK sunucu + çok tarayıcı-istemci modeli
      ([[project-dagitim-topolojisi]]) — lab için hangi makine sunucu?
- [x] KARAR (2026-08-18, Eren): **Tailscale kurulumu sihirbaza GÖMÜLÜR**,
      hocadan ekstra adım İSTENMEZ. Kurgu: (1) sihirbazda AÇIK onay
      kutusu (işaretli-gelen: "Uzaktan bakım kanalı kurulsun — önerilir");
      gizli kurulum YOK; (2) tek-kullanımlık + süreli pre-auth key ile
      sessiz kurulum (login ekranı yok); (3) tailnet ACL: lab cihazına
      yalnız Eren'in cihazlarından erişim, lab cihazı tailnet'i görmez;
      (4) P4 pilot mutabakatına "uzaktan bakım/güncelleme erişimi"
      maddesi; (5) kurulum günü ilk iş bağlantı testi — kurum ağı VPN
      kısıtlarsa B planı: geçici AnyDesk ile ilk kurulum.

### P3 — Donanım envanteri + AI model seçimi
- [x] Envanter GELDİ (2026-08-18): lab "işistasyonu" **i9-9940X (14C/28T,
      AVX-512) / 64GB / 3× GTX 1080 8GB** (kart sayısı düzeltmesi 2026-08-21,
      Eren aktarımı: "bir bilgisayarda 3 tane 1080") + Dell Precision 3660
      **i5-12600K (10C) / 32GB / RTX 3070 8GB**. (Bizim referans: RTX 3060
      6GB / 16GB.) **3-kart notu:** tek koşuyu hızlandırmaz (cupy hattı
      tek-GPU; VRAM havuzlanmaz), asıl kazanç proses-başına
      `CUDA_VISIBLE_DEVICES` ile ~3× paralel GPU-işi (çok-seed kapılar /
      M4 kolları / U1 bölümleri / set-paralel) — 64GB RAM ile birleşince
      iş istasyonunun sunucu rolü güçlenir; CUDA kontrolü kart-başına
      doğrulanmalı, süre-metrikli ölçümler yine münhasır (K-57a).
- [x] **DEĞERLENDİRME (2026-08-20):**
      1. **Motor için asıl kazanç RAM: 64GB.** Bizim 16GB'de RAM-guard'a
         takılan her şey (fsm610 pitch-2.0 "22M hücre" uyarısı, K-57b/c
         set-paralel OOM→seri-retry, "RAM<4GB'ken NFV-ağır başlatma"
         kuralı) lab'da rahatlar; set-paralel orkestrasyon (kodda hazır,
         bizde RAM yüzünden hızsız) lab'da GERÇEK hıza dönebilir.
         KARAR-6'nın (NFV-max baz) süre bedeli lab'da bizdekinden küçük.
      2. **GPU:** RTX 3070 8GB > bizim 3060 6GB (hem çip hem VRAM) —
         GPU-ağır NFV işleri için en iyi makine DELL. GTX 1080 8GB
         Pascal: cupy çalışır ama yaşlı mimari; hız orta, VRAM 8GB
         bizim 6GB OOM sınırlarını biraz genişletir. "Süper bilgisayar"
         değil — A1 sınıfı işler için hâlâ küçük.
      3. **Sunucu önerisi: i9-9940X/64GB** (motor RAM+çekirdek-ağır;
         topoloji: tek sunucu + çok istemci), Dell = istemci + GPU-ağır
         yedek. Alternatif tartışılır ama RAM kazancı GPU farkından büyük.
      4. **LLM/VL: mevcut seçim KORUNUR** — qwen2.5:3b + hakem 7b +
         qwen2.5vl her iki makinede rahat (8GB VRAM'de 7b-q4 sığar;
         64GB sistem RAM offload'u da bol). Model büyütme gereksiz;
         istenirse lab'da hakem rolü kalıcı 7b olabilir.
      5. **RİSK/AKSİYON:** (a) **CUDA_PATH/driver kontrolü sihirbaza
         ZORUNLU adım** — bugünkü bulgu: bizim fsm610 koşusu bile
         CUDA-path'siz CPU'da koştu; pilotta aynı tuzak "yavaş" izlenimi
         verir. (b) Kurulum sonrası PARİTE koşusu: 1-2 referans işi lab'da
         koşup bizim sonuçla karşılaştır (RAM-bağımlı dallanma/pitch
         politikası farkı olabilir — determinizm doğrulaması). (c) GTX
         1080 sürücü-EOL yolunda: pilotta sorun değil; premium/donanım-
         dahil paket şartnamesine "min 32GB RAM + 8GB VRAM (Ampere+)"
         yazılsın. (d) 64GB'de pitch/RAM-bütçe parametrelerinin donanımdan
         türediğini doğrula (sabit 16GB varsayımı kalmış olabilir).

### P4 — Kod koruma / lisanslama (ters mühendisliğe karşı)
- [x] **SkillSpector kuruldu (2026-09-01, Eren isteği):** NVIDIA'nın LLM'li kod
      güvenlik/tedarik-zinciri tarayıcısı (v2.11.x; `skillspector scan <dir>`;
      LLM'siz mod `--no-llm`; LLM'li mod için `SKILLSPECTOR_PROVIDER` — Claude
      CLI sağlayıcısı anahtar gerektirmiyor). Kullanım yeri: pilot/lab teslimi
      ÖNCESİ paket + bağımlılık güvenlik taraması (DENETIM_RAPORU hattının aracı).
      İlk duman taraması (src/nesting3d/selection, --no-llm): 19×HIGH SC8 =
      "__pycache__/bytecode pakete girmesin" (geliştirme ağacında normal;
      TESLİM paketinde temizlenecek — lisans/paketleme adımına kural) + 1 TT2.
      LLM'li derin tarama teslim-önü kapıda koşulacak (claude-cli sağlayıcısı
      anahtarsız).
- [ ] `docs/LISANS_UYGULAMA_PLANI.md` UYGULAMAYA ALINIR (plan hazır,
      ertelenmişti — artık tetiklendi: ilk teslimat geldi).
- [x] EULA TASLAĞI YAZILDI (2026-08-18, Eren talebi: "sihirbazda I-agree
      + haklar bizde/yapımcı benim"): `docs/EULA_TASLAK.md` v0.1 —
      FSEK eser sahipliği (Eren Kutlu) + süreli lisans + yasaklar +
      uzaktan-bakım maddesi + kabul-kaydı maddesi. Sihirbaza ZORUNLU
      "Okudum, kabul ediyorum" adımı (kabul logu: tarih+sürüm+makine
      kodu). ⚠️ Yürürlük öncesi AVUKAT incelemesi şart.
- [ ] 3 katman: EULA + süreli lisans (süre dolumu = salt-okunur) +
      Nuitka/Cython derleme ([[project-ip-koruma-lisanslama]]).
- [ ] GERÇEKÇİ BEKLENTİ notu: Python'da %100 kırılamaz koruma yok;
      hedef "ters mühendisliği zahmetli ve yasal olarak riskli" yapmak.
      Kritik algoritma çekirdeği (NFV/kanopi/karar yığını) öncelikli
      derlenecek modüller.
- [ ] Ek güvence seçenekleri (şifreleme dışında) — DEĞERLENDİRİLECEK:
      - Lisans sunucusu / çevrimiçi aktivasyon (telefon-evi telemetri)
      - Kritik çekirdeği HİÇ vermeme: motor bizim sunucuda, lab'a sadece
        istemci (SaaS mimarisi — hoca fikriyle de örtüşüyor, §3)
      - Donanım kilidi (makine parmak izi'ne bağlı lisans)
      - Loglama/watermark: hangi kurulum hangi sonucu üretti izlenebilir
      - Sözleşme: pilot/referans kullanımı için yazılı mutabakat (IP
        bizde kalır, kaynak paylaşılmaz)

### P5 — Uzaktan erişim / uzaktan geliştirme ❓ TASARIM SORUSU
Eren İstanbul'dan ayrılacak; lab'a her zaman gidilemez. Seçenekler:
- **A. Tailscale** (bizde deneyim VAR — kişisel kurulumda çalışıyor):
  lab sunucusuna Tailscale kur → SSH/RDP ile uzaktan bakım + git pull
  ile güncelleme. En düşük maliyet, en hızlı yol. **ÖN-FAVORİ.**
- **B. Kendi bulut sunucumuz (SaaS):** motor bizim sunucuda çalışır,
  lab tarayıcıdan kullanır. Geliştirme tamamen bizde; lab'da kurulum
  derdi biter; IP koruması en güçlü (kod hiç çıkmaz). Maliyet: sunucu
  kirası + GPU; hocanın "bizim server'da çalışsınlar" fikriyle birebir.
- **C. Hibrit:** lab'da on-prem kurulum (P2) + Tailscale bakım kanalı;
  paralelde SaaS altyapısı kurulunca oraya geçiş.
- [ ] KARAR: pilot için C ile başla (hoca "kur" dedi, on-prem bekliyor),
  SaaS'ı §3 fiyatlandırmayla birlikte tasarla. → Eren onayı bekliyor.
- [x] Güncelleme mekanizması KARARI (2026-08-18, Eren gereksinimi:
  "uzaktan bağlanıp değişiklik yapabileyim AMA kodlar hep şifreli
  kalsın"): **PAKETLİ SÜRÜM + updater.** git pull seçeneği ELENDİ
  (kaynağı lab'a koyar, P4'ü bozar). Akış: değişiklik+test Eren
  makinesinde → Nuitka/Cython derlenmiş sürüm paketi → Tailscale
  SSH/RDP ile kur / app-içi güncelle komutu → rollback için önceki
  paket saklanır; veri+config ayrı dizin (güncelleme ezmez). Kaynak
  lab makinesine HİÇ çıkmadığı için koruma her güncellemede otomatik
  sürer. Uzak bağlantı ayrıca bakım içindir (log/config/restart).
- [ ] Updater/paketleme implementasyonu P4 uygulamasıyla birlikte
  (LISANS_UYGULAMA_PLANI'na sürüm-paketi bölümü eklenecek).

### P6 — Uygulama özellik istekleri (hoca/lab, 2026-08-18) 🔶 PİLOT ÖNCESİ
- [x] **Koşu ilerleme göstergesi** ✅ 2026-08-18: her sayfada sağ-alt
      baloncukta TAHMİNİ yüzdeli ilerleme çubuğu (`/api/kosu-ilerleme` +
      `KosuIlerleme` deposu; beklenen süre son koşulardan EWMA ile
      öğrenilir, %97'de doyar — yalan "tamamlandı" yok). 13 yeni test.
      İleri adım (backlog): run_pipeline içine gerçek aşama kancası.
- [x] **Hata bildirimi** ✅ 2026-08-18: koşu düşerse kalıcı kırmızı
      baloncuk ("Koşu hata verdi (kod) — sipariş bekleyenlerde korunur");
      operatör kapatana dek kalır; gözcü (mail) hatası da aynı kanaldan
      yüzeye çıkar. Mail ile bildirim → backlog.
- [x] **Koşu modu seçimi (Eren istegi 2026-08-18)** ✅: aile-yönlendirme
      "auto"da heightmap'e itebiliyor; artık manuel yükleme + kısıt-onay
      ekranında operatör "NFV kalite / Heightmap" zorlayabilir (boş =
      eski davranış birebir). Kalıcı motor çözümü (yönlendirici düzeltmesi)
      → YONTEM §5 K-65, NFV probu kanıtı + dev-set doğrulaması bekler.

- [ ] **Gözcü sayaç/görünürlük düzeltmesi (2026-08-18 gece dersi):**
      onaya PARKLANAN sipariş gözcü panelinde "işlenen" SAYILMIYOR
      (total_processed=0 kalıyor) → operatör "işlemiyor" sanıyor.
      Parklanan işler panelde "işlendi → onay bekliyor" olarak
      görünmeli + gözcü kapalıyken panelde büyük uyarı.
- [ ] **"Maili yeniden işle" butonu (2026-08-18 canlı dersi):** iş
      geçmişinden kayıt silmek maili yeniden İŞLETMEZ (idempotency +
      UID hafızası — bilinçli tasarım). Eren bunu bekledi, olmadı;
      SQL+restart gerekti. Operatöre geçmiş/gözcü ekranında tek tık
      "bu maili yeniden işle" (ilgili idempotency kaydını düşür +
      taze tarama) verilmeli. Ayrıca gözcü durdurulduysa panelde
      BÜYÜK görünür uyarı ("gözcü kapalı") olmalı.

### P4/P5/P6 EKLERİ — Eren istek paketi (2026-08-20, değerlendirilmiş)
- [ ] **(P4) Makine kilidi KARARLAŞTI** (seçenekten karara): lisans makine
      parmak-izine bağlı; kopyalanan kurulum başka makinede AÇILMAZ.
- [ ] **(P4) İhlal-tespit katmanı (tamper/copy detection):** parmak-izi
      uyuşmazlığı + binary/lisans bütünlük hash'i + debugger/inject
      tespiti (best-effort). Kullanıcı arayüzünde SIFIR iz; imzalı gizli
      lokal log; bağlantı varken Eren'e bildirim (Tailscale/telefon-evi),
      offline'sa ilk bağlantıda. GERÇEKÇİ SINIR: caydırıcı katmandır,
      istemci-tarafı tespit kararlı saldırganca kapatılabilir; %100 =
      yalnız SaaS (çekirdek hiç çıkmaz). ⚠️ HUKUKİ ŞART: EULA'ya
      "ihlal-tespit/bildirim telemetrisi" maddesi AÇIKÇA yazılır
      (ekrandan gizli OLUR, sözleşmeden gizli OLMAZ — KVKK/delil
      geçerliliği); avukat inceleme kapsamına eklendi.
- [ ] **(P4-Faz2) Tek-komut sürüm-paket hattı:** kaynak→Nuitka/Cython
      derleme→paket→installer TEK script. Her değişiklik: yeni installer
      (yeni kurulum) + updater paketi (mevcut kurulum; rollback'li,
      veri/config ezilmez). Cevap: "sihirbaza sonradan ekleme" SIKINTISIZ,
      koşulu bu hattın script'leşmesi. Geliştirme AKIŞ NETLİĞİ: kaynak
      müşteri makinesine HİÇBİR senaryoda çıkmaz; Claude Code geliştirmeyi
      BİZİM makinede yapar, uzak makineden yalnız log/telemetri çekilir.
- [ ] **(YENİ, P5-bağlantılı) Veri geri-akış kanalı:** müşteri kurulumundan
      BİZE telemetri/geçmiş-özeti akışı (Tailscale). KATMANLI GİZLİLİK:
      özellik-vektörü + metrik düzeyi (anonim) akar; ham geometri (STL)
      müşteride kalır (savunma müşterisi kısıtı). EULA'da eğitim-kullanım
      RIZASI açık madde. Akan veri B1 kuralıyla held-out/eğitim stoğuna
      girer (registry kayıtlı).
- [ ] **(YENİ, P6) Job-history dönemsel raporu:** müşteriye özet ("bu ay
      X iş, ort. doluluk Y, ort. süre Z") + geliştirici kanalından uzak
      özet çekme.
- [ ] **(YENİ, P6) Auto-mode ONAYLI/ONAYSIZ switch'i:** onaysız seçilirse
      mailden çekilen iş HİÇ onay istemeden işlenir. Default=onaylı.
      Emniyet (onay değil, bilgilendirme): A2-INVALID sonuç onaysız modda
      da kırmızı baloncuk/mail bildirimi üretir, sessiz "tamam" olmaz.
- [ ] **(YENİ, P6) UI SADELEŞTİRME (hoca isteği: "olabildiğince basit"):**
      sekme/özellik envanteri → pilot "basit görünüm" (gereksiz sekmeler
      gizlenir; operatör akışı 3-4 ekran). Envanter çıkarılıp Eren'le
      hangi sekmelerin gizleneceği kararlaştırılır.

### P2b — ALUTEAM ZİYARETİ (2026-08-20: mühendis maili yüz-yüzeye kaydırdı)
- Mühendis (farklı kişi) 6-sorulu maile: "uzun yazmışsın, net cevap yok,
  Aluteam'e gel konuşalım" → İLK plan yüz-yüzeydi; **GÜNCELLEME 2026-08-20
  (Eren): bir süre Aluteam'e GELİNEMEYECEK → süreç UZAKTAN yürür (mail +
  kısa telefon); ziyaret ileride kurulumla birleşir.** Cevap taslağı:
  `MUHENDIS_MAIL_2026-08-20_GOVDE.txt` (ev-ödevi kanıtı + 3 tek-kelimelik
  soru + uzaktan-kanal beyanı; gönderim Eren onayında/eliyle).
- KISA ajanda (uzun liste YOK — ders alındı): (1) 610 parça kaç plana
  bölündü + plan-başına yükseklikler? (2) 399,6 çubuklar hangi planda,
  hangi duruşta? (3) İç-içe/söküm teyidi (rehberli söküm HTML CANLI
  gösterilir). + kurulum sırasında CUDA/parite koşusu (P3 aksiyonları).
- NOT: S2 ZATEN ÖZ-ÖLÇÜMLE KAPANDI (fabbproject: PLAN8, ~126 parça,
  ≥8 plan — HOCA_CEVAPLARI 2026-08-20) → ziyarette yalnız kalan boşluklar.
- İLETİŞİM KURALI (kalıcı): mühendise mail = KISA, tek-konu, madde başına
  1-2 satır; uzun teknik mail HOCAYA da özet + ek olarak gider.

### P7 — Süreç/operasyon
- [ ] Pilot kullanım geri bildirim döngüsü: lab kullanıcıları sorunları
      nasıl bildirecek? (mail/WhatsApp/uygulama-içi "sorun bildir")
- [ ] Referans anlaşması: "FSM lab pilotu" adının pazarlamada
      kullanılabilmesi için hocayla mutabakat.

---

## §2 — NOT→KISIT HATTI DOĞRULAMA LİSTESİ (P1'in "patlayamaz" kısmı)

Mevcut durum: `kisit_modu = "golge"` (configs/llm.local.json:64) —
kısıtlar tespit ediliyor ama plana OTOMATİK uygulanmıyor (Eren onaylı
gölge karar). **Gerçek testte bu bilinçli bir karar noktası:**

- [ ] KARAR: hoca-veri testinde gölge mi kalsın, onay-kapılı aktif mi?
      (Öneri: bildirim + kisit_onay ekranından ONAYLI uygulama — tam
      otomatik değil ama "not dikkate alınmadı" riskini sıfırlar.)
- [ ] Mail gövdesi notları: LLM çıkarımı doğru kısıt türüne map'leniyor mu
      (a2/duruş-kilidi/adet)? Halüsinasyon filtresi devrede mi?
- [ ] Ek/ZIP içi not kanalları: excel adet + teknik resim + gövde adet
      (hoca C6 cevabındaki 2 format) uçtan uca çalışıyor mu?
- [ ] Kabartma (kanal-3, parça-üstü XY etiketi): `kabartma_okuma` config
      açık mı, VL modeli lab donanımında çalışacak mı?
- [ ] Kısıt uygulanınca ÇIKTIDA görünürlük: sonuç ekranı/raporda "şu
      notlar bulundu → şu kısıtlar uygulandı" izi (hocaya kanıt).
- [ ] Negatif test: notsuz mail → sıfır yanlış-pozitif kısıt.
- [ ] Hata dayanıklılığı: LLM/Ollama çökük olsa bile pipeline nesting'i
      bitiriyor mu (kısıtsız + UYARI ile) — sessiz yutma YASAK, patlama
      da YASAK.

---

## §3 — PAZARLAMA / FİYATLANDIRMA MODELLERİ (hoca istişaresi 2026-08-17)

Hocanın önerdiği 3 model — hepsi tasarlanacak, kademe kataloğu çıkacak:

1. **SaaS / Abonelik:** "Gelsinler, bizim server'da çalışsın." Müşteri
   abone olur, motor bizim sunucuda. + IP en korunaklı, güncelleme anlık,
   gelir tekrarlı. − Sunucu/GPU maliyeti, veri gizliliği sorusu (savunma
   sanayi müşterisi STL'ini buluta atar mı? Baykar için muhtemelen HAYIR
   → on-prem premium'a itiş).
2. **Premium on-prem (donanım dahil):** "Donanımı da biz karşılarız,
   daha pahalıya satarız." Anahtar teslim: makine + kurulum + uygulama.
   Savunma/kurumsal için doğru paket (veri içeride kalır).
3. **Alt model (Lite):** Otomasyon yok — mailden çekmez; veri manuel
   yüklenir, algoritma çalışır. Daha ucuz giriş kademesi.

Yapılacaklar:
- [ ] Kademe tablosu: Lite / Standart (on-prem + mail otomasyonu) /
      Premium (donanım dahil) / SaaS — her birinin kapsamı, hedef müşteri
      profili, fiyat bandı (APP_YOL_HARITASI §7 eski taslakla birleştir).
- [ ] Baykar senaryosu: hangi kademe? (tahmin: on-prem premium; savunma
      sanayi veri-dışarı-çıkmaz kuralı) — hoca üzerinden ihtiyaç keşfi.
- [ ] Fiyatlandırma mantığı: kazandırılan yükseklik/süre üzerinden değer
      bazlı anlatı (karne: manuel >1 gün + daha yüksek vs. motor ~103dk
      + %17,9 daha alçak — hoca C5 kanıtı).
- [ ] Şirketleşme/ortaklık: hoca daha önce SaaS+ortaklık sinyali vermişti
      ([[project-konteyner-app-plani]]) — pilot başarılı olunca gündeme.

---

## §4 — AÇIK SORU İŞARETLERİ

| # | Soru | Durum |
|---|------|-------|
| S1 | Uzaktan erişim: Tailscale mi, özel sunucu mu, hibrit mi? | §1-P5 — öneri C, Eren kararı bekliyor |
| S2 | Lab kurulumu hangi mail kutusunu dinleyecek? | Açık |
| S3 | Hoca-veri testinde kısıt modu: gölge mi onay-kapılı mı? | §2 — karar bekliyor |
| S4 | Lab donanımı LLM/VL için yeterli mi? | Fotoğraflar bekleniyor (P3) |
| S5 | Baykar'a hangi paket/kademe? | Keşif — hoca üzerinden |
| S6 | Pilot için yazılı IP/referans mutabakatı gerekiyor mu? | Değerlendirilecek |
| S7 | Süper bilgisayar erişimi SaaS altyapısında kullanılabilir mi? | Fikir — araştırılacak |
| S8 | **"Rotasyonları değişmeyecek" = parçalar OLDUĞU GİBİ yerleştirilecek (Eren teyidi 2026-08-18).** Bizim koşu bu yoruma uygun (çubuklar dik → 691mm). GEOMETRİK ÇELİŞKİ HOCAYA GÖSTERİLECEK: 399,6mm çubuk dik dururken HİÇBİR yerleşim 284mm olamaz → mühendisin 284mm Netfabb referansı bu kısıtı sağlamıyor (çubuklar yatık olmalı). Mühendise nazikçe sorulacak: referans yerleşimde çubuklar hangi duruşta? Kısıt çubuklar için de geçerli mi? | 🔴 MAİL TASLAĞI HAZIRLANACAK |

---

## §5 — KAYIT KURALI

- Her yeni business gelişmesi (müşteri sinyali, hoca istişaresi, fiyat
  fikri, pilot geri bildirimi) TARİHLİ olarak bu dosyaya işlenir.
- Hocanın söyledikleri ayrıca `HOCA_CEVAPLARI.md`'ye (kronolojik kayıt
  kuralı) — burada iş kararına çevrilmiş hali tutulur.
- Teknik iş üretirse (kod/deney) normal disiplin: YONTEM_HARITASI + A11.
