"""Schema-explicit adapter for Vnstock financial DataFrames."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from .models import RawFinancialObservation, ValueBasis
from .normalization import NormalizationResult, normalize_observations


class VnstockSchemaError(ValueError):
    """The configured provider schema does not match the returned frame."""


@dataclass(frozen=True, slots=True)
class MetricColumn:
    source_column: str
    metric_code: str
    metric_label_vi: str
    unit: str


@dataclass(frozen=True, slots=True)
class FinancialFrameSchema:
    """Explicit mapping for one statement type and period."""

    period_end_column: str
    metrics: tuple[MetricColumn, ...]
    currency: str
    consolidated: bool
    value_basis: ValueBasis
    source_url: str | None = None
    source_url_column: str | None = None
    publication_date_column: str | None = None
    restatement_version_column: str | None = None

    def __post_init__(self) -> None:
        if not self.metrics:
            raise ValueError("metrics must contain at least one explicit mapping")
        if self.source_url is None and self.source_url_column is None:
            raise ValueError(
                "source_url or source_url_column is required for every figure"
            )


def _default_fundamental_factory() -> Any:
    try:
        module = importlib.import_module("vnstock")
    except ImportError as exc:
        raise RuntimeError(
            "Vnstock is not installed. Install the lead-approved pinned "
            "version or inject a fundamental_factory."
        ) from exc
    return module.Fundamental()


def _date_value(value: object, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise VnstockSchemaError(
            f"{field_name} must contain ISO dates"
        ) from exc


def _optional_date(value: object, field_name: str) -> date | None:
    if value is None or bool(pd.isna(value)):
        return None
    return _date_value(value, field_name)


def _records(frame: Any) -> list[Mapping[str, Any]]:
    if hasattr(frame, "to_dict"):
        records = frame.to_dict(orient="records")
    elif isinstance(frame, list):
        records = frame
    else:
        raise VnstockSchemaError(
            "Vnstock statement result must be a DataFrame-like table"
        )
    if not isinstance(records, list):
        raise VnstockSchemaError("Vnstock table could not be read as records")
    return records


def _statement_method(statement_type: str) -> str:
    methods = {
        "income_statement": "income_statement",
        "balance_sheet": "balance_sheet",
        "cash_flow_statement": "cash_flow",
        "ratio": "ratio",
    }
    try:
        return methods[statement_type]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported Vnstock statement_type: {statement_type}"
        ) from exc


class VnstockFinancialAdapter:
    """Fetch Vnstock tables while refusing to guess provider metadata."""

    def __init__(
        self,
        *,
        fundamental_factory: Callable[[], Any] = _default_fundamental_factory,
        source_name: str = "vnstock",
        ingested_at_factory: Callable[[], datetime] | None = None,
    ):
        self._fundamental_factory = fundamental_factory
        self.source_name = source_name
        self._ingested_at_factory = ingested_at_factory or (
            lambda: datetime.now(UTC)
        )

    def fetch(
        self,
        *,
        symbol: str,
        statement_type: str,
        period_type: str,
        schema: FinancialFrameSchema,
    ) -> NormalizationResult:
        if period_type not in {"quarter", "year"}:
            raise ValueError("period_type must be quarter or year")
        normalized_symbol = symbol.strip().upper()
        fundamental = self._fundamental_factory()
        equity = fundamental.equity(normalized_symbol)
        method = getattr(equity, _statement_method(statement_type))
        frame = method(period=period_type, orient="time_series")
        records = _records(frame)
        if not records:
            return NormalizationResult((), ())

        required = {
            schema.period_end_column,
            *(metric.source_column for metric in schema.metrics),
        }
        for optional in (
            schema.source_url_column,
            schema.publication_date_column,
            schema.restatement_version_column,
        ):
            if optional is not None:
                required.add(optional)
        missing = required - set(records[0])
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise VnstockSchemaError(
                f"Configured columns missing from Vnstock result: {missing_text}"
            )

        ingested_at = self._ingested_at_factory()
        raw: list[RawFinancialObservation] = []
        adapter_warnings: list[str] = []
        for row_index, row in enumerate(records):
            period_end = _date_value(
                row[schema.period_end_column],
                schema.period_end_column,
            )
            publication_date = (
                _optional_date(
                    row[schema.publication_date_column],
                    schema.publication_date_column,
                )
                if schema.publication_date_column is not None
                else None
            )
            version = (
                int(row[schema.restatement_version_column])
                if schema.restatement_version_column is not None
                else 1
            )
            source_url = (
                str(row[schema.source_url_column])
                if schema.source_url_column is not None
                else schema.source_url
            )
            if source_url is None:
                raise VnstockSchemaError(
                    f"Row {row_index} has no configured source URL"
                )
            for metric in schema.metrics:
                value = row[metric.source_column]
                if value is None or bool(pd.isna(value)):
                    adapter_warnings.append(
                        f"{normalized_symbol} {period_end.isoformat()} "
                        f"{metric.metric_code} is null in the provider row "
                        "and was not normalized."
                    )
                    continue
                raw.append(
                    RawFinancialObservation(
                        symbol=normalized_symbol,
                        period_end=period_end,
                        period_type=period_type,
                        statement_type=statement_type,
                        metric_code=metric.metric_code,
                        metric_label_vi=metric.metric_label_vi,
                        value=value,
                        currency=schema.currency,
                        unit=metric.unit,
                        consolidated=schema.consolidated,
                        value_basis=schema.value_basis,
                        restatement_version=version,
                        publication_date=publication_date,
                        source_url=source_url,
                        source_name=self.source_name,
                        ingested_at=ingested_at,
                    )
                )

        result = normalize_observations(raw)
        return NormalizationResult(
            observations=result.observations,
            warnings=tuple(adapter_warnings) + result.warnings,
        )
