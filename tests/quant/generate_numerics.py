"""Regenerate `backend/app/quant/indicators/NUMERICS.md` from the registry.

Run from the repository root:

    python tests/quant/generate_numerics.py

The document is generated rather than hand-maintained so that the Section 14
numerical documentation cannot drift away from the code: every per-indicator
entry is rendered from the `IndicatorSpec` the engine actually uses.
`test_documentation.py::test_numerics_document_is_up_to_date` fails if the
file on disk differs from what this script produces.

The generator lives under `tests/` rather than inside the indicator package
because the package is held to a purity rule that forbids file access, and
`test_purity.py` scans every module in it. A generator that writes a file
belongs outside that boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.quant.indicators import all_indicators

TARGET = REPO_ROOT / "backend" / "app" / "quant" / "indicators" / "NUMERICS.md"

PREAMBLE = """<!-- GENERATED FILE. Do not edit by hand.
     Regenerate with: python tests/quant/generate_numerics.py
     The per-indicator entries below are rendered from the IndicatorSpec
     records in this package, so the document and the engine cannot
     disagree. Edit the spec, then regenerate. -->

# Indicator numerics (WP5, Section 14)

Section 14 requires each indicator to document its formula, input price,
adjustment convention, warm-up period, missing-value behaviour, comparison
reference, and numerical tolerance. Those seven attributes are required
fields on `IndicatorSpec`, are rendered per indicator below, and are
enforced by `tests/quant/test_documentation.py`.

## Conventions that apply to every indicator

**Purity.** No indicator opens a file, a socket, or a database connection,
reads the clock, reads the environment, or draws a random number. Inputs
arrive as arrays the caller has already loaded, are copied on the way in,
and are marked read-only. `tests/quant/test_purity.py` enforces this
statically, by scanning the package for forbidden imports and attribute
names, and dynamically, by running every indicator with `open`, the socket
constructors, the process-spawning entry points, and `__import__` itself
replaced by functions that fail the test.

**Price basis.** FData OHLC is back-adjusted and expressed in thousands of
VND (Section 19.1), and every bar carries an `adjustment_status`
(Section 10.1). Nothing in this package re-adjusts, rescales, or converts a
price. Every indicator inherits whatever basis the caller supplied, which is
why each entry below restates the consequence rather than assuming it.

**Volume basis.** Volume is in shares and is NOT adjusted, while prices are.
Any statistic that multiplies a price by a volume therefore mixes an
adjusted series with an unadjusted one, and its level is comparable over
time only between corporate actions. Read the slope of the cumulative
money-flow series, not the level.

**Vietnamese price bands.** HOSE, HNX, and UPCoM all impose daily price
bands. A limit session can print `high == low == close`, which is a 0/0 form
for the classic money-flow multiplier. The convention adopted, and the
standard one, is a multiplier of zero, so the most one-sided sessions
contribute nothing to the accumulation/distribution line. The count of such
bars is reported as `zero_range_bars`, and on-balance volume, which signs a
limit-up day fully positive, is in the same block for exactly this reason.

**Missing values.** A missing bar is never imputed, interpolated, or
forward-filled. Three rules apply, and each indicator names which it
follows:

- *Windowed*: output is defined only when the whole window exists and holds
  no NaN, so one missing bar costs exactly one window of output and the
  series then recovers by itself.
- *Recursive with gap re-seed*: the input is split into maximal runs of
  consecutive defined bars and the recursion runs independently inside each
  run. A gap costs one further full warm-up period and never propagates
  beyond it.
- *Cumulative*: output is NaN at the undefined bar and the running total
  carries across unchanged, so the series resumes at its previous level.
  Used only for on-balance volume, the accumulation/distribution line, and
  volume-price trend, all three of which have an arbitrary origin.

**Warm-up.** Every indicator declares its warm-up as prose and as the
callable `IndicatorSpec.warm_up_bars`. `test_indicator_math.py` asserts that
the slowest output of each indicator first becomes defined at exactly the
declared bar, so the documented number is checked against behaviour on every
test run rather than trusted.

**Ratios.** Every division goes through `safe_divide`, which returns NaN
rather than an infinity when the denominator is zero. An undefined value
stays visibly undefined instead of becoming an infinity that survives into a
strategy comparison.

## Outstanding external verification

Section 14's acceptance criterion is that results "match an independent
reference or AmiBroker export within a documented tolerance". The
independent reference exists: `tests/quant/reference.py` reimplements every
indicator naively, in plain Python, sharing no code with the engine, and
each indicator is compared against it at its own documented tolerance,
alongside hand-computed cases whose expected values are written into the
tests as literals.

**No AmiBroker export has been supplied to this workstream, so the
AmiBroker half of that criterion is not met.** This matters beyond
belt-and-braces, because a reference implementation cannot detect a wrong
*convention*, only a wrong implementation of the chosen one. The
conventions most likely to differ from AmiBroker, and therefore most worth
checking against an export, are:

1. EMA seeding. This package seeds with an SMA of the first `period` values.
   A package seeding with the first observation produces different values
   for hundreds of bars.
2. The first bar's true range. This package leaves it undefined; some
   packages substitute `high - low`, which shifts every later ATR value.
3. The Bollinger standard deviation. This package uses the population form
   (`ddof = 0`). The sample form differs by a factor `sqrt(n / (n - 1))`,
   about 2.6 percent at `period = 20`.
4. The RSI value on a flat window. This package returns NaN where others
   conventionally return 50 or 100.

Each per-indicator tolerance below states the reference it applies to. Where
a looser tolerance is proposed for an eventual AmiBroker comparison, the
reason is FData's float32 storage (Section 19.1), not a weaker claim about
the mathematics.

Suggested next step for whoever holds the AmiBroker licence: export the
Section 14 indicators for a handful of tickers at the default parameters,
drop the CSV into `tests/quant/golden/amibroker/`, and add a comparison
test. Until that exists, treat the four conventions above as unverified
against the reference platform the user already trusts.

## Blocked and partially blocked indicators

**Relative strength versus VN-Index and versus sector.** The mathematics is
implemented and tested against a synthetic benchmark. Choosing the actual
benchmark is blocked: Section 10.2 requires an index code-to-name mapping
from an external source before these calculations are enabled, the 207 files
under `EOD/index` are named with numeric codes, and no security-master entry
with `security_type: "index"` and a populated `index_code` exists yet. The
resolver raises `BenchmarkMappingUnavailable` rather than guessing a code,
and the end-to-end tests skip themselves with that reason. This is a
dependency on the data stream (WP2), not on this workstream.

**Close versus VWAP.** Section 14 admits this to the money-flow block once
`Aux1` is confirmed as unadjusted VWAP, and `docs/data_dictionary.md` now
records that confirmation, dated 30 July 2026. Three things still stand
between the confirmation and the block, and none of them belong to this
workstream: the canonical `PriceBar` contract carries no VWAP or
unadjusted-close field, so the inputs cannot be delivered; the data
dictionary's own safeguard keeps `Aux1` out of every calculation pending an
explicit downstream design decision; and the verification covers five liquid
HOSE equities on one session, with corporate-action dates untested. There is
also a substantive trap: `Aux1` is unadjusted while OHLC is back-adjusted,
so dividing the stored close by the stored `Aux1` is correct only for bars
after the most recent corporate action and silently wrong before it. The
formula is implemented and tested as
`money_flow.close_versus_vwap(unadjusted_close, vwap)`, which takes the
unadjusted close explicitly so the mistake cannot be made by accident, and
`build_money_flow_block` accepts a finished value from a caller that can
legitimately produce one. It is never derived from the bars.

## Per-indicator record

"""


def render_indicator(spec) -> str:
    parameters = (
        ", ".join(f"`{key}={value!r}`" for key, value in spec.parameters.items())
        or "none"
    )
    outputs = ", ".join(f"`{name}`" for name in spec.outputs)
    scalars = ", ".join(f"`{name}`" for name in spec.scalar_outputs) or "none"

    lines = [
        f"### `{spec.indicator_id}` — {spec.title}",
        "",
        f"- **Block:** {spec.block}",
        f"- **Series outputs:** {outputs}",
        f"- **Scalar outputs:** {scalars}",
        f"- **Parameters (defaults):** {parameters}",
        f"- **Formula:** {spec.formula}",
        f"- **Input price:** {spec.input_price}",
        f"- **Adjustment convention:** {spec.adjustment_convention}",
        f"- **Warm-up:** {spec.warm_up}",
        f"- **Missing values:** {spec.missing_value_behavior}",
        f"- **Comparison reference:** {spec.comparison_reference}",
        (
            f"- **Tolerance:** absolute {spec.tolerance.absolute:g}, relative "
            f"{spec.tolerance.relative:g}. {spec.tolerance.basis}"
        ),
        "",
    ]
    return "\n".join(lines)


def render() -> str:
    blocks: dict[str, list] = {}
    for entry in all_indicators():
        blocks.setdefault(entry.spec.block, []).append(entry.spec)

    parts = [PREAMBLE]
    for block in sorted(blocks):
        parts.append(f"## Block: {block}\n")
        for spec in sorted(blocks[block], key=lambda item: item.indicator_id):
            parts.append(render_indicator(spec))
    return "".join(parts)


def main() -> int:
    text = render()
    with TARGET.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {TARGET.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
