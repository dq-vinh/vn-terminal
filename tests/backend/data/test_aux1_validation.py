from __future__ import annotations

from datetime import date

from backend.app.data.aux1_validation import (
    PublishedAveragePrice,
    compare_aux1_to_published_average,
)
from backend.app.data.fdata.parser import FDataParser
from backend.app.data.tasks import run_curated_aux1_validation


def test_aux1_matches_published_daily_average_for_five_tickers(
    tmp_path, fdata_writer
):
    published = {
        "FPT": 65.98,
        "HPG": 20.86,
        "SSI": 23.21,
        "MBB": 22.81,
        "VNM": 58.45,
    }
    local = {
        "FPT": 66.00,
        "HPG": 20.85,
        "SSI": 23.20,
        "MBB": 22.80,
        "VNM": 58.40,
    }
    parsed = {}
    observations = []
    for symbol, aux1 in local.items():
        source = fdata_writer(
            tmp_path / "stock" / f"{symbol}.dat",
            [(20260721, aux1, aux1, aux1, aux1, 100, aux1, 1)],
        )
        parsed[symbol] = FDataParser().parse_file(source, "stock")
        observations.append(
            PublishedAveragePrice(
                symbol=symbol,
                trading_date=date(2026, 7, 21),
                average_price=published[symbol],
                source_url=(
                    f"https://web.stockbiz.vn/Stocks/{symbol}/"
                    "HistoricalQuotes.aspx"
                ),
            )
        )

    report = compare_aux1_to_published_average(
        parsed, observations, tolerance_thousand_vnd=0.051
    )

    assert report.ticker_count == 5
    assert report.matched_count == 5
    assert report.conclusion == "confirmed_unadjusted_daily_average_price"
    assert report.max_absolute_difference <= 0.051
    assert report.aux1_allowed_in_calculations is False


def test_curated_aux1_task_uses_five_published_tickers(
    tmp_path, fdata_writer
):
    local = {
        "FPT": 66.00,
        "HPG": 20.85,
        "SSI": 23.20,
        "MBB": 22.80,
        "VNM": 58.40,
    }
    for symbol, aux1 in local.items():
        fdata_writer(
            tmp_path / "stock" / f"{symbol}.dat",
            [(20260721, aux1, aux1, aux1, aux1, 100, aux1, 1)],
        )

    report = run_curated_aux1_validation(tmp_path)

    assert report.ticker_count == 5
    assert report.matched_count == 5
    assert all(
        comparison.source_url.startswith("https://web.stockbiz.vn/")
        for comparison in report.comparisons
    )
