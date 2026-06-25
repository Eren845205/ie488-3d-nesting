# KAYNAKLAR — NFV Bakılmamış Yöntem Aileleri (2026-06-25)

> 2 paralel `deep-research` workflow ile 45 peer-reviewed kaynak tarandı; denediğimiz yöntemler
> (NFV/greedy/BLB, SA/ALNS-sıra, oryantasyon/pitch sweep, tie-break, GPU/FFT hız) DIŞLANDI.
> Tam sentez + sıralama: bu klasördeki **SENTEZ_RAPORU.md**.
> PDF'ler `pdf/` altında (açık erişim olanlar indirildi; `*.pdf` git'te ignore'lu = sadece lokal).
> Erişim: ✅ PDF indirildi · 🔒 paywall (sadece link + künye).

---

## KALİTE — Magics açığını kapatabilecek aileler

### A1. Phi-fonksiyonu / quasi-phi NLP + SÜREKLİ rotasyon ⭐ (Magics'in muhtemel sırrı)
1. ✅ **Romanova, Stoyan, Pankratov, Bennell et al. (2018)** — *Packing of concave polyhedra with
   continuous rotations using nonlinear optimisation.* **European Journal of Operational Research (EJOR)**.
   IPMach NAS Ukraine (Kharkiv) + Univ. of Southampton.
   → `pdf/KALITE_Romanova2018_EJOR_concave-polyhedra-continuous-rotation.pdf`
   → https://eprints.whiterose.ac.uk/id/eprint/139289/
   **Neden:** Concave parçaları SÜREKLİ rotasyon+öteleme ile min-yükseklikli kutuya; analitik quasi-phi
   (voxel/FFT YOK) + IPOPT NLP; N>30 tıkanır → decomposition (COMPOLY/FAPA) şart. **EN ÖNEMLİ kaynak.**

2. 🔒 **Stoyan, Romanova et al.** — *Optimal packing of irregular 3D objects... minimum height under
   continuous rotations.* **IFAC-PapersOnLine** (S2405896319314831).
   → https://www.sciencedirect.com/science/article/pii/S2405896319314831
   **Neden:** Hedefimizle birebir: min-YÜKSEKLİK + sürekli rotasyon. (DOĞRULANDI 3-0)

3. 🔒 **Romanova, Pankratov, Stoyan et al.** — *Decomposition algorithm for irregular placement
   (quasi-phi-functions).* **Springer LNCS** 978-3-030-33585-4_21.
   → https://link.springer.com/chapter/10.1007/978-3-030-33585-4_21
   **Neden:** O(n²) NLP'yi O(n) alt-problem dizisine indirger = ölçeklenebilirlik kaldıracı. (DOĞRULANDI 2-0)

4. 🔒 **Stoyan, Romanova, Pankratov (EJOR 2018)** — irregular 3D packing, phi-function NLP.
   → https://www.sciencedirect.com/science/article/abs/pii/S0377221718300468
5. 🔒 **Bennell, Stoyan, Romanova (JORS 2015)** — phi-function tabanlı yerleştirme.
   → https://link.springer.com/article/10.1057/jors.2015.94

### A2. Global compaction — layout-sonrası boşluk kapatma ⭐ (6GB-uyumlu, denenmemiş)
6. 🔒 **(CGF / Eurographics, cgf.13490)** — irregular packing, serbest rotasyon + kombinatoryal
   gap-closing (swap/replace/insert).
   → https://onlinelibrary.wiley.com/doi/abs/10.1111/cgf.13490
   **Neden:** Yerleşim BİTTİKTEN sonra eject-reinsert/swap ile global kompaksiyon — bizim sıfır-kazançlı
   sıra-metaheuristik (SA/ALNS) ve tek-parça tie-break'ten FARKLI. **İlk denenecek 6GB kalite hedefi.**

### A3. Öğrenme-tabanlı (düşük öncelik)
7. ✅ **DiffPack (arxiv 2310.19814)** — score-based diffusion, öğrenilen gradyan alanları, coarse-to-fine.
   → `pdf/KALITE_DiffPack_arxiv2310.19814_diffusion-packing.pdf` · https://arxiv.org/abs/2310.19814
   **Neden/uyarı:** 2D, sadece öteleme (rotasyon yok), 3D implemente değil → bizimle tam örtüşmüyor.
8. 🔒 **IR-BPP** — irregular bin packing derin RL. → https://github.com/alexfrom0815/IR-BPP
   **Neden/uyarı:** online bin-packing, offline height-min ile eşleşmiyor; düşük öncelik.

---

## HIZ — kaliteyi BOZMADAN (exact/birebir) hızlandırma

### B1. Binary AND+popcount / tensor-core 1-bit ⭐ (en somut, 6GB-uyumlu, EXACT)
9. ✅ **(arxiv 2006.16578)** — NVIDIA Turing tensor-core native 1-bit hesaplama: bit matrix-mult +
   **bit convolution** donanım primitifi.
   → `pdf/HIZ_Turing-1bit-tensorcore_arxiv2006.16578.pdf` · https://arxiv.org/abs/2006.16578
10. ✅ **(arxiv 2007.14178)** — GPU'da XNOR convolution; 3×3 kernel'de ~42.6× hız (XNOR+popcount).
    → `pdf/HIZ_XNOR-conv-GPU_arxiv2007.14178.pdf` · https://arxiv.org/abs/2007.14178
    **Neden:** occupancy+parça boolean → çakışma = bit-AND popcount, fp64 FFT'siz, **EXACT**.
    **bit-pack NO-GO'dan FARKLI** (depolama değil hesaplama). Hibrit: küçük parça→popcount. **İlk hız hedefi.**

### B2. Seyrek voxel — bellek (dolaylı ince pitch)
11. ✅ **Museth (2013)** — *VDB: High-Resolution Sparse Volumes with Dynamic Topology.* **ACM TOG.**
    → `pdf/HIZ_Museth2013_OpenVDB_TOG.pdf` · https://www.museth.org/Ken/Publications_files/Museth_TOG13.pdf
    **Neden:** %93-boş parçalara ideal seyrek depolama (boolean bitmask, O(1)); OOM gevşetir → ince pitch.
12. ✅ **Graham, van der Maaten (CVPR 2018)** — *3D Semantic Segmentation with Submanifold Sparse Conv.*
    → `pdf/HIZ_Graham2018_submanifold-sparse-conv_CVPR.pdf`
    → https://openaccess.thecvf.com/content_cvpr_2018/papers/Graham_3D_Semantic_Segmentation_CVPR_2018_paper.pdf
    **Neden/uyarı:** aktif voxel'e kısıtlı conv; submanifold variant TAM çıktı vermez → NFV feasible set'ine
    uymayabilir (dikkat).

### B3. Hiyerarşik broad-phase (exact'i değiştirmez, önüne eklenir)
13. ✅ **(Köln Üniv.)** — O(n) GPU sparse-volume BVH inşası.
    → `pdf/HIZ_Koln_On-linear-sparse-volume-BVH.pdf` · https://vis.uni-koeln.de/fileadmin/home/szellma1/authors_version.pdf
14. ✅ **(arxiv 2409.09918)** — RT-core donanımıyla mesh-mesh collision (DOĞRULANDI 2-0).
    → `pdf/HIZ_RT-core-mesh-collision_arxiv2409.09918.pdf` · https://arxiv.org/abs/2409.09918
    **Uyarı:** continuous variant YAKLAŞIK (birebir kısıtı ihlal).
15. ✅ **nvblox (arxiv 2311.00626)** — GPU ESDF (Euclidean signed distance field), 31× hız iddiası.
    → `pdf/HIZ_nvblox-GPU-ESDF_arxiv2311.00626.pdf` · https://arxiv.org/abs/2311.00626
16. 🔒 **(Springer s00170-021-07954-y)** — 3D nesting'de OBB-tree + clearance early-reject.
    → https://link.springer.com/article/10.1007/s00170-021-07954-y

### B4. AM-özel + elenenler
17. ✅ **(optimization-online 2022)** — Efficient pixel-based packing for AM production planning.
    → `pdf/HIZ_AM-pixel-based-packing_optimization-online2022.pdf`
    → https://optimization-online.org/wp-content/uploads/2022/08/An-Efficient-Pixel_based-Packing-Algorithm-for-Additive-Manufacturing-Production-Planning.pdf
18. 🔒 **(Taylor & Francis 2025.2604312)** — 3D nesting, çok-dilim NFP (no-fit polygon) collision.
    → https://www.tandfonline.com/doi/full/10.1080/00207543.2025.2604312
19. 🔒 **MIT sFFT** — sparse FFT O(k log n). → https://groups.csail.mit.edu/netmit/sFFT/
    **ELENDİ:** yaklaşık/block-sparse → bit-identical değil, birebir kısıtını ihlal eder.

---

## ÖZET — sonraki adım için 2 somut 6GB-denenmemiş ilk hedef
- **KALİTE → global compaction** (kaynak #6): layout-sonrası eject-reinsert/swap.
- **HIZ → binary AND+popcount korelasyon** (kaynak #9, #10): boolean için FFT'siz EXACT.
- **Süper bilgisayar yolu:** sürekli rotasyon NLP (#1-#3) — "n=28+0.5mm"den daha derin.
