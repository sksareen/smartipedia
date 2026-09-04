"""Backfill embeddings for topics that have none.

Every topic created before the fire-and-forget embedding task was fixed has a
NULL embedding, which makes semantic search return nothing. Run once after
deploying the fix; safe to re-run (it only touches NULL rows).

    docker exec smartipedia-backend-1 python -m scripts.backfill_embeddings
"""
import asyncio
import sys

from sqlalchemy import select, update

from app.database import async_session
from app.models import Topic
from app.services.llm import generate_embedding

CONCURRENCY = 5
BATCH = 50


async def embed_one(topic_id, slug, text, sem) -> bool:
    async with sem:
        try:
            embedding = await generate_embedding(text)
        except Exception as e:
            print(f"  fail {slug}: {e}", flush=True)
            return False
    if not embedding:
        print(f"  skip {slug}: no embedding returned", flush=True)
        return False
    async with async_session() as session:
        await session.execute(
            update(Topic).where(Topic.id == topic_id).values(embedding=embedding)
        )
        await session.commit()
    return True


async def main() -> int:
    sem = asyncio.Semaphore(CONCURRENCY)
    done = failed = 0

    while True:
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(Topic.id, Topic.slug, Topic.title, Topic.summary)
                    .where(Topic.embedding.is_(None))
                    .limit(BATCH)
                )
            ).all()

        if not rows:
            break

        results = await asyncio.gather(
            *(
                embed_one(r.id, r.slug, f"{r.title}: {r.summary or ''}".strip(), sem)
                for r in rows
            )
        )
        done += sum(results)
        failed += len(results) - sum(results)
        print(f"embedded {done} (failed {failed})", flush=True)

        # Every row came back unembeddable — stop rather than spin forever.
        if not any(results):
            print("no progress in this batch, aborting", flush=True)
            return 1

    print(f"done: {done} embedded, {failed} failed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
