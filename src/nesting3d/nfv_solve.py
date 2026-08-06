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
                  allowed_orientations=None, clearance_mm=0.0,
                  orientation_overrides=None):
    """coarse_to_fine._voxelize_with_fallback mantığı + margin (o fonksiyon margin geçmiyor).
    İnce-duvar parça pitch'te kaybolursa (ValueError) pitch'i kıs, floor'a kadar dene. (parts, used).
    allowed_orientations verilirse (K-18p AX24) n_orientations yok sayılır.

    orientation_overrides (K-56g NFV kolu, hoca S2 2026-07-22): {model adı ->
    poz indeks tuple'ı} — adı eşleşen model YALNIZ bu pozlarda voxelize edilir
    (sipariş-notu duruş kilidi; global allowed_orientations'ı o model için
    ezer). None (default) = bit-özdeş.

    clearance_mm > 0 iken xy margin + tek-taraflı z-dilation GERÇEK kullanılan
    pitch'ten türetilir (EVAL-1 NFV dikey-clearance fix); default 0.0 -> davranış
    BİT-ÖZDEŞ (margin param aynen, z-dilation yok)."""
    cur = pitch
    while True:
        eff_margin, z_dilate = _nfv_clearance_voxels(clearance_mm, cur, margin)
        try:
            return to_voxel_parts(instance, cur, n_orientations=n_orientations,
                                  margin=eff_margin, z_dilate=z_dilate,
                                  allowed_orientations=allowed_orientations,
                                  orientation_overrides=orientation_overrides), cur
        except ValueError:
            nxt = cur / 1.5
            if nxt <= floor_pitch:
                fm, fz = _nfv_clearance_voxels(clearance_mm, floor_pitch, margin)
                return (to_voxel_parts(instance, floor_pitch, n_orientations=n_orientations,
                                       margin=fm, z_dilate=fz,
                                       allowed_orientations=allowed_orientations,
                                       orientation_overrides=orientation_overrides), floor_pitch)
            cur = nxt


def solve_nfv(instance, *, plate_w_mm, plate_d_mm, fine_pitch=None,
              n_orientations=None, quality="fast", margin=1, seed=42, force=None,
              fine_settle=True, orient_ram_brake=False,
              time_budget_sec=None, clearance_mm=0.0,
              no_go_bounds=None,
              repair_separability=False,
              exit_guard=False, exit_guard_retries=2,
              orientation_overrides=None,
              pinned_placements=None, pin_3d=False,
              oncelik_adlari=None) -> CoarseToFineResult:
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
                                      clearance_mm=clearance_mm,
                                      orientation_overrides=orientation_overrides)

    # K-62 v8 (2026-08-04): NFV'ye pin destegi — MVP semantigi:
    # (a) pin donorleri cozum havuzundan DUSER (coklu-kopya, _pin_hazirla),
    # (b) pin FOOTPRINT kolonlari decode maskesine MUHURLENIR (best_decode
    #     degismez; cozucu pin kolonlarina hicbir sey koyamaz — pin ustu/alti
    #     ic-ice kullanim v8-MVP disi, bilincli konservatif),
    # (c) pinler settle/repair SONRASI gercek yerlesim olarak sahneye girer
    #     (tasinmazlik bedava; olcum katmani pin'i normal parca gorur).
    # default None = BIT-OZDES.
    #
    # K-62 v9 (pin_3d=True): (b) yerine pin GERCEK 3D voxelleriyle decode
    # occupancy'sine ON-YUKLENIR (occ_onyuk) — pinin alti/ustu SERBEST:
    # kanopi altina istif + delikten kule = insan cozumunun mekanigi.
    # v17 HAM-PIN duzeltmesi (2026-08-06): pin xy'de HAM damgalanir; dikey
    # tek-tarafli ust z-dilation tasir. Parca-pin xy boslugu boylece komsu
    # parcanin KENDI margin'inden gelir (1x = clearance; _pin_hazirla
    # sozlesmesi). v9'un "havuzla ayni dilation" damgasi parca-pin sartini
    # 2x'e cikariyordu (parca-parca decode'da zaten 2x — iki grid de sisik —
    # ama pin SABIT oldugundan tek tarafin marjini yeterli ve legaldir;
    # v8 2D-muhur de ham'di, 140.21 LEGAL saha kaniti). Sahneye commit
    # margin-0 (adim c, degismez). default False = v8 semantigi BIT-OZDES.
    _pin_specs = pinned_placements
    _pin_donors = None
    _occ_onyuk = None
    if _pin_specs:
        from src.nesting3d.coarse_to_fine import _pin_hazirla
        _pins0 = _pin_hazirla(_pin_specs, parts, used_pitch)
        _pin_ids = {p.id for p, _x, _y, _z in _pins0}
        _pin_donors = [p for p in parts if p.id in _pin_ids]
        parts = [p for p in parts if p.id not in _pin_ids]
        if pin_3d:
            from src.nesting3d.voxelize import voxelize_part as _vp3
            import numpy as _np
            _eff_m, _eff_zc = _nfv_clearance_voxels(clearance_mm, used_pitch,
                                                    margin)
            # K-62 v17 HAM-PIN (2026-08-06, v16 rip-up KOK fix'i): pin xy'de
            # HAM damgalanir (margin=0). _pin_hazirla sozlesmesi: "sabit nesne
            # dilation tasimaz, komsular kendi marjini tasir" -> parca-pin xy
            # boslugu 1x margin (=clearance). v9 pin'i TAM dilation'la
            # damgaliyordu -> parca-pin sarti 2x'e cikiyordu (cift-dilation
            # vergisi; rip-up'ta sokulen parca eski cebine donemiyordu).
            # z_dilate KALIR: pin ustune oturan parcanin dikey boslugunu
            # ALTTAKI nesnenin ust-dilation'i tasir (z_dilate=0 olsaydi parca
            # pin tepesine 0mm'e inerdi — A2 ihlali). margin=0 oldugundan
            # xy origin ofseti de kalkar (damga dogrudan pin bbox konumunda).
            _occ_onyuk = []
            for (_pp, _ix, _iy, _iz), _spec in zip(_pins0, _pin_specs):
                _rot = _spec.get("rot")
                _rot = (_np.eye(4) if _rot is None
                        else _np.asarray(_rot, dtype=float))
                _raw3 = _vp3(_pp.name, _pp.mesh, used_pitch,
                             rot_matrices=[_rot], method="slice",
                             margin=0, z_dilate=_eff_zc)
                _occ_onyuk.append((_raw3.orientations[0].grid,
                                   _ix, _iy, _iz))
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
    if _pin_specs and not pin_3d:
        # v8 semantigi: 2D footprint kolon muhru (pin ustu/alti da kapali).
        import numpy as _np
        _ng_mask = (_np.zeros((nx, ny), dtype=bool) if _ng_mask is None
                    else _np.asarray(_ng_mask, dtype=bool).copy())
        for _pp, _ix, _iy, _iz in _pins0:
            _f = _pp.orientations[0].filled
            _w = min(_f.shape[0], nx - _ix)
            _h = min(_f.shape[1], ny - _iy)
            if _w > 0 and _h > 0:
                _ng_mask[_ix:_ix + _w, _iy:_iy + _h] |= _f[:_w, :_h]

    # K-62 v11: opt-in yerlestirme onceligi (tip ADLARI -> id kumesi).
    # v13: dict {ad: rutbe} de kabul edilir (kucuk rutbe = once).
    # None (default) = tarihsel hacim-azalan sira BIT-OZDES.
    _onc_ids = None
    if oncelik_adlari:
        if isinstance(oncelik_adlari, dict):
            _onc_ids = {p.id: oncelik_adlari[p.name] for p in parts
                        if getattr(p, "name", None) in oncelik_adlari}
        else:
            _oset = set(oncelik_adlari)
            _onc_ids = {p.id for p in parts
                        if getattr(p, "name", None) in _oset}

    _, raw, strategy = best_decode(parts, nx, ny, pitch=used_pitch, force=force,
                                   time_budget_sec=decode_budget,
                                   no_go_mask=_ng_mask, exit_guard=exit_guard,
                                   exit_guard_retries=exit_guard_retries,
                                   occ_onyuk=_occ_onyuk, oncelik_ids=_onc_ids)

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
        # K-62 v12b: pin_3d'de settle artik PIN-FARKINDA — pinler fine occ'a
        # sabit damgalanir (onyuk_raw), hareketliler etrafina oturur.
        # (v9-MVP'de yapisal atlaniyordu; kuantizasyon vergisi geri alinir.)
        _settle_onyuk = None
        _settle_parts = parts_by_id
        _h_settle = bin3d.max_height_mm()
        if _pin_specs and pin_3d:
            _settle_parts = dict(parts_by_id)
            _settle_onyuk = []
            for _pp, _ix, _iy, _iz in _pins0:
                _settle_parts[_pp.id] = _pp
                _settle_onyuk.append((_pp.id, 0, _ix, _iy, _iz))
                _h_settle = max(_h_settle,
                                (_iz + _pp.orientations[0].grid.shape[2])
                                * used_pitch)
        s = fine_settle_raw(raw, _settle_parts,
                            plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
                            pitch=used_pitch, margin=settle_margin,
                            z_dilate=settle_zc,
                            h_coarse_mm=_h_settle,
                            no_go_bounds=no_go_bounds,
                            onyuk_raw=_settle_onyuk)
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
    if repair_separability and _pin_specs and pin_3d:
        # v9 MVP korumasi: repair de pin-farkinda degil (tahliye/yeniden-
        # yerlestirme pin voxellerini gormez) -> atlanir, iz birakilir.
        repair_note = "repair skipped (pin_3d v9)"
        repair_separability = False
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
    # K-62 v8: pinler FINAL sahneye (settle/repair sonrasi) gercek yerlesim
    # olarak eklenir. Settle pitch degistirmis olabilir -> pinler RESULT
    # pitch'te donor meshlerinden yeniden cozulur (mm-spec pitch-bagimsiz).
    if _pin_specs:
        from src.nesting3d.coarse_to_fine import _pin_hazirla as _ph
        _pins_f = (_pins0 if result_pitch == used_pitch
                   else _ph(_pin_specs, _pin_donors, result_pitch))
        for _pp, _ix, _iy, _iz in _pins_f:
            bin3d.place(_pp, 0, _ix, _iy, _iz)
            parts_by_id[_pp.id] = _pp

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


# R11 "auto" parca tavani. K-50 ilk olcumleri (kompakt 226p=63dk / 352p=70dk /
# 588p=375dk) tavani 150'ye koymustu — buyuk set uretim penceresini asiyordu.
# K-55 hizlandirmasi (cKDTree workers + distance_upper_bound budama; d4 588p
# settle+rafine 393dk -> 43.5dk ~9x, h/clear BIREBIR) gerekceyi kaldirdi ->
# K-58 (2026-07-19): tavan 600 = rot tavaniyla hizali. Gozcu siparisleri
# (10-112p) zaten kapsamdaydi; artik p2/226 - d4/588 bandi da auto'da.
# Ustunde auto ATLAR (iz birakir); r11=True acikca zorlayabilir.
R11_AUTO_PARCA_TAVANI = 600

# rot_kabul="auto" tavani (Eren karari 2026-07-15, d4 routing): rot DENETIMI
# ucuz — K-52 kaniti 588p @1.0 = 1.4dk (K-42'nin "2-4 saat"i eski parametre
# setiydi; YONTEM §3); asil sigorta sure butcesi (rot_butce_s, butce dolarsa
# kilitli sayilir = konservatif). (K-58'e dek R11 tavani 150'de AYRIYDI —
# "R11 pahali" gerekcesi K-55 ile dustu, iki tavan 600'de hizalandi.)
ROT_KABUL_AUTO_PARCA_TAVANI = 600


def solve_nfv_kalite(instance, *, plate_w_mm, plate_d_mm, clearance_mm=2.0,
                     no_go_bounds=None, seed=42, quality="max",
                     n_orientations=None, time_budget_sec=None,
                     r11=False, r11_samples=12000,
                     rot_kabul=False, rot_butce_s=1200.0,
                     orientation_overrides=None, pinned_placements=None,
                     _solve=None, _check_5dir=None, _check_rot=None):
    """K-36/38/41/44 sampiyon recetesi: kalite-NFV + kosullu exit_guard.

    Uc olcumle-kanitli kural tek fonksiyonda (kanit: MOTOR/YONTEM_HARITASI §3):
      1. PITCH = clearance_mm (K-38 clearance-kuantizasyonu: efektif bosluk =
         ceil(clearance/pitch)*pitch; tek-voxel TAM pencere pitch==clearance.
         (clearance/2, clearance) araligi ZEHIRLI — 3.5mm sanal sisme kaniti;
         daha ince tam basamak clearance/2 grid butcesini asiyor. Sampiyonlar:
         plan3 598.5 / plan2 544.5 / deneme5 223.5 hepsi pitch=clearance=2.0).
      2. ONCE HAM kos; 5-yon sokum denetimi kilit>0 derse exit_guard=True ile
         YENIDEN kos (K-41/44 recetesi: onleme>tamir K-29; guard vergisi
         aile-bagimli p2+12.5/d5+20.5/p3+66 — kilitsiz ailede odenmez).
      3. Rot-sokum (R10) denetimi BURADA KOSULMAZ (K-42: 226 parcada 2-4 saat;
         yalniz final muhurleme/rapor icin ayri adim).

    Doner: (CoarseToFineResult, telemetri_dict). Telemetri: pitch, ham/guard
    yukseklik + kilit sayilari, secilen bacak, sure. _solve/_check_5dir test
    enjeksiyonu icindir (A9 bayat-mock tuzagina karsi imzalar gercekle ayni).

    r11 (K-50 kablosu, 2026-07-14): False (default, BIT-OZDES eski davranis) |
    True (hep dene) | "auto" (yalniz n_placed <= R11_AUTO_PARCA_TAVANI).
    TEK-TARAFLI: uretim_r11 dort kapinin birini gecemezse sonuc AYNEN korunur;
    basarida tel["r11"] dz/height/clear/kilit tasir (mesh-duzeyi ekstra dusme —
    voxel sonucu ve bin3d DEGISMEZ; STL/rapor katmani dz'yi uygular).

    rot_kabul (hoca 2026-07-14 kriteri; K-52 probu): ham 5-yon KILITLI ciktiginda
    guard'i kosup vergiyi odemeden ONCE rot-sokum denetimine sorulur — rot
    kilit=0 ise ham SOKUM-PLANLI kabul edilir, guard HIC kosulmaz (vergi
    aile-bagimli p2+12.5/p3+66 idi). rot kilit>0 / hata / kilit-bilinmiyor ->
    eski akis (guard). False (default, BIT-OZDES) | True | "auto" (yalniz
    n_placed <= ROT_KABUL_AUTO_PARCA_TAVANI=600 — rot denetimi UCUZ, K-52:
    588p @1.0 = 1.4dk; K-42'nin "saatler"i eski parametre setiydi; asil
    sigorta rot_butce_s, butce dolarsa kilitli sayilir). tel["rot_kabul"]
    yalniz denendiginde yazilir. _check_rot test enjeksiyonu (res -> rapor).
    """
    from src.nesting3d.accessibility import check_separability_5dir
    solve = _solve or solve_nfv
    check = _check_5dir or check_separability_5dir
    t0 = time.perf_counter()

    def _r11_uygula(res, tel):
        if not r11:
            return
        n = int(res.n_placed)
        if r11 == "auto" and n > R11_AUTO_PARCA_TAVANI:
            tel["r11"] = {"uygulandi": False, "neden": "parca_tavani",
                          "n_placed": n, "tavan": R11_AUTO_PARCA_TAVANI}
            return
        try:
            from src.nesting3d.continuous_settle import uretim_r11
            from src.nesting3d.export_stl import placed_meshes
            meshes = placed_meshes(list(res.placements), res.fine_voxel_parts,
                                   float(res.fine_pitch))
            # HD-0 (plan 2026-07-15): rot-kabul R11 kapisina da akar — K-52
            # kaniti (R11'in yarattigi kilidin rot'la aklanmasi, d4 +8.64mm).
            # "auto" tavani BURADA cozulur (uretim_r11 n_placed bilmez);
            # tavan ROT tavanidir (rot denetimi ucuz, K-52) — R11 degil.
            rot_izin = ((n <= ROT_KABUL_AUTO_PARCA_TAVANI)
                        if rot_kabul == "auto" else bool(rot_kabul))
            sonuc = uretim_r11(meshes, clearance_mm=float(clearance_mm),
                               no_go_bounds=no_go_bounds,
                               samples_kompakt=int(r11_samples),
                               rot_kabul=rot_izin, rot_butce_s=rot_butce_s)
        except Exception as e:  # R11 hicbir kosulda cozumu dusuremez
            tel["r11"] = {"uygulandi": False, "neden": f"hata:{type(e).__name__}"}
            return
        if sonuc is None:
            tel["r11"] = {"uygulandi": False, "neden": "kapilar"}
        else:
            tel["r11"] = {"uygulandi": True, **sonuc}

    def _r11_zamanli(res, tel):
        """K-57 sure-kirilimi: r11 denemesinin duvar-saati tel['r11'] icine.

        r11 kapaliyken _r11_uygula tel'e dokunmaz -> anahtar da sure de
        eklenmez (bit-ozdes)."""
        _t = time.perf_counter()
        _r11_uygula(res, tel)
        if "r11" in tel:
            tel["r11"]["sure_s"] = round(time.perf_counter() - _t, 2)

    def _kilit(res):
        try:
            return int(check(list(res.placements), res.fine_voxel_parts).n_locked)
        except Exception:
            return None  # denetim kurulamadi -> bilinmiyor (guard'i yine de dene)

    def _rot_kabul_dene(res, tel):
        """Ham kilitliyken sokum-planli kabul denemesi (hoca 2026-07-14).

        True donerse cagiran guard'i ATLAR. Hata/kilit -> False + durust iz."""
        if not rot_kabul:
            return False
        n = int(res.n_placed)
        if rot_kabul == "auto" and n > ROT_KABUL_AUTO_PARCA_TAVANI:
            tel["rot_kabul"] = {"uygulandi": False, "neden": "parca_tavani",
                                "n_placed": n,
                                "tavan": ROT_KABUL_AUTO_PARCA_TAVANI}
            return False
        try:
            if _check_rot is not None:
                rapor = _check_rot(res)
            else:
                from src.nesting3d.continuous_settle import kilit_rot_meshes
                from src.nesting3d.export_stl import placed_meshes
                meshes = placed_meshes(list(res.placements),
                                       res.fine_voxel_parts,
                                       float(res.fine_pitch))
                rapor = kilit_rot_meshes(meshes, sure_butcesi_s=rot_butce_s)
        except Exception as e:
            tel["rot_kabul"] = {"uygulandi": False,
                                "neden": f"hata:{type(e).__name__}"}
            return False
        rk = int(rapor.n_locked)
        if rk > 0:
            tel["rot_kabul"] = {"uygulandi": False, "neden": "rot_kilitli",
                                "rot_kilit": rk}
            return False
        # K-52 musteri-yuzu: sokum talimatlari parca kimligiyle eslenir
        # (kilit_rot_meshes pid'i "m{i}" = res.placements sirasi).
        pls = list(res.placements)
        plan = []
        for pid, cert in rapor.certificates.items():
            s = str(pid)
            parca = None
            part_id = None  # HD-1: instance kimligi — UI join'i bununla yapar
            if s.startswith("m"):
                try:
                    idx = int(s[1:])
                except ValueError:
                    idx = None
                if idx is not None and 0 <= idx < len(pls):
                    pl = pls[idx]
                    part_id = getattr(pl, "part_id", None)
                    parca = (getattr(pl, "name", None)
                             or part_id or str(pl))
            plan.append({"parca": parca if parca is not None else s,
                         "part_id": part_id,
                         "eksen": getattr(cert, "eksen", None),
                         "aci_deg": float(getattr(cert, "aci_deg", 0.0) or 0.0),
                         "yon": getattr(cert, "yon", None),
                         "lift_vox": int(getattr(cert, "lift_vox", 0) or 0)})
        # P1: birlesik TAM cikis sirasi (peel + rot, ciktiklari anda) da
        # tasinir — rapor.removable_order "m{i}" -> instance part_id.
        sira = []
        for spid in getattr(rapor, "removable_order", None) or []:
            s2 = str(spid)
            hedef = s2
            if s2.startswith("m"):
                try:
                    idx2 = int(s2[1:])
                except ValueError:
                    idx2 = None
                if idx2 is not None and 0 <= idx2 < len(pls):
                    hedef = getattr(pls[idx2], "part_id", None) or s2
            sira.append(hedef)
        tel["rot_kabul"] = {"uygulandi": True, "rot_kilit": 0,
                            "cert": len(rapor.certificates),
                            "sokum_plani": plan,
                            **({"sokum_sirasi": sira} if sira else {})}
        return True

    _ts = time.perf_counter()
    ham = solve(instance, plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
                fine_pitch=float(clearance_mm), quality=quality, seed=seed,
                n_orientations=n_orientations, time_budget_sec=time_budget_sec,
                clearance_mm=float(clearance_mm), no_go_bounds=no_go_bounds,
                orientation_overrides=orientation_overrides,
                pinned_placements=pinned_placements)
    _solve_ham_s = time.perf_counter() - _ts
    _ts = time.perf_counter()
    ham_kilit = _kilit(ham)
    _kilit5_s = time.perf_counter() - _ts
    tel = {"recete": "nfv_kalite(K-36/41/44)", "pitch_mm": float(clearance_mm),
           "ham_height_mm": float(ham.height_mm), "ham_n_locked": ham_kilit,
           "guard_kosuldu": False, "guard_height_mm": None,
           "guard_n_locked": None, "secilen": "ham",
           # K-57 sure-kirilimi (davranis-notr telemetri)
           "solve_ham_s": round(_solve_ham_s, 2),
           "kilit5_s": round(_kilit5_s, 2)}
    if not ham_kilit:  # 0 veya None-degil-0 -> ham kilitsiz, guard vergisi odenmez
        if ham_kilit == 0:
            _r11_zamanli(ham, tel)
            tel["sure_s"] = round(time.perf_counter() - t0, 1)
            return ham, tel

    # ham KESIN kilitli (>0): guard vergisinden once rot-sokum kabulu dene
    # (hoca 2026-07-14: "zor cikan ama cikabilen" red sebebi degil).
    if ham_kilit:
        _ts = time.perf_counter()
        _rot_ok = _rot_kabul_dene(ham, tel)
        if "rot_kabul" in tel:
            tel["rot_kabul"]["sure_s"] = round(time.perf_counter() - _ts, 2)
        if _rot_ok:
            _r11_zamanli(ham, tel)
            tel["sure_s"] = round(time.perf_counter() - t0, 1)
            return ham, tel  # secilen="ham" (init degeri), guard_kosuldu=False

    _ts = time.perf_counter()
    guard = solve(instance, plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
                  fine_pitch=float(clearance_mm), quality=quality, seed=seed,
                  n_orientations=n_orientations, time_budget_sec=time_budget_sec,
                  clearance_mm=float(clearance_mm), no_go_bounds=no_go_bounds,
                  exit_guard=True,
                  orientation_overrides=orientation_overrides,
                  pinned_placements=pinned_placements)
    _solve_guard_s = time.perf_counter() - _ts
    _ts = time.perf_counter()
    guard_kilit = _kilit(guard)
    tel["kilit5_s"] = round(tel["kilit5_s"] + time.perf_counter() - _ts, 2)
    tel["solve_guard_s"] = round(_solve_guard_s, 2)
    tel.update(guard_kosuldu=True, guard_height_mm=float(guard.height_mm),
               guard_n_locked=guard_kilit)
    # Secim: kilitsiz olan kazanir; ikisi de kilitsiz/bilinmiyorsa alcak olan.
    ham_ok = ham_kilit == 0
    guard_ok = guard_kilit == 0
    if guard_ok and not ham_ok:
        secilen = ("guard", guard)
    elif ham_ok and not guard_ok:
        secilen = ("ham", ham)
    else:
        secilen = ("ham", ham) if ham.height_mm <= guard.height_mm else ("guard", guard)
    tel["secilen"] = secilen[0]
    _r11_zamanli(secilen[1], tel)
    tel["sure_s"] = round(time.perf_counter() - t0, 1)
    return secilen[1], tel
