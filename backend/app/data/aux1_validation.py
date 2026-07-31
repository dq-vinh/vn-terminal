"""Reproducible comparison of Aux1 with published daily average prices."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .models import ParsedFDataFile
from .quality.checks import date_from_code


@dataclass(frozen=True, slots=True)
class PublishedAveragePrice:
    symbol: str
    trading_date: date
    average_price: float
    source_url: str


@dataclass(frozen=True, slots=True)
class Aux1Comparison:
    symbol: str
    trading_date: date
    aux1: float
    published_average_price: float
    absolute_difference: float
    source_url: str
    matched: bool


@dataclass(frozen=True, slots=True)
class Aux1ValidationReport:
    comparisons: tuple[Aux1Comparison, ...]
    ticker_count: int
    matched_count: int
    max_absolute_difference: float
    conclusion: str
    aux1_allowed_in_calculations: bool = False


def compare_aux1_to_published_average(
    parsed_by_symbol: Mapping[str, ParsedFDataFile],
    observations: Sequence[PublishedAveragePrice],
    *,
    tolerance_thousand_vnd: float,
) -> Aux1ValidationReport:
    comparisons: list[Aux1Comparison] = []
    for observation in observations:
        parsed = parsed_by_symbol.get(observation.symbol.upper())
        if parsed is None:
            continue
        record = next(
            (
                item
                for item in parsed.records
                if date_from_code(item.date_code) == observation.trading_date
            ),
            None,
        )
        if record is None:
            continue
        difference = abs(record.aux1 - observation.average_price)
        comparisons.append(
            Aux1Comparison(
                symbol=observation.symbol.upper(),
                trading_date=observation.trading_date,
                aux1=record.aux1,
                published_average_price=observation.average_price,
                absolute_difference=difference,
                source_url=observation.source_url,
                matched=difference <= tolerance_thousand_vnd,
            )
        )

    ticker_count = len({item.symbol for item in comparisons})
    matched_count = len(
        {item.symbol for item in comparisons if item.matched}
    )
    confirmed = ticker_count >= 5 and matched_count == ticker_count
    return Aux1ValidationReport(
        comparisons=tuple(comparisons),
        ticker_count=ticker_count,
        matched_count=matched_count,
        max_absolute_difference=max(
            (item.absolute_difference for item in comparisons), default=float("inf")
        ),
        conclusion=(
            "confirmed_unadjusted_daily_average_price"
            if confirmed
            else "not_confirmed"
        ),
        # Aux1 is deliberately excluded from the canonical price-bar contract.
        aux1_allowed_in_calculations=False,
    )
