"""Canonical validation and projection for financial observations."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlparse

from .models import (
    FLOW_STATEMENTS,
    NormalizedFinancialObservation,
    RawFinancialObservation,
    ValueBasis,
)

SUPPORTED_UNITS = frozenset(
    {
        "vnd",
        "thousand_vnd",
        "million_vnd",
        "billion_vnd",
        "vnd_per_share",
        "shares",
        "ratio",
        "percent",
        "times",
    }
)
PERIOD_TYPES = frozenset({"quarter", "year"})
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    observations: tuple[NormalizedFinancialObservation, ...]
    warnings: tuple[str, ...]


def _validate_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    return source_url


def _validate_value(value: Decimal | float) -> Decimal:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("value must be finite")
    converted = Decimal(str(value))
    if not converted.is_finite():
        raise ValueError("value must be finite")
    return converted


def _validate_basis(item: RawFinancialObservation) -> None:
    if item.period_type == "year" and item.statement_type in FLOW_STATEMENTS:
        if item.value_basis is not ValueBasis.ANNUAL:
            raise ValueError(
                "annual flow observations must use value_basis=annual"
            )
    elif item.statement_type == "balance_sheet":
        if item.value_basis is not ValueBasis.POINT_IN_TIME:
            raise ValueError(
                "balance-sheet observations must use "
                "value_basis=point_in_time"
            )
    elif (
        item.statement_type == "ratio"
        and item.value_basis is not ValueBasis.RATIO
    ):
        raise ValueError("ratio observations must use value_basis=ratio")


def _metric_code(item: RawFinancialObservation) -> str:
    if (
        item.period_type == "quarter"
        and item.value_basis is ValueBasis.CUMULATIVE
    ):
        return f"{item.metric_code}_cumulative"
    return item.metric_code


def normalize_observations(
    rows: list[RawFinancialObservation] | tuple[RawFinancialObservation, ...],
) -> NormalizationResult:
    """Validate provider rows without inferring missing financial metadata."""

    observations: list[NormalizedFinancialObservation] = []
    warnings: list[str] = []
    for item in rows:
        symbol = item.symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol must not be empty")
        if item.period_type not in PERIOD_TYPES:
            raise ValueError("period_type must be quarter or year")
        if not item.statement_type.strip():
            raise ValueError("statement_type must not be empty")
        if not item.metric_code.strip():
            raise ValueError("metric_code must not be empty")
        if not item.metric_label_vi.strip():
            raise ValueError("metric_label_vi must not be empty")
        currency = item.currency.strip().upper()
        unit = item.unit.strip().lower()
        if unit not in SUPPORTED_UNITS:
            raise ValueError(f"unit is not supported: {item.unit}")
        dimensionless = unit in {"ratio", "percent", "times"}
        if currency == "N/A":
            if not dimensionless:
                raise ValueError(
                    "currency N/A is valid only for dimensionless units"
                )
        elif not CURRENCY_PATTERN.fullmatch(currency):
            raise ValueError("currency must be an explicit three-letter code")
        if item.restatement_version < 1:
            raise ValueError("restatement_version must be at least 1")
        if item.ingested_at.tzinfo is None:
            raise ValueError("ingested_at must be timezone-aware")
        if not item.source_name.strip():
            raise ValueError("source_name must not be empty")
        _validate_basis(item)

        observation = NormalizedFinancialObservation(
            symbol=symbol,
            period_end=item.period_end,
            period_type=item.period_type,
            statement_type=item.statement_type.strip(),
            metric_code=_metric_code(item),
            base_metric_code=item.metric_code.strip(),
            metric_label_vi=item.metric_label_vi.strip(),
            value=_validate_value(item.value),
            currency=currency,
            unit=unit,
            consolidated=item.consolidated,
            value_basis=item.value_basis,
            restatement_version=item.restatement_version,
            publication_date=item.publication_date,
            source_url=_validate_url(item.source_url),
            source_name=item.source_name.strip(),
            ingested_at=item.ingested_at,
        )
        observations.append(observation)
        if item.publication_date is None:
            warnings.append(
                f"{symbol} {item.period_end.isoformat()} "
                f"{item.metric_code} has no publication date; it is "
                "available for display and current screening but excluded "
                "from historical backtests."
            )

    return NormalizationResult(tuple(observations), tuple(warnings))


def _quarter(period_end_month: int) -> int:
    return ((period_end_month - 1) // 3) + 1


def derive_standalone_quarters(
    observations: tuple[NormalizedFinancialObservation, ...],
) -> NormalizationResult:
    """Retain cumulative values and derive only compatible standalone flows."""

    output = list(observations)
    warnings: list[str] = []
    existing_standalone = {
        (
            item.symbol,
            item.period_end,
            item.statement_type,
            item.base_metric_code,
            item.consolidated,
            item.currency,
            item.unit,
            item.restatement_version,
        )
        for item in observations
        if item.value_basis is ValueBasis.STANDALONE
    }
    groups: dict[
        tuple[str, str, str, bool, str, str, int, int],
        list[NormalizedFinancialObservation],
    ] = defaultdict(list)
    for item in observations:
        if (
            item.period_type == "quarter"
            and item.statement_type in FLOW_STATEMENTS
            and item.value_basis is ValueBasis.CUMULATIVE
        ):
            key = (
                item.symbol,
                item.statement_type,
                item.base_metric_code,
                item.consolidated,
                item.currency,
                item.unit,
                item.restatement_version,
                item.period_end.year,
            )
            groups[key].append(item)

    for group in groups.values():
        by_quarter = {_quarter(item.period_end.month): item for item in group}
        for quarter in sorted(by_quarter):
            current = by_quarter[quarter]
            identity = (
                current.symbol,
                current.period_end,
                current.statement_type,
                current.base_metric_code,
                current.consolidated,
                current.currency,
                current.unit,
                current.restatement_version,
            )
            if identity in existing_standalone:
                continue
            if quarter == 1:
                value = current.value
                calculation = "standalone_from_q1_cumulative"
            else:
                prior = by_quarter.get(quarter - 1)
                if prior is None:
                    warnings.append(
                        f"{current.symbol} {current.period_end.isoformat()} "
                        f"{current.base_metric_code} cumulative value has no "
                        "compatible prior quarter; standalone value was not "
                        "derived."
                    )
                    continue
                value = current.value - prior.value
                calculation = "standalone_from_cumulative_difference"
            output.append(
                NormalizedFinancialObservation(
                    symbol=current.symbol,
                    period_end=current.period_end,
                    period_type=current.period_type,
                    statement_type=current.statement_type,
                    metric_code=current.base_metric_code,
                    base_metric_code=current.base_metric_code,
                    metric_label_vi=current.metric_label_vi,
                    value=value,
                    currency=current.currency,
                    unit=current.unit,
                    consolidated=current.consolidated,
                    value_basis=ValueBasis.STANDALONE,
                    restatement_version=current.restatement_version,
                    publication_date=current.publication_date,
                    source_url=current.source_url,
                    source_name=current.source_name,
                    ingested_at=current.ingested_at,
                    calculation=calculation,
                )
            )

    output.sort(
        key=lambda item: (
            item.period_end,
            item.statement_type,
            item.metric_code,
            item.restatement_version,
            item.value_basis.value,
        )
    )
    return NormalizationResult(tuple(output), tuple(warnings))
