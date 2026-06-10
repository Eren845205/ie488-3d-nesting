# PLAN.md — IE 488 Dönem Projesi · İlk Hafta Prototipi (48 Saat)

> Tek kişilik · 2 günlük aksiyon planı · Aşama 1 (Üretim Planlama / Nesting).
> Çıktı hedefi: hoca toplantısında "çalışan baseline + algoritma kararı + literatür özet" üçlüsünü savunabilmek.
> Bu dosya yalnızca **plan**dır; kod içermez (pseudo-code seviyesinde).

---

## 1. Problem Tanımı

Additive Manufacturing (AM) **nesting** problemi: bir build platformuna (FDM tablası ya da SLM toz yatağı) birden çok parçanın **konum + oryantasyon** olarak yerleştirilmesi; amaç alan/hacim kullanımını maksimize etmek, atığı ve dolaylı olarak baskı süresini düşürmektir. Review (Tang vd. 2025) iki temel sınıf tanımlar:

- **NfAM (Nesting for AM)** — yalnızca yerleştirme: makinaya verilen parça setinin platform üstünde nasıl konumlanacağı.
- **NSfAM (Nesting & Scheduling for AM)** — yerleştirme + zaman çizelgeleme + makina ataması (çok makina, çok iş senaryosu).

Boyut açısından **2D nesting** (parçaların build plate'e izdüşümü; FDM'de çoğunlukla yeterli) ve **3D nesting** (toz yataklı SLM/SLS'de gerçek hacimsel yerleştirme) ayrı problem aileleridir. Bu prototip **NfAM + 2D** kapsamındadır.

Review'in 3 boyutlu sınıflandırma çerçevesi: (i) **image mapping** = parçanın matematiksel temsili, (ii) **nesting strategy** = pure-placement vs integrated, (iii) **optimization algorithm** = constructive heuristic, metaheuristic, exact, vs. Bu prototip her üç eksende de **en sade savunulabilir** seçimi yapar.

---

## 2. Hocanın İsteğini Nasıl Yorumladık

Direktif: "Generic ilk makaleden başla, nesting/3D yerleştirme problemi tasarla & geliştir, en fazla 2 kişilik grup, gelecek hafta sınıfta tartış." Direktiften çıkardığımız maddeler:

- "Generic ilk makale" → Tang vd. 2025 review makalesi (taksonomi + 8-sınıflı E/N × P/I × S/M çerçevesi).
- "Nesting / 3D yerleştirme" → uzun vadede 3D hedef; ancak 2 günde 3D voxel yapmak gerçekçi değil. 2D **izdüşüm** baseline'ı tasarlanır; aynı algoritma iskeleti 3D'ye taşınabilir.
- "Tasarla ve geliştir" → bu hafta = **çalışan minimal prototip + literatür yorumu + algoritma seçimi gerekçesi**. Hoca optimizasyon kalitesi değil yön ve disiplin bekliyor.
- "Sınıfta tartış" → savunmanın 3 ayağı var: ne yaptım, neden bu yöntemi seçtim, sonraki hafta neyi açacağım.

**Yorum sonucu:** 48 saat içinde 3 ana çıktı:
1. Çalışan Python prototipi (2D, 1 constructive heuristic + opsiyonel 2.si),
2. 3-makale derinliğinde literatür notu (review + 1 algoritma + 1 taksonomi),
3. 1-sayfalık savunma özeti (slayt veya PDF).

---

## 3. Literatür Özeti — Minimum Gerekli (3 Makale)

Tüm 8 PDF'i okumak hedef değil; 3 makaleyi savunabilecek kadar okumak hedef.

### M1 — Tang vd. 2025 — "Nesting Problems in Additive Manufacturing: Classification and Review"
- Dosya: `Nesting Problems in Additive Manufacturing - Classification and Review 2025.pdf`
- 75 makaleyi 3 eksende sınıflar: **image mapping** (E-IM = bounding box; N-IM = polygon/raster/voxel/sphere-tree), **nesting** (Pure-placement P vs Integrated I), **scope** (Single S vs Multiple M nesting).
- NfAM vs NSfAM ayrımını netleştirir; AABB (axis-aligned bounding box) en yaygın E-IM ve "en erken / en basit" yöntem olarak tanımlanır.
- Prototip için bağlanma noktası: **E\P\S** kutusu (Extended image mapping / Pure placement / Single platform) — yani AABB + tek build plate + yalnız yerleştirme. Bu kutu literatürde en kalabalık ve en kolay savunulabilir başlangıç noktasıdır.

### M2 — (algoritma makalesi) "Nesting algorithm for optimization part placement in additive manufacturing"
- Dosya: `Nesting algorithm for optimization part placement in additive manufacturing.pdf`
- Hedef okuma: constructive yerleştirme adımı + objective fonksiyonu (alan kullanım yüzdesi, bounding rectangle yüksekliği vb.) + rotation enumeration yaklaşımı.
- Prototip için bağlanma noktası: heuristic'in nasıl deterministik tanımlandığı; sıralama kriteri (alan azalan / en uzun kenar azalan).

### M3 — Araújo vd. taksonomi makalesi: "Analysis of irregular three-dimensional packing problems in additive manufacturing: a new taxonomy and dataset"
- Dosya: `Analysis of irregular three-dimensional packing problems in additive manufacturing  a new taxonomy and dataset.pdf`
- Hedef okuma: 4-boyutlu sınıflandırma çerçevesi (Wäscher / Dyckhoff türevi), AM'e özgü uyarlama, public dataset varsa not al.
- Prototip için bağlanma noktası: gelecek hafta 3D'ye geçerken referans olacak taksonomi; ayrıca test parça setinin neye benzemesi gerektiği konusunda fikir.

**Kapsam dışı (oku ama detaya inme):** voxel-OCCS makalesi, energy-aware SLM scheduling, 3D placement makalesi. Bunlar Aşama 2/3'e ertelendi.

---

## 4. Algoritma Kararı

Aday iki constructive heuristic (her ikisi de E\P\S kutusunda):

### Aday A — Bottom-Left (BL) / Bottom-Left-Fill (BLF)
- Parçayı sol-alttan başlayıp boşluk bulunca yerleştirir; en eski ve en sade nesting heuristic'i.
- Artı: implementasyonu en kısa, görselleştirmesi sezgisel, literatür referansı bol.
- Eksi: alan kullanımı orta seviyede; sıralama girdisine duyarlı.

### Aday B — Best-Fit Decreasing (BFD) (alan-azalan sıralama + en uygun boşluğa yerleştirme)
- Parçalar alan azalan sıralanır; her parça için kalan boş alanlardan **en az artık bırakan** boş kutuya konur.
- Artı: BL'den genelde daha iyi doluluk; "azalan sıralama" kararı net ve savunulabilir.
- Eksi: "boş alan listesi" yönetimi BL'den biraz daha karmaşık (maximal rectangles veya skyline tutmak gerekir).

### Karar
**Birincil = BL/BLF**, **opsiyonel ikinci = BFD** (zaman kalırsa 2. günün son bloğunda karşılaştırma için).
- Gerekçe: 48 saatte garantili teslim için en düşük riskli; BFD eklenirse "iki heuristic karşılaştırması" hocaya somut bir tartışma açar.
- Zaman daralırsa BFD atılır (Bölüm 12 — risk planı).

---

## 5. Parça Temsili (Image Mapping Kararı)

Review'in 3 seçeneği (artan zorluk):

| Seçenek | Zorluk | 2 gün için gerçekçi mi | Savunulabilirlik |
|---|---|---|---|
| AABB (bbox-only) | Düşük | Evet | Yüksek — review'de "en erken, en yaygın" |
| Polygon (N-IM, kenar listesi) | Orta | Riskli (NFP yaklaşımı gerekir) | Yüksek ama 2 gün kısa |
| Raster (piksel grid) | Orta | Mümkün ama görselleştirme + collision daha çetrefilli | Orta |

**Karar: AABB (bbox-only).** Parça = `(width, height)` ikilisi olarak tutulur; rotation izinli ise `(h, w)` da denenir. Bu seçim review'in E-IM dalı + Aşama 1 hedefiyle birebir örtüşür. Polygon/raster Aşama 2 için kapı (Bölüm 14).

---

## 6. Input Formatı

- **Birincil format:** `data/parts.csv` — sütunlar: `id, width_mm, height_mm, qty, rotatable`.
- **Hard-coded test seti:** `data/test_set_small.csv` (8–12 parça) ve `data/test_set_medium.csv` (20–30 parça). Boyutlar rastgele üretilmiş dikdörtgenler (10–80 mm aralığında) — Bölüm 9.
- JSON alternatifi şu an gereksiz; CSV yeterli ve elle düzenlenebilir.

---

## 7. Build Platform Parametreleri

- **Plate boyutu (varsayılan):** 220 × 220 mm (Ender-3 / Prusa MK4 sınıfı FDM yatağı; SLM EOS M290'a ölçeklemek için çarpan değiştirilir).
- **Plate parametresi:** `config/plate.yaml` veya doğrudan komut satırı bayrağı (`--plate-w 220 --plate-h 220`).
- **Rotation:** {0°, 90°} ayrık (yalnız iki yön). 180° ve 270° dikdörtgen için redundant. `rotatable` sütunu False ise sadece 0° denenir.
- **Parça arası boşluk (kenar payı):** sabit 1 mm (parametrik tutulur; FDM gerçekçi minimum).
- **Birim:** mm.

---

## 8. Yüksek Seviye Pseudo-code (İki Heuristic)

### 8.1 Bottom-Left (BL)

```
function bottom_left(parts, plate_w, plate_h):
    sort parts by max(width, height) descending   # uzun kenar azalan
    placements = []
    for part in parts:
        for orientation in allowed_orientations(part):    # {0°, 90°}
            position = find_lowest_leftmost_fit(part, orientation, placements, plate_w, plate_h)
            if position is not None:
                record placement (id, x, y, orientation)
                break
        else:
            mark part as UNPLACED
    return placements, unplaced_list

function find_lowest_leftmost_fit(part, orient, placed, W, H):
    # Aday noktalar = (0,0) + tüm yerleşmiş parçaların sağ-alt ve sol-üst köşeleri
    for candidate in sorted(candidates, by y asc, then x asc):
        if fits(part, candidate, placed, W, H, margin=1mm):
            return candidate
    return None
```

### 8.2 Best-Fit Decreasing (BFD) — opsiyonel

```
function bfd(parts, plate_w, plate_h):
    sort parts by area descending
    free_rects = [ (0,0,plate_w,plate_h) ]    # maximal rectangles listesi
    placements = []
    for part in parts:
        best = None
        for rect in free_rects:
            for orient in allowed_orientations(part):
                if part fits in rect:
                    score = leftover_area(rect, part, orient)   # az olan iyi
                    if best is None or score < best.score:
                        best = (rect, orient, score)
        if best is None:
            mark UNPLACED
        else:
            record placement
            split rect into up-to-2 new free_rects ve free_rects listesini güncelle
    return placements, unplaced_list
```

> Not: Bu pseudo-code'lar tasarım niyetidir; gerçek implementasyonda kenar payı ve sayısal stabilite için epsilon eklenir.

---

## 9. Test / Karşılaştırma Senaryosu

- **Parça setleri:** `small` (10 parça), `medium` (25 parça), `stress` (50 parça). Her set sabit random seed ile üretilir (tekrar-üretilebilirlik).
- **Geometri:** sadece dikdörtgenler (AABB temsili gerektirdiği için yeterli); boyut aralığı 10–80 mm.
- **Çalıştırma:** her algoritma her set için **1 koşu** (heuristic deterministik); rotation on/off karşılaştırması ekstra eksen.
- **Metrikler (tablolanacak):**
  1. **Doluluk oranı (utilization %)** = yerleşen parçaların toplam alanı / plate alanı.
  2. **Atık oranı (waste %)** = 100 - utilization.
  3. **Yerleştirilemeyen parça sayısı (unplaced count)** + bu parçaların toplam alanı.
  4. **Çalışma süresi (wall-clock ms)** — `time.perf_counter` ile.
- **Görsel çıktı:** her senaryo için `results/<algo>_<set>.png` (matplotlib `Rectangle` patch'leri; plate sınırı + parçalar + ID label'leri).
- **Sonuç tablosu:** `results/summary.csv` ve `results/summary.md` (markdown tablosu, hoca özetine direkt yapıştırılabilir).

---

## 10. Klasör Yapısı

```
IE 488 Project/
├── PLAN.md                       (bu dosya)
├── README.md                     (kısa: nedir, nasıl koşulur, sonuç tablosu link)
├── src/
│   ├── __init__.py
│   ├── part.py                   (Part veri sınıfı, AABB)
│   ├── plate.py                  (Plate + collision yardımcıları)
│   ├── bl.py                     (bottom-left heuristic)
│   ├── bfd.py                    (best-fit decreasing — opsiyonel)
│   ├── visualize.py              (matplotlib render)
│   └── run.py                    (CLI: --algo bl|bfd --set small|medium|stress)
├── data/
│   ├── test_set_small.csv
│   ├── test_set_medium.csv
│   └── test_set_stress.csv
├── results/
│   ├── bl_small.png
│   ├── bl_medium.png
│   ├── summary.csv
│   └── summary.md
├── docs/
│   ├── literatur_notu.md         (3 makale özeti — Bölüm 3'ün uzun hali)
│   └── hoca_ozet.md              (1-sayfalık savunma — Bölüm 13)
└── (mevcut PDF'ler ve _extract.py yerlerinde kalır)
```

---

## 11. 48 Saatlik Zaman Çizelgesi (6 Blok)

> Her blok ~6 saatlik dilim (≈ 5 saat aktif iş + 1 saat ara/yemek). 6 blok × 6 saat = 36 saat; geri kalan 12 saat = uyku + tampon (Blok 6 sonrası, Bölüm 11 sonundaki notla aynı).
>
> **Ön karar — KİLİTLENDİ (2026-05-19):** BFD heuristic'i **yapılacak** ve **skyline tabanlı** olarak implement edilecek. Gerekçe: iki heuristic karşılaştırması hocaya somut tartışma malzemesi verir; skyline implementasyonu maximal-rectangles'a göre daha hızlı yazılır (2 gün bütçesine sığar) ve doluluk açısından kabul edilebilir. Blok 4 bu kararla planlanmıştır. **Atılma kuralı yine geçerli** (Bölüm 12): zaman geride giderse BFD tamamen çıkarılır, MVP korunur.

### Blok 1 — Gün 1 Sabah (Saat 0–6) · "Anla + İskelet"
- Hedef:
  - Tang 2025 review'i Bölüm 3 (image mapping) + Bölüm 4 (sınıflandırma) okunmuş, 1 sayfa not (`docs/literatur_notu.md`'nin M1 kısmı).
  - Klasör yapısı kurulu, boş `src/` modülleri + `data/` CSV şeması belirli.
  - `Part`, `Plate` veri sınıfları yazılı (sadece data class düzeyinde, davranış yok).
  - **`data/test_set_small.csv` üretildi** — ya elle (8–12 satır), ya da 5 satırlık tek seferlik scratch script (`numpy.random.seed(42); rastgele dikdörtgenler`). Bu adım atlanırsa Blok 2'nin "Tamam kriteri" kırılır.
- Tamam kriteri: `python -c "from src.part import Part"` import hata vermiyor; literatür notunda M1 paragrafı bitmiş.
- Risk: PDF okuma uzayabilir → 2 saat sertlik koy, oku bırak; tam okuma değil "argüman + figür" tarama.

### Blok 2 — Gün 1 Öğle (Saat 6–12) · "BL Çalışsın"
- Hedef:
  - Bottom-Left heuristic'i `src/bl.py` içinde çalışır halde.
  - `small` test seti üzerinde en az 1 başarılı yerleşim + `results/bl_small.png` görseli.
  - Collision detection birim doğrulaması (3–4 elle yazılmış kenar durumu).
- Tamam kriteri: `python src/run.py --algo bl --set small` doğru görsel üretir; konsola utilization yazdırır.
- Risk: collision bug'ları → AABB-AABB overlap testi en basit haliyle (4 koşul); kompleks geometriye gitme.

### Blok 3 — Gün 1 Akşam (Saat 12–18) · "Metrik + Görsel Cila"
- Hedef:
  - `visualize.py` plate sınırı + parça ID + boş alan vurgusunu basabiliyor.
  - `medium` ve `stress` setleri üzerinde BL koşturulmuş; `summary.csv` yazılıyor.
  - Rotation on/off karşılaştırması (BL için) yapılmış.
- Tamam kriteri: 3 set × 2 rotation modu = 6 satırlık tablo `summary.md` içinde.
- Risk: matplotlib render uzayabilir → label/legend minimal tut, "yeterince güzel" yeterli.

### Blok 4 — Gün 2 Sabah (Saat 18–24) · "BFD (Opsiyonel) veya Konsolidasyon"
- Hedef (eğer Blok 1–3 zamanında bittiyse):
  - Best-Fit Decreasing'i `src/bfd.py`'ye yaz; aynı 3 set × 2 rotation üzerinde koştur.
  - BL vs BFD karşılaştırma grafiği (bar chart, utilization).
- Tamam kriteri: `summary.md` artık 2 algoritma × 3 set × 2 rotation = 12 satır içeriyor.
- Risk: BFD karmaşıklaşırsa **maximal rectangles** yerine **skyline** kullan, ya da bu bloğu Blok 5'e devret.
- **Atılma kuralı:** zaman geride ise BFD tamamen çıkar; bu blok kod kalitesi + edge-case testlerine harcanır.

### Blok 5 — Gün 2 Öğle (Saat 24–30) · "Literatür Notu Bitir + M2 + M3"
- Hedef:
  - M2 (algoritma makalesi) ve M3 (taksonomi) için her biri 3–5 cümlelik özet `docs/literatur_notu.md`'ye eklendi.
  - Her özetin sonunda **"prototipe yansıması"** alt-maddesi var (algoritma seçimine etkisi).
- Tamam kriteri: literatür notu 3 makale × ortalama yarım sayfa = ~1.5 sayfa, kaynak metadata (yazar, yıl, dergi) doğru.
- Risk: M2/M3'te derin matematiğe girme; argüman + sonuç tablosu + bizi neyle bağladığı yeterli.

### Blok 6 — Gün 2 Akşam (Saat 30–36) · "Savunma Özeti + Demo Provası"
- Hedef:
  - `docs/hoca_ozet.md` — 1 sayfalık özet (Bölüm 13'ün yapısı).
  - README.md yazımı (5–10 satır: nedir, nasıl koşulur, sonuçlar linki).
  - Canlı demo provası: laptop'ta `python src/run.py --algo bl --set medium` 2 dakikada koşuyor, görsel açılıyor, summary tablosu gösteriliyor.
  - Final commit + (varsa) git push.
- Tamam kriteri: Hoca toplantısında açılacak 3 dosya hazır → `hoca_ozet.md`, `summary.md`, `results/bl_medium.png`. Demo komutu tek satır.
- Risk: son anda bug bulursan → rollback için git history kullan; "çalışan eski sürümü göster" her zaman B planı.

> Saat 36–48 = tampon (uyku, son okuma, sunuma çalışma, beklenmedik hata). Bu tampon eritilmez; "ekstra özellik" eklemek için kullanılmaz.

---

## 12. Risk & Kesinti Planı — MVP Tanımı

### MVP (Minimum Viable Product) — kesin teslim
1. `src/bl.py` çalışır (Bottom-Left, AABB, rotation 0°/90°).
2. `data/test_set_small.csv` + `data/test_set_medium.csv` mevcut.
3. `results/bl_small.png` + `results/bl_medium.png` + 1 satırlık `summary.csv` (utilization + unplaced + time).
4. `docs/literatur_notu.md` — sadece M1 (review) özeti tamamlanmış.
5. `docs/hoca_ozet.md` — 3 maddelik (ne, nasıl, sonraki adım).

Bu beşi yoksa hocaya gidilmez. Geri kalan her şey "bonus".

### Atılma sırası (zaman daralırsa, ilk atılan en üstte)
1. **BFD heuristic** (Blok 4) — tamamen çıkarılır, "kapsam dışı / sonraki hafta" diye işaretlenir.
2. **`stress` test seti (50 parça)** — sadece small + medium yeter.
3. **Rotation on/off ikilemesi** — sadece rotation-on koşulur, off koşusu atlanır.
4. **M3 (taksonomi makalesi) özeti** — literatür notu 2 makaleyle bırakılır; M3 "okudum ama özetlemeye vakit kalmadı" diye dürüst not düşülür.
5. **Görsel cila** (label/legend/renk paleti) — siyah-beyaz minimum render yeter.

### Bilinen riskler ve karşılık
- **Collision bug** → AABB overlap testi tek satırlık formül (`not (a.right<=b.left or a.left>=b.right or ...)`); pseudo-code'a sadık kal.
- **Floating-point edge case** (parça plate'in tam sınırında) → 0.001 mm epsilon ekle; üstüne düşme.
- **CSV encoding (Türkçe karakter)** → utf-8 zorla, ID'lerde Türkçe karakter kullanma.
- **OneDrive senkron çakışması** → sık commit + ara ara `git status`; klasör adı boşluk içerdiği için path'leri tırnakla.

---

## 13. Hocaya Gösterilecek 1-Sayfalık Özet — İçerik Şablonu

`docs/hoca_ozet.md` aşağıdaki 3 madde + 1 görsel + 1 tablo içerir:

1. **Ne yaptım** — 2D AM nesting baseline'ı kurdum: AABB image mapping + Bottom-Left constructive heuristic + 220×220 mm FDM plate + rotation {0°, 90°}. Tang vd. 2025'in **E\P\S kutusu**na denk düşüyor.
2. **Nasıl yaptım** — Python, 3 modül (`part`, `plate`, `bl`), matplotlib görsel. Test setleri: 10 ve 25 parça. Metrikler: doluluk %, atık %, yerleştirilemeyen parça, çalışma süresi. (Tablo + 1 görsel buraya).
3. **Sonraki hafta nereye götürürüm** — şu üç yönden hangisini hoca isterse: (a) ikinci heuristic (BFD) + karşılaştırma, (b) polygon image mapping (N-IM) ve NFP'ye geçiş, (c) 3D voxel temsile sıçrayış (Araújo taksonomisi + voxel-OCCS makalesi).

**Saklama hatırlatması:** özet dosyası hoca toplantısı *öncesi* PDF'e basılsın (renderlanmış matplotlib görseliyle); dijital bir oynaklığa düşmemek için.

---

## 14. Sonraki Adımlar (Bu Prototipten Sonra) — Kapsam Dışı, İleriye Bırakıldı

Hocaya da bu liste söyleneceği için açık tutuluyor.

### Aşama 1 devamı (önümüzdeki hafta)
- **BFD ekleme** + BL ile karşılaştırma (bu hafta atılırsa).
- **Metaheuristic** — Simulated Annealing veya Genetic Algorithm wrapper'ı: parça sıralamasını değişken haline getirip BL'yi inner-loop olarak kullan.
- **Polygon image mapping (N-IM)** — düz dikdörtgenden kurtulup gerçek 2D kontur; No-Fit-Polygon (NFP) ile collision.

### Aşama 2 (Üretime Hazırlama Lab'i)
- 2D'den **3D**'ye geçiş: voxel grid temsili + height-map yaklaşımı (Tang review §3.2 N-IM 3D dalı).
- Lab'daki gerçek FDM/SLM build hacmine kalibrasyon.

### Aşama 3 (Üretim Lab'i)
- Gerçek baskı: heuristic çıktısının G-code/slicer'a aktarımı (örn. Cura plate placement).
- Termal interferans / support volume gibi AM-özgü kısıtlar.

### Aşama 4 (Üretim Sonrası)
- Baskı sonrası fire ölçümü vs heuristic'in tahmin ettiği "waste %" karşılaştırması — heuristic'in geri-kalibrasyonu.

### Aşama 5 (Veri Çıkarımı)
- Tüm aşamalardan toplanan veri ile heuristic seçim politikası öğren: parça setinin istatistiğine göre BL mi BFD mi metaheuristic mi seçileceğine karar verecek bir "meta-policy" katmanı.

---

## Ek — Kullanılacak Komutlar (Referans, Kod Değil)

> Bunlar prototipte _çağrılacak_ komutlardır; bu plan bunları üretmez, sadece beklenir.

- `python src/run.py --algo bl --set small --plate-w 220 --plate-h 220 --rotate on`
- `python src/run.py --algo bl --set medium --rotate off`
- `python src/run.py --algo bfd --set medium`  (eğer Blok 4 tamamlandıysa)
- `python _extract.py "<pdf-path>"`  (gerek olursa M2/M3 PDF'lerini metne çevirmek için)

---

**Plan sonu.** Bu dosya bir taahhüttür: MVP tanımı (Bölüm 12) tutulmazsa hoca toplantısına gidilmez; tutulursa BFD/2. heuristic eksik olsa bile savunma yapılabilir.
