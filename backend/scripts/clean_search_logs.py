"""Delete junk search-log rows (dry-run by default).

Removes the historical noise the analytics filters now exclude going forward:
template placeholders ("{search_term_string}"), stubs under 3 chars, and bare
category names. Reporting queries filter these anyway — this just shrinks the
table and fixes old counts.

Usage (from repo root, DATABASE_URL in .env):
    .venv/bin/python backend/scripts/clean_search_logs.py            # dry run
    .venv/bin/python backend/scripts/clean_search_logs.py --apply    # execute
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import delete, func, or_, select  # noqa: E402

from backend.app.database import async_session  # noqa: E402
from backend.app.models import SearchLog  # noqa: E402
from backend.app.services.topics import _METADATA_CATEGORIES  # noqa: E402


def _junk_clause():
    q = SearchLog.query
    return or_(
        q.like("%{%"),
        q.like("%}%"),
        func.length(func.trim(q)) < 3,
        func.lower(func.trim(q)).in_(_METADATA_CATEGORIES),
    )


async def main(apply: bool) -> None:
    async with async_session() as db:
        total = (await db.execute(select(func.count(SearchLog.id)))).scalar_one()
        junk = (
            await db.execute(
                select(func.count(SearchLog.id)).where(_junk_clause())
            )
        ).scalar_one()

    print(f"search_logs: {total} rows, {junk} junk")
    if not junk:
        print("nothing to do.")
        return
    if not apply:
        print("\ndry run — re-run with --apply to delete them.")
        return

    async with async_session() as db:
        await db.execute(delete(SearchLog).where(_junk_clause()))
        await db.commit()
    print(f"\ndeleted {junk} rows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
