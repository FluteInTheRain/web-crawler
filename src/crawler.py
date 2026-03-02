import requests
from typing import Optional, Dict, List
from urllib.parse import urljoin, urlparse
from pathlib import Path
import json


class WebCrawler:
    """Web crawler that fetches and processes URLs."""

    TIMEOUT = 10  # seconds
    VALID_CONTENT_TYPES = ["text/html", "application/json", "text/plain", "text/xml"]
    MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10MB

    def __init__(self, start_url: str, max_depth: int = 0):
        self.start_url = start_url
        self.max_depth = max_depth
        self.visited = set()
        self.results = []
        self.base_domain = urlparse(start_url).netloc

    def is_valid_web_url(self, url: str) -> bool:
        """Check if URL is a valid web URL (HTML/JSON/text only)."""
        try:
            parsed = urlparse(url)
            # Check if URL is on the same domain
            if parsed.netloc != self.base_domain:
                return False
            # Check for valid schemes
            if parsed.scheme not in ["http", "https"]:
                return False
            return True
        except Exception:
            return False

    def is_valid_content_type(self, content_type: str) -> bool:
        """Check if content type is a web-accessible format."""
        if not content_type:
            return False
        # Get the main type (before semicolon)
        main_type = content_type.split(";")[0].strip()
        return main_type in self.VALID_CONTENT_TYPES

    def fetch_url(self, url: str) -> Optional[Dict]:
        """
        Fetch a URL with comprehensive error handling.

        Returns:
            Dict with 'url', 'status', 'content' on success, None on failure
        """
        if url in self.visited:
            return None

        self.visited.add(url)

        if not self.is_valid_web_url(url):
            return {
                "url": url,
                "status": "skipped",
                "reason": "Invalid URL or different domain",
            }

        try:
            response = requests.get(
                url,
                timeout=self.TIMEOUT,
                allow_redirects=True,
                headers={"User-Agent": "WebCrawler/1.0"},
            )

            # Check content type before processing
            content_type = response.headers.get("Content-Type", "")
            if not self.is_valid_content_type(content_type):
                return {
                    "url": url,
                    "status": "skipped",
                    "reason": f"Binary or unsupported file type: {content_type}",
                }

            # Check content size
            content_length = len(response.content)
            if content_length > self.MAX_CONTENT_SIZE:
                return {
                    "url": url,
                    "status": "skipped",
                    "reason": f"Content too large ({content_length} bytes)",
                }

            # Handle 404 and other error status codes
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

            # Success
            return {
                "url": url,
                "status": "success",
                "code": response.status_code,
                "content_type": content_type,
                "content_length": content_length,
                "title": self._extract_title(response.text) if response.text else None,
            }

        except requests.exceptions.Timeout:
            return {
                "url": url,
                "status": "error",
                "reason": f"Timeout (>{self.TIMEOUT}s)",
            }

        except requests.exceptions.ConnectionError:
            return {"url": url, "status": "error", "reason": "Connection failed"}

        except requests.exceptions.TooManyRedirects:
            return {"url": url, "status": "error", "reason": "Too many redirects"}

        except requests.exceptions.RequestException as e:
            return {
                "url": url,
                "status": "error",
                "reason": f"Request failed: {str(e)}",
            }

        except Exception as e:
            return {
                "url": url,
                "status": "error",
                "reason": f"Unexpected error: {str(e)}",
            }

    def _extract_title(self, html: str) -> Optional[str]:
        """Extract title from HTML content."""
        try:
            import re

            match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            return match.group(1) if match else None
        except Exception:
            return None

    def crawl(self) -> List[Dict]:
        """Crawl starting URL up to max depth."""
        to_visit = [(self.start_url, 0)]

        while to_visit:
            url, depth = to_visit.pop(0)

            if depth > self.max_depth or url in self.visited:
                continue

            result = self.fetch_url(url)
            if result:
                self.results.append(result)

                # For depth 0, only fetch the starting URL
                if depth < self.max_depth and result.get("status") == "success":
                    # Extract links from HTML (future enhancement)
                    pass

        return self.results

    def save_results(self, output_path: Path) -> None:
        """Save crawl results to JSON file."""
        with open(output_path, "w") as f:
            json.dump(self.results, f, indent=2)
