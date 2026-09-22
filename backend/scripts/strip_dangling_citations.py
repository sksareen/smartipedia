"""Strip dangling [N] citation markers from sourceless articles (dry-run default).

Articles generated while web search was down have `sources == []` but still
contain inline [1], [2] markers pointing at nothing. This removes markers of
the form " [12]" from content_md and re-renders content_html. Mechanical
cleanup — no revision rows are written.

Usage (from repo root, DATABASE_URL in .env):
    .venv/bin/python backend/scripts/strip_dangling_citations.py            # dry run
    .venv/bin/python backend/scripts/strip_dangling_citations.py --apply    # execute
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import markdown  # noqa: E402
from sqlalchemy import select  # noqa: E402

from backend.app.database import async_session  # noqa: E402
from backend.app.models import Topic  # noqa: E402

_MARKER = re.compile(r" \[(\d{1,3})\]")


async def main(apply: bool) -> None:
    async with async_session() as db:
        rows = list((await db.execute(select(Topic))).scalars().all())

    todo = []
    for t in rows:
        if t.sources:  # has real sources — markers are legitimate
            continue
        markers = _MARKER.findall(t.content_md or "")
        if markers:
            todo.append((t, len(markers)))

    print(f"scanned {len(rows)} topics, {len(todo)} sourceless articles contain markers")
    for t, n in todo[:30]:
        print(f"  STRIP {n:3d} markers  {t.slug}")
    if len(todo) > 30:
        print(f"  ... and {len(todo) - 30} more")

    if not todo:
        print("nothing to do.")
        return
    if not apply:
        print(f"\ndry run — re-run with --apply to fix {len(todo)} articles.")
        return

    async with async_session() as db:
        for t, _ in todo:
            topic = await db.get(Topic, t.id)
            cleaned = _MARKER.sub("", topic.content_md or "")
            topic.content_md = cleaned
            topic.content_html = markdown.markdown(
                cleaned, extensions=["tables", "fenced_code", "toc"]
            )
        await db.commit()
    print(f"\nfixed {len(todo)} articles.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
