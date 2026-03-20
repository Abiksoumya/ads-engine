"""
AdEngineAI — Researcher Prompts
=================================
All prompts for the Researcher Agent live here.
Agent logic never contains raw prompt strings.

To improve research quality: edit this file only.
Agent code stays untouched.
"""


SYNTHESIS_SYSTEM = """You are an expert direct-response advertising researcher.

Your job is to analyse product data and extract the intelligence needed
to write high-converting video ad scripts.

Be specific and concrete:
    GOOD: "Reduces visible dark spots within 3 weeks"
    BAD:  "Helps with skin issues"

Use the exact language customers use in reviews — not marketing speak.
If data is missing or unclear, say so honestly in confidence_notes.

Respond with valid JSON only. No markdown, no explanation, no preamble."""


SYNTHESIS_SCHEMA = """{
  "product_name": "string",
  "product_category": "string — e.g. skincare, fitness equipment, SaaS tool",
  "pain_points": [
    "string — top 5 frustrations customers had BEFORE finding this product"
  ],
  "selling_points": [
    "string — top 5 concrete benefits customers experienced AFTER buying"
  ],
  "social_proof": [
    "string — up to 5 short quotable lines or stats from real customers"
  ],
  "target_audience": "string — 1 sentence: who buys this and why",
  "price_point": "string — the product price if found",
  "key_differentiator": "string — the ONE thing that makes this different from alternatives",
  "confidence_score": 0.0,
  "confidence_notes": "string — brief note on data quality and any gaps"
}"""


def build_synthesis_prompt(
    url: str,
    title: str,
    description: str,
    price: str,
    reviews: list[str],
    brand_tone: str = "",
    brand_audience: str = "",
) -> str:
    """
    Builds the user prompt for the synthesis Claude/Groq call.
    Accepts all scraped data and optional brand context.
    """
    lines = [
        f"Product URL: {url}",
        f"Product Title: {title}",
    ]

    if price:
        lines.append(f"Price: {price}")

    if description:
        lines.append(f"\nProduct Description:\n{description}")

    if reviews:
        sample = reviews[:30]  # cap at 30 to stay within token limits
        lines.append(f"\nCustomer Reviews ({len(sample)} of {len(reviews)} found):")
        for i, review in enumerate(sample, 1):
            lines.append(f"{i}. {review[:300]}")  # cap each review at 300 chars

    if brand_tone or brand_audience:
        lines.append("\nBrand Context:")
        if brand_tone:
            lines.append(f"  Tone: {brand_tone}")
        if brand_audience:
            lines.append(f"  Audience: {brand_audience}")

    lines.append(f"\nReturn your analysis as JSON matching this schema exactly:\n{SYNTHESIS_SCHEMA}")

    return "\n".join(lines)