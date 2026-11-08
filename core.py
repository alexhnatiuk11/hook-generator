from __future__ import annotations

import json
import os

from anthropic import Anthropic

MODEL = "claude-sonnet-5"

ANGLE_DESCRIPTIONS = {
    "Біль": "Focus on the frustrating everyday problem the product solves — the annoyance, "
    "repetition, or small daily pain point the viewer immediately recognizes.",
    "Сценка з життя": "Put the viewer directly into a specific, relatable everyday scenario "
    "('POV: you...') so they picture themselves living through the before/after moment.",
    "Гроші": "Frame the product around saving or wasting money — cost of the problem vs. "
    "cost of the fix, value for money, avoiding repeat purchases.",
    "Обмежена пропозиція": "Create urgency or fear of missing out — scarcity, limited availability, "
    "social momentum ('everyone is switching'), time pressure.",
    "Соціальний доказ": "Lean on trust signals — other customers, reviews, popularity — "
    "without inventing specific unverifiable numbers.",
}

ANGLES = list(ANGLE_DESCRIPTIONS.keys())

PROMPT_TEMPLATE = """You are a direct-response ad copywriter for SockLock, a subscription \
sock-pairing product. Below is the script of a currently winning video ad creative.

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
                "Відповідь моделі обірвалась по ліміту токенів (забагато кутів/варіантів "
                "за один запит). Зменш кількість варіантів на кут або кількість обраних кутів."
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


def to_combined_rows(variants_by_angle: dict) -> list[dict]:
    rows = []
    for angle, variants in variants_by_angle.items():
        if rows:
            rows.append({"angle": "", "variant": ""})
        hooks = variants.get("hooks", [])
        first_lines = variants.get("first_lines", [])
        on_screen_texts = variants.get("on_screen_texts", [])
        n = min(len(hooks), len(first_lines), len(on_screen_texts))
        for i in range(n):
            combined = (
                f"HOOK: {hooks[i]}\n"
                f"FIRST LINE: {first_lines[i]}\n"
                f"ON-SCREEN: {on_screen_texts[i]}"
            )
            rows.append({"angle": angle, "variant": combined})
    return rows
