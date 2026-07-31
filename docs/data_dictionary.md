# Data dictionary: Fialda FData binary format

**Status:** authoritative for WP1. This document reproduces Section 19.1 of
`vn_terminal_multi_ai_development_plan.md` v1.1 exactly, as instructed by
WP0 deliverable 5 ("Write docs/data_dictionary.md containing the verified
FData binary format from Section 19.1 of the plan, reproduced exactly").

**Owner:** Lead integrator authored this file at WP0. The data/backend
specialist (contracts/OWNERSHIP.md) codes WP1 against it and appends the
Aux1 verification result (see "Pending verification" below) once available.
Do not edit the quoted section below; append new findings in a new section
instead.

---

## Section 19.1 of the plan, quoted verbatim

> ### 19.1 Verified FData binary format (inspected 30 July 2026)
>
> Every EOD file is an exact multiple of 40 bytes with this layout:
>
> - A 40-byte header whose first uint32 (little-endian) is the record count.
> - 40-byte records, each holding a uint32 date in YYYYMMDD form followed by nine float32 fields, in order an unused field, open, high, low, close, volume, an unused field, `Aux1`, and `Aux2`.
> - OHLC values are back-adjusted and expressed in thousands of VND; volume is in shares.
> - The latest FPT bar (30 July 2026, O 65.2, H 67.2, L 64.8, C 67.0, V 7,571,500) matches the fixture in Section 10.1.
> - The `1m`, `5m`, `15m`, and `Tick` directories are empty and must be ignored, not treated as errors.
>
> This specification must be written into `docs/data_dictionary.md` so the data agent codes against evidence.

## Record layout, expanded for implementation

Restating the same evidence above in table form, for direct use when
writing the WP1 parser. This table adds no new claims; every value comes
from the quoted section above and from the P1 prompt in
`vn_terminal_ai_execution_playbook.md`, which names the source root and
subdirectories.

| Offset | Bytes | Type | Field | Notes |
|---|---|---|---|---|
| header | 40 | header block | (record count) | First `uint32`, little-endian, is the record count. Remaining header bytes are not described by Section 19.1 and must not be assumed to be padding without inspection. |
| record + 0 | 4 | `uint32` | `date` | `YYYYMMDD` form. |
| record + 4 | 4 | `float32` | unused | Order given by the plan as "an unused field" before `open`. |
| record + 8 | 4 | `float32` | `open` | Back-adjusted, thousands of VND. |
| record + 12 | 4 | `float32` | `high` | Back-adjusted, thousands of VND. |
| record + 16 | 4 | `float32` | `low` | Back-adjusted, thousands of VND. |
| record + 20 | 4 | `float32` | `close` | Back-adjusted, thousands of VND. |
| record + 24 | 4 | `float32` | `volume` | Shares. |
| record + 28 | 4 | `float32` | unused | Second unused field. |
| record + 32 | 4 | `float32` | `Aux1` | See "Aux1 hypothesis" below. Do not use in any calculation until confirmed (per the P1 prompt). |
| record + 36 | 4 | `float32` | `Aux2` | Small integer of unknown meaning; stays unused. |

Each record is 40 bytes (4 + 4 x 9 = 40), matching "40-byte records" in
Section 19.1.

Source root and subdirectories, from the P1 prompt in
`vn_terminal_ai_execution_playbook.md` (Section 6, "P1. FData adapter,
security master, storage"):

```
C:\FDATA\AmiBroker\EOD
├─ stock\
├─ index\
├─ der\
└─ cw\
```

The `1m`, `5m`, `15m`, and `Tick` directories exist alongside these but are
empty (verified 30 July 2026, Section 3.1 of the plan) and must be ignored
by the parser, not treated as errors (Section 19.1).

## Aux1 hypothesis: unadjusted VWAP, pending verification

Section 3.2 of the plan states the evidence for this hypothesis:

> `Aux1` very likely holds the unadjusted daily average price (VWAP).
> Inspection on 30 July 2026 found that for FPT in December 2006 `Aux1`
> reads 420-463 (thousand VND) against an adjusted close of about 10-11,
> matching FPT's actual unadjusted trading range at listing, while on
> current bars `Aux1` sits near but not equal to the close (FPT 66.57
> versus close 67.0). Confirming this against published VWAP for several
> tickers is a required WP1 task, because a confirmed `Aux1` yields
> per-day adjustment-factor estimates and lets the interface display
> support and resistance in real market prices. `Aux2` is a small integer
> of unknown meaning and remains unused.

**Status at WP0 close: unconfirmed.** WP1's acceptance criteria (Section
22) require testing this hypothesis "against published VWAP for several
tickers" before `Aux1` enters any calculation. `Section 14`'s money-flow
block reserves a `close_vs_vwap` field for this
(`contracts/schemas/models/money_flow.py`), left `null` until the
data/backend specialist records a conclusion here.

**Data/backend specialist: append the result below this line, with the
comparison tickers, the published VWAP source used, and the date of the
check. Do not delete the sections above.**

### WP1 Aux1 verification result, 30 July 2026

**Conclusion:** confirmed, with high confidence, as the unadjusted daily
average price for the tested equity sample, subject to source display
rounding. The comparison task is implemented in
`backend/app/data/tasks.py` and is reproducible with:

```powershell
python -m backend.app.data.tasks aux1 `
  --source-root "C:\FDATA\AmiBroker\EOD" `
  --output "data\quality_reports\aux1_validation_2026-07-30.json"
```

The test uses one common trading session, 21 July 2026, and compares the
FData float32 `Aux1` value with Stockbiz's published `Trung bình` (daily
average) field. Prices are in thousands of VND.

| Symbol | FData `Aux1` | Published daily average | Absolute difference |
|---|---:|---:|---:|
| FPT | 66.00 | 65.98 | 0.02 |
| HPG | 20.85 | 20.86 | 0.01 |
| SSI | 23.20 | 23.21 | 0.01 |
| MBB | 22.80 | 22.81 | 0.01 |
| VNM | 58.40 | 58.45 | 0.05 |

All five symbols match within the pre-specified tolerance of 0.051
thousand VND. This tolerance accommodates the published table's two-decimal
display and FData's float32 storage. The official SSI FastConnect
`DailyStockPrice` specification independently exposes `AveragePrice`
alongside `TotalMatchVal` and `TotalMatchVol`; its worked response is
consistent with a matched-trade value/volume average.

Published comparison pages:

- FPT: https://web.stockbiz.vn/Stocks/FPT/HistoricalQuotes.aspx
- HPG: https://web.stockbiz.vn/Stocks/HPG/HistoricalQuotes.aspx
- SSI: https://web.stockbiz.vn/Stocks/SSI/HistoricalQuotes.aspx
- MBB: https://web.stockbiz.vn/Stocks/MBB/HistoricalQuotes.aspx
- VNM: https://web.stockbiz.vn/Stocks/VNM/HistoricalQuotes.aspx
- SSI FastConnect `DailyStockPrice` specification:
  https://guide.ssi.com.vn/ssi-products/fastconnect-data/api-specs

**Safeguard:** `Aux1` remains excluded from the canonical `PriceBar`,
Parquet bar schema, API responses, indicators, and every calculation in
WP1-WP3. Confirmation is documented, but using the field operationally
requires an explicit downstream design decision. `Aux2` remains unused
and its meaning remains unknown.

**Limitation:** this result verifies five liquid HOSE equities on one
session and is not a formal Fialda field specification. Corporate-action
dates and non-equity categories should be tested separately before anyone
uses `Aux1` to derive adjustment factors.

## Baseline issue inventory (Section 19.2), for reference

Not part of the WP0 deliverable (which asks only for Section 19.1), but
recorded here because WP1/WP2 acceptance criteria (Section 22) are stated
as reproducing it. Quoted from Section 19.2 of the plan:

> The scan of all 2,471 EOD files (3.63 million records) found the
> following, each of which must become an automated test:
>
> - 505 files containing OHLC violations (`low <= open, close <= high` breached).
> - 34 files containing zero or negative prices.
> - 11,020 zero-volume records, including carry-forward bars.
> - 301 stock files ending in terminal zero-volume runs of five or more sessions, that is, suspended or delisted names.
> - 2,315 of 2,471 files current to 30 July 2026; about 156 files stopped updating earlier.
> - `EOD/cw/CSHB2604.dat` with a header count of 43 against 44 actual records and one out-of-order date. This file becomes a permanent malformed-file test fixture.
> - Mixed security types in the stock directory.
> - Historically adjusted prices with an undocumented adjustment method.
> - Missing initial listing sessions for some securities.

See Section 19.2 of `vn_terminal_multi_ai_development_plan.md` v1.1 for the
fourteen automated checks and four severity levels that follow this
inventory.
