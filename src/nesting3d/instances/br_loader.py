"""br_loader.py — Bischoff-Ratcliff BR1-BR15 instance yükleyici.

Yöntem: OR-Library ham dosyaları bu repoda mevcut olmadığından (internet erişimi
yok; bkz. data/br/README_br.md), yayınlanmış üretici parametrelerinden
(Bischoff & Ratcliff 1995, Tablo 2/3) seed'li yeniden üretim yapılır.

Konteyner: 100 x 100 x 100 birim (orijinal makaledeki standart; mm varsayılır).

Kullanım:
    from src.nesting3d.instances.br_loader import load_br_instance, BR_CLASSES

    inst = load_br_instance("BR1", instance_idx=0)
    # veya hepsini:
    for cls in BR_CLASSES:
        for idx in range(5):
            inst = load_br_instance(cls, instance_idx=idx)
"""

from __future__ import annotations

import hashlib
import random
from typing import Dict, List, NamedTuple, Tuple

from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
)


# ---------------------------------------------------------------------------
# Sınıf parametreleri (Bischoff & Ratcliff 1995, Tablo 2/3)
# ---------------------------------------------------------------------------

class _BRClassParams(NamedTuple):
    n_types_range: Tuple[int, int]   # kaç farklı kutu tipi
    qty_range: Tuple[int, int]       # toplam adet aralığı
    w_range: Tuple[int, int]         # genişlik (mm/birim)
    d_range: Tuple[int, int]         # derinlik
    h_range: Tuple[int, int]         # yükseklik


BR_CLASS_PARAMS: Dict[str, _BRClassParams] = {
    "BR1":  _BRClassParams((1, 1),   (50, 150),  (1, 5),   (1, 5),   (1, 5)),
    "BR2":  _BRClassParams((3, 5),   (50, 150),  (1, 5),   (1, 5),   (1, 5)),
    "BR3":  _BRClassParams((3, 5),   (20, 80),   (1, 10),  (1, 10),  (1, 10)),
    "BR4":  _BRClassParams((3, 8),   (20, 80),   (1, 15),  (1, 15),  (1, 15)),
    "BR5":  _BRClassParams((3, 8),   (10, 40),   (5, 20),  (5, 20),  (5, 20)),
    "BR6":  _BRClassParams((1, 3),   (100, 300), (1, 4),   (1, 4),   (1, 4)),
    "BR7":  _BRClassParams((3, 5),   (80, 200),  (2, 8),   (2, 8),   (2, 8)),
    "BR8":  _BRClassParams((3, 8),   (30, 100),  (5, 15),  (5, 15),  (5, 15)),
    "BR9":  _BRClassParams((5, 10),  (30, 80),   (1, 15),  (1, 15),  (1, 15)),
    "BR10": _BRClassParams((5, 10),  (20, 60),   (1, 20),  (1, 20),  (1, 20)),
    "BR11": _BRClassParams((2, 4),   (60, 180),  (3, 12),  (3, 12),  (3, 12)),
    "BR12": _BRClassParams((3, 6),   (20, 60),   (1, 20),  (1, 20),  (1, 5)),
    "BR13": _BRClassParams((3, 6),   (20, 60),   (1, 5),   (1, 5),   (1, 20)),
    "BR14": _BRClassParams((3, 8),   (20, 80),   (1, 15),  (1, 15),  (1, 15)),
    "BR15": _BRClassParams((5, 10),  (30, 90),   (1, 20),  (1, 20),  (1, 20)),
}

BR_CLASSES: List[str] = [f"BR{i}" for i in range(1, 16)]

# Orijinal makale standardı
_CONTAINER = ContainerSpec(width_mm=100.0, depth_mm=100.0, height_mm=None)

N_INSTANCES_PER_CLASS: int = 5  # her sınıf için üretilen örnek sayısı


# ---------------------------------------------------------------------------
# Üretici
# ---------------------------------------------------------------------------

def _make_seed(class_name: str, instance_idx: int) -> int:
    """Sınıf adı + indeks -> deterministik seed (süreç-arası sabit).

    hashlib.sha256 kullanılır; hash() PYTHONHASHSEED'e bağlı olduğundan
    süreç-arası deterministik değildir.
    """
    key = f"{class_name}_{instance_idx}".encode()
    return int(hashlib.sha256(key).hexdigest(), 16) % (2 ** 31)


def generate_br_instance(
    class_name: str,
    instance_idx: int = 0,
) -> NestingInstance:
    """Yayınlanmış parametrelerden seed'li BR instance üret.

    Args:
        class_name:    "BR1" .. "BR15"
        instance_idx:  0 .. N_INSTANCES_PER_CLASS-1

    Returns:
        NestingInstance — konteyner 100x100xNone, parçalar box source.

    Raises:
        KeyError: class_name bilinmiyor.
        ValueError: instance_idx sınır dışı.
    """
    if class_name not in BR_CLASS_PARAMS:
        raise KeyError(f"Bilinmeyen BR sınıfı: '{class_name}'. "
                       f"Geçerli: {list(BR_CLASS_PARAMS)}")
    if not (0 <= instance_idx < N_INSTANCES_PER_CLASS):
        raise ValueError(
            f"instance_idx {instance_idx} geçersiz; "
            f"[0, {N_INSTANCES_PER_CLASS}) aralığında olmalı."
        )

    params = BR_CLASS_PARAMS[class_name]
    seed = _make_seed(class_name, instance_idx)
    rng = random.Random(seed)

    n_types = rng.randint(*params.n_types_range)
    total_qty = rng.randint(*params.qty_range)

    # Her tipin boyutlarını oluştur
    type_dims: List[Tuple[float, float, float]] = []
    for _ in range(n_types):
        w = float(rng.randint(*params.w_range))
        # BR14: kare taban — d, w ile aynı (tek randint tüketilir)
        d = w if class_name == "BR14" else float(rng.randint(*params.d_range))
        h = float(rng.randint(*params.h_range))
        type_dims.append((w, d, h))

    # Toplam adedi tipler arasında böl (rastgele bölme)
    # Son tip kalan adedi alır
    qtys: List[int] = []
    remaining = total_qty
    for i in range(n_types - 1):
        min_q = 1
        max_q = remaining - (n_types - i - 1)
        q = rng.randint(min_q, max(min_q, max_q))
        qtys.append(q)
        remaining -= q
    qtys.append(remaining)

    parts: List[PartSpec] = []
    for i, ((w, d, h), qty) in enumerate(zip(type_dims, qtys)):
        parts.append(PartSpec(
            id=f"{class_name}_{instance_idx:02d}_type{i+1:02d}",
            name=f"type{i+1:02d}",
            qty=qty,
            source="box",
            width_mm=w,
            depth_mm=d,
            height_mm=h,
        ))

    return NestingInstance(
        container=_CONTAINER,
        parts=parts,
        meta={
            "family": "bischoff_ratcliff",
            "class": class_name,
            "instance_idx": instance_idx,
            "seed": seed,
            "n_types": n_types,
            "total_qty": total_qty,
            "source_method": "seed_regenerated",
            "reference": "Bischoff & Ratcliff (1995), Eur. J. Oper. Res. 84, 435-461",
        },
    )


def load_br_instance(
    class_name: str,
    instance_idx: int = 0,
    data_dir: "str | None" = None,
) -> NestingInstance:
    """BR instance yükle (şu an generate_br_instance çağırır).

    Ham OR-Library dosyası data/br/<class_name>_<idx:02d>.json varsa onu yükler;
    yoksa seed'li yeniden üretim yapar.

    Args:
        class_name:    "BR1" .. "BR15"
        instance_idx:  0 .. N_INSTANCES_PER_CLASS-1
        data_dir:      JSON cache dizini; None ise repo kökündeki data/br/ kullanılır.
                       Test amaçlı tmp_path girebilmek için opsiyonel.

    Bu fonksiyon ileride OR-Library dosyalarına erişim sağlanınca ham veriyi
    okuyacak şekilde genişletilebilir — arayüz değişmez.
    """
    from pathlib import Path

    if data_dir is None:
        _data_dir = Path(__file__).resolve().parents[3] / "data" / "br"
    else:
        _data_dir = Path(data_dir)

    json_path = _data_dir / f"{class_name}_{instance_idx:02d}.json"

    if json_path.exists():
        from src.nesting3d.instances.format import NestingInstance as _NI
        return _NI.from_json(json_path)

    return generate_br_instance(class_name, instance_idx)


def _parse_orlibrary_file(path: str) -> NestingInstance:  # noqa: ARG001
    """OR-Library ham dosyasını parse et (STUB — henüz uygulanmadı).

    Ham OR-Library dosyasına erişim sağlanınca bu fonksiyon implement edilir.
    """
    raise NotImplementedError(
        "OR-Library ham dosyası parser'ı henüz uygulanmadı. "
        "data/br/README_br.md'ye bakın."
    )
