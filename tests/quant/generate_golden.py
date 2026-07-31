"""Regenerate the golden fixtures in `tests/quant/golden/`.

Run from the repository root:

    python tests/quant/generate_golden.py

What a golden fixture is here, and what it is not. It is a frozen record of
what the engine produced on a named input, so that any later change to an
indicator has to be deliberate: `test_golden.py` fails until someone
regenerates the file, which forces the change through review. It is NOT
evidence that the numbers are correct. Correctness comes from the
hand-computed cases and the independent reference implementations in
`test_indicator_math.py`, `test_money_flow.py`, and
`test_relative_strength.py`, and ultimately from the AmiBroker cross-check
recorded as outstanding in `NUMERICS.md`.

Regenerate only after the correctness tests pass, and say in the commit
message which indicator changed and why. A golden diff on an indicator you
did not intend to touch is a bug report.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from helpers import FIXTURES, GOLDEN, call_kwargs, load_series

from backend.app.quant.indicators import (
    all_indicators,
    build_indicators_payload,
    build_money_flow_block,
    compute,
)

SYMBOLS = ("FPT", "KDH")

#: Extra parameter sets recorded alongside the documented defaults, chosen to
#: exercise a short window and a long one on the indicators a strategy is
#: most likely to re-parameterize.
EXTRA_PARAMETER_SETS: dict[str, tuple[dict, ...]] = {
    "sma": ({"period": 5}, {"period": 200}),
    "ema": ({"period": 5},),
    "rsi": ({"period": 7},),
    "atr": ({"period": 20},),
    "bollinger_bands": ({"period": 10, "num_std": 1.5},),
    "up_down_volume_ratio": ({"window": 60},),
    "unusual_volume": ({"window": 10, "multiple": 3.0},),
    "volume_at_price": ({"lookback": 250, "bins": 10},),
}


def leading_nan_count(values: np.ndarray) -> int:
    finite = np.isfinite(values)
    return int(len(values)) if not finite.any() else int(np.argmax(finite))


def sample_indices(values: np.ndarray) -> list[int]:
    """A fixed, reproducible set of positions to freeze.

    Storing every value of every indicator for two 520-bar securities would
    make a fixture nobody reads and a diff nobody can review. These
    positions cover the warm-up boundary, where off-by-one errors live, the
    middle of the series, and the last three bars, which is what the screener
    and the AI fact bundle actually read.
    """

    length = len(values)
    warm_up = leading_nan_count(values)
    candidates = [
        warm_up - 1,
        warm_up,
        warm_up + 1,
        length // 2,
        length - 3,
        length - 2,
        length - 1,
    ]
    return sorted({index for index in candidates if 0 <= index < length})


def jsonable(value):
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return None if not np.isfinite(number) else number
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    return value


def fixture_digest(symbol: str) -> str:
    path = FIXTURES / f"bars_{symbol}.json"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_record(symbol: str) -> dict:
    series = load_series(symbol)
    indicators: list[dict] = []

    for entry in all_indicators():
        indicator_id = entry.spec.indicator_id
        parameter_sets = [call_kwargs(entry.spec, series)]
        for extra in EXTRA_PARAMETER_SETS.get(indicator_id, ()):
            merged = call_kwargs(entry.spec, series)
            merged.update(extra)
            parameter_sets.append(merged)

        for parameters in parameter_sets:
            result = compute(indicator_id, series, **parameters)
            recorded_parameters = {
                key: value for key, value in parameters.items() if key != "benchmark"
            }
            outputs = {}
            for name in entry.spec.outputs:
                values = result[name]
                outputs[name] = {
                    "warm_up_bars": leading_nan_count(values),
                    "samples": {
                        str(index): jsonable(values[index])
                        for index in sample_indices(values)
                    },
                }
            indicators.append(
                {
                    "indicator_id": indicator_id,
                    "parameters": jsonable(recorded_parameters),
                    "uses_synthetic_benchmark": entry.spec.requires_benchmark,
                    "outputs": outputs,
                    "scalars": jsonable(dict(result.scalars)),
                }
            )

    payload = build_indicators_payload(series)
    return {
        "_comment": (
            "Golden regression baseline for the WP5 indicator engine. Regenerate with "
            "`python tests/quant/generate_golden.py` only after the correctness tests "
            "pass; see the module docstring of that script."
        ),
        "symbol": symbol,
        "source_fixture": f"contracts/fixtures/bars_{symbol}.json",
        "source_sha256": fixture_digest(symbol),
        "bar_count": len(series),
        "first_trading_date": series.trading_dates[0].isoformat(),
        "last_trading_date": series.trading_dates[-1].isoformat(),
        "adjustment_status": series.adjustment_status,
        "benchmark_note": (
            "Relative-strength entries use the deterministic synthetic benchmark in "
            "tests/quant/helpers.py, not VN-Index. The real benchmark is blocked on "
            "the Section 10.2 index code-to-name mapping owned by the data stream."
        ),
        "indicators": indicators,
        "money_flow_block": jsonable(build_money_flow_block(series)),
        "payload_series_ids": [item["indicator_id"] for item in payload["indicators"]],
    }


def main() -> int:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for symbol in SYMBOLS:
        record = build_record(symbol)
        path = GOLDEN / f"indicators_{symbol}.json"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
