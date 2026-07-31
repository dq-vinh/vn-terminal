"""Security-master construction without modification-time heuristics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from contracts.schemas.models.security_master import SecurityMaster

from ..models import ParsedFDataFile
from ..quality.checks import date_from_code


@dataclass(frozen=True, slots=True)
class SecurityReference:
    symbol: str
    exchange: str
    security_type: str
    company_name: str
    sector: str
    industry: str
    listing_date: date
    delisting_date: date | None
    trading_status: str
    lot_size: int
    source: str
    isin: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    index_code: str | None = None


@dataclass(frozen=True, slots=True)
class SecurityProfile:
    contract: SecurityMaster
    last_positive_volume_date: date | None
    blocked_reason: str | None = None


class SecurityMasterBuilder:
    def __init__(self, references: Mapping[str, SecurityReference]):
        self._references = {
            symbol.upper(): reference for symbol, reference in references.items()
        }

    def build(self, parsed: ParsedFDataFile) -> SecurityProfile:
        reference = self._references.get(parsed.symbol)
        positive_dates = [
            trading_date
            for record in parsed.records
            if record.volume > 0
            and (trading_date := date_from_code(record.date_code)) is not None
        ]
        last_positive = max(positive_dates, default=None)
        if reference is not None:
            valid_from = reference.valid_from or reference.listing_date
            return SecurityProfile(
                contract=SecurityMaster(
                    symbol=reference.symbol.upper(),
                    isin=reference.isin,
                    exchange=reference.exchange,
                    security_type=reference.security_type,
                    company_name=reference.company_name,
                    sector=reference.sector,
                    industry=reference.industry,
                    listing_date=reference.listing_date,
                    delisting_date=reference.delisting_date,
                    trading_status=reference.trading_status,
                    currency="VND",
                    price_unit="thousand_vnd",
                    lot_size=reference.lot_size,
                    source=reference.source,
                    valid_from=valid_from,
                    valid_to=reference.valid_to,
                    index_code=reference.index_code,
                ),
                last_positive_volume_date=last_positive,
            )

        valid_dates = [
            trading_date
            for record in parsed.records
            if (trading_date := date_from_code(record.date_code)) is not None
        ]
        first_date = min(valid_dates, default=date(1970, 1, 1))
        category_type = {
            "index": "index",
            "der": "derivative",
            "cw": "warrant",
            # Section 19.2 says the stock directory contains mixed types.
            "stock": "unknown",
        }.get(parsed.category, "unknown")
        missing_index_mapping = (
            parsed.category == "index" and parsed.symbol.isdigit()
        )
        return SecurityProfile(
            contract=SecurityMaster(
                symbol=parsed.symbol,
                isin=None,
                exchange="UNKNOWN",
                security_type=category_type,
                company_name="UNMAPPED",
                sector="UNKNOWN",
                industry="UNKNOWN",
                listing_date=first_date,
                delisting_date=None,
                trading_status=(
                    "blocked_missing_index_mapping"
                    if missing_index_mapping
                    else "unknown"
                ),
                currency="VND",
                price_unit="thousand_vnd",
                # One is a neutral storage placeholder, never a trading rule.
                lot_size=1,
                source="Fialda FData; authoritative security master unavailable",
                valid_from=first_date,
                valid_to=None,
                index_code=parsed.symbol if parsed.category == "index" else None,
            ),
            last_positive_volume_date=last_positive,
            blocked_reason=(
                "index_code_mapping_unavailable"
                if missing_index_mapping
                else "security_reference_unavailable"
            ),
        )
