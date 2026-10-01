import re

# ──────────────────────────────────────────────────────────────────────────────
# PII Masking
# ──────────────────────────────────────────────────────────────────────────────

def mask_pii(text: str) -> str:
    """Masks PII (email, credit card, phone) before sending to LLM."""
    # Email
    text = re.sub(r'[\w\.-]+@[\w\.-]+', '[REDACTED_EMAIL]', text)
    # Credit card (13-16 digits, optionally separated by spaces/dashes)
    text = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[REDACTED_CARD]', text)
    # Indian phone numbers: 10-digit starting with 6-9, optionally with +91 prefix
    text = re.sub(r'(?:\+91[\s-]?)?[6-9]\d{9}\b', '[REDACTED_PHONE]', text)
    # Generic international phone: +XX-XXX-XXX-XXXX patterns
    text = re.sub(r'\+?\d[\d\s\-\(\)]{8,14}\d', '[REDACTED_PHONE]', text)
    return text


# ──────────────────────────────────────────────────────────────────────────────
# Prompt Injection Detection
# ──────────────────────────────────────────────────────────────────────────────

_INJECTION_PHRASES = [
    "ignore all previous",
    "ignore previous instructions",
    "system prompt",
    "override instructions",
    "you are now a",
    "disregard your",
    "forget your instructions",
    "act as if you are",
    "pretend you are",
    "DAN mode",
]

def check_prompt_injection(text: str) -> bool:
    """Returns True if the input appears to be a prompt injection attempt."""
    lower = text.lower()
    return any(phrase in lower for phrase in _INJECTION_PHRASES)


# ──────────────────────────────────────────────────────────────────────────────
# Output Guardrails
# ──────────────────────────────────────────────────────────────────────────────

_RESTRICTED_OUTPUT = [
    "internal system error",
    "system prompt:",
    "you are a helpful assistant",
    "<system>",
]

def check_output_guardrails(text) -> bool:
    """Returns True if the output is safe to send to the user."""
    if isinstance(text, list):
        text = " ".join(str(x) for x in text)
    else:
        text = str(text)

    lower = text.lower()
    return not any(phrase in lower for phrase in _RESTRICTED_OUTPUT)
