from __future__ import annotations

import struct
from collections.abc import Iterable
from pathlib import Path

import pytest


def write_fdata_file(
    path: Path,
    rows: Iterable[tuple[int, float, float, float, float, float, float, float]],
    *,
    header_count: int | None = None,
) -> Path:
    """Create a minimal test-only FData file.

    Row order is date, open, high, low, close, volume, aux1, aux2. The two
    documented unused float32 fields are written as zero.
    """

    materialized = list(rows)
    count = len(materialized) if header_count is None else header_count
    payload = bytearray(40)
    struct.pack_into("<I", payload, 0, count)
    for date_code, open_, high, low, close, volume, aux1, aux2 in materialized:
        payload.extend(
            struct.pack(
                "<I9f",
                date_code,
                0.0,
                open_,
                high,
                low,
                close,
                volume,
                0.0,
                aux1,
                aux2,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.fixture
def fdata_writer():
    return write_fdata_file
