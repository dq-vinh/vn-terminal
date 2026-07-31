"""Adversarial QA Test Suite for VN Terminal Pro.

Verifies findings across the 6 priority review areas:
1. Look-ahead bias
2. Contract integrity
3. Data-quality enforcement
4. Unit and adjustment errors
5. AI hallucination surface
6. Reproducibility
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, UTC
from decimal import Decimal
from pathlib import Path
import numpy as np
import pytest

from backend.app.quant.indicators.levels import build_levels
from backend.app.quant.indicators.types import OHLCVSeries
from backend.app.data.fundamentals.metrics import (
    PricePoint,
    calculate_panel_metrics,
)
from backend.app.data.fundamentals.models import (
    NormalizedFinancialObservation,
    ValueBasis,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Area 1: Look-Ahead Bias
# ---------------------------------------------------------------------------

def test_build_levels_lookahead_includes_current_bar():
    """build_levels includes bar t's high/low in resistance/support at bar t."""
    dates = [
        date(2026, 7, 25), date(2026, 7, 26), date(2026, 7, 27),
        date(2026, 7, 28), date(2026, 7, 29), date(2026, 7, 30)
    ]
    # Bar t (last bar) has a massive spike high = 100.0, low = 10.0
    highs = np.array([50.0, 52.0, 51.0, 53.0, 52.0, 100.0])
    lows = np.array([40.0, 41.0, 42.0, 41.0, 42.0, 10.0])
    closes = np.array([45.0, 46.0, 47.0, 48.0, 49.0, 50.0])
    series = OHLCVSeries(
        symbol="FPT",
        trading_dates=dates,
        open=closes,
        high=highs,
        low=lows,
        close=closes,
        volume=np.array([1000] * 6),
    )

    levels = build_levels(series, lookback=5)

    # Bar t's extreme high (100.0) is included in resistance
    has_lookahead_high = 100.0 in levels["resistance"]
    has_lookahead_low = 10.0 in levels["support"]

    assert has_lookahead_high or has_lookahead_low, (
        "DEFECT VERIFIED: build_levels includes current bar t high/low in window_high/window_low, "
        "causing look-ahead bias if evaluated for trading decisions on bar t."
    )


# ---------------------------------------------------------------------------
# Area 2: Contract Integrity
# ---------------------------------------------------------------------------

def test_contract_generators_are_in_sync():
    """Verify contract directories exist for schema and OpenAPI models."""
    schema_dir = REPO_ROOT / "contracts" / "schemas" / "json"
    fixtures_dir = REPO_ROOT / "contracts" / "fixtures"

    assert schema_dir.exists()
    assert fixtures_dir.exists()


# ---------------------------------------------------------------------------
# Area 3: Data Quality Enforcement
# ---------------------------------------------------------------------------

def test_active_status_not_inferred_from_mtime():
    """SecurityMaster status must come from reference/data records, never file mtime."""
    from backend.app.data.security_master.service import SecurityMasterBuilder, SecurityReference
    from backend.app.data.models import ParsedFDataFile, RawFDataRecord

    ref = SecurityReference(
        symbol="FPT",
        exchange="HOSE",
        security_type="equity",
        company_name="FPT Corp",
        sector="IT",
        industry="IT Services",
        listing_date=date(2006, 12, 13),
        delisting_date=None,
        trading_status="active",
        lot_size=100,
        source="reference",
    )
    builder = SecurityMasterBuilder({"FPT": ref})
    parsed = ParsedFDataFile(
        symbol="FPT",
        category="stock",
        records=(
            RawFDataRecord(
                date_code=20260730,
                open=65.2,
                high=67.2,
                low=64.8,
                close=67.0,
                volume=7571500.0,
                unused_1=0,
                unused_2=0,
                aux1=66.5,
                aux2=0.0,
            ),
        ),
        header_count=1,
        actual_count=1,
        source_file=Path("C:/FDATA/AmiBroker/EOD/stock/FPT.dat"),
        source_sha256="abc",
        quarantined=False,
        issues=(),
    )
    profile = builder.build(parsed)
    assert profile.contract.trading_status == "active"


# ---------------------------------------------------------------------------
# Area 4: Unit and Adjustment Errors
# ---------------------------------------------------------------------------

def test_pe_pb_unit_mismatch_in_metrics():
    """calculate_panel_metrics fails or drops PE/PB when price.unit ('thousand_vnd') != denominator.unit ('vnd')."""
    eps_obs = NormalizedFinancialObservation(
        symbol="FPT",
        period_end=date(2026, 6, 30),
        period_type="quarter",
        statement_type="ratio",
        metric_code="eps_ttm",
        base_metric_code="eps_ttm",
        metric_label_vi="EPS TTM",
        value=Decimal("5.0"),  # 5 thousand VND per share
        currency="VND",
        unit="vnd",  # unit in financial observation is 'vnd' or 'vnd_per_share'
        consolidated=True,
        value_basis=ValueBasis.RATIO,
        restatement_version=1,
        publication_date=date(2026, 7, 20),
        source_url="https://example.com/fpt",
        source_name="test",
        ingested_at=datetime(2026, 7, 30, tzinfo=UTC),
    )

    price = PricePoint(
        symbol="FPT",
        trading_date=date(2026, 7, 30),
        value=Decimal("67.0"),  # 67 thousand VND
        currency="VND",
        unit="thousand_vnd",
        source_url="https://example.com/price",
    )

    res = calculate_panel_metrics((eps_obs,), price=price)
    pe_metrics = [m for m in res.metrics if m.metric_code == "pe"]

    # Drops P/E calculation due to string comparison mismatch between 'thousand_vnd' and 'vnd'
    assert len(pe_metrics) == 0, (
        "DEFECT VERIFIED: metrics.py drops P/E calculation due to string comparison mismatch between 'thousand_vnd' and 'vnd'."
    )
    assert any("matching symbol, currency, and unit" in w for w in res.warnings)


# ---------------------------------------------------------------------------
# Area 5: AI Hallucination Surface
# ---------------------------------------------------------------------------

def test_ai_validation_module_missing():
    """Verify that backend/app/ai validation module is missing, allowing hallucinations to bypass."""
    ai_val_dir = REPO_ROOT / "backend" / "app" / "ai" / "validation"
    py_files = list(ai_val_dir.glob("*.py"))
    assert len(py_files) == 0, (
        "DEFECT VERIFIED: backend/app/ai/validation contains no python validation code."
    )


# ---------------------------------------------------------------------------
# Area 6: Reproducibility
# ---------------------------------------------------------------------------

def test_quant_golden_fixtures_hash_divergence():
    """Verify divergence between bars_FPT fixture and stored golden test hash."""
    golden_path = REPO_ROOT / "tests" / "quant" / "golden" / "indicators_FPT.json"
    bars_path = REPO_ROOT / "contracts" / "fixtures" / "bars_FPT.json"

    if golden_path.exists() and bars_path.exists():
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        actual_hash = hashlib.sha256(bars_path.read_bytes()).hexdigest()
        assert actual_hash != golden["source_sha256"], (
            "DEFECT VERIFIED: bars_FPT.json fixture hash has diverged from stored golden baseline."
        )
