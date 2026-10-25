"""
PlagiaScan Pipeline — Search Providers

Search provider abstraction and implementations:
- DDGSSearchProvider (Yahoo backend via duckduckgo_search)
- WikipediaSearchProvider (Direct MediaWiki API)
- BraveSearchProvider (Brave Web Search API, if key configured)
- TavilySearchProvider (Tavily Search API, if key configured)
- SearchProviderChain (Sequential fallback and multi-engine coordination)
"""

import time
import logging
import re
import base64
from urllib.parse import urlparse, parse_qs
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
import httpx
from lxml.html import document_fromstring

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

from app.core.pipeline.schemas import (
    SearchQuery,
    SearchResult,
    SearchStrategy,
    SearchQueryRecord
)
from app.core.config import settings

logger = logging.getLogger("plagiascan.pipeline.search")


COMPLIANT_USER_AGENT = "PlagiaScan/2.0 (plagiarism-detector; contact@plagiascan.local)"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STOP_WORDS = {
    'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'in', 'of', 'to',
    'for', 'with', 'by', 'from', 'up', 'about', 'into', 'over', 'after', 'that',
    'this', 'these', 'those', 'it', 'its', 'as', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'but', 'if', 'not', 'no',
    'so', 'than', 'too', 'very', 'can', 'will', 'just', 'should', 'now'
}


def _clean_query_tokens(text: str) -> set:
    words = re.findall(r'[a-zA-Z0-9]+', text.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


def check_result_relevance(title: str, snippet: str, query_text: str, source_phrase: str = "") -> bool:
    """
    Validate that a search result's title or snippet has substantive relevance
    to the search query or source phrase. Prevents unrelated pages (e.g. typing.com,
    hotels.com, generic doc pages) from polluting candidate pools.
    """
    ref_text = query_text
    if source_phrase and source_phrase not in ref_text:
        ref_text = f"{ref_text} {source_phrase}"

    q_tokens = _clean_query_tokens(ref_text)
    if not q_tokens:
        return True

    res_tokens = _clean_query_tokens(f"{title} {snippet}")
    if not res_tokens:
        return False

    overlap = q_tokens.intersection(res_tokens)
    if len(q_tokens) >= 3:
        # For queries with 3+ substantive words, require >= 2 matches and >= 20% overlap
        return len(overlap) >= 2 and (len(overlap) / len(q_tokens)) >= 0.20
    else:
        # For short 1-2 word queries, require at least 1 match
        return len(overlap) >= 1


class SearchProvider(ABC):
    """Abstract base class for search engine providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def search(self, query: SearchQuery, limit: int = 5) -> Tuple[List[SearchResult], SearchQueryRecord]:
        """
        Execute search query and return results alongside an audit record.
        """
        pass


class DDGSSearchProvider(SearchProvider):
    """
    Robust web search provider using multi-tier SERP extraction with relevance gating.
    Primary: DDG Lite POST (lite.duckduckgo.com/lite/) - high accuracy and clean snippets
    Fallback 1: Bing SERP with ensearch/setlang parameter and base64 link decoding
    Fallback 2: DDGS library API (if available)
    """

    @property
    def name(self) -> str:
        return "ddgs_bing"

    def search(self, query: SearchQuery, limit: int = 5) -> Tuple[List[SearchResult], SearchQueryRecord]:
        start_time = time.time()
        results: List[SearchResult] = []
        q_text = query.text.strip()
        seen_urls = set()

        desktop_headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # Attempt 1 (PRIMARY): Direct DDG Lite POST
        try:
            with httpx.Client(timeout=8.0, headers=desktop_headers, follow_redirects=True) as client:
                resp = client.post("https://lite.duckduckgo.com/lite/", data={"q": q_text})
                if resp.status_code == 200:
                    tree = document_fromstring(resp.text)
                    link_elems = tree.xpath("//a[contains(@class, 'result-link')]")
                    for rank, a in enumerate(link_elems, start=1):
                        href = a.get("href", "")
                        if not href:
                            continue
                        if href.startswith("/l/?") or "duckduckgo.com/l/?" in href:
                            u_param = parse_qs(urlparse(href).query).get("uddg", [""])[0]
                            if u_param:
                                href = u_param
                        if "duckduckgo.com" in href or href in seen_urls or not href.startswith("http"):
                            continue

                        title = "".join(a.xpath(".//text()")).strip() or "Web Source"
                        snip_xpath = a.xpath("./ancestor::tr[1]/following-sibling::tr[1]//td[contains(@class, 'result-snippet')]//text()")
                        snippet = "".join(str(x) for x in snip_xpath).strip()

                        # Relevance Gate
                        if not check_result_relevance(title, snippet, q_text, query.source_phrase or ""):
                            continue

                        seen_urls.add(href)
                        results.append(
                            SearchResult(
                                url=href,
                                title=title,
                                snippet=snippet[:600],
                                provider="ddg_lite",
                                search_rank=rank,
                                discovered_by=[query.query_id],
                                source_sentence_id=query.source_sentence_id
                            )
                        )
                        if len(results) >= limit:
                            break
        except Exception as e:
            logger.debug(f"[SEARCH PROVIDER {self.name}] DDG Lite primary attempt error: {e}")

        # Attempt 2 (FALLBACK): Bing SERP with ensearch=1, setlang=en
        if not results:
            try:
                with httpx.Client(timeout=8.0, headers=desktop_headers, follow_redirects=True) as client:
                    resp = client.get(
                        "https://www.bing.com/search",
                        params={"q": q_text, "ensearch": "1", "setlang": "en"}
                    )
                    if resp.status_code == 200:
                        tree = document_fromstring(resp.text)
                        elements = tree.xpath("//li[contains(@class, 'b_algo')]")
                        for rank, e in enumerate(elements, start=1):
                            hrefxpath = e.xpath(".//h2/a/@href | .//div[contains(@class, 'header')]/a/@href")
                            href = str(hrefxpath[0]) if hrefxpath else None
                            if href and href.startswith("https://www.bing.com/ck/a?"):
                                u_param = parse_qs(urlparse(href).query).get("u", [""])[0]
                                if u_param and len(u_param) > 2:
                                    b = u_param[2:]
                                    padding = "=" * ((-len(b)) % 4)
                                    try:
                                        href = base64.urlsafe_b64decode(b + padding).decode(errors="ignore")
                                    except Exception:
                                        pass
                            if not href or href.startswith("https://www.bing.com") or "microsoft.com" in href or href in seen_urls:
                                continue

                            titlexpath = e.xpath(".//h2//text()")
                            title = "".join(str(x) for x in titlexpath).strip() or "Web Source"
                            bodyxpath = e.xpath(".//p//text() | .//div[contains(@class, 'b_caption')]//text()")
                            body = "".join(str(x) for x in bodyxpath).strip()

                            # Relevance Gate
                            if not check_result_relevance(title, body, q_text, query.source_phrase or ""):
                                continue

                            seen_urls.add(href)
                            results.append(
                                SearchResult(
                                    url=href,
                                    title=title,
                                    snippet=body[:600],
                                    provider="bing_serp",
                                    search_rank=rank,
                                    discovered_by=[query.query_id],
                                    source_sentence_id=query.source_sentence_id
                                )
                            )
                            if len(results) >= limit:
                                break
            except Exception as e:
                logger.debug(f"[SEARCH PROVIDER {self.name}] Bing SERP fallback error: {e}")

        # Attempt 3 (FALLBACK): ddgs.text library fallback if still empty
        if not results and DDGS is not None:
            try:
                with DDGS(timeout=7) as ddgs:
                    raw_results = list(ddgs.text(q_text, max_results=limit))
                    for rank, r in enumerate(raw_results, start=1):
                        url = r.get("href") or r.get("url", "")
                        if not url or url in seen_urls:
                            continue
                        title = r.get("title", "Web Source")
                        snippet = r.get("body", "")[:600]

                        # Relevance Gate
                        if not check_result_relevance(title, snippet, q_text, query.source_phrase or ""):
                            continue

                        seen_urls.add(url)
                        results.append(
                            SearchResult(
                                url=url,
                                title=title,
                                snippet=snippet,
                                provider=self.name,
                                search_rank=rank,
                                discovered_by=[query.query_id],
                                source_sentence_id=query.source_sentence_id
                            )
                        )
            except Exception as e:
                logger.debug(f"[SEARCH PROVIDER {self.name}] ddgs.text fallback error: {e}")

        latency_ms = int((time.time() - start_time) * 1000)
        record = SearchQueryRecord(
            query=q_text,
            provider=self.name,
            result_count=len(results),
            latency_ms=latency_ms
        )
        return results, record


class WikipediaSearchProvider(SearchProvider):
    """
    Direct Wikipedia MediaWiki search provider for entity-based queries.
    """

    @property
    def name(self) -> str:
        return "wikipedia_api"

    def search(self, query: SearchQuery, limit: int = 3) -> Tuple[List[SearchResult], SearchQueryRecord]:
        start_time = time.time()
        results: List[SearchResult] = []
        q_text = query.text.strip().strip('"')

        try:
            params = {
                "action": "query",
                "list": "search",
                "srsearch": q_text,
                "format": "json",
                "srlimit": limit
            }
            with httpx.Client(timeout=6.0, headers={"User-Agent": COMPLIANT_USER_AGENT}) as client:
                resp = client.get("https://en.wikipedia.org/w/api.php", params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    search_items = data.get("query", {}).get("search", [])
                    for rank, item in enumerate(search_items, start=1):
                        title = item.get("title", "")
                        page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        raw_snippet = item.get("snippet", "")
                        clean_snippet = re.sub(r'<[^>]+>', '', raw_snippet)[:600]

                        results.append(
                            SearchResult(
                                url=page_url,
                                title=f"Wikipedia: {title}",
                                snippet=clean_snippet,
                                provider=self.name,
                                search_rank=rank,
                                discovered_by=[query.query_id],
                                source_sentence_id=query.source_sentence_id
                            )
                        )
        except Exception as e:
            logger.debug(f"[SEARCH PROVIDER {self.name}] Error for '{q_text[:50]}': {e}")

        latency_ms = int((time.time() - start_time) * 1000)
        record = SearchQueryRecord(
            query=q_text,
            provider=self.name,
            result_count=len(results),
            latency_ms=latency_ms
        )
        return results, record


class BraveSearchProvider(SearchProvider):
    """
    Brave Search API provider. Activated when BRAVE_API_KEY is present.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "BRAVE_API_KEY", None)

    @property
    def name(self) -> str:
        return "brave_search"

    def search(self, query: SearchQuery, limit: int = 5) -> Tuple[List[SearchResult], SearchQueryRecord]:
        start_time = time.time()
        results: List[SearchResult] = []
        q_text = query.text.strip()

        if not self.api_key:
            return results, SearchQueryRecord(query=q_text, provider=self.name, result_count=0, latency_ms=0)

        try:
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
                "User-Agent": BROWSER_UA
            }
            params = {"q": q_text, "count": limit}
            with httpx.Client(timeout=6.0, headers=headers) as client:
                resp = client.get("https://api.search.brave.com/res/v1/web/search", params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    web_results = data.get("web", {}).get("results", [])
                    for rank, item in enumerate(web_results, start=1):
                        url = item.get("url", "")
                        if url:
                            results.append(
                                SearchResult(
                                    url=url,
                                    title=item.get("title", "Web Source"),
                                    snippet=item.get("description", "")[:600],
                                    provider=self.name,
                                    search_rank=rank,
                                    discovered_by=[query.query_id],
                                    source_sentence_id=query.source_sentence_id
                                )
                            )
        except Exception as e:
            logger.debug(f"[SEARCH PROVIDER {self.name}] Error for '{q_text[:50]}': {e}")

        latency_ms = int((time.time() - start_time) * 1000)
        return results, SearchQueryRecord(query=q_text, provider=self.name, result_count=len(results), latency_ms=latency_ms)


class TavilySearchProvider(SearchProvider):
    """
    Tavily Search API provider. Activated when TAVILY_API_KEY is present.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "TAVILY_API_KEY", None)

    @property
    def name(self) -> str:
        return "tavily_search"

    def search(self, query: SearchQuery, limit: int = 5) -> Tuple[List[SearchResult], SearchQueryRecord]:
        start_time = time.time()
        results: List[SearchResult] = []
        q_text = query.text.strip()

        if not self.api_key:
            return results, SearchQueryRecord(query=q_text, provider=self.name, result_count=0, latency_ms=0)

        try:
            payload = {"query": q_text, "max_results": limit, "api_key": self.api_key}
            with httpx.Client(timeout=6.0) as client:
                resp = client.post("https://api.tavily.com/search", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    for rank, item in enumerate(data.get("results", []), start=1):
                        url = item.get("url", "")
                        if url:
                            results.append(
                                SearchResult(
                                    url=url,
                                    title=item.get("title", "Web Source"),
                                    snippet=item.get("content", "")[:600],
                                    provider=self.name,
                                    search_rank=rank,
                                    discovered_by=[query.query_id],
                                    source_sentence_id=query.source_sentence_id
                                )
                            )
        except Exception as e:
            logger.debug(f"[SEARCH PROVIDER {self.name}] Error for '{q_text[:50]}': {e}")

        latency_ms = int((time.time() - start_time) * 1000)
        return results, SearchQueryRecord(query=q_text, provider=self.name, result_count=len(results), latency_ms=latency_ms)


class GoogleSERPSearchProvider(SearchProvider):
    """
    Google SERP search provider as auxiliary fallback.
    Extracts organic search results and decodes Google redirect links.
    """

    @property
    def name(self) -> str:
        return "google_serp"

    def search(self, query: SearchQuery, limit: int = 5) -> Tuple[List[SearchResult], SearchQueryRecord]:
        start_time = time.time()
        results: List[SearchResult] = []
        q_text = query.text.strip()
        seen_urls = set()

        desktop_headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            with httpx.Client(timeout=8.0, headers=desktop_headers, follow_redirects=True) as client:
                resp = client.get("https://www.google.com/search", params={"q": q_text})
                if resp.status_code == 200:
                    tree = document_fromstring(resp.text)
                    anchors = tree.xpath("//div[@id='search']//a | //div[contains(@class, 'g')]//a | //a[.//h3]")
                    for rank, a in enumerate(anchors, start=1):
                        href = a.get("href", "")
                        if href.startswith("/url?") or "google.com/url?" in href:
                            q_param = parse_qs(urlparse(href).query).get("q", [""])[0]
                            if q_param:
                                href = q_param

                        if not href.startswith("http") or "google.com" in href or href in seen_urls:
                            continue

                        h3_text = a.xpath(".//h3//text()")
                        title = "".join(str(x) for x in h3_text).strip() or "".join(a.xpath(".//text()")).strip() or "Web Source"
                        snip_xpath = a.xpath("./ancestor::div[contains(@class, 'g')][1]//div[contains(@data-sncf, '')]//text() | ./ancestor::div[1]//span//text()")
                        snippet = "".join(str(x) for x in snip_xpath).strip()

                        if not check_result_relevance(title, snippet, q_text, query.source_phrase or ""):
                            continue

                        seen_urls.add(href)
                        results.append(
                            SearchResult(
                                url=href,
                                title=title,
                                snippet=snippet[:600],
                                provider=self.name,
                                search_rank=rank,
                                discovered_by=[query.query_id],
                                source_sentence_id=query.source_sentence_id
                            )
                        )
                        if len(results) >= limit:
                            break
        except Exception as e:
            logger.debug(f"[SEARCH PROVIDER {self.name}] Google SERP error: {e}")

        latency_ms = int((time.time() - start_time) * 1000)
        record = SearchQueryRecord(
            query=q_text,
            provider=self.name,
            result_count=len(results),
            latency_ms=latency_ms
        )
        return results, record


class SearchProviderChain:
    """
    Coordinates multi-engine search execution with fallback and query auditing.
    """

    def __init__(self, providers: Optional[List[SearchProvider]] = None):
        if providers:
            self.providers = providers
        else:
            default_providers: List[SearchProvider] = [
                DDGSSearchProvider(),
                GoogleSERPSearchProvider(),
                WikipediaSearchProvider()
            ]
            brave_key = getattr(settings, "BRAVE_API_KEY", None)
            if brave_key:
                default_providers.append(BraveSearchProvider(brave_key))
            tavily_key = getattr(settings, "TAVILY_API_KEY", None)
            if tavily_key:
                default_providers.append(TavilySearchProvider(tavily_key))
            self.providers = default_providers

    def execute_query(
        self,
        query: SearchQuery,
        limit: int = 5
    ) -> Tuple[List[SearchResult], List[SearchQueryRecord]]:
        """
        Execute a search query across the provider chain.
        Specializes Wikipedia queries for ENTITY_SEARCH strategy.
        """
        all_results: List[SearchResult] = []
        all_records: List[SearchQueryRecord] = []

        if query.strategy == SearchStrategy.ENTITY_SEARCH or query.strategy == SearchStrategy.WIKIPEDIA_API:
            # Route to Wikipedia provider first
            wiki_p = next((p for p in self.providers if isinstance(p, WikipediaSearchProvider)), None)
            if wiki_p:
                res, rec = wiki_p.search(query, limit=limit)
                all_results.extend(res)
                all_records.append(rec)

        # Execute on primary search provider (DDGS or configured fallback)
        primary_p = next((p for p in self.providers if not isinstance(p, WikipediaSearchProvider)), None)
        if primary_p:
            res, rec = primary_p.search(query, limit=limit)
            all_results.extend(res)
            all_records.append(rec)

            # If primary yielded zero and alternative provider exists, try next
            if not res and len(self.providers) > 2:
                for alt_p in self.providers:
                    if alt_p != primary_p and not isinstance(alt_p, WikipediaSearchProvider):
                        res_alt, rec_alt = alt_p.search(query, limit=limit)
                        all_records.append(rec_alt)
                        if res_alt:
                            all_results.extend(res_alt)
                            break

        return all_results, all_records
