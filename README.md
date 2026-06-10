# IE 488 — AM Nesting Projesi

2D Additive Manufacturing nesting: AABB image mapping + Bottom-Left ve Best-Fit Decreasing constructive heuristic'leri (baseline) + **Simulated Annealing optimizasyon katmani** (katki), 220x220 mm FDM tablasi, rotation {0 derece, 90 derece}. Tang vd. 2025 review'inin E\P\S kutusuna denk duser.

SA, parca yerlestirme sirasini optimize ederek baseline'in en iyisini kisitli setlerde gecer: **medium 86.90% -> 90.88% (+3.99 puan)**, **stress 82.66% -> 91.65% (+8.99 puan)**. Ayrintilar: `docs/rapor.md`.

## Asama 2 — 3D Voxel Nesting (hoca direktifi 2026-06-09)

2D iskeletin 3D'ye tasinmis hali (`src/nesting3d/`, plan: `PLAN_3D.md`): 3 karmasik STL model (sandalye x10, braket x5, halka x15) **voxelize** edilir, hacim-azalan sirayla **DBLF** (deepest-bottom-left-fill, heightmap) ile sabit tabanli + yuksekligi minimize edilen kutuya yerlestirilir, **SA** sira+oryantasyon uzayinda arar, sonuc **tek STL** olarak disari verilir.

Sonuclar (pitch 3.44 mm, 64x64 taban grid): **default** (30 parca) DBLF 44.7 mm — SA dogruluyor (baseline bu cozunurlukte optimuma yakin); **stress** (42 parca) DBLF 58.4 mm -> SA **55.0 mm (-3.4 mm)**, density 0.387 -> 0.406. Tablo: `results/summary_3d.md`.

## Hizli demo (kod bilmeden)

Proje klasorundeki bat dosyalarina **cift tikla**:
- `DEMO_BASLAT.bat` — 2D baseline'i calistirir, yerlesim + karsilastirma gorsellerini acar.
- `DEMO_OPTIMIZASYON.bat` — 2D SA optimizasyonunu canli calistirir (~3 sn), once/sonra gorsellerini acar.
- `DEMO_3D.bat` — 3D pipeline'i iki senaryoda calistirir (~1 dk), yerlesim gorselleri + STL ciktilarini uretir.

## Kurulum

```
pip install numpy matplotlib pytest trimesh
```

## Kullanim

Tek algoritma kosusu:
```
python src/run.py --algo bl --set medium
```

Simulated Annealing optimizasyonu (tek set, canli):
```
python src/run_sa.py --set medium
```

Tum baseline senaryolarini benchmark et (12 senaryo, summary.csv + PNG'ler):
```
python src/bench.py
```

Baseline vs SA karsilastirmasi (meta_summary + karsilastirma/yakinsama grafikleri):
```
python src/bench_meta.py
```

3D pipeline (once bir kez `python scripts/generate_models.py`):
```
python -m src.nesting3d.run3d --scenario all --export-stl
```

Testleri calistir (72 test: 47 2D + 25 3D):
```
python -m pytest
```

`--algo` secenekleri (2D): `bl`, `bfd`
`--set` secenekleri (2D): `small` (10 parca), `medium` (25 parca), `stress` (50 parca)
`--rotation` bayragi (2D): `on` (varsayilan), `off`
`--scenario` secenekleri (3D): `default` (30 parca), `stress` (42 parca), `all`

## Sonuclar

- `results/summary.md` — 12 baseline senaryosunun tablosu (2D)
- `results/meta_summary.md` — baseline vs SA karsilastirma tablosu (2D)
- `results/comparison_bar.png` — BL vs BFD bar grafigi
- `results/comparison_with_sa.png` — BL vs BFD vs SA bar grafigi
- `results/sa_convergence.png` — SA yakinsama egrisi (2D)
- `results/summary_3d.md` — 3D DBLF vs SA tablosu
- `results/nesting3d_*.png` — 3D yerlesim gorselleri
- `results/nesting3d_result_*.stl` — yerlesmis sahnenin STL ciktisi
- `results/sa3d_convergence_*.png` — 3D SA yakinsama egrileri
- `results/*.png` — her senaryo icin yerlesim gorseli

## Dokumantasyon

- `docs/rapor.md` — final raporu (yontem + sonuclar + tartisma)
- `docs/hoca_ozet.md` — 1 sayfalik savunma ozeti
- `docs/literatur_notu.md` — M1 Tang 2025, M2 Calabrese 2022, M3 Araujo 2019 notlari
- `PLAN.md` — 14 baslikli proje plani ve algoritma kararlari (Asama 1, 2D)
- `PLAN_3D.md` — 3D voxel nesting fazinin plani ve tasarim kararlari (Asama 2)
