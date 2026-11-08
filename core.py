from __future__ import annotations

import csv
import datetime
import hashlib
import json
import os
import re

from anthropic import Anthropic

from product_facts import ALLOWED_NUMBERS, PRODUCT_FACTS

MODEL = "claude-sonnet-5"

LOG_PATH = "logs/generations.csv"

ANGLE_DESCRIPTIONS = {
    "Pain": "Focus on the frustrating everyday problem the product solves — the annoyance, "
    "repetition, or small daily pain point the viewer immediately recognizes.",
    "Relatable Scenario": "Put the viewer directly into a specific, relatable everyday scenario "
    "('POV: you...') so they picture themselves living through the before/after moment.",
    "Money": "Frame the product around saving or wasting money — cost of the problem vs. "
    "cost of the fix, value for money, avoiding repeat purchases.",
    "Interesting Fact": "Lead with a surprising or explanatory fact about the product or the "
    "problem it solves (how the clip works, why socks go missing) to spark curiosity, "
    "without inventing specific unverifiable numbers.",
    "Social Proof": "Lean on trust signals — other customers, reviews, popularity — "
    "without inventing specific unverifiable numbers.",
}

ANGLES = list(ANGLE_DESCRIPTIONS.keys())

PROMPT_TEMPLATE = """You are a direct-response ad copywriter for SockLock. Below is the script \
of a currently winning video ad creative.

Verified product facts (the only numbers you may use):
{product_facts}

Your task: generate fresh variants for a new creative modification, reusing the same \
underlying offer as the winning script but varying the framing across the requested angles, \
so a designer can quickly assemble new ads without rewriting copy from scratch.

Winning script:
---
{script}
---

{tested_block}

Angles to cover:
{angles}

For EACH angle, generate exactly {n} variants for each of these three categories:
1. hook - the opening line of the video (first 1-2 seconds, must grab attention)
2. first_line - the first spoken/voiceover line right after the hook
3. on_screen_text - short on-screen text overlay (3-6 words, punchy)

If a list of already-tested hooks is provided above, do NOT repeat them verbatim and prefer \
patterns similar to the ones marked as winning/high-performing, avoid patterns similar to \
ones marked as losing/low-performing.

IMPORTANT: Do not invent specific statistics, numbers, review counts, customer counts, \
ratings, or unverifiable factual claims (e.g. "50,000 households", "5-star reviews", \
"thousands of customers") unless such a number literally appears in the winning script above. \
For social-proof-style angles, use qualitative phrasing (e.g. "loved by real customers", \
"thousands of happy parents" only if already implied by the script) instead of fabricated figures.

Respond with ONLY valid JSON, no markdown fences, in this exact shape:
{{
  "<angle name>": {{
    "hooks": ["...", "..."],
    "first_lines": ["...", "..."],
    "on_screen_texts": ["...", "..."]
  }},
  ...
}}
"""


def build_tested_block(tested_rows: list[dict] | None) -> str:
    if not tested_rows:
        return ""
    lines = ["Already-tested hooks (for reference, avoid duplicating verbatim):"]
    for row in tested_rows:
        hook = row.get("hook", "")
        angle = row.get("angle", "")
        status = row.get("status", "")
        lines.append(f"- [{status or 'unknown'}] [{angle or 'unspecified'}] {hook}")
    return "\n".join(lines)


def build_angles_block(angles: list[str]) -> str:
    lines = []
    for angle in angles:
        description = ANGLE_DESCRIPTIONS.get(angle, "")
        lines.append(f"- {angle}: {description}" if description else f"- {angle}")
    return "\n".join(lines)


def generate_variants(
    script: str,
    angles: list[str],
    n: int,
    api_key: str,
    tested_rows: list[dict] | None = None,
) -> dict:
    client = Anthropic(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(
        script=script,
        product_facts=PRODUCT_FACTS.strip(),
        tested_block=build_tested_block(tested_rows),
        angles=build_angles_block(angles),
        n=n,
    )
    message = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [b.text for b in message.content if b.type == "text"]
    raw = "".join(text_blocks).strip()
    raw = _strip_markdown_fence(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        if message.stop_reason == "max_tokens":
            raise ValueError(
                "Response got cut off by the token limit (too many angles/variants in one "
                "request). Reduce the number of variants per angle or the number of angles."
            ) from e
        raise ValueError(f"Model did not return valid JSON:\n{raw}") from e


def _strip_markdown_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def log_generation(script: str, angles: list[str], n: int) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    is_new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "script_hash", "angles", "n_variants", "model"])
        script_hash = hashlib.sha1(script.encode("utf-8")).hexdigest()[:8]
        writer.writerow(
            [datetime.datetime.utcnow().isoformat(), script_hash, ";".join(angles), n, MODEL]
        )


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def _is_duplicate_hook(hook: str, tested_rows: list[dict] | None) -> bool:
    if not tested_rows:
        return False
    normalized = _normalize(hook)
    return any(_normalize(row.get("hook", "")) == normalized for row in tested_rows)


def _is_too_long(hook: str, max_words: int = 12) -> bool:
    return len(hook.split()) > max_words


def _suspicious_numbers(text: str) -> list[str]:
    found = re.findall(r"\$?\d+%?", text)
    return [f for f in found if re.sub(r"[^\d]", "", f) not in ALLOWED_NUMBERS]


def flatten_to_rows(variants_by_angle: dict) -> list[dict]:
    rows = []
    type_labels = {
        "hooks": "hook",
        "first_lines": "first_line",
        "on_screen_texts": "on_screen_text",
    }
    for angle, variants in variants_by_angle.items():
        for key, label in type_labels.items():
            for text in variants.get(key, []):
                rows.append({"angle": angle, "type": label, "text": text})
    return rows


def to_combined_rows(variants_by_angle: dict, tested_rows: list[dict] | None = None) -> list[dict]:
    rows = []
    for angle, variants in variants_by_angle.items():
        if rows:
            rows.append({"angle": "", "variant": "", "check": ""})
        hooks = variants.get("hooks", [])
        first_lines = variants.get("first_lines", [])
        on_screen_texts = variants.get("on_screen_texts", [])
        n = min(len(hooks), len(first_lines), len(on_screen_texts))
        for i in range(n):
            flags = []
            if _is_duplicate_hook(hooks[i], tested_rows):
                flags.append("hook looks like an already-tested one")
            if _is_too_long(hooks[i]):
                flags.append("hook too long for a 3-second opener")
            for label, text in (
                ("hook", hooks[i]),
                ("first_line", first_lines[i]),
                ("on_screen", on_screen_texts[i]),
            ):
                suspicious = _suspicious_numbers(text)
                if suspicious:
                    flags.append(f"verify fact in {label}: {', '.join(suspicious)}")
            combined = (
                f"HOOK: {hooks[i]}\n"
                f"FIRST LINE: {first_lines[i]}\n"
                f"ON-SCREEN: {on_screen_texts[i]}"
            )
            rows.append(
                {
                    "angle": angle,
                    "variant": combined,
                    "check": "; ".join(flags) if flags else "ok",
                }
            )
    return rows
