"""How many stored formulas read a bare number as mm (FORMULA-BARE-UNIT).

Read-only: it counts the ``expression_bare_mm`` warnings every non-mm part's
features and parameter table would carry, and changes nothing (the fix is
the user's own edit). Run it against a database with::

    POSTGRES_URL=postgresql://... uv run python -m documents.bare_unit_scan
"""

import asyncio
import json
import sys
from dataclasses import asdict, dataclass

from loft_wire.bare_units import parameter_warnings
from py_kit.db import async_dsn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from documents import db
from documents.feature_expressions import formula_warnings, load_feature


@dataclass
class ScanReport:
    """What :func:`scan` found."""

    parts_scanned: int = 0
    parts_with_warnings: int = 0
    feature_formulas: int = 0
    parameter_formulas: int = 0
    unreadable_features: int = 0


async def scan(session: AsyncSession) -> ScanReport:
    """Count the warnings of every part whose unit is not mm."""
    report = ScanReport()
    parts = (
        await session.execute(select(db.Part).where(db.Part.length_unit != "mm"))
    ).scalars()
    for part in parts:
        report.parts_scanned += 1
        found = len(parameter_warnings(part.parameters, part.length_unit))
        report.parameter_formulas += found
        rows = (
            await session.execute(
                select(db.Feature).where(db.Feature.part_id == part.id)
            )
        ).scalars()
        for row in rows:
            try:
                envelope = load_feature(row)[0]
            except ValueError:
                report.unreadable_features += 1
                continue
            count = len(formula_warnings(part, envelope) or [])
            report.feature_formulas += count
            found += count
        report.parts_with_warnings += found > 0
    return report


async def run_scan(url: str) -> ScanReport:
    """:func:`scan` the database at *url*."""
    engine = create_async_engine(async_dsn(url))
    try:
        async with async_sessionmaker(engine)() as session:
            return await scan(session)
    finally:
        await engine.dispose()


def main() -> None:
    """Print the report as JSON; POSTGRES_URL names the database."""
    from documents.main import DocumentsSettings

    url = DocumentsSettings().postgres_url
    if url is None:
        sys.exit("bare_unit_scan: set POSTGRES_URL")
    report = asyncio.run(run_scan(url))
    json.dump(asdict(report), sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
