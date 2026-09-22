"""Quarantine SEO-spam topics (dry-run by default).

Sets quality.status = "quarantined" on topics whose titles match the spam
patterns in services/moderation.py. Quarantined topics stay readable at their
URL but disappear from the homepage, search, graph and sitemap.

Usage (from repo root, DATABASE_URL in .env):
    .venv/bin/python backend/scripts/quarantine_spam.py            # dry run
    .venv/bin/python backend/scripts/quarantine_spam.py --apply    # execute
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select  # noqa: E402

from backend.app.database import async_session  # noqa: E402
from backend.app.models import Topic  # noqa: E402
from backend.app.services.moderation import is_spam_title  # noqa: E402


async def main(apply: bool) -> None:
    async with async_session() as db:
        rows = list((await db.execute(select(Topic))).scalars().all())

    hits = [t for t in rows if is_spam_title(t.title)]
    already = [
        t for t in hits
        if (t.metadata_ or {}).get("quality", {}).get("status") == "quarantined"
    ]
    todo = [t for t in hits if t not in already]

    print(f"scanned {len(rows)} topics, {len(hits)} match spam patterns ({len(already)} already quarantined)")
    for t in todo:
        print(f"  QUARANTINE  {t.slug}  —  {t.title}")

    if not todo:
        print("nothing to do.")
        return
    if not apply:
        print(f"\ndry run — re-run with --apply to quarantine {len(todo)} topics.")
        return

    async with async_session() as db:
        for t in todo:
            topic = await db.get(Topic, t.id)
            meta = dict(topic.metadata_ or {})
            quality = dict(meta.get("quality", {}))
            quality["status"] = "quarantined"
            flagged = list(quality.get("flagged_issues", []))
            flagged.append("quarantined as SEO spam (automated cleanup 2026-09)")
            quality["flagged_issues"] = flagged
            meta["quality"] = quality
            topic.metadata_ = meta
        await db.commit()
    print(f"\nquarantined {len(todo)} topics.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
