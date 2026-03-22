import json
import re

import httpx

from ..config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """\
You are Smartipedia, an open-source AI encyclopedia. You write clear, accurate, \
well-sourced encyclopedia articles.

Rules:
- Write in neutral, encyclopedic tone (like Wikipedia but more readable)
- Use markdown: headings (##), bold, bullet points, tables where useful
- Be comprehensive but concise — aim for 800-1500 words
- Include concrete facts, dates, numbers where relevant
- At the end, include a "## Related Topics" section with 5-8 related topic titles \
  (these become links in the knowledge graph). Format each as a bullet: `- Topic Name`
- At the end, include a "## Summary" section with a single sentence summary

IMPORTANT: You will be given web search results as context. Use them to ground your \
article in facts. Cite sources inline using [1], [2] etc. Do NOT fabricate facts.

INFOBOX: After the article, include a JSON infobox block wrapped in a fenced code block \
tagged `infobox`. This should contain 4-8 key structured facts about the topic as \
key-value pairs. For people: birth date, nationality, occupation, etc. For places: \
location, population, area, etc. For concepts: field, first described, key figures, etc. \
For companies: founded, headquarters, CEO, industry, etc. Only include facts you are \
confident about from the sources. Example format:

```infobox
{"Type": "Person", "Born": "June 28, 1971", "Nationality": "South African-American", "Occupation": "Engineer, entrepreneur"}
```

METADATA: Also include a JSON metadata block wrapped in a fenced code block tagged \
`metadata`. It must contain:
- "tags": 3-8 lowercase hyphenated tags relevant to the topic (e.g. ["quantum-physics", "computing"])
- "category": the primary knowledge domain — one of: "Science", "Technology", "Mathematics", \
  "History", "Society", "Arts", "Philosophy", "Health", "Economics", "Geography", "Law", "Engineering"
- "subcategory": a more specific domain (e.g. "Quantum Physics", "Molecular Biology")
- "difficulty": one of "beginner", "intermediate", "advanced", "expert"

```metadata
{"tags": ["quantum-physics", "computing", "qubits"], "category": "Science", "subcategory": "Quantum Physics", "difficulty": "advanced"}
```"""


async def generate_topic(
    title: str,
    search_results: list[dict],
    openrouter_key: str | None = None,
    model: str | None = None,
) -> dict:
    """Generate an encyclopedia article via OpenRouter.

    Returns {"content_md": str, "related_topics": list[str], "summary": str, "infobox": dict, "metadata": dict, "model": str}
    """
    api_key = openrouter_key or settings.openrouter_api_key
    model_id = model or settings.openrouter_model

    if not api_key:
        raise ValueError("No OpenRouter API key provided. Pass X-OpenRouter-Key header or set OPENROUTER_API_KEY.")

    sources_text = ""
    for i, r in enumerate(search_results, 1):
        sources_text += f"[{i}] {r['title']}\n    URL: {r['url']}\n    {r['snippet']}\n\n"

    user_prompt = f"""Write an encyclopedia article about: **{title}**

Use these web search results as factual grounding:

{sources_text}

Remember to include:
1. A "## Related Topics" section at the end with 5-8 related topics
2. A "## Summary" section with a one-sentence summary
3. An ```infobox``` JSON block with key structured facts
4. A ```metadata``` JSON block with tags, category, subcategory, difficulty"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://smartipedia.com",
        "X-Title": "Smartipedia",
    }

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.3,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    model_used = data.get("model", settings.openrouter_model)

    # Parse infobox from content
    infobox = {}
    infobox_match = re.search(r"```infobox\s*\n(.*?)\n```", content, re.DOTALL)
    if infobox_match:
        try:
            infobox = json.loads(infobox_match.group(1).strip())
        except json.JSONDecodeError:
            pass
        content = content[:infobox_match.start()] + content[infobox_match.end():]

    # Parse metadata from content
    topic_metadata = {}
    metadata_match = re.search(r"```metadata\s*\n(.*?)\n```", content, re.DOTALL)
    if metadata_match:
        try:
            topic_metadata = json.loads(metadata_match.group(1).strip())
        except json.JSONDecodeError:
            pass
        content = content[:metadata_match.start()] + content[metadata_match.end():]

    # Inject default quality status
    topic_metadata.setdefault("quality", {"status": "generated", "reviewed_by": [], "flagged_issues": []})

    # Parse related topics and summary from the content
    related_topics = []
    summary = ""
    in_related = False
    in_summary = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("## related topics"):
            in_related = True
            in_summary = False
            continue
        if stripped.lower().startswith("## summary"):
            in_related = False
            in_summary = True
            continue
        if stripped.startswith("## "):
            in_related = False
            in_summary = False
            continue
        if in_related and stripped.startswith("- "):
            topic = stripped[2:].strip().strip("*[]")
            if topic:
                related_topics.append(topic)
        if in_summary and stripped:
            summary = stripped

    return {
        "content_md": content,
        "related_topics": related_topics,
        "summary": summary,
        "infobox": infobox,
        "metadata": topic_metadata,
        "model": model_used,
    }


async def generate_topic_preview(title: str) -> str:
    """Generate a quick one-line preview (under 15 words) for a topic via LLM."""
    api_key = settings.openrouter_api_key
    if not api_key:
        return f"{title} — an encyclopedia topic"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://smartipedia.com",
        "X-Title": "Smartipedia",
    }

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": "You write ultra-short encyclopedia previews. Reply with ONLY a single sentence under 15 words. No quotes, no punctuation at the start. Just a concise factual description."},
            {"role": "user", "content": f"What is: {title}"},
        ],
        "max_tokens": 60,
        "temperature": 0.2,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Preview generation failed: {e}")
        return f"{title} — explore this topic"


async def generate_embedding(
    text: str,
    api_key: str | None = None,
) -> list[float] | None:
    """Generate a 1536-dim embedding via OpenRouter."""
    key = api_key or settings.openrouter_api_key
    if not key:
        return None

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://smartipedia.com",
        "X-Title": "Smartipedia",
    }

    payload = {
        "model": settings.embedding_model,
        "input": text[:8000],  # truncate to stay within limits
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        print(f"Embedding generation failed: {e}")
        return None
