import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from urllib.parse import urljoin, urlparse
import uuid

import requests
from bs4 import BeautifulSoup

try:
    import truststore

    truststore.inject_into_ssl()  # Use macOS/Windows/Linux system trust store
except ImportError:
    pass  # Fallback to certifi if truststore is unavailable

from src.utils.url_utils import normalise_domain, sanitize_filename, deduplicate_urls
from src.utils.http_utils import make_http_session
from src.utils.html_parser import (
    extract_title,
    extract_meta_tags,
    extract_headings,
    extract_links,
    extract_sections,
    extract_plain_text,
)
from src.utils.markdown_utils import build_markdown_document
from src.utils.sitemap import read_robots_sitemaps, collect_sitemap_urls
from src.utils.json_utils import write_json


class WebCrawler:
    """
    Web crawler that:
      1. Discovers all pages via the site's sitemap (robots.txt -> sitemap.xml).
      2. Falls back to link-following from the root URL if no sitemap is found.
      3. Extracts title, description, headings, and full content from every page.
    """

    DEFAULT_TIMEOUT = 15
    DEFAULT_MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10 MB
    DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; WebCrawler/1.0)"
    DEFAULT_HEADING_LEVELS: Tuple[str, ...] = ("h1", "h2", "h3")

    def __init__(
        self,
        root_url: str,
        max_pages: Optional[int] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_content_size: int = DEFAULT_MAX_CONTENT_SIZE,
        user_agent: str = DEFAULT_USER_AGENT,
        heading_levels: Tuple[str, ...] = DEFAULT_HEADING_LEVELS,
        boilerplate_tags: Tuple[str, ...] = (
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
            "aside",
        ),
        concurrency: int = 1,
    ):
        """
        Initialise the crawler with a root URL and tunable options.

        :param root_url: Starting URL; all discovered URLs must share its domain.
        :param max_pages: Stop after fetching this many pages (None = unlimited).
        :param timeout: HTTP request timeout in seconds.
        :param max_content_size: Skip pages larger than this byte count.
        :param user_agent: User-Agent header sent with every request.
        :param heading_levels: HTML heading tags to collect, e.g. ('h1', 'h2').
        :param boilerplate_tags: Tags to strip before text extraction.
        :param concurrency: Number of worker threads for parallel page fetching.
        """
        self.root_url = root_url.rstrip("/")
        self.base_domain = normalise_domain(urlparse(root_url).netloc)
        self.max_pages = max_pages
        self.timeout = timeout
        self.max_content_size = max_content_size
        self.heading_levels = heading_levels
        self.boilerplate_tags = boilerplate_tags

        self.concurrency = max(1, concurrency)
        self.visited: set = set()
        self._visited_lock = threading.Lock()
        self.results: List[Dict] = []
        self.session = make_http_session(user_agent)

    # ------------------------------------------------------------------
    # Domain filtering
    # ------------------------------------------------------------------

    def is_same_domain(self, url: str) -> bool:
        """
        Return True when the URL belongs to the same domain as root_url.

        :param url: Absolute URL to check.
        :returns: True if the domain matches, False otherwise.
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            return normalise_domain(parsed.netloc) == self.base_domain
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Sitemap discovery
    # ------------------------------------------------------------------

    def _get_sitemap_seed_urls(self) -> List[str]:
        """
        Return the initial list of sitemap locations to crawl.

        Reads Sitemap: directives from /robots.txt; falls back to /sitemap.xml.

        :returns: List of sitemap URLs to start from.
        """
        locations = read_robots_sitemaps(self.root_url, self.session, self.timeout)
        if not locations:
            locations.append(urljoin(self.root_url, "/sitemap.xml"))
        return locations

    def find_sitemap_urls(self) -> List[str]:
        """
        Discover all page URLs listed in the site's sitemap(s).

        Strategy:
          1. Read /robots.txt for Sitemap: directives.
          2. Fall back to /sitemap.xml when none declared.
          3. Recursively parse all found sitemaps (handles sitemap indexes).
          4. Deduplicate and filter to same-domain URLs only.

        :returns: Deduplicated, same-domain list of page URLs.
        """
        seed_urls = self._get_sitemap_seed_urls()
        raw_urls = collect_sitemap_urls(seed_urls, self.session, self.timeout)
        return deduplicate_urls(raw_urls, self.is_same_domain)

    # ------------------------------------------------------------------
    # Page fetching
    # ------------------------------------------------------------------

    def _classify_response(
        self, url: str, response: requests.Response
    ) -> Optional[Dict]:
        """
        Inspect an HTTP response and return an error/skip result dict if the
        page should not be parsed, or None when parsing can proceed.

        :param url: Original request URL.
        :param response: HTTP response object.
        :returns: Error or skip result dict, or None if the response is acceptable.
        """
        if response.status_code == 404:
            return {"url": url, "status": "error", "code": 404, "reason": "Not Found"}

        if response.status_code >= 400:
            return {
                "url": url,
                "status": "error",
                "code": response.status_code,
                "reason": response.reason,
            }

        content_length = len(response.content)
        if content_length > self.max_content_size:
            return {
                "url": url,
                "status": "skipped",
                "reason": f"Content too large ({content_length} bytes)",
            }

        content_type = response.headers.get("Content-Type", "")
        main_type = content_type.split(";")[0].strip()
        if main_type != "text/html":
            return {
                "url": url,
                "status": "skipped",
                "reason": f"Non-HTML content: {content_type}",
            }

        return None

    def fetch_page(self, url: str) -> Optional[Dict]:
        """
        Fetch a single page and return a structured result dict.

        Skips already-visited URLs. On success, result keys are:
          url, status, code, content_length,
          title, description, keywords, headings, sections, content, links.

        Thread-safe: the visited check and mark are performed atomically under
        a lock so parallel workers never fetch the same URL twice.

        :param url: Absolute URL of the page to fetch.
        :returns: Result dict, or None if the URL was already visited.
        """
        with self._visited_lock:
            if url in self.visited:
                return None
            self.visited.add(url)

        try:
            response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            rejection = self._classify_response(url, response)
            if rejection:
                return rejection

            parsed = self.parse_html(response.text, response.url)
            return {
                "url": url,
                "status": "success",
                "code": response.status_code,
                "content_length": len(response.content),
                **parsed,
            }

        except requests.exceptions.Timeout:
            return {
                "url": url,
                "status": "error",
                "reason": f"Timeout (>{self.timeout}s)",
            }
        except requests.exceptions.SSLError as e:
            return {"url": url, "status": "error", "reason": f"SSL error: {e}"}
        except requests.exceptions.ConnectionError as e:
            return {"url": url, "status": "error", "reason": f"Connection failed: {e}"}
        except requests.exceptions.TooManyRedirects:
            return {"url": url, "status": "error", "reason": "Too many redirects"}
        except Exception as e:
            return {
                "url": url,
                "status": "error",
                "reason": f"Unexpected error: {str(e)}",
            }

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------

    def parse_html(self, html: str, base_url: str) -> Dict:
        """
        Parse an HTML document and return a dict of extracted fields.

        Delegates to module-level helpers for each extraction step so that
        any step can be called independently across the project.

        Returns keys: title, description, keywords, headings, sections, content, links.

        :param html: Raw HTML string.
        :param base_url: Absolute URL used to resolve relative links.
        :returns: Dict of extracted page data.
        """
        soup = BeautifulSoup(html, "html.parser")

        title = extract_title(soup)
        meta = extract_meta_tags(soup)
        headings = extract_headings(soup, levels=self.heading_levels)
        links = extract_links(soup, base_url)

        # extract_sections removes boilerplate in-place before walking the DOM
        sections = extract_sections(soup, boilerplate_tags=self.boilerplate_tags)
        content = extract_plain_text(soup)

        return {
            "title": title,
            "description": meta["description"],
            "keywords": meta["keywords"],
            "headings": headings,
            "sections": sections,
            "content": content,
            "links": links,
        }

    # ------------------------------------------------------------------
    # Crawl orchestration
    # ------------------------------------------------------------------

    def _discover_urls(self) -> List[str]:
        """
        Discover URLs via sitemap, falling back to the root URL when none found.

        :returns: List of page URLs to crawl.
        """
        urls = self.find_sitemap_urls()
        if urls:
            print(f"Discovered {len(urls)} URLs via sitemap.")
        else:
            print("No sitemap found - starting from root URL.")
            urls = [self.root_url]
        return urls

    def _fetch_pages(self, urls: List[str]) -> List[Dict]:
        """
        Fetch URLs, optionally in parallel, respecting max_pages if set.

        When concurrency > 1 a ThreadPoolExecutor is used; otherwise pages
        are fetched sequentially. Progress is printed as each page completes.

        :param urls: Ordered list of URLs to fetch.
        :returns: List of result dicts for all fetched pages.
        """
        if self.max_pages is not None and self.max_pages > 0:
            urls = urls[: self.max_pages]

        total = len(urls)
        results: List[Dict] = []
        print_lock = threading.Lock()
        counter = [0]  # mutable int shared across threads

        def fetch_and_report(url: str) -> Optional[Dict]:
            result = self.fetch_page(url)
            with print_lock:
                counter[0] += 1
                print(f"[{counter[0]}/{total}] {url}")
            return result

        if self.concurrency <= 1:
            for url in urls:
                result = fetch_and_report(url)
                if result:
                    results.append(result)
        else:
            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                futures = {executor.submit(fetch_and_report, url): url for url in urls}
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)

        return results

    def crawl(self) -> List[Dict]:
        """
        Run the full crawl pipeline and return all results.

        Steps:
          1. Discover URLs via sitemap (robots.txt -> sitemap.xml).
          2. Fall back to root URL when no sitemap is available.
          3. Fetch and parse every discovered page.

        :returns: List of result dicts (success, error, and skipped pages).
        """
        print("Discovering pages via sitemap...")
        urls = self._discover_urls()

        print("Fetching pages...\n")
        self.results = self._fetch_pages(urls)
        return self.results

    # ------------------------------------------------------------------
    # Persist results
    # ------------------------------------------------------------------

    def _build_meta_entry(
        self, page_id: str, filename: str, item: Dict, crawled_at: str
    ) -> Dict:
        """
        Build the metadata dict for a single page result.

        :param page_id: UUID string assigned to this page.
        :param filename: Output Markdown filename.
        :param item: Full result dict from fetch_page().
        :param crawled_at: ISO-8601 timestamp string.
        :returns: Metadata dict for inclusion in metadata.json.
        """
        return {
            "id": page_id,
            "filename": filename,
            "url": item.get("url", ""),
            "title": item.get("title"),
            "description": item.get("description"),
            "keywords": item.get("keywords"),
            "crawled_at": crawled_at,
            "status": item.get("status"),
            "content_length": item.get("content_length"),
        }

    def _unique_filename(self, url: str, stem_counts: Dict[str, int]) -> str:
        """
        Generate a unique Markdown filename for a URL, avoiding collisions.

        :param url: URL of the page.
        :param stem_counts: Mutable dict tracking stem usage (updated in-place).
        :returns: Unique filename string ending in '.md'.
        """
        stem = sanitize_filename(url)
        stem_counts[stem] = stem_counts.get(stem, 0) + 1
        if stem_counts[stem] > 1:
            stem = f"{stem}_{stem_counts[stem]}"
        return f"{stem}.md"

    def _write_metadata_index(self, metadata: List[Dict], output_dir: Path) -> None:
        """
        Write the metadata.json index file to the output directory.

        :param metadata: List of metadata dicts for all saved pages.
        :param output_dir: Directory where metadata.json will be written.
        """
        write_json(metadata, output_dir / "metadata.json")

    def save_as_markdown_dir(self, output_dir: Path) -> List[Dict]:
        """
        Save all successful crawl results as Markdown files plus a metadata index.

        Output layout:
          <output_dir>/<page-stem>.md   (one per successfully crawled page)
          <output_dir>/metadata.json    (index of all pages)

        :param output_dir: Target directory (created automatically if absent).
        :returns: List of metadata dicts for every saved page.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        metadata: List[Dict] = []
        stem_counts: Dict[str, int] = {}
        crawled_at = datetime.now(timezone.utc).isoformat()

        for item in self.results:
            if item.get("status") != "success":
                continue

            page_id = str(uuid.uuid4())
            filename = self._unique_filename(item.get("url", ""), stem_counts)

            metadata.append(self._build_meta_entry(page_id, filename, item, crawled_at))

            md_content = build_markdown_document(
                title=item.get("title") or item.get("url", ""),
                description=item.get("description"),
                sections=item.get("sections", []),
                source_url=item.get("url", ""),
            )
            (output_dir / filename).write_text(md_content, encoding="utf-8")

        self._write_metadata_index(metadata, output_dir)
        return metadata

    def save_results(self, output_path: Path) -> None:
        """
        Save all crawl results as a single JSON file.

        :param output_path: Destination file path.
        """
        write_json(self.results, output_path)
