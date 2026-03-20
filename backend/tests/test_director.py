"""
AdEngineAI — Director Agent Tests
====================================
Unit tests: run without API keys — use mocked LLM responses.
Integration test: requires GROQ_API_KEY, marked separately.

Run unit tests:
    pytest tests/test_director.py -v -k "not integration"

Run integration test:
    pytest tests/test_director.py -v -m integration
"""

import os
import pytest
from unittest.mock import AsyncMock, patch

from researcher.agent import ResearchResult


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESEARCH = ResearchResult(
    product_name="SuperGlow Vitamin C Serum",
    product_url="https://example.com/superglow",
    product_category="skincare",
    pain_points=[
        "Dark spots that don't respond to cheaper products",
        "Hyperpigmentation that persists for years",
        "Greasy serums that don't absorb properly",
        "Products that promise results but deliver none",
        "Expensive dermatologist treatments",
    ],
    selling_points=[
        "Visibly reduces dark spots within 3 weeks",
        "Lightweight — absorbs in under 30 seconds",
        "Nurse-recommended and dermatologist-tested",
        "Works on all skin types including sensitive",
        "Clinical-grade 20% vitamin C concentration",
    ],
    social_proof=[
        '"Cleared my dark spots in 3 weeks!"',
        '"As a nurse, this is legitimately effective."',
        '"My skin looks 5 years younger."',
    ],
    target_audience="Women 28-45 with hyperpigmentation who've failed with cheaper alternatives",
    price_point="$49.99",
    key_differentiator="Clinical-grade vitamin C that's stable enough to actually absorb",
    confidence_score=0.85,
    confidence_notes="Good data",
)

# Simulated LLM response — 5 well-formed scripts
SAMPLE_LLM_RESPONSE = [
    {
        "hook_type": "problem",
        "hook_line": "Still waking up to dark spots?",
        "script": (
            "Still waking up to dark spots every single morning? "
            "You've tried the creams, the serums, the expensive treatments. "
            "Nothing seems to work. Here's what most brands won't tell you — "
            "the vitamin C in most drugstore serums degrades before it even reaches your skin. "
            "That means you're paying for nothing. "
            "SuperGlow uses a clinically-stable 20% vitamin C formula that actually absorbs. "
            "The difference? Real customers are seeing visible results in just three weeks. "
            "Dark spots fading. Skin tone evening out. Confidence coming back. "
            "Over 47,000 people have already made the switch. "
            "Your skin deserves something that actually works. "
            "Try SuperGlow today — link in bio."
        ),
        "hook_score": {
            "score": 87,
            "primary_trigger": "loss aversion",
            "reasoning": "Opens by naming the exact frustration the viewer already feels. High relevance for the target audience who've tried and failed with cheaper products.",
            "best_platform": "instagram",
        },
        "ad_headline": "Dark Spots Gone in 3 Weeks",
        "ad_description": "Clinical-grade vitamin C that actually absorbs. 47,000+ customers. See results or your money back.",
        "caption_instagram": "Tired of dark spots that won't budge? This is why nothing worked before 👇 Link in bio.",
        "caption_tiktok": "POV: you finally found what actually works for dark spots",
        "caption_linkedin": "Discover the science behind why most vitamin C serums fail — and what actually works.",
        "hashtags": ["#skincare", "#vitaminc", "#darkspots", "#hyperpigmentation", "#glowup",
                     "#skincareRoutine", "#clearskin", "#superglow", "#serumreview",
                     "#skintok", "#beautytips", "#skincarecommunity", "#glowingskin",
                     "#antiaging", "#brightening"],
    },
    {
        "hook_type": "secret",
        "hook_line": "The reason your serum isn't working...",
        "script": (
            "The reason your serum isn't working has nothing to do with your skin. "
            "Most vitamin C serums are already dead by the time you apply them. "
            "Vitamin C degrades when exposed to light and air — "
            "and most brands use unstable formulas that lose potency within weeks of opening. "
            "SuperGlow solved this with a patented stabilisation technology "
            "that keeps the formula active for the full duration of use. "
            "That's why dermatologists recommend it. "
            "That's why nurses use it personally. "
            "And that's why customers are seeing dark spots fade in as little as three weeks. "
            "You're not the problem. Your serum is. "
            "Switch to something that actually delivers. "
            "SuperGlow — link in bio."
        ),
        "hook_score": {
            "score": 92,
            "primary_trigger": "curiosity gap",
            "reasoning": "Opens with a revelation that reframes the viewer's past failures as not their fault. Extremely high shareability for this audience.",
            "best_platform": "tiktok",
        },
        "ad_headline": "Why Your Serum Isn't Working",
        "ad_description": "Most vitamin C degrades before it absorbs. SuperGlow's stable formula actually reaches your skin.",
        "caption_instagram": "Nobody talks about this 👇 Why your vitamin C serum is probably doing nothing.",
        "caption_tiktok": "The dark truth about vitamin C serums nobody tells you",
        "caption_linkedin": "The formulation gap in the skincare industry — and how SuperGlow closed it.",
        "hashtags": ["#skincaretruth", "#vitaminc", "#skincarescience", "#darkspots",
                     "#hyperpigmentation", "#skincarevitiamin", "#beautyhacks",
                     "#skincaretips", "#serumreview", "#superglow", "#glowup",
                     "#clearskin", "#skintok", "#beautytok", "#skincareingredients"],
    },
    {
        "hook_type": "social_proof",
        "hook_line": "47,000 people switched. Here's why.",
        "script": (
            "47,000 people have switched to SuperGlow in the last six months. "
            "We asked them why. "
            "Sarah said: 'I cleared my dark spots in three weeks after years of trying everything.' "
            "Maria said: 'As a nurse, I've tested a lot of products. This one is legitimately different.' "
            "James said: 'I bought it for my wife and she won't stop talking about it.' "
            "The common thread? They all tried cheaper alternatives first. "
            "They all wasted money on products that made promises they couldn't keep. "
            "SuperGlow uses a clinical-grade formula that dermatologists actually recommend. "
            "Not because of marketing. Because of results. "
            "Join 47,000 people who stopped settling. "
            "Try SuperGlow — link in bio."
        ),
        "hook_score": {
            "score": 84,
            "primary_trigger": "social proof",
            "reasoning": "Leads with scale then backs it with specific named testimonials. The nurse quote adds credibility that's rare in skincare advertising.",
            "best_platform": "facebook",
        },
        "ad_headline": "47,000 Switched to SuperGlow",
        "ad_description": "Real customers. Real results. Dark spots visibly reduced in 3 weeks or your money back.",
        "caption_instagram": "47,000 people can't be wrong 🙌 Real results, real people. Link in bio.",
        "caption_tiktok": "I asked 47,000 SuperGlow customers why they switched. Their answers:",
        "caption_linkedin": "What 47,000 customers taught us about what actually works in skincare.",
        "hashtags": ["#skincarereview", "#vitaminc", "#darkspots", "#testimonial",
                     "#skincareresults", "#superglow", "#hyperpigmentation", "#realresults",
                     "#beautycommunity", "#skintok", "#glowup", "#clearskin",
                     "#skincareRoutine", "#brightening", "#skincaretransformation"],
    },
    {
        "hook_type": "visual_first",
        "hook_line": "Watch what 3 weeks does.",
        "script": (
            "Watch what three weeks of SuperGlow does to dark spots. "
            "Week one — you'll notice your skin looks more even in tone. "
            "The dullness starts to lift. "
            "Week two — dark spots begin to fade visibly. "
            "Friends start asking if you've changed something. "
            "Week three — the transformation is undeniable. "
            "The spots that have bothered you for years? Significantly lighter. "
            "This isn't a filter. This isn't edited. "
            "This is what happens when clinical-grade vitamin C actually absorbs into your skin. "
            "SuperGlow is the only serum with a stabilised 20% formula that dermatologists recommend. "
            "See it for yourself. "
            "Try SuperGlow for 30 days — completely risk free. "
            "Link in bio."
        ),
        "hook_score": {
            "score": 79,
            "primary_trigger": "visual transformation",
            "reasoning": "Week-by-week progression creates anticipation and makes the result feel achievable and real. Works best when paired with strong before/after visuals.",
            "best_platform": "instagram",
        },
        "ad_headline": "See Results in 3 Weeks",
        "ad_description": "Week-by-week visible transformation. Clinical vitamin C that absorbs. 30-day risk-free trial.",
        "caption_instagram": "Week 1 → Week 2 → Week 3 ✨ Watch the transformation. Link in bio.",
        "caption_tiktok": "3 weeks of SuperGlow. Watch what happens.",
        "caption_linkedin": "A 3-week clinical demonstration of what stable vitamin C actually does to skin.",
        "hashtags": ["#beforeandafter", "#skintransformation", "#vitaminc", "#darkspots",
                     "#skincareglow", "#superglow", "#glowup", "#hyperpigmentation",
                     "#skincareresults", "#clearskin", "#skintok", "#beautytransformation",
                     "#realresults", "#skincareroutine", "#brighteningserum"],
    },
    {
        "hook_type": "emotional",
        "hook_line": "You deserve to feel confident.",
        "script": (
            "You deserve to feel confident in your own skin. "
            "Not just on good days — every day. "
            "But when you've been dealing with dark spots for years, "
            "confidence starts to feel like something other people have. "
            "You avoid certain lighting. You reach for more coverage. "
            "You've tried product after product and nothing lasts. "
            "That's not a skin problem. That's an exhausting cycle. "
            "SuperGlow was created for exactly this moment — "
            "when you're ready to stop covering up and start clearing up. "
            "Clinical-grade vitamin C that actually works, backed by dermatologists, "
            "loved by over 47,000 people who felt exactly like you do right now. "
            "You've waited long enough. "
            "Try SuperGlow — link in bio."
        ),
        "hook_score": {
            "score": 88,
            "primary_trigger": "aspiration and identity",
            "reasoning": "Connects to the deeper emotional desire beneath the surface problem. 'Confidence' resonates strongly with the 28-45 female audience who've been struggling for years.",
            "best_platform": "instagram",
        },
        "ad_headline": "Finally Feel Confident in Your Skin",
        "ad_description": "Stop covering up. Start clearing up. 47,000 people made the switch. 30-day guarantee.",
        "caption_instagram": "For everyone who's been hiding behind more coverage 💛 You deserve better. Link in bio.",
        "caption_tiktok": "This one's for everyone tired of the cycle. You deserve to feel confident.",
        "caption_linkedin": "The confidence gap in skincare — why results matter more than promises.",
        "hashtags": ["#selfconfidence", "#skincare", "#vitaminc", "#darkspots",
                     "#selflove", "#superglow", "#glowup", "#hyperpigmentation",
                     "#skincarejourney", "#clearskin", "#beautytok", "#skintok",
                     "#confidence", "#skincaremotivation", "#realbeauty"],
    },
]


# ---------------------------------------------------------------------------
# Director Agent unit tests
# ---------------------------------------------------------------------------

class TestDirectorAgent:

    def _make_agent(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            from director.agent import DirectorAgent
            return DirectorAgent()

    @pytest.mark.asyncio
    async def test_returns_exactly_five_scripts(self):
        agent = self._make_agent()
        with patch("director.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_RESPONSE)):
            scripts = await agent.run(SAMPLE_RESEARCH)
        assert len(scripts) == 5

    @pytest.mark.asyncio
    async def test_scripts_in_correct_hook_order(self):
        agent = self._make_agent()
        with patch("director.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_RESPONSE)):
            scripts = await agent.run(SAMPLE_RESEARCH)
        types = [s.hook_type for s in scripts]
        assert types == ["problem", "secret", "social_proof", "visual_first", "emotional"]

    @pytest.mark.asyncio
    async def test_all_scripts_have_hook_score(self):
        from director.agent import HookScore
        agent = self._make_agent()
        with patch("director.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_RESPONSE)):
            scripts = await agent.run(SAMPLE_RESEARCH)
        for script in scripts:
            assert isinstance(script.hook_score, HookScore)
            assert 0 <= script.hook_score.score <= 100
            assert script.hook_score.reasoning != ""

    @pytest.mark.asyncio
    async def test_all_scripts_have_platform_captions(self):
        agent = self._make_agent()
        with patch("director.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_RESPONSE)):
            scripts = await agent.run(SAMPLE_RESEARCH)
        for script in scripts:
            assert script.caption_instagram != ""
            assert script.caption_tiktok != ""
            assert script.caption_linkedin != ""

    @pytest.mark.asyncio
    async def test_all_scripts_have_hashtags(self):
        agent = self._make_agent()
        with patch("director.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_RESPONSE)):
            scripts = await agent.run(SAMPLE_RESEARCH)
        for script in scripts:
            assert len(script.hashtags) > 0

    @pytest.mark.asyncio
    async def test_ad_headline_max_40_chars(self):
        agent = self._make_agent()
        with patch("director.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_RESPONSE)):
            scripts = await agent.run(SAMPLE_RESEARCH)
        for script in scripts:
            assert len(script.ad_headline) <= 40, \
                f"Headline too long: '{script.ad_headline}' ({len(script.ad_headline)} chars)"

    @pytest.mark.asyncio
    async def test_returns_fallbacks_when_llm_fails(self):
        agent = self._make_agent()
        with patch("director.agent.complete_json", new=AsyncMock(side_effect=Exception("API error"))):
            scripts = await agent.run(SAMPLE_RESEARCH)
        assert len(scripts) == 5
        for script in scripts:
            assert script.hook_score.score == 50
            assert "Fallback" in script.hook_score.reasoning

    @pytest.mark.asyncio
    async def test_handles_partial_llm_response(self):
        """If LLM returns only 3 scripts, fills the missing 2 with fallbacks."""
        agent = self._make_agent()
        partial = SAMPLE_LLM_RESPONSE[:3]
        with patch("director.agent.complete_json", new=AsyncMock(return_value=partial)):
            scripts = await agent.run(SAMPLE_RESEARCH)
        assert len(scripts) == 5

    @pytest.mark.asyncio
    async def test_word_count_property(self):
        agent = self._make_agent()
        with patch("director.agent.complete_json", new=AsyncMock(return_value=SAMPLE_LLM_RESPONSE)):
            scripts = await agent.run(SAMPLE_RESEARCH)
        for script in scripts:
            assert script.word_count > 0

    @pytest.mark.asyncio
    async def test_brand_context_reaches_prompt(self):
        agent = self._make_agent()
        captured: list[str] = []

        async def capture(cfg, system, user):
            captured.append(user)
            return SAMPLE_LLM_RESPONSE

        with patch("director.agent.complete_json", new=capture):
            await agent.run(
                SAMPLE_RESEARCH,
                brand_tone="warm and empowering",
                brand_audience="women over 40",
            )

        assert len(captured) == 1
        assert "warm and empowering" in captured[0]
        assert "women over 40" in captured[0]


# ---------------------------------------------------------------------------
# Integration test — real Groq call
# Run: pytest tests/test_director.py -v -m integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDirectorIntegration:

    @pytest.mark.asyncio
    async def test_director_with_real_research(self):
        """
        Full Director run with real Groq API.
        Requires: GROQ_API_KEY in .env
        """
        from director.agent import DirectorAgent

        agent = DirectorAgent()
        scripts = await agent.run(
            SAMPLE_RESEARCH,
            brand_tone="confident and science-backed",
            brand_audience="women 28-45 interested in skincare",
        )

        assert len(scripts) == 5

        print("\n" + "="*60)
        for script in scripts:
            print(f"\nHOOK TYPE:   {script.hook_type.upper()}")
            print(f"HOOK LINE:   {script.hook_line}")
            print(f"SCORE:       {script.hook_score.score}/100")
            print(f"TRIGGER:     {script.hook_score.primary_trigger}")
            print(f"REASONING:   {script.hook_score.reasoning}")
            print(f"BEST FOR:    {script.hook_score.best_platform}")
            print(f"WORDS:       {script.word_count}")
            print(f"HEADLINE:    {script.ad_headline}")
            print(f"SCRIPT:\n{script.script}")
            print("-"*60)