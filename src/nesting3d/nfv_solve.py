"""nfv_solve.py — NFV cavity yerleştirici (opt-in "kalite modu" üretim çözücüsü).

ENGEL 1 ÇÖZÜMÜ (kanıt `scripts/c3_nfv_solve.py`): üretimin coarse→fine+drop boru hattı NFV'nin
3B-cavity pozisyonlarını BOZUYORDU. Çözüm: NFV'yi HEDEF pitch'te tam-yerleştirici koş (best_decode),
çıktıyı (part_id,oi,x,y,z) → Bin3D'ye REPLAY et (Bin3D.place TAM (x,y,z)'ye koyar, drop YOK →
Placement3D üretir + heightmap günceller). Cavity korunur; non-overlap OccupancyBin3D.place ile garanti.

Sonuç `CoarseToFineResult` (solve_coarse_to_fine ile AYNI şekil) → render/export/UI değişmeden tüketir.
Downstream `tune_result.{winning_config_name,baseline_height_mm,all_results,improvement_mm}` okuduğundan
sentetik minimal TuneResult konur. cupy yoksa best_decode CPU'ya düşer (graceful).
"""
from __future__ import annotations
import time
from types import SimpleNamespace

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.coarse_to_fine import CoarseToFineResult, clearance_to_voxels
from src.nesting3d.tuner import TuneResult
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.instances.pitch import suggest_nfv_pitch
from src.nesting3d.capabilities import probe_capabilities
from src.nesting3d.parallel_decode import best_decode

# NFV oryantasyon seçimi (ÖLÇÜM 2026-06-24 c3_quality_levers + 2026-07-03 K-18):
#   * n=8 default. NEDEN SABİT-DEĞİL-AMA-SABİT: n=8 oryantasyon seti n=4'ü İÇERİR (4⊂8) → NFV greedy
#     n=8'de en az n=4 kadar iyi seçer → kalite HER veride garantili >= n=4 (Plan2'ye overfit DEĞİL,
#     küme-içerme matematiği). Sweet spot: 4→8 ~%6 kazanç.
#   * Adaptif DBLF-prob DENENDİ → NO-GO: heightmap-DBLF n-getiriyi TERS tahmin etti (Plan2 trail
#     n=4:639<n=8:645 dedi ama NFV'de n=8=522<n=4=556 İYİ) + prob 919s yavaş. DBLF NFV'yi temsil etmez.
#   * quality="max" (K-18p, 2026-07-03): 24 EKSEN-HİZALI poz (AX24 = master 0..7 + 12..27).
#     Eski ilk-N merdiveni (8→12→28) EĞİK pozları (8..11) içeriyordu — K-13/K-15 kanıtı: greedy eğik
#     pozu miyop kullanır (zarar/nötr). AX24 eğiksiz; 8⊂24 küme-içerme + K-18 ölçümü: plan2
#     n24+settle 512.5 (n8 baz 522'den −%1.8; n24 baz 520.0 = K-13 A24 kontrolüyle birebir sanity).
#     Bedel decode ~3-4× → default'a DEĞİL yalnız quality=max'a. RAM<13GB → n=8 güvenli taban
#     (AX24 16GB'de plan2 226-parçada ölçülerek doğrulandı, K-18 koşusu).
NFV_DEFAULT_ORIENTATIONS = 8
NFV_AX24 = tuple(range(8)) + tuple(range(12, 28))  # 24 eksen-hizalı (eğik 8..11 HARİÇ)


# AX24 kapisi: mevcut total-RAM esigi (bu makinede 16GB>=13 -> AX24 KORUNUR). Sihirli sabit degil,
# K-18 olcumunde 16GB'de plan2-226 AX24 dogrulandigi icin toplam-RAM tavani.
_AX24_TOTAL_RAM_GB = 13.0


def _quality_max_decision(ram_bytes, *, n_parts=None, ram_available_bytes=None,
                          grid_cells=None, bytes_per_cell=8.0, safety_factor=2.0,
                          avail_headroom=0.8):
    """quality='max' oryantasyon karari + gerekce. Doner: (orients|None, reason).

    Katman 1 (KORUNUR): total RAM < _AX24_TOTAL_RAM_GB -> n=8 guvenli taban (mevcut davranis birebir).
    Katman 2 (YENI emniyet freni, OPSIYONEL): sadece n_parts + ram_available_bytes + grid_cells'in
      HEPSI verilirse devreye girer. Tahmini decode/voxel-parts bellek ihtiyaci turemis esikten:
          est = safety_factor * n_parts * len(NFV_AX24) * grid_cells * bytes_per_cell
      (fizik: AX24'te parca basina 24 oryantasyon gridi + FFT float64 gecici seti resident; bellek
       oryantasyon SAYISIYLA buyur -> AX24'un n=8'e gore asil bedeli). Kullanilabilir butce
      avail_headroom * ram_available_bytes'i asarsa n=8'e dus (OOM koruma). SABIT SIHIRLI SAYI YOK:
      esik olculebilir (parca, grid, available) buyuklukten turer + tum katsayilar parametreyle
      override edilebilir. Girdilerden herhangi biri None -> fren KAPALI (davranis degismez)."""
    if ram_bytes / 1e9 < _AX24_TOTAL_RAM_GB:
        return None, "RAM<13GB -> n=8 guvenli taban"
    if n_parts is not None and ram_available_bytes is not None and grid_cells is not None:
        est = safety_factor * float(n_parts) * len(NFV_AX24) * float(grid_cells) * bytes_per_cell
        budget = avail_headroom * float(ram_available_bytes)
        if est > budget:
            return None, (f"AX24 emniyet freni: est {est / 1e9:.2f}GB > "
                          f"available*{avail_headroom:g} {budget / 1e9:.2f}GB -> n=8 guvenli taban")
    return NFV_AX24, f"AX24 n={len(NFV_AX24)} (24 eksen-hizali, K-18)"


def _quality_max_orientations(ram_bytes, **kw):
    """Geriye-uyum ince katman: yalniz poz setini (None|NFV_AX24) dondurur (reason'i atar).
    Mevcut cagiranlar (test dahil) bu imzayi kullanir; yeni fren yolu _quality_max_decision'da."""
    return _quality_max_decision(ram_bytes, **kw)[0]


def _grid_cells_estimate(instance, pitch):
    """En buyuk parca bounding-box'inin verilen pitch'te tahmini voxel hucre sayisi (grid buyuklugu
    proxy'si). Olcu alinamazsa (mesh parca, boyut yok, gecersiz pitch) None -> fren kapali/konservatif."""
    if pitch is None or pitch <= 0:
        return None
    best = 0.0
    for p in getattr(instance, "parts", []) or []:
        w = getattr(p, "width_mm", None) or 0.0
        d = getattr(p, "depth_mm", None) or 0.0
        h = getattr(p, "height_mm", None) or 0.0
        best = max(best, (w / pitch) * (d / pitch) * (h / pitch))
    return best or None


def _nfv_clearance_voxels(clearance_mm, pitch, margin):
    """NFV yolu için (eff_margin, z_dilate) türet.

    clearance_mm <= 0.0 (default) -> (margin, 0): mevcut NFV davranışı BİT-ÖZDEŞ
      (xy dilation = geçilen margin param, z-dilation YOK).
    clearance_mm > 0 -> clearance_to_voxels(clearance, pitch) = (n, n): xy margin
      ve z_dilate ikisi de formülden (margin==z_c=max(1,ceil(clearance/pitch)))
      → yatay dilation + tek-taraflı dikey dilation birlikte >= clearance boşluğu
      GERÇEK kullanılan pitch'ten türer (pitch küçülürse voxel sayısı artar,
      mm-boşluk sabit kalır)."""
    if clearance_mm and clearance_mm > 0.0:
        return clearance_to_voxels(clearance_mm, pitch)
    return margin, 0


def _voxelize_nfv(instance, pitch, floor_pitch, n_orientations, margin,
                  allowed_orientations=None, clearance_mm=0.0):
    """coarse_to_fine._voxelize_with_fallback mantığı + margin (o fonksiyon margin geçmiyor).
    İnce-duvar parça pitch'te kaybolursa (ValueError) pitch'i kıs, floor'a kadar dene. (parts, used).
    allowed_orientations verilirse (K-18p AX24) n_orientations yok sayılır.

    clearance_mm > 0 iken xy margin + tek-taraflı z-dilation GERÇEK kullanılan
    pitch'ten türetilir (EVAL-1 NFV dikey-clearance fix); default 0.0 -> davranış
    BİT-ÖZDEŞ (margin param aynen, z-dilation yok)."""
    cur = pitch
    while True:
        eff_margin, z_dilate = _nfv_clearance_voxels(clearance_mm, cur, margin)
        try:
            return to_voxel_parts(instance, cur, n_orientations=n_orientations,
                                  margin=eff_margin, z_dilate=z_dilate,
                                  allowed_orientations=allowed_orientations), cur
        except ValueError:
            nxt = cur / 1.5
            if nxt <= floor_pitch:
                fm, fz = _nfv_clearance_voxels(clearance_mm, floor_pitch, margin)
                return (to_voxel_parts(instance, floor_pitch, n_orientations=n_orientations,
                                       margin=fm, z_dilate=fz,
                                       allowed_orientations=allowed_orientations), floor_pitch)
            cur = nxt


def solve_nfv(instance, *, plate_w_mm, plate_d_mm, fine_pitch=None,
              n_orientations=None, quality="fast", margin=1, seed=42, force=None,
              fine_settle=True, orient_ram_brake=False,
              time_budget_sec=None, clearance_mm=0.0,
              no_go_bounds=None,
              repair_separability=False,
              exit_guard=False, exit_guard_retries=2) -> CoarseToFineResult:
    """NFV cavity decode → CoarseToFineResult. force: best_decode strateji zorla (test/debug).

    clearance_mm=0.0 (default): MEVCUT davranış BİT-ÖZDEŞ (xy dilation=margin
    param, dikey clearance mekanizması yok — tarihsel NFV). >0 iken (EVAL-1 fix):
    HER voxelize (coarse + fine-settle) xy margin + TEK-TARAFLI z-dilation'ı
    GERÇEK kullanılan pitch'ten türetir (clearance_to_voxels: margin==z_c=
    max(1,ceil(clearance/pitch))) → parça-arası her yönde >= clearance_mm boşluk.
    NFV yolu Bin3D z_clearance'tan geçmediğinden dikey boşluk yalnız bu z-dilation
    ile gelir; taban etkilenmez (parçalar plakaya oturur).

    fine_settle=True (default): K-17 pozisyon-koruyan fine z-kompaksiyon post-pass'i —
    kazanan layout used_pitch/4'te yeniden oturtulur, kuantizasyon vergisi geri alınır
    (ölçüm: plan3 +%1.6 / plan2 +%1.1 / plan1 +%0.4). Kalite yönü TEK TARAFLI: yükseklik
    iyileşmezse (veya bellek/hata) coarse sonucu AYNEN korunur → default-on güvenli.

    fine_pitch=None (varsayılan) → NFV-farkında pitch otomatik seçilir (suggest_nfv_pitch):
    parçayı kaybetmeyen EN KABA güvenli pitch + bellek/plaka guard. Açık pitch → opt-in override.

    n_orientations seçimi:
      * Açık int verilirse o kullanılır.
      * None (varsayılan) → quality'ye göre:
          - quality="fast"  → n=8 (4⊂8 → kalite her veride >= n=4, sweet spot; ÖLÇÜM gerekçesi yukarıda).
          - quality="max"   → AX24: 24 eksen-hizalı poz, eğiksiz (K-18p; RAM<13GB → n=8 taban).
    """
    t0 = time.perf_counter()
    nfv_reason = None
    if fine_pitch is None:
        fine_pitch, feasible, nfv_reason = suggest_nfv_pitch(
            instance, plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
            ram_bytes=probe_capabilities().ram_bytes, margin=margin,
        )
        # feasible=False → en kaba pitch bile bellek bütçesini aşıyor; yine de denenir (best_decode
        # GPU→CPU→seri graceful fallback ile en uygun yolu bulur), ama reason raporlanır (uyarı).
    n_reason = None
    allowed_orients = None
    if n_orientations is None:
        if quality == "max":
            caps = probe_capabilities()
            brake_kw = {}
            if orient_ram_brake:
                # opt-in emniyet freni: parca-sayisi + available-RAM + grid tahmininden turemis esik.
                # default (orient_ram_brake=False) -> brake_kw bos -> mevcut AX24/taban davranisi BIREBIR.
                brake_kw = dict(
                    n_parts=int(sum(getattr(p, "qty", 1) or 1 for p in getattr(instance, "parts", []) or [])),
                    ram_available_bytes=caps.ram_available_bytes,
                    grid_cells=_grid_cells_estimate(instance, fine_pitch),
                )
            allowed_orients, detail = _quality_max_decision(caps.ram_bytes, **brake_kw)
            n_reason = f"quality=max {detail}"
            n_orientations = len(allowed_orients) if allowed_orients is not None else NFV_DEFAULT_ORIENTATIONS
        else:
            n_orientations = NFV_DEFAULT_ORIENTATIONS
            n_reason = f"n={n_orientations} (default, 4subset8 garanti)"
    parts, used_pitch = _voxelize_nfv(instance, fine_pitch, fine_pitch, n_orientations, margin,
                                      allowed_orientations=allowed_orients,
                                      clearance_mm=clearance_mm)
    # fine-settle aynı clearance kuralına uyar (aksi hâlde settle kazanılan boşluğu
    # geri yer). used_pitch'ten türetilen (xy margin, z-dilation) settle'a geçilir.
    settle_margin, settle_zc = _nfv_clearance_voxels(clearance_mm, used_pitch, margin)
    nx, ny = int(plate_w_mm // used_pitch), int(plate_d_mm // used_pitch)

    # ÇİFT-SAAT FIX: decode kendi t0'ini sifirdan baslattigi icin TAM butceyi alirdi (voxelize'da
    # gecen sure sayilmazdi -> replay-tarafi kesme ile birlesince bitmis gecerli layout kesilebiliyordu).
    # KALAN butceyi gecir: voxelize'da tuketilen sure dusulur. <=0 ise 0.0 (butce voxelize'da bitti ->
    # decode aninda temiz-bos dusus + budget_exceeded izi). None -> None (default davranis BIREBIR).
    if time_budget_sec is None:
        decode_budget = None
    else:
        decode_budget = time_budget_sec - (time.perf_counter() - t0)
        if decode_budget <= 0:
            decode_budget = 0.0

    # NO-GO (2026-07-09, kullanici karari "hepsine eklenecek"): yasak-bolge
    # mm-bbox'u kullanilan pitch'te maskeye cevrilir; decode occupancy'sinde
    # TAM yukseklik muhurlenir. default None = BIT-OZDES eski davranis.
    _ng_mask = None
    if no_go_bounds is not None:
        _ng_mask = Bin3D.no_go_mask_from_bounds(
            no_go_bounds, plate_w_mm, plate_d_mm, used_pitch)

    _, raw, strategy = best_decode(parts, nx, ny, pitch=used_pitch, force=force,
                                   time_budget_sec=decode_budget,
                                   no_go_mask=_ng_mask, exit_guard=exit_guard,
                                   exit_guard_retries=exit_guard_retries)

    # REPLAY → Bin3D (tek kaynak: Placement3D + heightmap). TAM (x,y,z), drop YOK → cavity korunur.
    # Kesme decode'da yapildi (kalan butceye gore, kesin); replay O(n) ucuz ve deterministik → decode'un
    # dondurdugu raw neyse AYNEN oynat (ikinci kez kesme YOK -> bitmis gecerli layout korunur).
    bin3d = Bin3D(plate_w_mm, plate_d_mm, used_pitch)
    parts_by_id = {p.id: p for p in parts}
    budget_exceeded = time_budget_sec is not None and "budget_exceeded" in strategy
    for (pid, oi, x, y, z) in raw:
        bin3d.place(parts_by_id[pid], oi, x, y, z)

    # K-17 fine-settle post-pass: kuantizasyon vergisini geri al (yalnız iyileştirirse).
    # Butce aktif VE asilmissa settle'i ATLA: tam raw ile kosarsa decode'un kestigi parcalari sessizce
    # geri getirir (n_placed ile celisir) + MAX_SETTLE_SWEEPS butceyi sinirsiz asabilir. Butce henuz
    # asilmadiysa settle'a dokunma (v1: settle'in icine butce sizdirmak kapsam disi).
    settle_note = None
    result_pitch = used_pitch
    if fine_settle and budget_exceeded:
        settle_note = "settle skipped (budget)"
    elif fine_settle:
        from src.nesting3d.fine_settle import fine_settle_raw
        s = fine_settle_raw(raw, parts_by_id,
                            plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
                            pitch=used_pitch, margin=settle_margin,
                            z_dilate=settle_zc,
                            h_coarse_mm=bin3d.max_height_mm(),
                            no_go_bounds=no_go_bounds)
        if s is not None:
            fine_bin = Bin3D(plate_w_mm, plate_d_mm, s.fine_pitch)
            for (pid, oi, xf, yf, zf) in s.raw_fine:
                fine_bin.place(s.fine_parts[pid], oi, xf, yf, zf)
            # R2: exit_guard aciksa settle'in z-alcaltmasi YENI kilit
            # uretebilir (parca kaviteye derinlesir) -> kilitli settle
            # REDDEDILIR, coarse (garanti-cikisli) sonuc korunur.
            settle_kilit = 0
            if exit_guard:
                from src.nesting3d.accessibility import check_separability_5dir
                settle_kilit = check_separability_5dir(
                    fine_bin.placements, s.fine_parts).n_locked
            if settle_kilit > 0:
                settle_note = (f"settle REDDEDILDI (exit_guard: "
                               f"{settle_kilit} kilit uretecekti)")
            else:
                settle_note = (f"settle {bin3d.max_height_mm():.1f}->"
                               f"{fine_bin.max_height_mm():.1f}mm @{s.fine_pitch}mm")
                bin3d, parts_by_id, result_pitch = fine_bin, s.fine_parts, s.fine_pitch

    # R1 (2026-07-09, A2 5-yon metrigi): opsiyonel KILIT-TAHLIYE post-pass —
    # 5-yonde kilitli parcalar tahliye edilip kurallara uygun yeniden
    # yerlestirilir (dilate'li mevcut grid'ler -> clearance korunur).
    # default False = BIT-OZDES eski davranis. Ilk saha kaniti: K-29 probu.
    repair_note = None
    if repair_separability:
        from src.nesting3d.separability_repair import repair_separability as _onar
        _ng = None
        if no_go_bounds is not None:
            _ng = Bin3D.no_go_mask_from_bounds(
                no_go_bounds, plate_w_mm, plate_d_mm, result_pitch)
        rr = _onar(bin3d.placements, parts_by_id,
                   plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
                   pitch=result_pitch, no_go_mask=_ng)
        if rr.repaired:
            onarilan_bin = Bin3D(plate_w_mm, plate_d_mm, result_pitch,
                                 no_go_mask=_ng)
            for p in rr.placements:
                onarilan_bin.place(parts_by_id[p.part_id], p.orientation_idx,
                                   p.x, p.y, p.z)
            bin3d = onarilan_bin
            repair_note = (f"repair {rr.n_locked_before}->{rr.n_locked_after}"
                           f" kilit / {rr.rounds_used} tur"
                           + (f" ({rr.note})" if rr.note else ""))
    elapsed = time.perf_counter() - t0

    h = bin3d.max_height_mm()
    density = bin3d.packing_density()
    # sentetik minimal TuneResult (downstream raporlama: all_results satırı .height_mm/.density/.time_s okur)
    row = SimpleNamespace(height_mm=h, density=density, time_s=elapsed)
    tune_result = TuneResult(result=None, winning_config_name="nfv",
                             baseline_height_mm=h, improvement_mm=0.0,
                             all_results=[("nfv", row)])

    return CoarseToFineResult(
        placements=bin3d.placements, bin3d=bin3d, height_mm=h, density=density,
        winning_config="nfv", coarse_height_mm=h, coarse_pitch=used_pitch,
        fine_pitch=result_pitch,  # settle kabul edildiyse used_pitch/scale — GLB/export bu pitch'le hizalanır
        coarse_time_s=0.0, fine_time_s=elapsed, n_placed=len(bin3d.placements),
        tune_result=tune_result, fine_voxel_parts=parts_by_id, fine_angle_used=False,
        adaptive_reason=f"nfv strategy={strategy}" + (f" | {nfv_reason}" if nfv_reason else "")
        + (f" | {n_reason}" if n_reason else "")
        + (f" | {settle_note}" if settle_note else "")
        + (f" | {repair_note}" if repair_note else ""),
    )
