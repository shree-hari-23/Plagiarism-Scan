"""
PlagiaScan Pipeline — SSRF-Safe Page Fetcher

Handles resilient, secure fetching and distillation of candidate web pages.
Features:
- SSRF defense (blocking private/loopback/link-local IPs and cloud metadata)
- Compliant User-Agent management
- WebDistiller extraction with clean text and metadata
- Snippet fallback for bot-blocked/JS-heavy pages
- In-memory TTL caching
- Response size and timeout enforcement
"""

import re
import time
import socket
import ipaddress
import hashlib
import logging
from urllib.parse import urlparse, urljoin
from typing import Optional, Dict, Tuple, List
from datetime import datetime

import httpx

from app.core.pipeline.schemas import CandidatePage, SearchResult
from app.core.pipeline.text_normalizer import TextNormalizer
from app.core.scraper.distiller import WebDistiller

logger = logging.getLogger("plagiascan.pipeline.fetcher")


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

COMPLIANT_USER_AGENT = "PlagiaScan/2.0 (plagiarism-detector; contact@plagiascan.local)"


class PageFetcher:
    """
    SSRF-safe webpage fetcher with HTML distillation and caching.
    """

    _PRIVATE_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),  # Cloud metadata AWS/GCP
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10"),
    ]

    def __init__(
        self,
        timeout: float = 9.0,
        max_bytes: int = 10_000_000,
        cache_ttl_seconds: int = 3600
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.cache_ttl_seconds = cache_ttl_seconds
        # In-memory cache: canonical_url -> (CandidatePage, timestamp)
        self._cache: Dict[str, Tuple[CandidatePage, float]] = {}

    def is_ssrf_safe(self, url: str) -> bool:
        """
        Validate whether the given URL target is external and safe to fetch.
        Blocks local hostnames and private/reserved IP addresses.
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False

            hostname = parsed.hostname
            if not hostname:
                return False

            lower_host = hostname.lower()
            if lower_host in ("localhost", "local", "internal") or lower_host.endswith(".local") or lower_host.endswith(".internal"):
                return False

            # Resolve DNS
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip = ipaddress.ip_address(ip_str)
                for net in self._PRIVATE_NETWORKS:
                    if ip in net:
                        logger.warning(f"[SSRF BLOCKED] Destination IP {ip} in private network {net} for {url}")
                        return False

            return True
        except Exception as e:
            logger.warning(f"[SSRF CHECK ERROR] Could not validate {url}: {e}")
            return False

    def fetch_page(self, candidate: SearchResult) -> Optional[CandidatePage]:
        """
        Fetch webpage HTML, distill content, and return CandidatePage.
        Falls back to snippet if full page fetch fails or yields minimal text.
        """
        url = candidate.url
        canonical = candidate.canonical_url or url

        # Check cache
        if canonical in self._cache:
            page, cached_at = self._cache[canonical]
            if time.time() - cached_at < self.cache_ttl_seconds:
                logger.debug(f"[CACHE HIT] {canonical}")
                return page

        # SSRF safety check
        if not self.is_ssrf_safe(url):
            logger.warning(f"[FETCH SKIPPED] SSRF check failed for {url}")
            return self._create_snippet_fallback(candidate, "ssrf_blocked")

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "User-Agent": COMPLIANT_USER_AGENT if ("wikipedia.org" in url or "wikimedia.org" in url) else BROWSER_UA
        }

        start_time = time.time()
        final_url = url
        http_status = 0
        raw_html = ""

        try:
            with httpx.Client(
                follow_redirects=True,
                max_redirects=5,
                timeout=self.timeout,
                headers=headers
            ) as client:
                resp = client.get(url)
                final_url = str(resp.url)
                http_status = resp.status_code

                content_type = resp.headers.get("content-type", "").lower()
                if "text/html" in content_type or "text/plain" in content_type or "application/xhtml" in content_type:
                    # Enforce max bytes
                    raw_html = resp.text[:self.max_bytes]
                else:
                    logger.debug(f"[FETCH] Non-HTML content-type '{content_type}' for {url}")
        except Exception as e:
            logger.debug(f"[FETCH EXCEPTION] {url}: {e}")

        fetch_latency = int((time.time() - start_time) * 1000)

        page_text = ""
        page_title = candidate.title
        author = None
        pub_date = None

        if http_status == 200 and len(raw_html) > 150:
            try:
                distilled = WebDistiller.distill(raw_html, url=final_url)
                page_text = distilled.get("clean_text", "")
                if distilled.get("title"):
                    page_title = distilled["title"]
                author = distilled.get("author")
                pub_date = distilled.get("published_date")
                if distilled.get("canonical_url"):
                    canonical = distilled["canonical_url"]
            except Exception as e:
                logger.debug(f"[DISTILL ERROR] {url}: {e}")

        # If page distilled words < 40, try snippet fallback
        words = page_text.split()
        if len(words) < 40:
            if candidate.snippet and len(candidate.snippet.split()) >= 12:
                logger.info(f"[SNIPPET FALLBACK] Using snippet for {url} ({len(candidate.snippet.split())} words)")
                page_text = candidate.snippet
                fetch_source = "snippet_fallback"
            else:
                logger.debug(f"[FETCH REJECTED] No usable text for {url}")
                return None
        else:
            fetch_source = "full_page"

        content_hash = hashlib.sha256(page_text.encode("utf-8")).hexdigest()
        normalized_content = TextNormalizer.normalize(page_text)
        domain = urlparse(final_url).netloc.lower()

        candidate_page = CandidatePage(
            url=url,
            final_url=final_url,
            canonical_url=canonical,
            title=page_title,
            author=author,
            published_date=pub_date,
            content=page_text,
            normalized_content=normalized_content,
            word_count=len(page_text.split()),
            domain=domain,
            fetch_source=fetch_source,
            http_status=http_status,
            fetch_latency_ms=fetch_latency,
            content_hash=content_hash,
            extracted_at=datetime.utcnow(),
            source_sentence_ids=list(candidate.discovered_by)
        )

        # Store in cache
        self._cache[canonical] = (candidate_page, time.time())
        return candidate_page

    def _create_snippet_fallback(self, candidate: SearchResult, reason: str) -> Optional[CandidatePage]:
        """Fallback to search snippet if available and valid."""
        if not candidate.snippet or len(candidate.snippet.split()) < 12:
            return None

        clean_snippet = candidate.snippet
        return CandidatePage(
            url=candidate.url,
            final_url=candidate.url,
            canonical_url=candidate.canonical_url or candidate.url,
            title=candidate.title,
            content=clean_snippet,
            normalized_content=TextNormalizer.normalize(clean_snippet),
            word_count=len(clean_snippet.split()),
            domain=urlparse(candidate.url).netloc.lower(),
            fetch_source=f"snippet_fallback_{reason}",
            http_status=0,
            fetch_latency_ms=0,
            content_hash=hashlib.sha256(clean_snippet.encode("utf-8")).hexdigest(),
            extracted_at=datetime.utcnow(),
            source_sentence_ids=list(candidate.discovered_by)
        )

    def fetch_pages_concurrent(
        self,
        candidates: List[SearchResult],
        max_workers: int = 6
    ) -> List[CandidatePage]:
        """
        Fetches and distills multiple candidate pages concurrently using ThreadPoolExecutor.
        Enforces SSRF safety and per-request timeouts.
        Matches Section 5 of the Source Attribution Engine guide.
        """
        if not candidates:
            return []

        import concurrent.futures

        fetched_pages: List[CandidatePage] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(candidates))) as executor:
            future_to_cand = {executor.submit(self.fetch_page, cand): cand for cand in candidates}
            for future in concurrent.futures.as_completed(future_to_cand):
                try:
                    page = future.result()
                    if page and page.word_count >= 10:
                        fetched_pages.append(page)
                except Exception as e:
                    cand = future_to_cand[future]
                    logger.debug(f"[CONCURRENT FETCH ERROR] {cand.url}: {e}")

        return fetched_pages

    @classmethod
    def verify_source_url(
        cls,
        target_text: str,
        candidate_url: str,
        min_match_ratio: float = 0.8,
        page: Optional[CandidatePage] = None
    ) -> bool:
        """
        Automated 'Fetch & Verify' Gate (Section 3 of requirements).
        Never displays or attributes a link directly from a search engine
        without programmatically confirming:
        1. The link is alive (HTTP response 200).
        2. The document text actually exists on that page (direct containment
           or >=80% distinct words match).
        """
        try:
            if not target_text or not candidate_url:
                return False

            if page is not None:
                # 1. Reject broken links
                if page.http_status != 200:
                    return False
                page_text = page.content.lower()
            else:
                # Standalone fetch verification
                import requests
                from bs4 import BeautifulSoup
                headers = {"User-Agent": BROWSER_UA}
                response = requests.get(candidate_url, headers=headers, timeout=5)
                # 1. Reject broken links
                if response.status_code != 200:
                    return False
                # 2. Extract clean body text
                soup = BeautifulSoup(response.text, "html.parser")
                page_text = soup.get_text(separator=" ").lower()

            # 3. Normalize both target and page content
            clean_target = re.sub(r"\s+", " ", target_text.lower()).strip()
            clean_page = re.sub(r"\s+", " ", page_text).strip()

            if not clean_target or not clean_page:
                return False

            # 4. Check for direct containment
            if clean_target in clean_page:
                return True

            # Fallback: check if at least 80% of distinct words exist together
            target_words = set(clean_target.split())
            if not target_words:
                return False
            matched_words = [w for w in target_words if w in clean_page]
            return (len(matched_words) / len(target_words)) >= min_match_ratio

        except Exception as e:
            logger.debug(f"[VERIFY SOURCE ERROR] {candidate_url}: {e}")
            return False
