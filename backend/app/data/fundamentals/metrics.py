"""Deterministic Section 17 financial-panel calculations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from urllib.parse import urlparse

from contracts.schemas.models.api_envelopes import DerivedMetric

from .models import NormalizedFinancialObservation, ValueBasis

SIX_PLACES = Decimal("0.000001")
RATIO_LABELS = {
    "revenue_qoq_growth": "Tăng trưởng doanh thu QoQ",
    "revenue_yoy_growth": "Tăng trưởng doanh thu YoY",
    "gross_margin": "Biên lợi nhuận gộp",
    "operating_margin": "Biên lợi nhuận hoạt động",
    "net_margin": "Biên lợi nhuận ròng",
    "roe": "Tỷ suất lợi nhuận trên vốn chủ sở hữu",
    "roa": "Tỷ suất lợi nhuận trên tổng tài sản",
    "debt_to_equity": "Nợ phải trả trên vốn chủ sở hữu",
    "free_cash_flow": "Dòng tiền tự do",
    "pe": "Hệ số giá trên lợi nhuận",
    "pb": "Hệ số giá trên giá trị sổ sách",
}


@dataclass(frozen=True, slots=True)
class PricePoint:
    symbol: str
    trading_date: date
    value: Decimal
    currency: str
    unit: str
    source_url: str

    def __post_init__(self) -> None:
        parsed = urlparse(self.source_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "PricePoint source_url must be an absolute HTTP(S) URL"
            )


@dataclass(frozen=True, slots=True)
class PanelCalculationResult:
    metrics: tuple[DerivedMetric, ...]
    trace_observations: tuple[NormalizedFinancialObservation, ...]
    warnings: tuple[str, ...]


def _rounded(value: Decimal) -> Decimal:
    return value.quantize(SIX_PLACES, rounding=ROUND_HALF_EVEN)


def _scope_code(code: str, consolidated: bool) -> str:
    return code if consolidated else f"{code}_separate"


def _quarter(period_end: date) -> tuple[int, int]:
    return period_end.year, ((period_end.month - 1) // 3) + 1


def _latest_versions(
    observations: tuple[NormalizedFinancialObservation, ...],
) -> tuple[NormalizedFinancialObservation, ...]:
    latest: dict[
        tuple[str, date, str, str, bool], NormalizedFinancialObservation
    ] = {}
    for item in observations:
        key = (
            item.symbol,
            item.period_end,
            item.statement_type,
            item.metric_code,
            item.consolidated,
        )
        current = latest.get(key)
        if current is None or (
            item.restatement_version,
            item.ingested_at,
        ) > (
            current.restatement_version,
            current.ingested_at,
        ):
            latest[key] = item
    return tuple(latest.values())


class _MetricBuilder:
    def __init__(self) -> None:
        self.metrics: list[DerivedMetric] = []
        self.traces: list[NormalizedFinancialObservation] = []
        self.warnings: list[str] = []

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def emit(
        self,
        *,
        code: str,
        period_end: date,
        value: Decimal,
        unit: str,
        inputs: tuple[NormalizedFinancialObservation, ...],
        formula: str,
        price: PricePoint | None = None,
    ) -> None:
        current = max(inputs, key=lambda item: item.period_end)
        rendered_code = _scope_code(code, current.consolidated)
        rounded = _rounded(value)
        self.metrics.append(
            DerivedMetric(
                symbol=current.symbol,
                period_end=period_end,
                metric_code=rendered_code,
                metric_label_vi=RATIO_LABELS[code],
                value=float(rounded),
                unit=unit,
            )
        )
        publication_dates = [item.publication_date for item in inputs]
        publication_date = (
            max(item for item in publication_dates if item is not None)
            if all(item is not None for item in publication_dates)
            else None
        )
        if publication_date is None:
            self.warn(
                f"{current.symbol} {period_end.isoformat()} {rendered_code} "
                "uses an input without a publication date; the displayed "
                "metric is excluded from historical backtests."
            )
        self.traces.append(
            NormalizedFinancialObservation(
                symbol=current.symbol,
                period_end=period_end,
                period_type=current.period_type,
                statement_type="derived_metric",
                metric_code=rendered_code,
                base_metric_code=code,
                metric_label_vi=RATIO_LABELS[code],
                value=rounded,
                currency=(
                    inputs[0].currency
                    if unit not in {"ratio", "times"}
                    else "N/A"
                ),
                unit=unit,
                consolidated=current.consolidated,
                value_basis=(
                    current.value_basis
                    if unit not in {"ratio", "times"}
                    else ValueBasis.RATIO
                ),
                restatement_version=max(
                    item.restatement_version for item in inputs
                ),
                publication_date=publication_date,
                source_url=(
                    price.source_url if price is not None else current.source_url
                ),
                source_name="deterministic_calculation",
                ingested_at=max(item.ingested_at for item in inputs),
                calculation=formula,
            )
        )


def _compatible(
    left: NormalizedFinancialObservation,
    right: NormalizedFinancialObservation,
) -> bool:
    return (
        left.symbol == right.symbol
        and left.consolidated == right.consolidated
        and left.currency == right.currency
        and left.unit == right.unit
        and left.period_type == right.period_type
    )


def _previous_period(
    candidates: list[NormalizedFinancialObservation],
    current: NormalizedFinancialObservation,
    *,
    year_offset: int = 0,
) -> NormalizedFinancialObservation | None:
    if current.period_type == "year":
        target = (current.period_end.year - max(year_offset, 1), 0)
        return next(
            (
                item
                for item in candidates
                if item.period_end.year == target[0]
                and _compatible(current, item)
            ),
            None,
        )
    year, quarter = _quarter(current.period_end)
    if year_offset:
        target = (year - year_offset, quarter)
    elif quarter == 1:
        target = (year - 1, 4)
    else:
        target = (year, quarter - 1)
    return next(
        (
            item
            for item in candidates
            if _quarter(item.period_end) == target
            and _compatible(current, item)
        ),
        None,
    )


def _safe_ratio(
    builder: _MetricBuilder,
    *,
    code: str,
    numerator: NormalizedFinancialObservation,
    denominator: NormalizedFinancialObservation,
    period_end: date,
    formula: str,
    multiplier: Decimal = Decimal(1),
    additional_inputs: tuple[NormalizedFinancialObservation, ...] = (),
) -> None:
    if not _compatible(numerator, denominator):
        builder.warn(
            f"{numerator.symbol} {period_end.isoformat()} {code} was not "
            "calculated because input currency, unit, scope, or period type "
            "does not match."
        )
        return
    if denominator.value == 0:
        builder.warn(
            f"{numerator.symbol} {period_end.isoformat()} {code} was not "
            "calculated because its denominator is zero."
        )
        return
    builder.emit(
        code=code,
        period_end=period_end,
        value=(numerator.value * multiplier) / denominator.value,
        unit="ratio",
        inputs=(numerator, denominator, *additional_inputs),
        formula=formula,
    )


def calculate_panel_metrics(
    observations: tuple[NormalizedFinancialObservation, ...],
    *,
    price: PricePoint | None = None,
) -> PanelCalculationResult:
    """Calculate all feasible initial-panel metrics from explicit inputs."""

    items = _latest_versions(observations)
    builder = _MetricBuilder()
    standalone = [
        item
        for item in items
        if item.value_basis in {ValueBasis.STANDALONE, ValueBasis.ANNUAL}
    ]
    cumulative = [
        item for item in items if item.value_basis is ValueBasis.CUMULATIVE
    ]
    for item in cumulative:
        has_standalone = any(
            candidate.symbol == item.symbol
            and candidate.period_end == item.period_end
            and candidate.base_metric_code == item.base_metric_code
            and candidate.consolidated == item.consolidated
            for candidate in standalone
        )
        if not has_standalone:
            builder.warn(
                f"{item.symbol} {item.period_end.isoformat()} "
                f"{item.base_metric_code} is cumulative; no standalone "
                "quarter is available for growth or margin calculations."
            )

    by_period: dict[
        tuple[str, bool, str, date],
        dict[str, NormalizedFinancialObservation],
    ] = {}
    for item in items:
        key = (
            item.symbol,
            item.consolidated,
            item.period_type,
            item.period_end,
        )
        by_period.setdefault(key, {})[item.metric_code] = item

    revenues = [item for item in standalone if item.metric_code == "revenue"]
    for revenue in revenues:
        qoq_base = _previous_period(revenues, revenue)
        if qoq_base is not None:
            _safe_ratio(
                builder,
                code=(
                    "revenue_yoy_growth"
                    if revenue.period_type == "year"
                    else "revenue_qoq_growth"
                ),
                numerator=replace(
                    revenue, value=revenue.value - qoq_base.value
                ),
                denominator=qoq_base,
                period_end=revenue.period_end,
                formula="(revenue_current / revenue_previous) - 1",
            )
        if revenue.period_type == "quarter":
            yoy_base = _previous_period(revenues, revenue, year_offset=1)
            if yoy_base is not None:
                _safe_ratio(
                    builder,
                    code="revenue_yoy_growth",
                    numerator=replace(
                        revenue, value=revenue.value - yoy_base.value
                    ),
                    denominator=yoy_base,
                    period_end=revenue.period_end,
                    formula="(revenue_current / revenue_prior_year) - 1",
                )

        period_values = by_period[
            (
                revenue.symbol,
                revenue.consolidated,
                revenue.period_type,
                revenue.period_end,
            )
        ]
        for numerator_code, metric_code in (
            ("gross_profit", "gross_margin"),
            ("operating_profit", "operating_margin"),
            ("net_income", "net_margin"),
        ):
            numerator = period_values.get(numerator_code)
            if numerator is not None and numerator in standalone:
                _safe_ratio(
                    builder,
                    code=metric_code,
                    numerator=numerator,
                    denominator=revenue,
                    period_end=revenue.period_end,
                    formula=f"{numerator_code} / revenue",
                )

        net_income = period_values.get("net_income")
        equity = period_values.get("equity")
        assets = period_values.get("total_assets")
        prior_key = (
            _previous_period(
                [
                    item
                    for item in items
                    if item.metric_code == "equity"
                ],
                equity,
            )
            if equity is not None
            else None
        )
        prior_assets = (
            _previous_period(
                [
                    item
                    for item in items
                    if item.metric_code == "total_assets"
                ],
                assets,
            )
            if assets is not None
            else None
        )
        annualizer = Decimal(4) if revenue.period_type == "quarter" else Decimal(1)
        if net_income is not None and equity is not None and prior_key is not None:
            average_equity = (equity.value + prior_key.value) / Decimal(2)
            average_observation = replace(equity, value=average_equity)
            _safe_ratio(
                builder,
                code="roe",
                numerator=net_income,
                denominator=average_observation,
                period_end=revenue.period_end,
                formula="annualized_net_income / average_equity",
                multiplier=annualizer,
                additional_inputs=(prior_key,),
            )
        if net_income is not None and assets is not None and prior_assets is not None:
            average_assets = (assets.value + prior_assets.value) / Decimal(2)
            average_observation = replace(assets, value=average_assets)
            _safe_ratio(
                builder,
                code="roa",
                numerator=net_income,
                denominator=average_observation,
                period_end=revenue.period_end,
                formula="annualized_net_income / average_total_assets",
                multiplier=annualizer,
                additional_inputs=(prior_assets,),
            )
        liabilities = period_values.get("total_liabilities")
        if liabilities is not None and equity is not None:
            _safe_ratio(
                builder,
                code="debt_to_equity",
                numerator=liabilities,
                denominator=equity,
                period_end=revenue.period_end,
                formula="total_liabilities / equity",
            )
        operating_cash_flow = period_values.get("operating_cash_flow")
        capital_expenditure = period_values.get("capital_expenditure")
        if (
            operating_cash_flow is not None
            and capital_expenditure is not None
            and _compatible(operating_cash_flow, capital_expenditure)
        ):
            builder.emit(
                code="free_cash_flow",
                period_end=revenue.period_end,
                value=operating_cash_flow.value - capital_expenditure.value,
                unit=operating_cash_flow.unit,
                inputs=(operating_cash_flow, capital_expenditure),
                formula="operating_cash_flow - capital_expenditure",
            )

    if price is not None:
        for denominator_code, metric_code in (
            ("eps_ttm", "pe"),
            ("book_value_per_share", "pb"),
        ):
            denominator = max(
                (
                    item
                    for item in items
                    if item.metric_code == denominator_code
                    and item.consolidated
                ),
                key=lambda item: item.period_end,
                default=None,
            )
            if denominator is None:
                continue
            if (
                denominator.value <= 0
                or price.value <= 0
                or denominator.symbol != price.symbol
                or denominator.currency != price.currency
                or denominator.unit != price.unit
            ):
                builder.warn(
                    f"{price.symbol} {denominator.period_end.isoformat()} "
                    f"{metric_code} requires a positive denominator and "
                    "a price with matching symbol, currency, and unit."
                )
                continue
            builder.emit(
                code=metric_code,
                period_end=denominator.period_end,
                value=price.value / denominator.value,
                unit="times",
                inputs=(denominator,),
                formula=f"market_price / {denominator_code}",
                price=price,
            )

    ordered_metrics = tuple(
        sorted(
            builder.metrics,
            key=lambda metric: (metric.period_end, metric.metric_code),
        )
    )
    ordered_traces = tuple(
        sorted(
            builder.traces,
            key=lambda item: (item.period_end, item.metric_code),
        )
    )
    return PanelCalculationResult(
        metrics=ordered_metrics,
        trace_observations=ordered_traces,
        warnings=tuple(builder.warnings),
    )
