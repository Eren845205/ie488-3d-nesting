"""loader.py — CSV to list[Part] with quantity expansion.

Loads a CSV following PLAN.md §6 schema (id, width_mm, height_mm, qty, rotatable).
Parts with qty > 1 are expanded into multiple Part instances with suffixed IDs.
Encoding is always UTF-8; IDs must be ASCII-only (per §12 risk note).
"""

import csv
from pathlib import Path
from typing import List

from src.part import Part


def load_parts(csv_path: Path | str) -> List[Part]:
    """Read a CSV file and return a flat list of Part instances.

    Qty-expansion rule: a row with qty=3 yields Part instances with IDs
    '<id>_a', '<id>_b', '<id>_c'.  qty=1 yields just '<id>' (no suffix).

    Args:
        csv_path: path to the CSV file.

    Returns:
        Flat list of Part instances ready for a nesting algorithm.

    Raises:
        FileNotFoundError: if the CSV file does not exist.
        ValueError: if a required column is missing or a value is invalid.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    required_columns = {"id", "width_mm", "height_mm", "qty", "rotatable"}
    parts: List[Part] = []

    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)

        if reader.fieldnames is None:
            raise ValueError("CSV file is empty or has no header row.")

        missing = required_columns - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        for row_num, row in enumerate(reader, start=2):
            part_id = row["id"].strip()
            width_mm = float(row["width_mm"])
            height_mm = float(row["height_mm"])
            qty = int(row["qty"])
            rotatable_raw = row["rotatable"].strip().lower()
            rotatable = rotatable_raw in ("true", "1", "yes")

            if qty < 1:
                raise ValueError(
                    f"Row {row_num}: qty must be >= 1, got {qty} for id={part_id}"
                )

            if qty == 1:
                parts.append(Part(part_id, width_mm, height_mm, qty, rotatable))
            else:
                suffix_chars = _qty_suffixes(qty)
                for suffix in suffix_chars:
                    instance_id = f"{part_id}_{suffix}"
                    parts.append(
                        Part(instance_id, width_mm, height_mm, 1, rotatable)
                    )

    return parts


def _qty_suffixes(qty: int) -> List[str]:
    """Return label suffixes for qty instances: a, b, c, ..., z, aa, ab, ..."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    if qty <= 26:
        return list(letters[:qty])
    suffixes = []
    for i in range(qty):
        high, low = divmod(i, 26)
        if high == 0:
            suffixes.append(letters[low])
        else:
            suffixes.append(letters[high - 1] + letters[low])
    return suffixes
