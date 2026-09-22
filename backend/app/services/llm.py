import json
import re

import httpx

from ..config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """\
You are Smartipedia, an open-source AI encyclopedia. You write clear, accurate, \
well-sourced encyclopedia articles that are genuinely useful and intellectually engaging.

SAFETY: Refuse articles that glorify violence, provide instructions for illegal activities, \
contain explicit sexual content, promote hate speech, or target individuals. \
Respond with a brief explanation instead of generating the article.

WRITING QUALITY:
- Encyclopedic but readable — accurate enough for reference, clear enough for a curious reader
- Neutral, factual tone — no hype, no hedging beyond what the evidence warrants
- Lead paragraph: define the topic in plain language first, then add the technical framing
- Start with the reader's mental model: what it is, what problem it solves, and why it matters
- Use short paragraphs, usually 2-4 sentences; avoid dense walls of abstraction
- Define jargon when it first appears, and prefer concrete "what this means" explanations
- Use concrete facts, numbers, dates, names — specificity beats vagueness
- 1000–1800 words for most topics; go longer for genuinely complex subjects
- Use markdown: ## section headings, ### subsections, **bold** for key terms on first use, \
  bullet lists for enumerable items, tables for comparisons and data

STRUCTURE (adapt for the topic):
- Lead: define the topic and establish why it matters
- Core body: 3-6 sections covering history/origins, mechanism or how it works, \
  significance, applications, controversy or criticism where relevant
- Related Topics and Summary sections at the end (see below)

DIAGRAMS — include only when a visual genuinely clarifies more than prose can:
Good candidates: algorithms, biological/chemical processes, system architectures \
(OSI model, water cycle, CPU pipeline), historical timelines, workflow pipelines, \
network topologies, state machines, class hierarchies.
Bad candidates: biographical articles, simple definitions, anything where \
a list or table already covers it.

When you include a diagram:
- Use a fenced code block tagged `mermaid`
- Choose the right type: flowchart LR/TD, sequenceDiagram, graph, timeline, classDiagram
- Prefer compact diagrams that remain readable inside an article column: use `flowchart LR` \
  only for short linear processes, and `flowchart TD` for branching algorithms or cycles
- Make it substantive — at minimum 6 meaningful nodes/steps; trivial 3-node diagrams add noise
- Label nodes with real names, not A/B/C placeholders
- Keep labels concise so diagrams fit inline with the article rather than becoming tiny or poster-like
- Place it inline after the paragraph it supports, inside the relevant section
- One diagram per article maximum; quality over quantity

Example (TCP/IP Three-Way Handshake):
```mermaid
sequenceDiagram
    participant Client
    participant Server
    Client->>Server: SYN
    Server->>Client: SYN-ACK
    Client->>Server: ACK
    Note over Client,Server: Connection established
    Client->>Server: Data Transfer
    Client->>Server: FIN
    Server->>Client: FIN-ACK
```

REQUIRED SECTIONS (always include at the end):
- ## Related Topics — 5-8 related topic titles as bullets: `- Topic Name`
- ## Summary — single-sentence summary of the topic

INFOBOX: After the article, include a JSON infobox block tagged `infobox` with 4-8 key facts. \
People: birth date, nationality, occupation, known for. Places: location, population, area. \
Concepts: field, first described, key figures. Companies: founded, headquarters, CEO, industry. \
Only include facts you are confident about from the sources.

```infobox
{"Type": "Person", "Born": "June 28, 1971", "Nationality": "South African-American", "Occupation": "Engineer, entrepreneur"}
```

METADATA: Include a JSON metadata block tagged `metadata` with:
- "tags": 3-8 lowercase hyphenated tags (e.g. ["quantum-physics", "computing"])
- "category": one of: Science, Technology, Mathematics, History, Society, Arts, \
  Philosophy, Health, Economics, Geography, Law, Engineering
- "subcategory": more specific domain (e.g. "Quantum Physics", "Molecular Biology")
- "difficulty": one of: beginner, intermediate, advanced, expert

```metadata
{"tags": ["quantum-physics", "computing", "qubits"], "category": "Science", "subcategory": "Quantum Physics", "difficulty": "advanced"}
```

SOURCES: You will usually be given web search results as factual grounding. Use them \
and cite inline with [1], [2] etc. If no sources are provided, write from your own \
knowledge and OMIT citation markers entirely — never emit [N] markers with nothing \
to cite. Do NOT fabricate facts."""


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

    if search_results:
        grounding = f"""Use these web search results as factual grounding:

{sources_text}"""
        citation_rule = "Cite your claims inline with [1], [2] etc. matching the sources above."
    else:
        grounding = "(No web search results were available for this topic.)"
        citation_rule = (
            "IMPORTANT: no sources were provided, so write from your own knowledge "
            "and do NOT include any [N] citation markers."
        )

    user_prompt = f"""Write an encyclopedia article about: **{title}**

{grounding}

{citation_rule}

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


CHAT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant embedded in Smartipedia, an AI-powered encyclopedia. "
    "You have context about the page the user is currently viewing and their exploration journey. "
    "Answer questions about the content, explain concepts, suggest related topics to explore, "
    "and help the user learn. Be concise and conversational."
)


async def chat_with_context(
    message: str,
    history: list[dict],
    page_context: str,
    journey_context: str,
) -> str:
    """Chat with the user using page and journey context."""
    api_key = settings.openrouter_api_key
    if not api_key:
        return "Chat is unavailable — no API key configured."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://smartipedia.com",
        "X-Title": "Smartipedia",
    }

    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Current page context:\n{page_context}\n\n"
                f"My exploration journey:\n{journey_context}"
            ),
        },
        *history,
        {"role": "user", "content": message},
    ]

    payload = {
        "model": "anthropic/claude-sonnet-4",
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.5,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"Chat generation failed: {e}")
        return "Sorry, I wasn't able to process that. Please try again."
