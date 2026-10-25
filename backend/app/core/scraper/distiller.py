"""
Web Distiller: Extracts clean, readable prose from raw HTML or web responses.
Removes headers, footers, navigation bars, cookie banners, advertisements,
scripts, and sidebars to isolate the core article content for comparison.

IMPROVED: Better handling of GeeksforGeeks, Medium, WordPress, docs sites,
and Cloudflare-protected pages. Smarter boilerplate removal and multi-parser
content container detection.
"""

from typing import Dict, Any, Optional
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse

try:
    import trafilatura
except ImportError:
    trafilatura = None


class WebDistiller:
    """
    Cleans raw HTML into distilled text prose suitable for plagiarism comparison.
    Primary: Trafilatura (state-of-the-art article text extraction)
    Fallback: Multi-container BeautifulSoup/lxml content selector pipeline
    """

    # Elements that are typically boilerplate or non-content
    BOILERPLATE_TAGS = [
        "nav", "header", "footer", "aside", "script", "style", "noscript",
        "iframe", "svg", "form", "button", "input", "textarea", "select",
        "meta", "link"
    ]

    # Class / ID substrings that signal ads, comments, or boilerplate
    BOILERPLATE_PATTERNS = re.compile(
        r'(comment|advert|banner|cookie|gdpr|sidebar|nav|menu|social|footer|header|'
        r'promo|widget|signup|newsletter|related|share|follow|subscribe|'
        r'breadcrumb|pagination|toolbar|topbar|popup|modal|overlay|'
        r'advertisement|sponsor|ads-|ad-|adsense|disqus)',
        re.IGNORECASE
    )

    # Ordered list of site-specific content container selectors
    CONTENT_SELECTORS = [
        # GeeksforGeeks article body
        ("div", {"class": re.compile(r'article-body|article--content|entry-content', re.I)}),
        # Medium / Substack
        ("article", {}),
        ("section", {"data-field": "body"}),
        # WordPress blogs
        ("div", {"class": re.compile(r'entry-content|post-content|the-content', re.I)}),
        # Documentation sites (FastAPI, ReadTheDocs, MkDocs)
        ("div", {"class": re.compile(r'md-content|rst-content|doc-content', re.I)}),
        # Generic semantic containers
        ("main", {}),
        ("div", {"role": "main"}),
        ("div", {"class": re.compile(r'(content|article|body|post|page|text|prose)', re.I)}),
        ("div", {"id": re.compile(r'(content|article|main|body|post|page)', re.I)}),
    ]

    @classmethod
    def extract_canonical_url(cls, html_content: str, base_url: str = "") -> Optional[str]:
        """
        Extract <link rel="canonical" href="..."> from HTML header and resolve relative URLs.
        Helps redirect scrapers and mirrors to the genuine origin source.
        """
        if not html_content:
            return None
        from urllib.parse import urljoin
        m = re.search(r'<link[^>]+rel=[\'"]canonical[\'"][^>]+href=[\'"]([^\'"]+)[\'"]', html_content, re.IGNORECASE)
        if not m:
            m = re.search(r'<link[^>]+href=[\'"]([^\'"]+)[\'"][^>]+rel=[\'"]canonical[\'"]', html_content, re.IGNORECASE)
        if m:
            href = m.group(1).strip()
            if base_url:
                href = urljoin(base_url, href)
            return href
        return None

    @classmethod
    def distill(cls, html_content: str, url: str = "") -> Dict[str, Any]:
        """
        Distills raw HTML into clean, readable text.
        Returns a dict with title, clean_text, word_count, domain, canonical_url.
        """
        if not html_content or not html_content.strip():
            return {
                "title": "",
                "clean_text": "",
                "word_count": 0,
                "domain": urlparse(url).netloc if url else "",
                "canonical_url": ""
            }

        # Detect Cloudflare challenge or anti-bot pages early
        if cls._is_blocked_page(html_content):
            return {
                "title": "",
                "clean_text": "",
                "word_count": 0,
                "domain": urlparse(url).netloc if url else "",
                "canonical_url": "",
                "blocked": True
            }

        canonical_url = cls.extract_canonical_url(html_content, base_url=url) or ""

        # 1. Try primary prose extraction via trafilatura (Section 3/5 of guide)
        if trafilatura is not None:
            try:
                traf_text = trafilatura.extract(
                    html_content,
                    url=url,
                    include_links=False,
                    include_images=False,
                    favor_precision=True
                )
                if traf_text and len(traf_text.split()) >= 40:
                    traf_meta = trafilatura.extract_metadata(html_content)
                    title = traf_meta.title if (traf_meta and traf_meta.title) else ""
                    author = traf_meta.author if (traf_meta and traf_meta.author) else None
                    pub_date = traf_meta.date if (traf_meta and traf_meta.date) else None
                    if not canonical_url and traf_meta and getattr(traf_meta, "url", None):
                        canonical_url = traf_meta.url
                    if not title:
                        m = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
                        title = m.group(1).strip() if m else ""

                    return {
                        "title": title,
                        "clean_text": traf_text[:100000],
                        "word_count": len(traf_text.split()),
                        "domain": urlparse(url).netloc if url else "",
                        "author": author,
                        "published_date": pub_date,
                        "distiller": "trafilatura",
                        "canonical_url": canonical_url
                    }
            except Exception:
                pass

        # 2. Fallback to BeautifulSoup / lxml multi-container extraction
        soup = None
        for parser in ("lxml", "html.parser"):
            try:
                soup = BeautifulSoup(html_content, parser)
                break
            except Exception:
                continue

        if soup is None:
            clean = re.sub(r'<[^>]+>', ' ', html_content)
            clean = re.sub(r'\s+', ' ', clean).strip()
            return {
                "title": "",
                "clean_text": clean[:50000],
                "word_count": len(clean.split()),
                "domain": urlparse(url).netloc if url else ""
            }

        # 1. Extract Page Title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text(separator=" ").strip()

        # 2. Remove known boilerplate tags entirely
        for tag in cls.BOILERPLATE_TAGS:
            for el in soup.find_all(tag):
                el.decompose()

        # 3. Remove elements matching boilerplate class/id patterns
        for el in soup.find_all(True):
            try:
                classes = " ".join(el.get("class", [])) if isinstance(el.get("class"), list) else str(el.get("class", ""))
                elem_id = str(el.get("id", ""))
                combined = f"{classes} {elem_id}"
                if cls.BOILERPLATE_PATTERNS.search(combined):
                    # Only remove if not a large content block
                    if len(el.get_text()) < 1500:
                        el.decompose()
            except Exception:
                continue

        # 4. Find the best content container using site-specific selectors
        main_content = None

        for tag_name, attrs in cls.CONTENT_SELECTORS:
            try:
                found = soup.find(tag_name, attrs)
                if found:
                    text_len = len(found.get_text().strip())
                    if text_len >= 200:  # only use if it has substantial text
                        main_content = found
                        break
            except Exception:
                continue

        # Fallback to body
        if main_content is None:
            main_content = soup.body or soup

        # 5. Extract text from paragraph and heading elements
        paragraphs = []
        seen_texts: set = set()

        for p in main_content.find_all(["p", "h1", "h2", "h3", "h4", "li", "td", "blockquote", "pre"]):
            text = p.get_text(separator=" ").strip()
            text = re.sub(r'\s+', ' ', text)
            text_lower = text.lower()
            if (
                len(text) >= 25
                and text_lower not in seen_texts
                and not cls._is_boilerplate_line(text)
            ):
                seen_texts.add(text_lower)
                paragraphs.append(text)

        if paragraphs:
            clean_text = "\n\n".join(paragraphs)
        else:
            raw_text = main_content.get_text(separator=" ")
            clean_text = re.sub(r'\s+', ' ', raw_text).strip()

        # Truncate to avoid extremely large payloads
        clean_text = clean_text[:100000]
        domain = urlparse(url).netloc if url else ""

        return {
            "title": title,
            "clean_text": clean_text,
            "word_count": len(clean_text.split()),
            "domain": domain,
            "canonical_url": canonical_url
        }

    @staticmethod
    def _is_blocked_page(html: str) -> bool:
        """Detect Cloudflare, CAPTCHA, or access-denied pages."""
        if len(html) < 500:
            return True
        lower = html.lower()
        blocked_signals = [
            "enable javascript",
            "cf-browser-verification",
            "cloudflare ray id",
            "just a moment",
            "ddos protection by cloudflare",
            "access denied",
            "403 forbidden",
            "checking your browser",
        ]
        return any(sig in lower for sig in blocked_signals)

    @staticmethod
    def _is_boilerplate_line(text: str) -> bool:
        """Detect common boilerplate lines that are not article content."""
        t = text.strip().lower()
        if len(text) < 20:
            return True
        boilerplate_starts = [
            "cookie", "privacy policy", "terms of", "all rights reserved",
            "copyright", "subscribe", "sign in", "log in", "register",
            "advertisement", "sponsored", "share this", "follow us",
            "related articles", "you may also", "read more", "see also",
            "table of contents", "jump to", "skip to", "back to top",
        ]
        for bp in boilerplate_starts:
            if t.startswith(bp):
                return True
        return False
