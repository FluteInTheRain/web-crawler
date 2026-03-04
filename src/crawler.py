import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from typing import Optional, Dict, List, Tuple
from urllib.parse import urljoin, urlparse
from pathlib import Path
import xml.etree.ElementTree as ET
import certifi
import json
import uuid
import re
from datetime import datetime, timezone

try:
    import truststore

    truststore.inject_into_ssl()  # Use macOS/Windows/Linux system trust store
except ImportError:
    pass  # Fallback to certifi if truststore is unavailable


class WebCrawler:
    """
    Web crawler that:
    1. Discovers all pages via the site's sitemap (robots.txt -> sitemap.xml)
    2. Falls back to link-following from the root URL if no sitemap is found
    3. Extracts title, description, headings, and full page content from every page
    """

    TIMEOUT = 15  # seconds
    MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10 MB

    def __init__(self, root_url: str, max_pages: Optional[int] = None):
        self.root_url = root_url.rstrip("/")
        self.base_domain = self._normalise_domain(urlparse(root_url).netloc)
        self.visited: set = set()
        self.results: List[Dict] = []
        self.session = self._make_session()
        # If provided and >0, stop after fetching this many pages
        self.max_pages: Optional[int] = max_pages

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_domain(netloc: str) -> str:
        """Strip leading www. for consistent domain comparison."""
        return netloc.removeprefix("www.")

    @staticmethod
    def _make_session() -> requests.Session:
        """Create a Session with SSL settings."""
        session = requests.Session()
        adapter = HTTPAdapter()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.verify = certifi.where()
        return session

    def _default_headers(self) -> Dict[str, str]:
        return {"User-Agent": "Mozilla/5.0 (compatible; WebCrawler/1.0)"}

    def is_same_domain(self, url: str) -> bool:
        """Return True if the URL belongs to the same domain as root_url."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ["http", "https"]:
                return False
            return self._normalise_domain(parsed.netloc) == self.base_domain
        except Exception:
            return False

    def _get(self, url: str) -> Optional[requests.Response]:
        """Perform a GET request, return Response on success or None on failure."""
        try:
            response = self.session.get(
                url,
                timeout=self.TIMEOUT,
                allow_redirects=True,
                headers=self._default_headers(),
            )
            return response if response.ok else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Sitemap discovery
    # ------------------------------------------------------------------

    def find_sitemap_urls(self) -> List[str]:
        """
        Discover all page URLs listed in the site's sitemap(s).

        Strategy:
          1. Fetch /robots.txt and extract any Sitemap: directives
          2. Fall back to /sitemap.xml if none declared
          3. Parse each sitemap, recursing into sitemap-index files
        """
        sitemap_locations = self._get_sitemap_locations()
        visited_sitemaps: set = set()
        queue = sitemap_locations[:]
        page_urls: List[str] = []

        while queue:
            sitemap_url = queue.pop(0)
            if sitemap_url in visited_sitemaps:
                continue
            visited_sitemaps.add(sitemap_url)

            response = self._get(sitemap_url)
            if not response:
                continue

            page_locs, child_sitemaps = self._parse_sitemap(response.text)
            page_urls.extend(page_locs)
            queue.extend(c for c in child_sitemaps if c not in visited_sitemaps)

        # Deduplicate and filter to same domain only
        seen: set = set()
        result: List[str] = []
        for url in page_urls:
            clean = url.split("#")[0].rstrip("/") or url
            if clean and clean not in seen and self.is_same_domain(clean):
                seen.add(clean)
                result.append(clean)

        return result

    def _get_sitemap_locations(self) -> List[str]:
        """
        Read robots.txt and return any Sitemap: URLs found.
        Falls back to /sitemap.xml when none are declared.
        """
        locations: List[str] = []
        robots_url = urljoin(self.root_url, "/robots.txt")
        response = self._get(robots_url)

        if response:
            for line in response.text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("sitemap:"):
                    loc = stripped.split(":", 1)[1].strip()
                    if loc:
                        locations.append(loc)

        if not locations:
            locations.append(urljoin(self.root_url, "/sitemap.xml"))

        return locations

    def _parse_sitemap(self, xml_text: str) -> Tuple[List[str], List[str]]:
        """
        Parse a sitemap XML string.

        Returns:
            (page_urls, child_sitemap_urls)
        """
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return [], []

        def strip_ns(tag: str) -> str:
            """Remove XML namespace prefix e.g. {http://...}urlset -> urlset."""
            return tag.split("}")[-1] if "}" in tag else tag

        tag = strip_ns(root.tag)

        if tag == "sitemapindex":
            child_sitemaps = [
                loc.text.strip()
                for sitemap in root
                if strip_ns(sitemap.tag) == "sitemap"
                for loc in sitemap
                if strip_ns(loc.tag) == "loc" and loc.text
            ]
            return [], child_sitemaps

        if tag == "urlset":
            page_urls = [
                loc.text.strip()
                for url_el in root
                if strip_ns(url_el.tag) == "url"
                for loc in url_el
                if strip_ns(loc.tag) == "loc" and loc.text
            ]
            return page_urls, []

        return [], []

    # ------------------------------------------------------------------
    # Page fetching & HTML parsing
    # ------------------------------------------------------------------

    def fetch_page(self, url: str) -> Optional[Dict]:
        """
        Fetch a single page and return a structured result dict.

        Result keys on success:
          url, status, code, content_length,
          title, description, keywords, headings, content, links
        """
        if url in self.visited:
            return None
        self.visited.add(url)

        try:
            response = self.session.get(
                url,
                timeout=self.TIMEOUT,
                allow_redirects=True,
                headers=self._default_headers(),
            )
            effective_url = response.url
            content_type = response.headers.get("Content-Type", "")
            main_type = content_type.split(";")[0].strip()

            if response.status_code == 404:
                return {
                    "url": url,
                    "status": "error",
                    "code": 404,
                    "reason": "Not Found",
                }

            if response.status_code >= 400:
                return {
                    "url": url,
                    "status": "error",
                    "code": response.status_code,
                    "reason": response.reason,
                }

            content_length = len(response.content)
            if content_length > self.MAX_CONTENT_SIZE:
                return {
                    "url": url,
                    "status": "skipped",
                    "reason": f"Content too large ({content_length} bytes)",
                }

            if main_type != "text/html":
                return {
                    "url": url,
                    "status": "skipped",
                    "reason": f"Non-HTML content: {content_type}",
                }

            parsed = self.parse_html(response.text, effective_url)
            return {
                "url": url,
                "status": "success",
                "code": response.status_code,
                "content_length": content_length,
                **parsed,
            }

        except requests.exceptions.Timeout:
            return {
                "url": url,
                "status": "error",
                "reason": f"Timeout (>{self.TIMEOUT}s)",
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

    @staticmethod
    def _extract_sections(soup: BeautifulSoup) -> List[Dict]:
        """
        Walk the cleaned DOM and return an ordered list of sections that
        preserve the original document structure::

            [
              {"level": 1, "heading": "Intro", "body": "paragraph text …"},
              {"level": 2, "heading": "Details", "body": "more text …"},
              …
            ]

        ``level`` mirrors the HTML heading level (h1=1, h2=2, …).
        Content that appears before the first heading is stored with
        ``level=0`` and ``heading=None``.
        """
        # Remove boilerplate first (modifies soup in-place)
        for tag in soup(
            ["script", "style", "noscript", "nav", "footer", "header", "aside"]
        ):
            tag.decompose()

        sections: List[Dict] = []
        current: Dict = {"level": 0, "heading": None, "body": []}

        def _walk(node) -> None:
            for child in list(node.children):
                name = getattr(child, "name", None)
                if name is None:
                    # Plain text node
                    text = str(child).strip()
                    if text:
                        current["body"].append(text)
                    continue

                if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    # Flush the current section before starting a new one
                    if current["heading"] or current["body"]:
                        sections.append(
                            {
                                "level": current["level"],
                                "heading": current["heading"],
                                "body": "\n\n".join(
                                    " ".join(p.split())
                                    for p in current["body"]
                                    if p.strip()
                                ),
                            }
                        )
                    current["level"] = int(name[1])
                    current["heading"] = child.get_text(strip=True)
                    current["body"] = []
                elif name in ("p", "li", "blockquote", "pre", "td", "figcaption"):
                    text = child.get_text(separator=" ", strip=True)
                    if text:
                        current["body"].append(text)
                else:
                    # Recurse into divs, sections, articles, etc.
                    _walk(child)

        body = soup.find("body") or soup
        _walk(body)

        # Flush the last section
        if current["heading"] or current["body"]:
            sections.append(
                {
                    "level": current["level"],
                    "heading": current["heading"],
                    "body": "\n\n".join(
                        " ".join(p.split()) for p in current["body"] if p.strip()
                    ),
                }
            )

        return sections

    def parse_html(self, html: str, base_url: str) -> Dict:
        """
        Parse an HTML page with BeautifulSoup and extract:
          - title       : <title> text
          - description : meta description / og:description
          - keywords    : meta keywords
          - headings    : {"h1": [...], "h2": [...], "h3": [...]}
          - sections    : ordered list of {level, heading, body} dicts
          - content     : full visible plain text
          - links       : list of absolute URLs from <a href>
        """
        soup = BeautifulSoup(html, "html.parser")

        # --- Title ---
        title_tag = soup.find("title")
        title: Optional[str] = title_tag.get_text(strip=True) if title_tag else None

        # --- Meta tags ---
        description: Optional[str] = None
        keywords: Optional[str] = None
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("property") or "").lower()
            content = meta.get("content", "")
            if name in ("description", "og:description") and not description:
                description = content
            elif name == "keywords" and not keywords:
                keywords = content

        # --- Headings structured by level ---
        headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
        for tag in soup.find_all(["h1", "h2", "h3"]):
            text = tag.get_text(strip=True)
            if text:
                headings[tag.name].append(text)

        # --- Links (before any decomposition) ---
        links: List[str] = []
        seen_links: set = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            absolute = urljoin(base_url, href).split("#")[0]
            if absolute and absolute not in seen_links:
                seen_links.add(absolute)
                links.append(absolute)

        # --- Structured sections (decomposes boilerplate in-place) ---
        sections = self._extract_sections(soup)

        # --- Full plain text (soup is already cleaned by _extract_sections) ---
        content = " ".join(soup.get_text(separator=" ").split())

        return {
            "title": title,
            "description": description,
            "keywords": keywords,
            "headings": headings,
            "sections": sections,
            "content": content,
            "links": links,
        }

    # ------------------------------------------------------------------
    # Main crawl entry point
    # ------------------------------------------------------------------

    def crawl(self) -> List[Dict]:
        """
        Full crawl pipeline:
          1. Discover URLs via sitemap (robots.txt -> sitemap.xml)
          2. Fall back to the root URL if no sitemap is found
          3. Fetch and parse every discovered page
        """
        print("\U0001f50d Discovering pages via sitemap...")
        urls = self.find_sitemap_urls()

        if urls:
            print(f"   Found {len(urls)} URLs in sitemap.\n")
        else:
            print("   No sitemap found \u2014 starting from root URL.\n")
            urls = [self.root_url]

        for i, url in enumerate(urls, start=1):
            # Respect max_pages if set (>0)
            if (
                self.max_pages is not None
                and self.max_pages > 0
                and len(self.results) >= self.max_pages
            ):
                print(f"   Reached max_pages limit ({self.max_pages}) — stopping.")
                break

            print(f"   [{i}/{len(urls)}] {url}")
            result = self.fetch_page(url)
            if result:
                self.results.append(result)

        return self.results

    # ------------------------------------------------------------------
    # Persist results
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_filename(url: str) -> str:
        """Derive a readable, filesystem-safe stem from a URL path."""
        parsed = urlparse(url)
        path = parsed.path.strip("/").replace("/", "_") or "index"
        stem = re.sub(r"[^0-9A-Za-z._-]", "_", path)[:120]
        return stem

    def save_as_markdown_dir(self, output_dir: Path) -> List[Dict]:
        """
        Persist crawl results to *output_dir*:

        * One ``.md`` file per successfully crawled page.
        * A ``metadata.json`` index containing, for every page::

              id, filename, url, title, description,
              keywords, crawled_at, status, content_length

        Markdown file structure
        -----------------------
        # <title>

        <intro body — content before first heading>

        ## / ### / … <heading>

        <body text for that section>

        …

        ---
        **Source:** <cite link>

        Returns the metadata list.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        metadata: List[Dict] = []
        stem_counts: Dict[str, int] = {}
        crawled_at = datetime.now(timezone.utc).isoformat()

        for item in self.results:
            # Only persist pages that were successfully fetched and have content
            status = item.get("status", "")
            if status != "success":
                continue

            page_id = str(uuid.uuid4())
            url = item.get("url", "")

            # Build a unique filename
            stem = self._sanitize_filename(url)
            stem_counts[stem] = stem_counts.get(stem, 0) + 1
            if stem_counts[stem] > 1:
                stem = f"{stem}_{stem_counts[stem]}"
            filename = f"{stem}.md"

            meta_entry: Dict = {
                "id": page_id,
                "filename": filename,
                "url": url,
                "title": item.get("title"),
                "description": item.get("description"),
                "keywords": item.get("keywords"),
                "crawled_at": crawled_at,
                "status": status,
                "content_length": item.get("content_length"),
            }
            metadata.append(meta_entry)

            # ---- Write Markdown file ----
            title = item.get("title") or url
            sections: List[Dict] = item.get("sections", [])

            md_lines: List[str] = []

            # Document title
            md_lines.append(f"# {title}")
            md_lines.append("")

            # Description as a lead paragraph if present
            if item.get("description"):
                md_lines.append(f"> {item['description']}")
                md_lines.append("")

            # Structured sections
            for section in sections:
                level = section.get("level", 0)
                heading = section.get("heading")
                body = (section.get("body") or "").strip()

                if heading:
                    # Offset by 1: h1 → ##, h2 → ###, h3 → ####, etc.
                    md_heading = "#" * min(level + 1, 6)
                    md_lines.append(f"{md_heading} {heading}")
                    md_lines.append("")

                if body:
                    md_lines.append(body)
                    md_lines.append("")

            # Cite link at the end
            md_lines.append("---")
            md_lines.append("")
            md_lines.append(f"**Source:** [{url}]({url})")
            md_lines.append("")

            outpath = output_dir / filename
            outpath.write_text("\n".join(md_lines), encoding="utf-8")

        # ---- Write metadata index ----
        meta_path = output_dir / "metadata.json"
        meta_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return metadata

    def save_results(self, output_path: Path) -> None:
        """Save all crawl results as a single JSON file."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
