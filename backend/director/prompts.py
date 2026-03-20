"""
AdEngineAI — Director Prompts
================================
All prompts for the Director Agent live here.
Agent logic never contains raw prompt strings.

To improve script quality: edit this file only.
Agent code stays untouched.

Script target: ~60 seconds = 150-160 words of voiceover.
"""

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

DIRECTOR_SYSTEM = """You are an expert direct-response video ad copywriter.
You specialise in writing 60-second video ad scripts that stop the scroll and convert.

Your scripts follow a proven story arc:
    Hook (0-5s)      — stop the scroll immediately
    Problem (5-20s)  — agitate the pain the viewer already feels
    Solution (20-40s)— introduce the product as the answer
    Proof (40-52s)   — back it up with social proof or results
    CTA (52-60s)     — one clear call to action

Rules:
    - Each script must be 150-160 words (exactly 60 seconds of voiceover)
    - Write in second person ("you", "your") — speak directly to the viewer
    - Hook line must be the first 3-5 words — make it impossible to scroll past
    - Never mention the brand name in the first 10 seconds
    - Use the exact language customers use — no corporate speak
    - Each of the 5 hooks must feel completely different in tone and angle
    - Hook scores must be honest — not every hook deserves a 90+

Respond with valid JSON only. No markdown, no explanation, no preamble."""


# ---------------------------------------------------------------------------
# Hook type definitions — what makes each one different
# ---------------------------------------------------------------------------

HOOK_DEFINITIONS = {
    "problem": (
        "Opens by naming a specific painful frustration the viewer already feels. "
        "Makes them think 'that's exactly my problem.' "
        "Example opener: 'Still waking up to dark spots...'"
    ),
    "secret": (
        "Opens with a curiosity gap — something most people don't know. "
        "Makes them think 'I need to hear this.' "
        "Example opener: 'The reason your serum isn't working...'"
    ),
    "social_proof": (
        "Opens with a real result from a real customer. "
        "Makes them think 'if it worked for them, it could work for me.' "
        "Example opener: '47,000 people have already tried this...'"
    ),
    "visual_first": (
        "Opens describing a vivid before/after visual transformation. "
        "Designed for silent viewing — the image tells the story. "
        "Example opener: 'Watch what happens when...'"
    ),
    "emotional": (
        "Opens by connecting to a deeper emotional desire or identity. "
        "Makes them feel understood on a personal level. "
        "Example opener: 'You deserve to feel confident in your skin...'"
    ),
}


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

SCRIPT_SCHEMA = """{
  "hook_type": "problem | secret | social_proof | visual_first | emotional",
  "hook_line": "string — opening 3-5 words, the scroll-stopper",
  "script": "string — full 150-160 word voiceover script with 60s story arc",
  "hook_score": {
    "score": 0,
    "primary_trigger": "string — e.g. loss aversion, curiosity gap, social proof, aspiration",
    "reasoning": "string — 1-2 sentences: why this hook should convert for this audience",
    "best_platform": "instagram | tiktok | linkedin | facebook"
  },
  "ad_headline": "string — max 40 chars, benefit-first, for Meta/LinkedIn ads",
  "ad_description": "string — max 125 chars, supporting copy with proof or urgency",
  "caption_instagram": "string — 150 chars max, casual tone, emojis ok",
  "caption_tiktok": "string — 100 chars max, punchy, trend-aware",
  "caption_linkedin": "string — 200 chars max, professional tone, no emojis",
  "hashtags": ["string — 15 relevant hashtags, mix of high and niche volume"]
}"""


FULL_OUTPUT_SCHEMA = f"""Return a JSON array of exactly 5 script objects.
Each object must match this schema:
{SCRIPT_SCHEMA}

The 5 objects must be in this exact order:
1. problem hook
2. secret hook
3. social_proof hook
4. visual_first hook
5. emotional hook"""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_director_prompt(
    product_name: str,
    product_category: str,
    pain_points: list[str],
    selling_points: list[str],
    social_proof: list[str],
    target_audience: str,
    key_differentiator: str,
    price_point: str,
    brand_tone: str = "",
    brand_audience: str = "",
    competitor_hooks: list[str] | None = None,
) -> str:
    """
    Builds the user prompt for the Director Agent LLM call.
    All research intelligence is packed in here cleanly.
    """
    hook_descriptions = "\n".join(
        f"  {i+1}. {name.upper()}: {desc}"
        for i, (name, desc) in enumerate(HOOK_DEFINITIONS.items())
    )

    lines = [
        "=== PRODUCT INTELLIGENCE ===",
        f"Product:          {product_name}",
        f"Category:         {product_category}",
        f"Price:            {price_point or 'not found'}",
        f"Target audience:  {target_audience}",
        f"Key differentiator: {key_differentiator}",
        "",
        "=== TOP PAIN POINTS (use these to write problem/emotional hooks) ===",
    ]

    for i, pain in enumerate(pain_points[:5], 1):
        lines.append(f"  {i}. {pain}")

    lines += [
        "",
        "=== TOP SELLING POINTS (use these in solution/proof sections) ===",
    ]
    for i, point in enumerate(selling_points[:5], 1):
        lines.append(f"  {i}. {point}")

    if social_proof:
        lines += ["", "=== SOCIAL PROOF (use in social_proof hook + proof sections) ==="]
        for i, proof in enumerate(social_proof[:3], 1):
            lines.append(f"  {i}. {proof}")

    if brand_tone or brand_audience:
        lines += ["", "=== BRAND CONTEXT ==="]
        if brand_tone:
            lines.append(f"  Tone:     {brand_tone}")
        if brand_audience:
            lines.append(f"  Audience: {brand_audience}")

    if competitor_hooks:
        lines += ["", "=== COMPETITOR HOOKS TO DIFFERENTIATE FROM ==="]
        for i, hook in enumerate(competitor_hooks[:3], 1):
            lines.append(f"  {i}. {hook}")
        lines.append("  (Do NOT copy these — find a different angle)")

    lines += [
        "",
        "=== HOOK TYPES TO WRITE ===",
        hook_descriptions,
        "",
        "=== OUTPUT FORMAT ===",
        FULL_OUTPUT_SCHEMA,
    ]

    return "\n".join(lines)