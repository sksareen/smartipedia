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
```"""


async def generate_topic(
    title: str,
    search_results: list[dict],
    openrouter_key: str | None = None,
    model: str | None = None,
) -> dict:
    """Generate an encyclopedia article via OpenRouter.

    Args:
        openrouter_key: BYOK — agent's own OpenRouter key. Falls back to server key.
        model: Model override. Falls back to server default.

    Returns {"content_md": str, "related_topics": list[str], "summary": str, "infobox": dict, "model": str}
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
3. An ```infobox``` JSON block with key structured facts"""

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
        # Remove infobox block from content
        content = content[:infobox_match.start()] + content[infobox_match.end():]

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
        "model": model_used,
    }
