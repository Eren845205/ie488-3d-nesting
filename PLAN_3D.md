# PLAN_3D.md — IE 488 · Aşama 2: 3D Voxel Nesting

> 2D prototipin (BL + BFD + SA, `src/` altında) üzerine, hoca direktifi doğrultusunda 3D faz.
> Direktif kaynağı: `WhatsApp Image 2026-06-09 at 21.28.07.jpeg` (el yazısı not, 2026-06-09 toplantısı).
> Bu dosya yalnızca **plan**dır; kod içermez. Mevcut 2D koda **dokunulmaz** — tüm yeni iş `src/nesting3d/` altında.

---

## 1. Hoca Direktifinin Yorumu

Nottaki pipeline: **3D complex form (3D mesh) → voxelization → order → yerleştirme → .STL**

| Nottaki öğe | Yorum |
|---|---|
| `M.Bin`, tabanı sabit, yüksekliği kesikli + "en iyiyi indir" | Taban sabit, **yükseklik minimize** edilecek → 3D strip packing (open-dimension, literatürde ODP/3D-SPP) |
| Üç şekil, `×10 / ×5 / ×15` | **3 farklı karmaşık model**, sabit adetlerle (toplam 30 parça) |
| "3D Complex form (3D Mesh)" + sandalye çizimi | Basit prizma değil; içbükeyliği olan gerçek mesh'ler (STL) |
| "Voxilatation" | Mesh → voxel grid. 2D'deki AABB/raster yaklaşımının 3D karşılığı; collision check grid üzerinde |
| "Order" | Parça sıralama (2D BFD'deki alan-azalanın 3D'si: **hacim-azalan**) + sıralı yerleştirme |
| ".STL" | Sonuç yerleşimin tek STL sahnesi olarak export'u |

2D'deki mimari birebir genellenir: **constructive baseline (DBLF) + SA iyileştirme**. Tang 2025 taksonomisinde bu, N-IM (voxel) / Pure-placement / Single kutusuna geçiş demektir — sunumda "E\P\S'den N\P\S'ye yükseldik" diye çerçevelenir.

---

## 2. Tasarım Kararları (kilitli)

1. **Kütüphane: `trimesh`** (+ `numpy`, mevcut `matplotlib`). Yükleme, voxelization (`mesh.voxelized(pitch)`), transform ve STL export tek pakette. Render için `pyglet` istemez — görselleştirme matplotlib `voxels`/3D ile yapılır.
2. **Modeller: prosedürel üretim, internete bağımlılık yok.** `scripts/generate_models.py` trimesh primitive + boolean birleşimleriyle 3 karmaşık model üretip `data/models/*.stl`'e yazar:
   - `chair.stl` — sandalye (hocanın çizdiği örnek; 4 ayak + oturak + sırt, içbükey) → **×10**
   - `bracket.stl` — L-braket (delikli, asimetrik) → **×5**
   - `ring.stl` — halka/torus benzeri parça (boşluklu) → **×15**
   Kullanıcı isterse herhangi bir STL'i aynı klasöre koyup CLI'dan seçebilir — pipeline model-bağımsız.
3. **Bin: 220 × 220 mm taban** (2D plate ile aynı, tutarlılık), yükseklik serbest. Voxel pitch parametrik; varsayılan **pitch = 220/64 ≈ 3.4 mm** → taban grid'i 64×64. Modeller en uzun kenarı 40–80 mm olacak şekilde ölçeklenir (parça başına ~12–24 voxel kenar).
4. **Yerleştirme temsili: heightmap-tabanlı DBLF.** Bin için 2D yükseklik haritası (`H[x,y]`), her parça oryantasyonu için alt-profil (`bottom[x,y]`) ve üst-profil (`top[x,y]`) tutulur. Bir (x,y) konumunda iniş yüksekliği `z = max(H[x+i, y+j] − bottom[i,j])` formülüyle O(parça tabanı) sürede bulunur; yerleştirme sonrası `H` üst-profille güncellenir.
   **Bilinen ve kabul edilen sınırlama:** heightmap, çıkıntı altı boşluklara (cavity) parça sokamaz — sunumda dürüstçe söylenir ("tam 3D voxel collision Aşama 3 kapısı"). Karşılığında SA iterasyonları makul sürede koşar.
5. **Rotasyonlar: 4 eksen-hizalı oryantasyon** — z ekseni etrafında {0°, 90°} × yatırma {dik, yan}. 24 tam rotasyon değil; gerekçe: AM'de parça stabilitesi + arama uzayını küçük tutmak. Parametrik bırakılır.
6. **Amaç fonksiyonu:** birincil `max_height` (kullanılan en yüksek voxel katmanı, mm), eşitlik bozucu `packing_density` (parça voxel hacmi / kullanılan zarf hacmi). 2D'deki utilization mantığının open-dimension karşılığı.
7. **SA: 2D `metaheuristic.py` deseni kopyalanır,** decode = DBLF. Komşuluk: sıra swap (2D'dekiyle aynı) + rastgele bir parçanın oryantasyon flip'i. Soğutma parametreleri 2D'den miras alınıp kalibre edilir.
8. **Parça arası boşluk:** voxelization'da 1 voxel dilation opsiyonu (`--margin 1`) — 2D'deki 1 mm kenar payının karşılığı.

---

## 3. Klasör Yapısı ve Modüller

```
src/nesting3d/
├── __init__.py
├── models.py        # STL yükleme + ölçekleme
├── voxelize.py      # mesh → VoxelPart (oryantasyon profilleri dahil)
├── bin3d.py         # Bin3D: heightmap, yerleştirme kaydı, metrikler
├── dblf.py          # DBLF constructive baseline
├── sa3d.py          # SA wrapper (decode = dblf)
├── export_stl.py    # yerleşimi orijinal mesh'lerle tek STL'e bas
├── visualize3d.py   # matplotlib 3D render (voxel + bin sınırı)
└── run3d.py         # CLI
scripts/generate_models.py   # 3 prosedürel STL üret → data/models/
data/models/                 # chair.stl, bracket.stl, ring.stl
tests/test_voxelize.py, test_dblf.py, test_sa3d.py, test_export3d.py
results/  (dblf_*.png, sa3d_*.png, nesting3d_result.stl, summary_3d.csv/.md, sa3d_convergence.png)
DEMO_3D.bat
```

### Fonksiyon imzası seviyesinde tasarım

```
# models.py
load_model(stl_path, target_max_dim_mm) -> trimesh.Trimesh        # yükle + ölçekle + origine taşı
default_model_set() -> list[(name, mesh, qty)]                    # (chair,10) (bracket,5) (ring,15)

# voxelize.py
@dataclass VoxelPart:
    id: str; name: str; mesh: trimesh.Trimesh
    orientations: list[Orientation]    # her biri: rot_matrix, grid (bool 3D), bottom[x,y], top[x,y], footprint
    volume_voxels: int
voxelize_part(name, mesh, pitch, n_orientations=4, margin=0) -> VoxelPart
expand_quantities(model_set, pitch) -> list[VoxelPart]            # qty kadar id'lendirerek çoğalt (2D loader._qty_suffixes deseni)

# bin3d.py
@dataclass Placement3D: part_id, x, y, z, orientation_idx
class Bin3D:
    __init__(self, plate_w_mm, plate_d_mm, pitch)
    drop_z(self, orient, x, y) -> int                             # heightmap formülü
    place(self, part, orient_idx, x, y) -> Placement3D            # H güncelle + kayıt
    max_height_mm(self) -> float
    packing_density(self) -> float

# dblf.py
dblf(parts: list[VoxelPart], bin3d_factory) -> (placements, bin3d)
    # sıralama: volume_voxels azalan ("Order" adımı)
    # konum taraması: tüm (x,y) için drop_z; en küçük (z, y, x) seçilir; oryantasyonlar arasında en iyi
score(placements, bin3d) -> (max_height_mm, -packing_density)     # lexicographic amaç

# sa3d.py
@dataclass SA3DResult: best_placements, best_height_mm, baseline_height_mm, history, ...
simulated_annealing_3d(parts, bin_factory, iters, T0, cooling, seed) -> SA3DResult
    # komşuluk: swap(i,j) | orientation_flip(i); kabul: Metropolis (2D metaheuristic.py ile aynı iskelet)

# export_stl.py
export_scene(placements, voxel_parts, out_path) -> Path
    # her placement: orijinal mesh'e rot_matrix + (x,y,z)*pitch translasyonu uygula; trimesh.util.concatenate → tek STL

# run3d.py CLI
python -m src.nesting3d.run3d --algo dblf|sa --models default --pitch 3.4 --rotations 4 --seed 42
    # çıktılar: konsol metrikleri + results/ görselleri + summary_3d.csv/.md + (--export-stl ile) STL
```

---

## 4. Test Planı (pytest, mevcut kültürle aynı)

| Dosya | Kapsam |
|---|---|
| `test_voxelize.py` | grid boş değil; volume_voxels > 0; bottom/top profilleri grid ile tutarlı; margin=1 dilation hacmi artırır; 4 oryantasyon birbirinden farklı footprint verebilir |
| `test_dblf.py` | tek küp parça (0,0,0)'a iner; ikinci özdeş küp z=0'da yana konur (üst üste binmez — **no-overlap invariantı heightmap tutarlılığıyla**); taban sınırı aşılmaz; hacim-azalan sıra doğrulanır; deterministiklik (aynı girdi → aynı çıktı) |
| `test_sa3d.py` | SA sonucu baseline'dan **kötü olamaz** (best-so-far korunur, 2D'deki garantiyle aynı); seed sabitken tekrar-üretilebilir; history monoton-azalan best içerir |
| `test_export3d.py` | STL dosyası oluşur, yüklenebilir (`trimesh.load`), parça sayısı × mesh hacmi toplamı ≈ sahne hacmi (tolerans %1); yerleştirilen mesh'ler bin tabanı dışına taşmaz |

Hedef: ~20–25 yeni test; mevcut 47 test kırılmadan geçer (2D'ye dokunulmadığının kanıtı).

---

## 5. Demo Script — `DEMO_3D.bat`

`DEMO_BASLAT.bat` deseniyle:
1. `python scripts/generate_models.py` (modeller yoksa üret)
2. `python -m src.nesting3d.run3d --algo sa --export-stl` (içinde önce DBLF baseline koşar, SA iyileştirir, ikisini de raporlar)
3. `start results\sa3d_result.png` + `start results\sa3d_convergence.png`
4. Konsolda tablo: DBLF yüksekliği vs SA yüksekliği (mm) + density + süre
5. `results\nesting3d_result.stl` yolu ekrana yazılır — hoca isterse herhangi bir STL viewer/slicer'da açılır (Windows 3D Viewer dahil)

---

## 6. Kabul Kriterleri

1. `pip install trimesh` sonrası `DEMO_3D.bat` tek tıkla, temiz makinede hatasız koşar (< ~3 dk).
2. 30 parça (10+5+15) yerleşir, hiçbiri UNPLACED değil (taban yeterli; yükseklik serbest olduğu için her parça sığar — sığmıyorsa bug).
3. SA yüksekliği ≤ DBLF yüksekliği (en az eşit; medium-benzeri kazanç beklenir, 2D'deki gibi dürüst raporlanır).
4. `nesting3d_result.stl` üretilir ve dış araçta açılır.
5. Tüm testler (eski 47 + yeni ~20) geçer.
6. `results/summary_3d.md` — DBLF vs SA × (rotasyon 1/4) tablosu, sunuma yapıştırılabilir.

---

## 7. İş Sırası (5 blok)

1. **Modeller + Voxelization** — `generate_models.py`, `models.py`, `voxelize.py` + testleri. Tamam kriteri: 3 STL üretildi, voxel grid'leri ve profilleri testlerden geçiyor.
2. **Bin3D + DBLF baseline** — heightmap, drop_z, dblf + testleri. Tamam kriteri: 30 parça yerleşiyor, `dblf_result.png` üretiliyor, yükseklik konsola yazılıyor.
3. **SA** — `sa3d.py` (2D iskeletten port) + kalibrasyon + testleri. Tamam kriteri: SA ≤ DBLF, convergence grafiği var.
4. **STL export + görsel cila** — `export_stl.py`, `visualize3d.py` final hali + testleri. Tamam kriteri: STL dış viewer'da açılıyor.
5. **Demo + özet** — `DEMO_3D.bat`, `summary_3d.md`, README'ye 3D bölümü, sunum güncellemesi.

### Atılma sırası (zaman daralırsa)
1. Rotasyon sayısı 4 → 1 (sadece orijinal duruş)
2. `--margin` dilation opsiyonu
3. Matplotlib 3D görsel cilası (voxel render ağırsa basit scatter/bar)
4. SA kalibrasyon turu (2D parametreleri olduğu gibi kullan)

**MVP = Blok 1+2+4**: voxelization + DBLF + STL export. SA olmadan da pipeline hocanın çizdiği okun tamamını kapatır; SA, 2D'deki hikâyenin devamı olarak en güçlü "bonus".

### Riskler
- **trimesh voxelization yavaşlığı / kaba pitch'te boş grid** → pitch'i parça başına min 10 voxel kenar verecek şekilde doğrula; `voxelized().fill()` ile içi dolu grid kullan (yüzey-only grid hacim metriklerini bozar).
- **Boolean union (model üretimi) kırılgan** → `manifold3d` backend'i yoksa modeli union'sız, parçaları kesişen kompozit mesh olarak bırak (voxelization yine doğru çalışır).
- **64×64 tabanda DBLF taraması × SA iterasyonu pahalı** → drop_z'yi numpy sliding-window ile vektörize et; yetmezse SA iterasyon sayısını düşür ve dürüstçe raporla.
- **OneDrive + büyük STL** → results STL'i tek dosya tut (~birkaç MB), git'e ekle.

---

**Plan sonu.** Bölüm 6'daki 6 kriter tutmadan sunuma gidilmez; tutarsa hikâye "2D'de kurduğumuz iskeleti (constructive + SA) hocanın çizdiği 3D pipeline'a taşıdık" cümlesiyle kapanır.
