"""bin3d.py — open-top bin with heightmap state (PLAN_3D.md §2.3, §2.4).

The bin has a fixed base (plate_w x plate_d mm, voxelized at `pitch`) and an
unbounded height — the quantity being minimized.  State is a 2D heightmap
H[x, y] (int, voxel units): the top of the tallest occupied voxel per column.

Known, accepted limitation (PLAN_3D.md §2.4): a heightmap cannot slide parts
into cavities under overhangs.  Honest trade-off for fast SA decodes.
"""

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from src.nesting3d.voxelize import Orientation, VoxelPart

# Dirty aday-penceresi bu orandan buyukse yerel yeniden-hesap tam-hesaptan ucuz
# DEGIL (kopya ek-yuku) -> tam yola dus (tip-gecisi / plaka-parca sicramalari).
_DC_FALLBACK_FRAC = 0.75



@dataclass
class Placement3D:
    """One placed part: voxel cell (x, y, z) of its grid's (0,0,0) corner."""

    part_id: str
    name: str
    x: int
    y: int
    z: int
    orientation_idx: int


class Bin3D:
    """Heightmap bin. All placement math is in voxel units; mm at the edges."""

    # NO-GO muhur sentineli (voxel): drop bu kolonlara ASLA oturamaz (argmin
    # dogal olarak kacinir). int32 guvenli; z_clearance toplami tasma yapmaz.
    NO_GO_SEAL: int = 500_000

    def __init__(self, plate_w_mm: float = 220.0, plate_d_mm: float = 220.0,
                 pitch: float = 220.0 / 64, z_clearance: int = 0,
                 drop_cache: bool = False, drop_cache_cap_mb: float = 300.0,
                 no_go_mask=None):
        self.plate_w_mm = float(plate_w_mm)
        self.plate_d_mm = float(plate_d_mm)
        self.pitch = float(pitch)
        # z_clearance: parça başka parça ÜZERİNE oturduğunda araya konan boş
        # hücre sayısı (voxel).  Yatay boşluk voxelize._dilate'te; dikey boşluk
        # burada tek taraflı verilir — çift taraflı z-dilation'dan yarı maliyet
        # (hoca min 1 mm şartı, 2026-06-11).  Plakaya oturan parça (drop z=0)
        # yükseltilmez.
        self.z_clearance = int(z_clearance)
        self.nx = int(plate_w_mm // pitch)
        self.ny = int(plate_d_mm // pitch)
        self.height = np.zeros((self.nx, self.ny), dtype=np.int32)
        # NO-GO area (2026-07-07, hoca gercek-makine kisiti): yasak bolge
        # kolonlari NO_GO_SEAL ile muhurlenir -> drop/argmin oraya yerlesim
        # koyamaz. default None = BIT-OZDES eski davranis. Metrikler
        # (max/mean/rms/density) muhurlu kolonlari YOK SAYAR.
        self._no_go = None
        if no_go_mask is not None:
            m = np.asarray(no_go_mask, dtype=bool)
            if m.shape != (self.nx, self.ny):
                raise ValueError(
                    f"no_go_mask sekli {m.shape} != grid ({self.nx},{self.ny})")
            if m.any():
                self._no_go = m
                self.height[m] = self.NO_GO_SEAL
        self.placements: List[Placement3D] = []
        self.placed_voxels: int = 0

        # -- H-16 dirty-region drop_map onbellegi (OPT-IN, default KAPALI) ----
        # Bu bos OrderedDict/deque/sayac alanlari HER ZAMAN kurulur (asagida) —
        # bu, sabit ve ihmal edilebilir bir allocation'dir. Kapaliyken
        # drop_map/place kod yolu davranissal olarak BIREBIR eski: `_dc_enabled`
        # False oldugu icin sicak yolda TEK bir bool okunur ve dallar hep
        # onbelleksiz yola gider (kurulu-ama-bos yapilar hic dokunulmaz kalir,
        # ekstra hesap/kopya yok). Acikken footprint-anahtarli (id(orient)) Z
        # onbellegi tutulur; ayni-model ozdes parca ORNEKLERI ayni Orientation
        # nesnesini PAYLASIR (voxelize.expand_quantities:
        # orientations=template.orientations) -> id(orient) ozdes footprint'leri
        # gruplar, cache HIT'i oradan gelir.
        self._dc_enabled: bool = bool(drop_cache)
        self._dc_cap_bytes: int = int(drop_cache_cap_mb * 2 ** 20)
        self._dc_fallback_frac: float = _DC_FALLBACK_FRAC
        # aradaki place sayisi bunu asarsa disjoint-pencere ek-yuku tam-hesabi
        # gecer -> tam yola dus (dagilmis-cok-yerlesim koruma).
        self._dc_max_windows: int = 96
        # key=id(orient) -> [orient_ref, Z, seq]; OrderedDict = LRU siralamasi
        self._dc_cache: "OrderedDict[int, list]" = OrderedDict()
        # her place()'in degistirdigi H bbox'i: (seq, (r0, r1, c0, c1))
        self._dc_log: "Deque[Tuple[int, Tuple[int, int, int, int]]]" = deque()
        self._dc_seq: int = 0            # monoton place() sayaci
        self._dc_bytes: int = 0          # onbellekteki toplam Z byte
        # istatistik (KAPI olcumu icin)
        self._dc_hits: int = 0           # artimli + degismedi (yerel/kopyasiz)
        self._dc_miss: int = 0           # girisi yok -> tam hesap
        self._dc_fallback: int = 0       # giris var ama pencere buyuk -> tam
        self._dc_evictions: int = 0
        self._dc_peak_bytes: int = 0
        self._dc_peak_keys: int = 0

    # -- placement ----------------------------------------------------------

    def drop_map(self, orient: Orientation) -> Optional[np.ndarray]:
        """Drop-z for EVERY feasible (x, y) of this orientation, vectorized.

        Returns an (nx-fw+1, ny-fh+1) int array, or None when the footprint
        does not fit the base at all.  Z[x, y] = the rest height of the part's
        grid origin if dropped at (x, y):
            max over filled columns (i, j) of H[x+i, y+j] - bottom[i, j]

        Invariant (drop_cache=True olunca): donen dizi cache-ICI paylasilan bir
        buffer OLABILIR (bir sonraki cagride yerinde guncellenir) — caller SALT-
        OKUR kullanmali, dondurulen array UZERINDE MUTASYON YAPMAMALI (mevcut
        caginlar — _best_position/tower_order/place_in_order — dogrulandi,
        yalniz okuyor). Kapaliyken (drop_cache=False, uretim default) her
        cagri taze bir dizi doner, bu kisitlama gecerli degildir.
        """
        # H-16 OPT-IN: dirty-region onbellegi. KAPALI iken (uretim default) tek
        # bool okunur, kalan kod yolu BIREBIR eski (davranis/allocation ozdes).
        if self._dc_enabled:
            return self._drop_map_cached(orient)

        fw, fh = orient.filled.shape
        npx, npy = self.nx - fw + 1, self.ny - fh + 1
        if npx <= 0 or npy <= 0:
            return None

        # Hizli yol: dolu-dikdortgen footprint + tek-deger taban (KUTU parcalar)
        # → ayrik kayan-maksimum, ~25x hizli. Konkav footprint / degisken taban
        # (numune STL) None doner ve genel donguye duser. Sonuc bire bir ayni.
        fast = self._drop_map_fast(orient, npx, npy)
        if fast is not None:
            return fast

        return self._drop_map_general(orient, npx, npy)

    def _drop_map_full(self, orient: Orientation, npx: int, npy: int
                       ) -> np.ndarray:
        """Tam (onbelleksiz) drop_map — hizli yol, yoksa genel yol. Kapali-yol
        ile BIREBIR ayni sonuc; cache MISS/fallback bunu cagirir."""
        fast = self._drop_map_fast(orient, npx, npy)
        if fast is not None:
            return fast
        return self._drop_map_general(orient, npx, npy)

    # -- H-16 dirty-region onbellegi (yalniz drop_cache=True iken calisir) ----

    def _drop_map_cached(self, orient: Orientation) -> Optional[np.ndarray]:
        """Onbellekli drop_map. Ayni footprint-anahtari (id(orient)) icin son
        tam Z saklanir; sonraki cagrida yalniz aradaki place()'lerin KIRLETTIGI
        aday-penceresi yeniden hesaplanir, gerisi Z_prev'den kopyalanir.

        Dogruluk: yerel yeniden-hesap tam-hesapla tamsayi max-reduksiyonu
        AYNIDIR (h16_on_analiz: sizinti 0/20, bit-ozdes 20/20) -> yukseklik ve
        yerlesim BIREBIR degismez. Pencere buyukse veya giris yoksa tam yola
        dusulur (kalite her kosulda korunur)."""
        fw, fh = orient.filled.shape
        npx, npy = self.nx - fw + 1, self.ny - fh + 1
        if npx <= 0 or npy <= 0:
            return None

        key = id(orient)
        entry = self._dc_cache.get(key)
        if entry is not None and entry[0] is orient:
            if entry[2] == self._dc_seq:
                # Hicbir place() olmadi -> Z aynen gecerli (kopya bile gerekmez;
                # cagiran Z'yi salt-okur kullanir: _best_position/tower_order).
                self._dc_cache.move_to_end(key)
                self._dc_hits += 1
                return entry[1]
            wins = self._dc_windows_since(entry[2], fw, fh, npx, npy)
            if wins is not None:
                # DISJOINT kirli pencereler (place BASINA ayri) -> her biri
                # kucuk kalir; birlesik-bbox uzak-kose sismesinden kacinir.
                Z = entry[1].copy()
                filled = orient.filled
                bf = orient.bottom[filled].astype(np.int32, copy=False)
                for (wx0, wx1, wy0, wy1) in wins:
                    self._drop_region_into(
                        Z, filled, bf, fw, fh, wx0, wx1, wy0, wy1)
                entry[1] = Z
                entry[2] = self._dc_seq
                self._dc_cache.move_to_end(key)
                self._dc_hits += 1
                return Z
            # wins is None -> kirli alan cok buyuk/dagilmis, tam hesap ucuz
            self._dc_fallback += 1
        else:
            self._dc_miss += 1

        Z = self._drop_map_full(orient, npx, npy)
        self._dc_put(key, orient, Z)
        return Z

    def _drop_region_into(self, Z: np.ndarray, filled: np.ndarray,
                          bf: np.ndarray, fw: int, fh: int, x0: int, x1: int,
                          y0: int, y1: int) -> None:
        """Z'nin [x0:x1, y0:y1] aday penceresini YERINDE yeniden hesapla —
        `_drop_map_general` ile AYNI vektorize tamsayi max-reduksiyonu, yalniz
        bu pencere (sliding_window_view H alt-blogu uzerinde). bf = dolu
        kolonlarin tabani (cagri basi bir kez). max birlesmeli + tamsayi ->
        full drop_map ile BIRE BIR ayni."""
        if bf.size == 0:            # bos footprint (gercek parcada olmaz)
            Z[x0:x1, y0:y1] = 0
            return
        wy = y1 - y0
        K = int(bf.shape[0])
        # Bu pencere icin gerekli H alt-blogu: aday (x0..x1) footprint (fw,fh)
        subH = self.height[x0:x1 + fw - 1, y0:y1 + fh - 1]
        W = sliding_window_view(subH, (fw, fh))     # (wx, wy, fw, fh) view
        # Bellek tavani: (blok, wy, K) int32 pencere kopyasi (general ile ayni)
        CAP = 16_000_000
        per_row = wy * K
        rows = max(1, CAP // per_row) if per_row else (x1 - x0)
        for bx0 in range(0, x1 - x0, rows):
            bx1 = min(bx0 + rows, x1 - x0)
            Wf = W[bx0:bx1, :, filled]              # (blok, wy, K) kopya
            Wf -= bf
            acc = Wf.max(axis=2)                    # (blok, wy)
            np.maximum(acc, 0, out=acc)
            if self.z_clearance:
                acc[acc > 0] += self.z_clearance
            Z[x0 + bx0:x0 + bx1, y0:y1] = acc

    def _drop_region(self, orient: Orientation, x0: int, x1: int,
                     y0: int, y1: int) -> np.ndarray:
        """Aday alt-dikdortgen [x0:x1, y0:y1] icin YEREL drop hesabi (bagimsiz
        (x1-x0, y1-y0) dizi dondurur — testler kullanir). Hot yol
        `_drop_region_into` ile ayni tamsayi max-reduksiyonu."""
        ci, cj = np.nonzero(orient.filled)
        bvals = orient.bottom[ci, cj].astype(np.int32, copy=False)
        H = self.height
        acc = np.zeros((x1 - x0, y1 - y0), dtype=np.int32)
        for i, j, b in zip(ci.tolist(), cj.tolist(), bvals.tolist()):
            np.maximum(acc, H[x0 + i:x1 + i, y0 + j:y1 + j] - b, out=acc)
        np.maximum(acc, 0, out=acc)
        if self.z_clearance:
            acc[acc > 0] += self.z_clearance
        return acc

    def _dc_windows_since(self, entry_seq: int, fw: int, fh: int,
                          npx: int, npy: int):
        """entry_seq'ten SONRAKI HER place()'i AYRI bir aday-penceresine cevir
        (bbox birlesimi DEGIL — uzak yerlesimler tek dev pencereye sismesin).

        Her place H bbox'i sorgu footprint'ine (fw,fh) gore genisletilir + kirpilir.
        Doner:
          [(wx0,wx1,wy0,wy1), ...] — yeniden-hesaplanacak disjoint pencereler
          None — toplam alan / pencere sayisi cok buyuk -> tam hesap daha ucuz
        (Cagiran zaten entry_seq==_dc_seq durumunu (degismedi) elemistir.)
        """
        wins = []
        area = 0
        cap = self._dc_fallback_frac * npx * npy
        for seq, bb in self._dc_log:
            if seq <= entry_seq:
                continue
            r0, r1, c0, c1 = bb
            wx0 = r0 - fw + 1
            if wx0 < 0:
                wx0 = 0
            wx1 = r1 if r1 < npx else npx
            wy0 = c0 - fh + 1
            if wy0 < 0:
                wy0 = 0
            wy1 = c1 if c1 < npy else npy
            if wx0 >= wx1 or wy0 >= wy1:
                continue
            wins.append((wx0, wx1, wy0, wy1))
            area += (wx1 - wx0) * (wy1 - wy0)
            if area >= cap or len(wins) > self._dc_max_windows:
                return None
        return wins

    def _dc_put(self, key: int, orient: Orientation, Z: np.ndarray) -> None:
        """Cache'e Z yaz (LRU); bellek tavani asilirsa en eski anahtari at
        (atma = sonraki cagri tam-hesap; DOGRULUK hic bozulmaz)."""
        cache = self._dc_cache
        old = cache.get(key)
        if old is not None:
            self._dc_bytes -= old[1].nbytes
        cache[key] = [orient, Z, self._dc_seq]
        cache.move_to_end(key)
        self._dc_bytes += Z.nbytes
        while self._dc_bytes > self._dc_cap_bytes and len(cache) > 1:
            _k, ev = cache.popitem(last=False)
            self._dc_bytes -= ev[1].nbytes
            self._dc_evictions += 1
        if self._dc_bytes > self._dc_peak_bytes:
            self._dc_peak_bytes = self._dc_bytes
        if len(cache) > self._dc_peak_keys:
            self._dc_peak_keys = len(cache)

    def _dc_prune_log(self) -> None:
        """place-log'un artik hicbir cache girisinin ihtiyac duymadigi eski
        bbox'larini at (log basi seq'ler ARTAN sirada -> onden kirp)."""
        cache = self._dc_cache
        if not cache:
            self._dc_log.clear()
            return
        oldest = min(e[2] for e in cache.values())
        log = self._dc_log
        while log and log[0][0] <= oldest:
            log.popleft()

    def drop_cache_stats(self) -> Dict[str, object]:
        """H-16 onbellek istatistikleri (KAPI olcumu). Kapaliyken sifirlar."""
        total = self._dc_hits + self._dc_miss + self._dc_fallback
        return {
            "enabled": self._dc_enabled,
            "hits": self._dc_hits,
            "misses": self._dc_miss,
            "fallbacks": self._dc_fallback,
            "full_computes": self._dc_miss + self._dc_fallback,
            "hit_ratio": (self._dc_hits / total) if total else 0.0,
            "keys": len(self._dc_cache),
            "peak_keys": self._dc_peak_keys,
            "peak_bytes": self._dc_peak_bytes,
            "peak_mb": self._dc_peak_bytes / 2 ** 20,
            "evictions": self._dc_evictions,
            "cap_mb": self._dc_cap_bytes / 2 ** 20,
        }

    def _drop_map_general(self, orient: Orientation, npx: int, npy: int
                          ) -> np.ndarray:
        """Konkav footprint / degisken taban genel yolu — VEKTORIZE.

        Z[x, y] = max over dolu kolon (i, j) of  H[x+i, y+j] - bottom[i, j].
        Eski hali dolu kolonlar uzerinde Python `for` dongusuydu (cProfile:
        tottime %72, motorun gercek darbogazi; gercek STL parcalari konkav →
        hizli yol None doner, bu genel yola duser). Burada ayni redaksiyon
        `sliding_window_view` ile tek numpy reduksiyonuna cekildi: kayan pencere
        son iki eksende footprint maskesiyle indekslenir (dolu kolonlar), taban
        cikarilir, son eksende max alinir. max birlesmeli/yer-degistirmeli ve
        islem tamsayi (yuvarlamasiz) oldugundan sonuc Python dongusuyle BIRE BIR
        AYNI — yalnizca hizlanir, yukseklik degismez (kalite garantisi).

        Bellek: pencere kopyasi (blok, npy, K) int32 (K = dolu kolon sayisi).
        Tepe noktayi sinirlamak icin x ekseni bloklara bolunur; bir satir bile
        CAP'i asarsa (cok nadir, devasa footprint) guvenli yavas dongu yoluna
        dusulur (`_drop_map_loop`) — regresyon/OOM yok.
        """
        filled = orient.filled
        bf = orient.bottom[filled].astype(np.int32, copy=False)  # (K,)
        K = int(bf.shape[0])
        if K == 0:  # bos footprint (gercek parcalarda olmaz) — dongu ile ayni
            return np.zeros((npx, npy), dtype=np.int32)

        CAP = 16_000_000  # ~64 MB int32 pencere tepe noktasi
        per_row = npy * K
        if per_row > CAP:  # tek x-satiri bile sigmiyor → guvenli dongu fallback
            return self._drop_map_loop(orient, npx, npy)
        rows = max(1, CAP // per_row)

        fw, fh = filled.shape
        W = sliding_window_view(self.height, (fw, fh))  # view (npx,npy,fw,fh)
        Z = np.empty((npx, npy), dtype=np.int32)
        for x0 in range(0, npx, rows):
            x1 = min(x0 + rows, npx)
            Wf = W[x0:x1, :, filled]   # (blok, npy, K) kopya — dolu kolonlar
            Wf -= bf                   # taban cikar (broadcast son eksen)
            Wf.max(axis=2, out=Z[x0:x1])
        np.maximum(Z, 0, out=Z)
        if self.z_clearance:
            Z[Z > 0] += self.z_clearance  # parça üstüne oturma -> dikey boşluk
        return Z

    def _drop_map_loop(self, orient: Orientation, npx: int, npy: int
                       ) -> np.ndarray:
        """drop_map genel yolunun saf-Python dongu referansi — yalniz devasa
        footprint icin bellek-guvenli fallback (`_drop_map_general` CAP asiminda
        cagirir). Vektorize yolla bire bir ayni sonucu uretir."""
        Z = np.zeros((npx, npy), dtype=np.int32)
        cols_i, cols_j = np.nonzero(orient.filled)
        for i, j, b in zip(cols_i, cols_j, orient.bottom[cols_i, cols_j]):
            np.maximum(Z, self.height[i:i + npx, j:j + npy] - b, out=Z)
        np.maximum(Z, 0, out=Z)
        if self.z_clearance:
            Z[Z > 0] += self.z_clearance  # parça üstüne oturma -> dikey boşluk
        return Z

    def _drop_map_fast(self, orient: Orientation, npx: int, npy: int
                       ) -> Optional[np.ndarray]:
        """drop_map'in hizli yolu — sadece dolu-dikdortgen + tek-deger taban.

        Kutu parcalar icin (filled tamamen dolu, bottom her kolonda ayni deger
        b0) drop_map = H'nin (fw x fh) sol-hizali penceresi uzerinde kayan-
        maksimum eksi b0. Islem AYRILABILIR: once eksen0 boyunca fw kaydirma,
        sonra eksen1 boyunca fh kaydirma — her biri O(npx*npy) numpy maksimumu.
        Toplam O((fw+fh)*npx*npy), dongunun O(fw*fh*npx*npy)'sine kiyasla cok
        daha ucuz. Kaydirma kurulumu sol-hizali valid pencereyi INSA YOLUYLA
        garantiler (merkezleme/offset belirsizligi YOK); sonuc genel donguyle
        bire bir ayni.
        """
        filled = orient.filled
        if not filled.all():
            return None  # konkav footprint → genel yol
        bottom = orient.bottom
        b0 = int(bottom.flat[0])
        if not (bottom == b0).all():
            return None  # degisken taban → genel yol

        fw, fh = filled.shape
        H = self.height
        # Eksen0: m0[x, :] = max_{k in [0,fw)} H[x+k, :], x in [0, npx)
        m0 = H[:npx].copy()
        for k in range(1, fw):
            np.maximum(m0, H[k:k + npx], out=m0)
        # Eksen1: Z[x, y] = max_{k in [0,fh)} m0[x, y+k], y in [0, npy)
        Z = m0[:, :npy].copy()
        for k in range(1, fh):
            np.maximum(Z, m0[:, k:k + npy], out=Z)

        if b0:
            Z -= b0
        np.maximum(Z, 0, out=Z)
        if self.z_clearance:
            Z[Z > 0] += self.z_clearance
        return Z

    def drop_z(self, orient: Orientation, x: int, y: int) -> int:
        """Drop-z for a single (x, y) — used by tests and spot checks."""
        f = orient.filled
        sub = self.height[x:x + f.shape[0], y:y + f.shape[1]]
        vals = sub[f] - orient.bottom[f]
        z = max(int(vals.max()), 0)
        if self.z_clearance and z > 0:
            z += self.z_clearance
        return z

    def place(self, part: VoxelPart, orientation_idx: int,
              x: int, y: int, z: int) -> Placement3D:
        """Commit a placement: raise the heightmap by the part's top profile."""
        orient = part.orientations[orientation_idx]
        f = orient.filled
        fw, fh = f.shape
        sub = self.height[x:x + fw, y:y + fh]
        np.copyto(sub, np.maximum(sub, z + orient.top), where=f)

        # H-16: dirty-region logu (yalniz cache acikken). Degisen H hucreleri
        # yerlestirmenin footprint bbox'inin ICINDE (place yalniz orada yukseltir)
        # -> footprint bbox GUVENLI ust-kume (dirty pencere superset -> birebir).
        if self._dc_enabled:
            self._dc_seq += 1
            self._dc_log.append((self._dc_seq, (x, x + fw, y, y + fh)))
            self._dc_prune_log()

        p = Placement3D(part.id, part.name, x, y, z, orientation_idx)
        self.placements.append(p)
        self.placed_voxels += orient.voxel_count
        return p

    # -- metrics (PLAN_3D.md §2.6) -------------------------------------------

    def max_height_voxels(self) -> int:
        if self._no_go is not None:
            h = self.height[~self._no_go]
            return int(h.max()) if h.size else 0
        return int(self.height.max())

    def max_height_mm(self) -> float:
        return self.max_height_voxels() * self.pitch

    @staticmethod
    def no_go_mask_from_bounds(bounds, plate_w_mm: float, plate_d_mm: float,
                               pitch: float) -> np.ndarray:
        """Yasak bolge mm-bbox'undan grid maskesi (KONSERVATIF: bbox tabani).

        bounds: ((x0,y0),(x1,y1)) mm veya trimesh.bounds (3D — z yok sayilir).
        Kubbe/yuvarlak uclu no-go sekillerinde bbox bir miktar FAZLA yasaklar
        (guvenli yon; hoca kisiti asla ihlal edilmez). Hucre, bbox ile KESISIYORSA
        yasak (yarim hucre tasmasi da muhurlenir).
        """
        b = np.asarray(bounds, dtype=float)
        x0, y0 = float(b[0][0]), float(b[0][1])
        x1, y1 = float(b[1][0]), float(b[1][1])
        nx = int(plate_w_mm // pitch)
        ny = int(plate_d_mm // pitch)
        mask = np.zeros((nx, ny), dtype=bool)
        i0 = max(0, int(np.floor(x0 / pitch)))
        j0 = max(0, int(np.floor(y0 / pitch)))
        i1 = min(nx, int(np.ceil(x1 / pitch)))
        j1 = min(ny, int(np.ceil(y1 / pitch)))
        if i1 > i0 and j1 > j0:
            mask[i0:i1, j0:j1] = True
        return mask

    def mean_height_mm(self) -> float:
        """Average column height (no-go muhurlu kolonlar haric)."""
        h = self.height[~self._no_go] if self._no_go is not None else self.height
        return (float(h.mean()) if h.size else 0.0) * self.pitch

    def rms_height_mm(self) -> float:
        """Root-mean-square column height — the SA tie-breaker (compactness).

        Quadratic on purpose: a part standing tall on the floor and the same
        part lying flat can occupy the SAME column-volume (mean gives no
        gradient between them), but RMS strictly prefers the flat, spread-out
        pose.  That gradient is what lets SA walk off the max-height plateau.
        """
        hh = self.height[~self._no_go] if self._no_go is not None else self.height
        h = hh.astype(np.float64)
        return (float(np.sqrt((h * h).mean())) if h.size else 0.0) * self.pitch

    def packing_density(self) -> float:
        """Placed part volume / used envelope (base area x max height)."""
        h = self.max_height_mm()
        if h <= 0:
            return 0.0
        envelope = self.plate_w_mm * self.plate_d_mm * h
        return self.placed_voxels * self.pitch ** 3 / envelope

    def mesh_fill_ratio(self, part_volume_mm3: float) -> float:
        """Real mesh volume / used envelope (base area x max height).

        Second, independent fill metric that sits ALONGSIDE packing_density
        (which is left untouched).  packing_density uses the SWOLLEN voxel
        volume (placed_voxels * pitch**3) — voxelization rounds each part up to
        the pitch grid, so that number over-states occupancy on coarse pitches.
        This metric instead takes the TRUE mesh volume supplied by the caller
        (box parts = full w*d*h; STL parts = true_fill * bbox) and divides by the
        same envelope, giving the real material-fill fraction of the build box.

        The two are different axes on purpose (voxel-swelled vs. real-mesh); the
        report shows both.  Returns 0.0 when height/envelope is non-positive.
        """
        h = self.max_height_mm()
        if h <= 0:
            return 0.0
        envelope = self.plate_w_mm * self.plate_d_mm * h
        if envelope <= 0 or part_volume_mm3 <= 0:
            return 0.0
        return float(part_volume_mm3) / envelope
