import httpx

from ..config import settings


async def web_search(query: str, num_results: int = 8) -> list[dict]:
    """Search the web via SearxNG and return results with URLs, titles, snippets."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.searxng_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "engines": "google,brave,duckduckgo",
                    "language": "en",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for r in data.get("results", [])[:num_results]:
            results.append(
                {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("content", ""),
                }
            )
        return results
    except Exception as e:
        print(f"SearxNG search error: {e}")
        return []
