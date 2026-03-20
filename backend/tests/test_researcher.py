"""
AdEngineAI — Researcher Agent Tests
=====================================
Unit tests: run without any API keys or network — use mocks.
Integration test: requires GROQ_API_KEY + real URL, marked separately.

Run unit tests only:
    pytest tests/test_researcher.py -v

Run everything including integration:
    pytest tests/test_researcher.py -v -m "not integration"
    pytest tests/test_researcher.py -v -m integration
"""

import os
import pytest
from unittest.mock import AsyncMock, patch

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_REVIEWS = [
    "I was struggling with dark spots for years — this cleared them in 3 weeks!",
    "Finally found something that actually works on my hyperpigmentation.",
    "A bit pricey but absolutely worth it. My skin looks 5 years younger.",
    "I was skeptical but wow. The difference in my skin tone is incredible.",
    "As a nurse I've tried many products. This is legitimately effective.",
    "Wish it were cheaper but the results are undeniable.",
    "Unfortunately the pump broke after 2 weeks — customer service was slow.",
    "Expected faster results but it did work eventually. Good product overall.",
]

SAMPLE_SCRAPED = {
    "url": "https://example.com/superglow-serum",
    "title": "SuperGlow Vitamin C Serum",
    "description": "Award-winning serum that brightens skin in 2 weeks.",
    "price": "$49.99",
    "reviews": SAMPLE_REVIEWS,
    "scrape_method": "httpx",
    "error": None,
}

SAMPLE_SYNTHESIS = {
    "product_name": "SuperGlow Vitamin C Serum",
    "product_category": "skincare",
    "pain_points": [
        "Dark spots that don't respond to cheaper products",
        "Hyperpigmentation that persists for years",
        "Greasy serums that don't absorb properly",
        "Products that promise results but deliver none",
        "Expensive dermatologist treatments",
    ],
    "selling_points": [
        "Visibly reduces dark spots within 3 weeks",
        "Lightweight — absorbs in under 30 seconds",
        "Nurse-recommended and dermatologist-tested",
        "Works on all skin types including sensitive",
        "Clinical-grade 20% vitamin C concentration",
    ],
    "social_proof": [
        '"Cleared my dark spots in 3 weeks!"',
        '"As a nurse, this is legitimately effective."',
        '"My skin looks 5 years younger."',
    ],
    "target_audience": "Women 28-45 with hyperpigmentation who've failed with cheaper alternatives",
    "price_point": "$49.99",
    "key_differentiator": "Clinical-grade vitamin C that's stable enough to actually absorb",
    "confidence_score": 0.85,
    "confidence_notes": "Good data — 8 reviews with clear before/after language",
}


# ---------------------------------------------------------------------------
# Scraper unit tests
# ---------------------------------------------------------------------------

class TestScraper:

    @pytest.mark.asyncio
    async def test_scrape_returns_product_on_success(self):
        from mcp_tools.scraper import ScraperTool, ScrapedProduct

        scraper = ScraperTool()
        scraper._scrape_httpx = AsyncMock(return_value=ScrapedProduct(**SAMPLE_SCRAPED))

        result = await scraper.scrape("https://example.com/product")
        assert result.title == "SuperGlow Vitamin C Serum"
        assert result.price == "$49.99"
        assert len(result.reviews) == len(SAMPLE_REVIEWS)

    @pytest.mark.asyncio
    async def test_scrape_never_raises_on_failure(self):
        from mcp_tools.scraper import ScraperTool

        scraper = ScraperTool()
        scraper._scrape_httpx = AsyncMock(side_effect=Exception("Connection timeout"))

        result = await scraper.scrape("https://unreachable.com/product")
        assert result.error is not None
        assert result.title == ""

    @pytest.mark.asyncio
    async def test_has_enough_data_true_when_title_and_description(self):
        from mcp_tools.scraper import ScrapedProduct

        product = ScrapedProduct(
            url="https://example.com",
            title="My Product",
            description="Great product description",
        )
        assert product.has_enough_data is True

    @pytest.mark.asyncio
    async def test_has_enough_data_false_when_empty(self):
        from mcp_tools.scraper import ScrapedProduct

        product = ScrapedProduct(url="https://example.com")
        assert product.has_enough_data is False

    def test_domain_detection_amazon(self):
        from mcp_tools.scraper import ScraperTool, _JS_HEAVY_DOMAINS

        scraper = ScraperTool()
        domain = scraper._get_domain("https://www.amazon.com/dp/B08L5TNJHG")
        assert any(d in domain for d in _JS_HEAVY_DOMAINS)

    def test_domain_detection_static_site(self):
        from mcp_tools.scraper import ScraperTool, _JS_HEAVY_DOMAINS

        scraper = ScraperTool()
        domain = scraper._get_domain("https://mystore.com/products/item")
        assert not any(d in domain for d in _JS_HEAVY_DOMAINS)


# ---------------------------------------------------------------------------
# Researcher Agent unit tests
# ---------------------------------------------------------------------------

class TestResearcherAgent:

    def _make_agent(self):
        """Creates a ResearcherAgent with a mocked scraper and LLM."""
        from mcp_tools.scraper import ScraperTool, ScrapedProduct
        from researcher.agent import ResearcherAgent

        scraper = ScraperTool()
        scraper.scrape = AsyncMock(return_value=ScrapedProduct(**SAMPLE_SCRAPED))

        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            agent = ResearcherAgent(scraper=scraper)
            agent.llm_cfg = agent.llm_cfg  # already set in __init__

        return agent, scraper

    @pytest.mark.asyncio
    async def test_run_returns_research_result(self):
        from researcher.agent import ResearchResult

        agent, _ = self._make_agent()

        with patch("researcher.agent.complete_json", new=AsyncMock(return_value=SAMPLE_SYNTHESIS)):
            result = await agent.run("https://example.com/product")

        assert isinstance(result, ResearchResult)
        assert result.product_name == "SuperGlow Vitamin C Serum"
        assert result.product_category == "skincare"

    @pytest.mark.asyncio
    async def test_result_has_five_pain_points(self):
        agent, _ = self._make_agent()

        with patch("researcher.agent.complete_json", new=AsyncMock(return_value=SAMPLE_SYNTHESIS)):
            result = await agent.run("https://example.com/product")

        assert len(result.pain_points) == 5

    @pytest.mark.asyncio
    async def test_confidence_score_in_range(self):
        agent, _ = self._make_agent()

        with patch("researcher.agent.complete_json", new=AsyncMock(return_value=SAMPLE_SYNTHESIS)):
            result = await agent.run("https://example.com/product")

        assert 0.0 <= result.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_is_usable_true_with_good_data(self):
        agent, _ = self._make_agent()

        with patch("researcher.agent.complete_json", new=AsyncMock(return_value=SAMPLE_SYNTHESIS)):
            result = await agent.run("https://example.com/product")

        assert result.is_usable is True

    @pytest.mark.asyncio
    async def test_pipeline_completes_when_scrape_fails(self):
        """Pipeline must never crash — fallback result returned instead."""
        from mcp_tools.scraper import ScraperTool
        from researcher.agent import ResearcherAgent

        scraper = ScraperTool()
        scraper.scrape = AsyncMock(side_effect=Exception("Timeout"))

        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            agent = ResearcherAgent(scraper=scraper)

        with patch("researcher.agent.complete_json", new=AsyncMock(return_value=SAMPLE_SYNTHESIS)):
            result = await agent.run("https://unreachable.com/product")

        assert result is not None
        assert len(result.scrape_warnings) > 0

    @pytest.mark.asyncio
    async def test_pipeline_completes_when_llm_fails(self):
        """Even LLM failure should return a fallback, not raise."""
        from researcher.agent import ResearchResult

        agent, _ = self._make_agent()

        with patch("researcher.agent.complete_json", new=AsyncMock(side_effect=Exception("API error"))):
            result = await agent.run("https://example.com/product")

        assert isinstance(result, ResearchResult)
        assert result.confidence_score == 0.0
        assert any("Synthesis failed" in w for w in result.scrape_warnings)

    @pytest.mark.asyncio
    async def test_brand_context_passed_to_prompt(self):
        """Brand tone and audience should reach the synthesis prompt."""
        agent, _ = self._make_agent()

        captured_prompts: list[str] = []

        async def capture_prompt(cfg, system, user):
            captured_prompts.append(user)
            return SAMPLE_SYNTHESIS

        with patch("researcher.agent.complete_json", new=capture_prompt):
            await agent.run(
                "https://example.com/product",
                brand_tone="bold and direct",
                brand_audience="fitness enthusiasts 25-35",
            )

        assert len(captured_prompts) == 1
        assert "bold and direct" in captured_prompts[0]
        assert "fitness enthusiasts" in captured_prompts[0]


# ---------------------------------------------------------------------------
# Sentiment extraction unit tests (no LLM, no network)
# ---------------------------------------------------------------------------

class TestSentimentExtraction:

    def test_extracts_pain_points_from_negative_reviews(self):
        from researcher.agent import ResearcherAgent

        agent = ResearcherAgent.__new__(ResearcherAgent)
        negative_reviews = [
            "I was disappointed because it didn't work as expected.",
            "Unfortunately the pump broke after 2 weeks — poor quality.",
            "I wish it were cheaper but the quality doesn't justify the price.",
        ]
        result = agent._extract_sentiment(negative_reviews)
        assert len(result["pain_points"]) > 0

    def test_extracts_selling_points_from_positive_reviews(self):
        from researcher.agent import ResearcherAgent

        agent = ResearcherAgent.__new__(ResearcherAgent)
        positive_reviews = [
            "I absolutely love this — it's the best serum I've ever used!",
            "Amazing results in just 2 weeks, would definitely recommend.",
            "Finally found something that works perfectly for my skin.",
        ]
        result = agent._extract_sentiment(positive_reviews)
        assert len(result["selling_points"]) > 0

    def test_handles_empty_reviews(self):
        from researcher.agent import ResearcherAgent

        agent = ResearcherAgent.__new__(ResearcherAgent)
        result = agent._extract_sentiment([])
        assert result["pain_points"] == []
        assert result["selling_points"] == []
        assert result["social_proof"] == []


# ---------------------------------------------------------------------------
# Integration test — hits real Groq API + real URL
# Run: pytest tests/test_researcher.py -v -m integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestResearcherIntegration:

    @pytest.mark.asyncio
    async def test_research_real_product_url(self):
        """
        Full pipeline against a real URL with real Groq API.
        Requires: GROQ_API_KEY in .env and network access.
        """
        from researcher.agent import ResearcherAgent

        agent = ResearcherAgent()
        result = await agent.run(
            product_url="https://www.allbirds.com/products/mens-tree-runners",
            brand_tone="sustainable and confident",
            brand_audience="eco-conscious consumers 25-40",
        )

        assert result.product_name != ""
        assert result.confidence_score > 0.0
        print(f"\nProduct:      {result.product_name}")
        print(f"Category:     {result.product_category}")
        print(f"Confidence:   {result.confidence_score:.2f}")
        print(f"Pain points:  {result.pain_points[:2]}")
        print(f"Selling pts:  {result.selling_points[:2]}")
        print(f"Audience:     {result.target_audience}")
        print(f"Differentia:  {result.key_differentiator}")
        print(f"Warnings:     {result.scrape_warnings}")