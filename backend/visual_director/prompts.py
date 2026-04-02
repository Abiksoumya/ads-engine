"""
AdEngineAI — Visual Director Prompts
======================================
LLM prompts for generating video briefs.

Two prompt types:
  1. Campaign prompt  — product ad from script
  2. Creation prompt  — any video from text description
"""

# ─── System prompt ───────────────────────────────────────────────────────────

VISUAL_DIRECTOR_SYSTEM = """You are an expert AI video director and creative strategist.
You specialize in creating cinematic video briefs for social media ads and content videos.

Your job is to take a script or description and produce a detailed video brief
that tells exactly how each scene should look, feel, and move.

You understand:
- Color theory and mood
- Camera movements and angles
- Visual storytelling and pacing
- Social media video formats (TikTok, Reels, YouTube)
- Product advertising psychology
- Cinematic techniques

You always output valid JSON only. No explanation, no markdown, no extra text.
Just the JSON object."""


# ─── Campaign prompt (product ad) ────────────────────────────────────────────

def build_campaign_brief_prompt(
    hook_type: str,
    hook_line: str,
    script_text: str,
    product_name: str,
    product_description: str,
    product_images: list[str],
    scene_count: int,
    user_preferences: dict,
) -> str:
    images_text = "\n".join([f"  - {url}" for url in product_images[:3]]) if product_images else "  - No images provided"
    prefs = user_preferences or {}

    return f"""Create a detailed video brief for this product advertisement.

PRODUCT:
  Name: {product_name}
  Description: {product_description}
  Images available:
{images_text}

SCRIPT:
  Hook type: {hook_type}
  Hook line: "{hook_line}"
  Full script: {script_text}

USER PREFERENCES:
  Tone: {prefs.get('tone', 'auto - based on hook type')}
  Color palette: {prefs.get('color_palette', 'auto')}
  Pacing: {prefs.get('pacing', 'medium')}
  Background style: {prefs.get('background_style', 'auto')}
  Duration: {scene_count * 10} seconds ({scene_count} scenes x 10 seconds each)

INSTRUCTIONS:
Generate exactly {scene_count} scenes for this video ad.

Scene structure rules:
- Scene 1: Hook visual — grabs attention, matches the hook line
- Middle scenes: Product benefit / feature showcase
- Last scene: CTA — product + call to action

For each scene provide:
- background: detailed description of setting/environment
- action: what physically happens in this scene
- color_mood: specific colors and lighting description  
- camera: camera movement and angle
- text_overlay: text shown on screen (or null if none)
- use_product_image: true if product image should appear in this scene
- kling_prompt: the exact text prompt to send to Kling AI video generator
  (make this very detailed and cinematic, 50-100 words)

The kling_prompt must:
- Describe the visual scene in detail
- Include lighting, atmosphere, camera movement
- End with: "cinematic quality, 4K, professional advertisement"
- If use_product_image is true, reference the product naturally

Output this exact JSON structure:
{{
  "overall": {{
    "tone": "string - e.g. dramatic_to_relief, inspirational, energetic",
    "color_palette": "string - e.g. warm_orange_to_cool_blue",
    "pacing": "fast | medium | slow",
    "music_mood": "none",
    "voiceover_script": "string - the exact words spoken as voiceover (condensed from script, max 80 words)"
  }},
  "scenes": [
    {{
      "scene_number": 1,
      "duration": 10,
      "background": "string",
      "action": "string",
      "color_mood": "string",
      "camera": "string",
      "text_overlay": "string or null",
      "use_product_image": true or false,
      "kling_prompt": "string - detailed prompt for Kling AI"
    }}
  ]
}}"""


# ─── Video Creator prompt (text to video) ────────────────────────────────────

def build_creation_brief_prompt(
    user_prompt: str,
    uploaded_images: list[str],
    scene_count: int,
    user_preferences: dict,
) -> str:
    images_text = "\n".join([f"  - {url}" for url in uploaded_images[:3]]) if uploaded_images else "  - No images provided"
    prefs = user_preferences or {}

    return f"""Create a detailed video brief and script for this video idea.

USER'S VIDEO IDEA:
"{user_prompt}"

UPLOADED IMAGES (if any):
{images_text}

USER PREFERENCES:
  Tone: {prefs.get('tone', 'auto')}
  Color palette: {prefs.get('color_palette', 'auto')}
  Pacing: {prefs.get('pacing', 'medium')}
  Background style: {prefs.get('background_style', 'auto')}
  Duration: {scene_count * 10} seconds ({scene_count} scenes x 10 seconds each)

INSTRUCTIONS:
First, write a voiceover script for this video (max 80 words).
Then generate exactly {scene_count} scenes.

The video should tell a clear story:
- Opening: hook the viewer in first 3 seconds
- Middle: develop the story/message
- End: conclusion or call to action

For each scene provide:
- background: detailed description of setting/environment
- action: what physically happens in this scene
- color_mood: specific colors and lighting
- camera: camera movement and angle
- text_overlay: text shown on screen (or null)
- use_uploaded_image: true if user's uploaded image should appear
- kling_prompt: exact detailed prompt for Kling AI (50-100 words)

Output this exact JSON structure:
{{
  "overall": {{
    "tone": "string",
    "color_palette": "string",
    "pacing": "fast | medium | slow",
    "music_mood": "none",
    "voiceover_script": "string - the voiceover narration for the full video"
  }},
  "scenes": [
    {{
      "scene_number": 1,
      "duration": 10,
      "background": "string",
      "action": "string",
      "color_mood": "string",
      "camera": "string",
      "text_overlay": "string or null",
      "use_uploaded_image": true or false,
      "kling_prompt": "string - detailed prompt for Kling AI"
    }}
  ]
}}"""


# ─── Tone options ─────────────────────────────────────────────────────────────

TONE_OPTIONS = [
    "dramatic_to_relief",
    "inspirational",
    "energetic",
    "professional",
    "emotional",
    "humorous",
    "mysterious",
    "urgent",
    "warm_and_friendly",
    "luxury",
]

COLOR_PALETTE_OPTIONS = [
    "warm_orange_to_cool_blue",
    "dark_and_moody",
    "bright_and_vibrant",
    "minimal_white",
    "golden_hour",
    "cool_blue_tech",
    "earthy_natural",
    "neon_futuristic",
    "soft_pastel",
    "high_contrast_bw",
]

PACING_OPTIONS = ["fast", "medium", "slow"]

BACKGROUND_OPTIONS = [
    "nature_forest",
    "urban_city",
    "studio_minimal",
    "office_corporate",
    "home_lifestyle",
    "abstract_geometric",
    "outdoor_adventure",
    "luxury_interior",
]