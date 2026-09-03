"""selection/splits.py -- Aile-dengeli (stratified) + isim-bagimsiz hold-out bolme.

Neden bu modul (overfit dongusu sertlestirme, 2026-06-17)
---------------------------------------------------------
Eski `_split` (build_selection_model._split) tabloyu instance_id'ye gore
ALFABETIK sirayla alip SON %20'yi hold-out yapiyordu. Sonuc: hold-out tamamen
instance'a verilen ISME bagliydi. Kullanici "z_yeni" diye adlandirinca her yeni
instance hold-out'a, "a_yeni" diye adlandirinca her yeni instance train'e
duserdi -> overfit olcumu farkinda olmadan manipule edilebilir + hold-out
aile-dengesiz olur (bir aile hic temsil edilmez).

Bu modul stratified bolme yapar: hold-out HER aileden orantili pay alir.
Boylece tek bir isim-prefix'i tum hold-out'u kaplayamaz ve her aile hem
train'de hem hold-out'ta temsil edilir (1-NN komsu bulabilir).

Geriye-uyum garantisi
---------------------
Tek aile + zaten instance_id'ye gore sirali tablo durumunda
`stratified_holdout_split` ESKI `_split` ile BYTE-AYNI sonuc verir
(aile-ici sira korunur, son n_holdout alinir). gengap'in mevcut sentetik
testleri (hepsi aile="test") bu yuzden kirilmaz.

DEGiSMEZ-A: motor modullerini (bin3d/sa3d/dblf/voxelize) import etmez.
Determinizm: ayni tablo -> ayni bolme (rastgelelik yok).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Iterator, List, Tuple

from src.nesting3d.selection.dataset import TrainingRow


def _group_by_family(table: List[TrainingRow]) -> "OrderedDict[str, List[TrainingRow]]":
    """Instance'lari aileye gore grupla. Aile gorulus sirasi + aile-ici GELEN sira
    korunur (yeniden siralanmaz).

    Neden gelen sira korunur: cagiran (build_training_table) tabloyu zaten
    instance_id'ye gore siralayip verir -> aile-ici sira gercekte instance_id
    sirasidir. Burada YENIDEN siralamak, ham (sirasiz) listelerle cagrildiginda
    (or. gengap'in sentetik testleri) "hangi instance hold-out" karari beklenenden
    sapardi. Gelen sirayi koruyarak hem gercek pipeline hem ham-liste cagrilari
    deterministik ve ongorulebilir kalir."""
    groups: "OrderedDict[str, List[TrainingRow]]" = OrderedDict()
    for row in table:
        groups.setdefault(row.aile, []).append(row)
    return groups


def stratified_holdout_split(
    table: List[TrainingRow],
    holdout_ratio: float = 0.2,
) -> Tuple[List[TrainingRow], List[TrainingRow]]:
    """Aile-dengeli, isim-bagimsiz train/hold-out bolme.

    Her aileden `holdout_ratio` oraninda (en az aile basina 0, toplam en az 1)
    instance hold-out'a alinir. Aile-ici secim: instance_id'ye gore sirali
    listenin SONUNDAN alinir (deterministik + tek-aile durumunda eski _split
    ile ozdes).

    Args:
        table:         TrainingRow listesi.
        holdout_ratio: Hold-out orani (varsayilan 0.2).

    Returns:
        (train, holdout) -- ikisi de instance_id'ye gore sirali.

    Garanti:
        - Toplam >= 1 instance varsa hold-out en az 1 instance icerir.
        - Her aile icin: aile boyutu >= 2 ise o aileden en az 1 hold-out alinir
          (kucuk aileler train'e oncelik verir; aile boyutu 1 ise train'de kalir).
        - train ve holdout AYRIK; birlesimleri tum tabloyu kapsar.
    """
    n = len(table)
    if n == 0:
        return [], []

    groups = _group_by_family(table)
    train: List[TrainingRow] = []
    holdout: List[TrainingRow] = []

    for aile, rows in groups.items():
        m = len(rows)
        if m <= 1:
            # Tek ornekli aile: hold-out'a koyma (train onceligi -> model ogrensin)
            train.extend(rows)
            continue
        # Aileden hold-out adedi: orantili, en az 1 (aile >= 2 ise)
        n_h = max(1, round(m * holdout_ratio))
        n_h = min(n_h, m - 1)  # ailenin en az 1 ornegi train'de kalsin
        train.extend(rows[: m - n_h])
        holdout.extend(rows[m - n_h:])

    # Toplam fail-safe: hic hold-out cikmadiysa (or. her aile tek ornek)
    # en buyuk aileden son ornegi hold-out'a tasi.
    if not holdout and n >= 2:
        # En buyuk aileyi bul, son ornegini hold-out yap
        largest = max(groups.values(), key=len)
        moved = largest[-1]
        holdout.append(moved)
        train = [r for r in train if r.instance_id != moved.instance_id]

    train.sort(key=lambda r: r.instance_id)
    holdout.sort(key=lambda r: r.instance_id)
    return train, holdout


def leave_one_family_out(
    table: List[TrainingRow],
) -> Iterator[Tuple[str, List[TrainingRow], List[TrainingRow]]]:
    """Leave-one-family-out (LOFO) jeneratoru.

    Her tur: bir aile TAMAMEN hold-out, geri kalan aileler train. Bu, modelin
    HIC GORMEDIGI bir aile tipinde nasil genelledigini olcer -- kullanici yeni
    bir AILE ekledigi senaryonun en dogru testi.

    Yields:
        (left_out_aile, train, holdout) -- her aile icin bir tur.
        Tek aile varsa hic tur uretilmez (LOFO anlamsiz).

    Determinizm: aileler alfabetik sirayla birakir.
    """
    groups = _group_by_family(table)
    if len(groups) < 2:
        return
    for aile in sorted(groups.keys()):
        holdout = sorted(groups[aile], key=lambda r: r.instance_id)
        train = sorted(
            (r for a, rows in groups.items() if a != aile for r in rows),
            key=lambda r: r.instance_id,
        )
        yield aile, train, holdout
