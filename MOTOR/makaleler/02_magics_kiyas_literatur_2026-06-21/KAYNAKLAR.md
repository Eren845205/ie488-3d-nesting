# Kaynaklar — Magics Kıyası Literatür Turu (2026-06-21)

> Deep-research turu: 22 kaynak çekildi, 106 iddia, 25 çekişmeli doğrulama
> (24 onaylı / 1 çürütüldü). Tümü peer-reviewed veya tanınmış araştırma grubu.
> Sentez: [SENTEZ_RAPORU.md](SENTEZ_RAPORU.md). Yol haritası: repo kökü
> `PLAN_IYILESTIRME_YOLHARITASI.md`.
>
> Amaç: bizim 3B nesting motorunun Magics'e göre kalite (621 vs 492 = 1.26×,
> doluluk %8) ve hız (Plan2 78dk) açığını kapatacak akademik yöntemleri belgelemek.
> **Hocaya gösterilebilir + ileride "hangi tekniği nereden aldık" izi.**

---

## A. İNDİRİLEN PDF'ler (`pdf/`, açık erişim, doğrulandı)

| Dosya | Künye | Motora karşılığı (yol haritası fazı) |
|---|---|---|
| `EJOR2018_Romanova_quasi-phi_concave-polyhedra.pdf` | Romanova, Bennell, Stoyan, Pankratov (2018), *European Journal of Operational Research* 268(1):37-53. "Packing of concave polyhedra with continuous rotations using nonlinear optimisation." | **Faz 3 (K1)** — quasi-phi-function NLP + COMPOLY compaction. %16-28 iyileşme. ANA KAYNAK. |
| `SFF2015_Araujo_AM-nesting-DBLF-review.pdf` | Araujo, Özcan, Atkin, Baumers, Tuck (2015), *Solid Freeform Fabrication Symposium* (Nottingham OR). AM nesting yöntemleri + DBLF limitleri + NFP+GLS + octree (Cagan) + Ikonen GA + Gogate-Pande referansları. | **Faz 1/2/4** — DBLF zayıflığı teyidi, octree (H2), cavity-aware (K3), kaba-rotasyon gap teyidi. |
| `NVIDIA2010_Laine_efficient-sparse-voxel-octrees.pdf` | Laine, Karras (2010), *NVIDIA Research / I3D*. "Efficient Sparse Voxel Octrees." | **Faz 1 (H2)** — seyrek voxel/octree veri yapısı, bellek+hız. |

---

## B. DERGİ-ERİŞİMLİ (paywall — DOI ile, künye doğrulandı)

> Açık-erişim PDF'i bulunamadı (publisher 403/paywall). Abstract'lar bağımsız arama +
> yazar preprint ile verbatim doğrulandı. Gerekirse üniversite erişimiyle indirilebilir.

| Künye | DOI / Erişim | Motora karşılığı |
|---|---|---|
| Lamas-Fernandez, Bennell, Martinez-Sykora (2022), *Operations Research* (INFORMS). "Voxel-Based Solution Approaches to the Three-Dimensional Irregular Packing Problem." | 10.1287/opre.2022.2260 | **Faz 1 (H2)** — Nofit-Voxel (NFV) primitifi. KRİTİK hız kaynağı. (Not: sabit yönelim.) |
| Ma, Chen, Hu, Wang (2018), *Computer Graphics Forum* 37(5):49-59 (Eurographics SGP, HKU). "Packing Irregular Objects in 3D Space via Hybrid Optimization." | 10.1111/cgf.13490 | **Faz 2 (K2)** — sürekli konum+yönelim optimizasyonu (coarse-to-fine rotasyon). |
| Araujo, Panesar et al. (2020), *International Journal of Production Research* 58(22):6917-6933. (DBLF+GA, AM nesting; rotasyon-hız gerilimi.) | 10.1080/00207543.2019.1686187 | **Faz 2 caveat** — envelope-primitif > algoritma seçimi bulgusu; rotasyon tek kol değil. |
| Litvinchev, Pankratov, Romanova (2019), *IFAC-PapersOnLine* 52-13. (AM min-HEIGHT phi-function NLP, sürekli rotasyon.) | 10.1016/j.ifacol.2019.11.526 | **Faz 3 (K1)** — build-HEIGHT minimizasyon formülasyonu (EJOR min-hacim yerine). |
| Oh, Witherell, Lu, Sprock (2020), *Additive Manufacturing* Vol 36 (NIST, Elsevier). "Nesting and Scheduling Problems for AM: A Taxonomy and Review." | 10.1016/j.addma.2020.101492 | **Çerçeve** — AM nesting taksonomisi; problemi konumlandırma (NfAM sınıfı). |
| Stoyan, Pankratov, Romanova (2016), *Journal of the Operational Research Society* 67(5):786-800. (Quasi-phi-functions, 2D/3D sürekli rotasyon+öteleme.) | 10.1057/jors.2015.94 | **Faz 3 (K1)** — quasi-phi analitik tanım temeli. |
| Stoyan, Pankratov, Romanova (2016), *Journal of Global Optimization*. (Ellipsoid paketleme, radical-free quasi-phi → NLP.) | 10.1007/s10898-015-0331-2 | **Faz 3 (K1)** — radical-free quasi-phi → NLP indirgeme. |
| Cagan, Degentesh, Yin (1998), *Computer-Aided Design* 30(10):781-790. (3D component layout, SA + octree çakışma.) | 10.1016/S0010-4485(98)00036-X | **Faz 1 (H2)** — octree hiyerarşik çakışma testi. (Araujo 2015 içinden.) |
| Ikonen, Biles, Kumar, Wissel, Ragade (1997), *ICGA*. "A genetic algorithm for packing three-dimensional non-convex objects having cavities and holes." | ICGA 1997 | **Faz 4 (K3)** — cavity/part-in-part yerleşim, gerçek-3B çakışma. (Araujo 2015 içinden.) |
| Gogate, Pande (2008), *International Journal of Production Research* 46(20). (Voxel bottom-left, 45° artışla 8 yönelim.) | IJPR 46(20) 2008 | **Bonus** — kaba-rotasyon gap'inin paylaşılan olduğu teyidi. (Araujo 2015 içinden.) |
| HAPE3D — "a new constructive algorithm for the 3D irregular packing problem." | ResearchGate 276460677 | Ek referans — constructive 3D packing. |

---

## C. ÇÜRÜTÜLEN İDDİA (kayıt için — yöntem güvenilirliği)

> Çekişmeli doğrulamada **0-3 ile çürütüldü** (yöntemin yanlış iddiayı elemesi):

- ~~"Daha yüksek rotasyon serbestliği yoğunlukta yalnız KÜÇÜK iyileşme sağlar, ek
  hesap maliyeti ince rotasyonu caydırır."~~ → ÇÜRÜTÜLDÜ. (Kaynak: IJPR 2020. Ancak
  aynı makalenin "envelope-primitif temsil algoritma seçiminden önemli" bulgusu
  GEÇERLİ kalır — Faz 2 caveat'ında işlendi.)

---

## D. NASIL OKUNMALI (öncelik)

1. **EJOR 2018** (indi) — Faz 3'ün ana kaynağı; quasi-phi + COMPOLY. En kritik.
2. **SFF 2015 Araujo** (indi) — tek belgede DBLF limiti + octree + cavity + gap
   teyidi; Faz 1/2/4'ün haritası. Hızlı başlangıç.
3. **NVIDIA 2010** (indi) — Faz 1 octree veri yapısı, mühendislik referansı.
4. CGF 2018 + IFAC 2019 (paywall) — Faz 2/3 formülasyon detayı; üniversite
   erişimiyle indirilebilir.

**Entegrasyon kapısı (önceki turdan):** makale → tekniği kodla → benchmark kapısı →
ortalamayı geçmezse MERGE YOK. Ölçüm: Faz 0 kıyas harness'ı (Plan1/Plan2 hoca verisi).
