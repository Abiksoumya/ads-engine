"""
AdEngineAI — Scraper Tool
==========================
Extracts product data from any e-commerce URL.

Auto-detects:
    - JS-heavy pages (Amazon, Shopify, Flipkart) → Playwright
    - Static pages (everything else)              → httpx + BeautifulSoup

Called only by: researcher/agent.py
Never called directly by any API route.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Domains that require a real browser to render
_JS_HEAVY_DOMAINS = {
    "amazon.com", "amazon.in", "amazon.co.uk", "amazon.de",
    "flipkart.com",
    "walmart.com",
    "myntra.com",
    "ajio.com",
}

# Review CSS selectors per platform — tried in order, first match wins
_REVIEW_SELECTORS = [
    "[data-hook='review-body'] span",   # Amazon
    ".spr-review-content-body",         # Shopify (Judge.me)
    ".review__content",                 # Shopify (generic)
    "[itemprop='reviewBody']",          # Schema.org standard
    ".review-text",
    ".review-content",
    "[class*='review'] p",
]


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class ScrapedProduct:
    url: str
    title: str = ""
    description: str = ""
    price: str = ""
    reviews: list[str] = field(default_factory=list)
    scrape_method: str = ""          # "playwright" | "httpx"
    error: Optional[str] = None

    @property
    def has_enough_data(self) -> bool:
        """Returns True if we have enough to generate a useful ad."""
        return bool(self.title and (self.description or self.reviews))


# ---------------------------------------------------------------------------
# Scraper Tool
# ---------------------------------------------------------------------------

class ScraperTool:
    """
    Used by the Researcher Agent to extract product intelligence.

    Usage:
        scraper = ScraperTool()
        product = await scraper.scrape("https://example.com/product")
    """

    def __init__(self, proxy_url: Optional[str] = None):
        # proxy_url: Bright Data endpoint for production
        # Leave None in development — scrapes direct
        self.proxy_url = proxy_url

    async def scrape(self, url: str) -> ScrapedProduct:
        """
        Main entry point. Auto-selects scraping method by domain.
        Always returns a ScrapedProduct — never raises. Errors go in .error field.
        """
        domain = self._get_domain(url)
        needs_js = any(d in domain for d in _JS_HEAVY_DOMAINS)

        logger.info(f"Scraping {url} — method: {'playwright' if needs_js else 'httpx'}")

        try:
            if needs_js:
                return await self._scrape_playwright(url)
            else:
                return await self._scrape_httpx(url)
        except Exception as e:
            logger.warning(f"Scrape failed for {url}: {e}")
            return ScrapedProduct(url=url, error=str(e))

    # ------------------------------------------------------------------
    # Playwright — for JS-heavy pages
    # ------------------------------------------------------------------

    async def _scrape_playwright(self, url: str) -> ScrapedProduct:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        async with async_playwright() as p:
            launch_kwargs: dict = {"headless": True}
            if self.proxy_url:
                launch_kwargs["proxy"] = {"server": self.proxy_url}

            browser = await p.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                title = await page.title()
                html = await page.content()

                # Extract structured data via JS evaluation
                structured = await page.evaluate("""() => {
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    const results = [];
                    scripts.forEach(s => {
                        try { results.push(JSON.parse(s.textContent)); }
                        catch(e) {}
                    });
                    return results;
                }""")

                # Extract reviews using selectors
                reviews = []
                for selector in _REVIEW_SELECTORS:
                    elements = await page.query_selector_all(selector)
                    for el in elements[:50]:
                        text = await el.text_content()
                        if text:
                            text = text.strip()
                            if len(text) > 30:
                                reviews.append(text)
                    if reviews:
                        break

                return self._parse(
                    url=url,
                    html=html,
                    title=title,
                    structured=structured,
                    reviews=reviews,
                    method="playwright",
                )
            finally:
                await browser.close()

    # ------------------------------------------------------------------
    # httpx + BeautifulSoup — for static pages
    # ------------------------------------------------------------------

    async def _scrape_httpx(self, url: str) -> ScrapedProduct:
        try:
            import httpx
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "httpx or beautifulsoup4 not installed. Run: pip install httpx beautifulsoup4 lxml"
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        client_kwargs: dict = {"timeout": 20.0}
        if self.proxy_url:
            client_kwargs["proxy"] = self.proxy_url

        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Structured data
        structured = []
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                structured.append(json.loads(tag.string or ""))
            except Exception:
                pass

        # Reviews
        reviews = []
        for selector in _REVIEW_SELECTORS:
            for el in soup.select(selector)[:50]:
                text = el.get_text(strip=True)
                if len(text) > 30:
                    reviews.append(text)
            if reviews:
                break

        return self._parse(
            url=url,
            html=response.text,
            title=soup.title.string.strip() if soup.title else "",
            structured=structured,
            reviews=reviews,
            method="httpx",
        )

    # ------------------------------------------------------------------
    # Parser — same for both methods
    # ------------------------------------------------------------------

    def _parse(
        self,
        url: str,
        html: str,
        title: str,
        structured: list,
        reviews: list[str],
        method: str,
    ) -> ScrapedProduct:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError("beautifulsoup4 not installed.")

        soup = BeautifulSoup(html, "lxml")

        # Description: og:description > meta description > structured data
        description = (
            self._meta(soup, "og:description")
            or self._meta(soup, "description")
            or self._structured_field(structured, "description")
        )

        # Price: structured data first, then regex on page text
        price = (
            self._structured_price(structured)
            or self._regex_price(soup.get_text())
        )

        return ScrapedProduct(
            url=url,
            title=title,
            description=description[:600] if description else "",
            price=price,
            reviews=reviews[:100],
            scrape_method=method,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_domain(url: str) -> str:
        try:
            return urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            return ""

    @staticmethod
    def _meta(soup, name: str) -> str:
        tag = (
            soup.find("meta", {"property": name})
            or soup.find("meta", {"name": name})
        )
        return tag.get("content", "").strip() if tag else ""

    @staticmethod
    def _structured_field(structured: list, field: str) -> str:
        for item in structured:
            if isinstance(item, dict) and item.get(field):
                return str(item[field])
        return ""

    @staticmethod
    def _structured_price(structured: list) -> str:
        for item in structured:
            if not isinstance(item, dict):
                continue
            offers = item.get("offers", {})
            if isinstance(offers, dict) and offers.get("price"):
                currency = offers.get("priceCurrency", "$")
                return f"{currency}{offers['price']}"
        return ""

    @staticmethod
    def _regex_price(text: str) -> str:
        patterns = [r"\$[\d,]+\.?\d*", r"₹[\d,]+\.?\d*", r"£[\d,]+\.?\d*", r"€[\d,]+\.?\d*"]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return ""