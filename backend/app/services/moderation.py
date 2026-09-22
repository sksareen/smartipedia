"""Content moderation for topic generation.

Two layers:
1. Input filter — fast blocklist + heuristic check on titles before calling LLM.
2. LLM prompt — system prompt instructs the model to refuse inappropriate content.
"""

import re

# Categories of blocked content with representative patterns.
# These catch obvious attempts. The LLM system prompt handles subtler cases.
_BLOCKED_PATTERNS: list[re.Pattern] = [
    # Violence / harm
    re.compile(r"\b(how to (make|build|create) (a )?(bomb|weapon|explosive|poison|meth|drug))", re.I),
    re.compile(r"\b(how to (kill|murder|assassinate|poison|torture|harm|attack))", re.I),
    re.compile(r"\b(mass (shooting|murder|killing)s? (guide|how|tutorial))", re.I),
    re.compile(r"\b(terrorist|terrorism) (attack|how|guide|manual)", re.I),
    # CSAM
    re.compile(r"\bchild\b.*\b(porn|sex|nude|naked|erotic)", re.I),
    re.compile(r"\b(pedophil|paedophil)", re.I),
    # Explicit sexual content (encyclopedic articles about sexuality are fine,
    # but explicit how-to / fetish generation is not)
    re.compile(r"\b(porn(ograph)? (of|with|featuring|video|site))", re.I),
    re.compile(r"\b(how to (have sex|seduce|groom))", re.I),
    # Hate / supremacy
    re.compile(r"\b(white|black|race) supremac", re.I),
    re.compile(r"\b(nazi|neo-nazi) (ideology|movement|party) (guide|manual|how)", re.I),
    # Self-harm
    re.compile(r"\b(how to (commit suicide|kill (my|your)self|self[- ]harm))", re.I),
    re.compile(r"\bsuicide method", re.I),
    # Illegal activity
    re.compile(r"\b(how to (hack|ddos|dox|swat|stalk|blackmail|counterfeit))", re.I),
    re.compile(r"\b(how to (steal|rob|shoplift|launder money))", re.I),
]

# Single-word or short-phrase exact blocks (lowercased)
_BLOCKED_EXACT: set[str] = set()

# SEO-spam campaigns: free generation attracts bulk marketing content ("How to
# Audit a virtual card for subscriptions..."). Plain topics ("Virtual card",
# "Link building", "SEO") stay allowed — only the promotional how-to
# conjunctions and outright spam terms are blocked.
_SPAM_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bhow\b.*\bvirtual([-\s]?credit)?[-\s]?cards?\b", re.I),
    re.compile(r"\bhow\b.*\blink[-\s]?building\b", re.I),
    re.compile(r"\b(ad[-\s]?spend|vcc|cracked keys?)\b", re.I),
    re.compile(r"\blink[-\s]?building (software|tool|playbook|platform|app)\b", re.I),
    re.compile(r"\breloadable\b.*\b(virtual|cards?|visa)\b", re.I),
    re.compile(r"\bvirtual[-\s]?card issuance\b", re.I),
    re.compile(r"\bvirtual visa\b.*\bcards?\b", re.I),
    re.compile(r"\bno[-\s]?kyc\b", re.I),
    re.compile(r"\bautomated seo backlinks\b", re.I),
    re.compile(r"\bhow\b.*\bindexnow\b", re.I),
    re.compile(r"\bvirtual[-\s]?credit[-\s]?cards?\b.*\b(billing|probe|cascade|isolation)\b", re.I),
    re.compile(r"\bseo\b.*\b(trial|unlimited|software|tool)s?\b.*\b(how|guide|choose)\b", re.I),
]


class ModerationError(Exception):
    """Raised when content is rejected by moderation."""
    pass


def is_spam_title(title: str) -> bool:
    """Whether a title matches known SEO-spam campaign patterns."""
    cleaned = (title or "").strip().lower()
    return any(p.search(cleaned) for p in _SPAM_PATTERNS)


def check_title(title: str) -> None:
    """Check a topic title against moderation rules.

    Raises ModerationError if the title is blocked.
    Does nothing if the title is acceptable.
    """
    if not title or not title.strip():
        raise ModerationError("Title cannot be empty.")

    cleaned = title.strip().lower()

    # Exact match
    if cleaned in _BLOCKED_EXACT:
        raise ModerationError(
            "This topic cannot be generated. Please choose a different subject."
        )

    # Pattern match
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(cleaned):
            raise ModerationError(
                "This topic cannot be generated. Smartipedia does not create content "
                "related to violence, illegal activities, explicit material, or hate speech."
            )

    # Spam match — bulk SEO / promotional how-tos
    if is_spam_title(title):
        raise ModerationError(
            "This topic looks like promotional or SEO content, which Smartipedia "
            "doesn't generate. Try a neutral encyclopedic title instead."
        )

    # Heuristic: title is suspiciously long (likely a prompt injection attempt)
    if len(title) > 300:
        raise ModerationError(
            "Topic title is too long. Please use a concise title (under 300 characters)."
        )
