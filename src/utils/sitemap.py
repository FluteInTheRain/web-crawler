import xml.etree.ElementTree as ET
from typing import List
from urllib.parse import urljoin

import requests

from src.utils.url_utils import strip_xml_namespace


def parse_sitemap(xml_text: str) -> tuple[List[str], List[str]]:
    """
    Parse a sitemap XML string and return page URLs and child sitemap URLs.

    :param xml_text: Raw XML content of a sitemap or sitemap index.
    :returns: Tuple of (page_urls, child_sitemap_urls).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return [], []

    tag = strip_xml_namespace(root.tag)

    if tag == "sitemapindex":
        child_sitemaps = [
            loc.text.strip()
            for sitemap in root
            if strip_xml_namespace(sitemap.tag) == "sitemap"
            for loc in sitemap
            if strip_xml_namespace(loc.tag) == "loc" and loc.text
        ]
        return [], child_sitemaps

    if tag == "urlset":
        page_urls = [
            loc.text.strip()
            for url_el in root
            if strip_xml_namespace(url_el.tag) == "url"
            for loc in url_el
            if strip_xml_namespace(loc.tag) == "loc" and loc.text
        ]
        return page_urls, []

    return [], []


def read_robots_sitemaps(
    root_url: str,
    session: requests.Session,
    timeout: int = 15,
) -> List[str]:
    """
    Fetch /robots.txt and return any Sitemap: directive values found.

    :param root_url: Base URL of the site (e.g. 'https://example.com').
    :param session: Configured requests.Session to use for the request.
    :param timeout: Request timeout in seconds.
    :returns: List of sitemap URLs declared in robots.txt (may be empty).
    """
    locations: List[str] = []
    robots_url = urljoin(root_url, "/robots.txt")
    try:
        response = session.get(robots_url, timeout=timeout, allow_redirects=True)
        if response.ok:
            for line in response.text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("sitemap:"):
                    loc = stripped.split(":", 1)[1].strip()
                    if loc:
                        locations.append(loc)
    except Exception:
        pass
    return locations


def collect_sitemap_urls(
    sitemap_locations: List[str],
    session: requests.Session,
    timeout: int = 15,
) -> List[str]:
    """
    Recursively fetch all page URLs from an initial list of sitemap locations.

    Handles sitemap index files by recursing into child sitemaps.

    :param sitemap_locations: Seed list of sitemap URLs to start from.
    :param session: Configured requests.Session for HTTP requests.
    :param timeout: Request timeout in seconds.
    :returns: Flat list of all discovered page URLs (may include duplicates).
    """
    visited_sitemaps: set = set()
    queue = sitemap_locations[:]
    page_urls: List[str] = []

    while queue:
        sitemap_url = queue.pop(0)
        if sitemap_url in visited_sitemaps:
            continue
        visited_sitemaps.add(sitemap_url)

        try:
            response = session.get(sitemap_url, timeout=timeout, allow_redirects=True)
            if not response.ok:
                continue
        except Exception:
            continue

        page_locs, child_sitemaps = parse_sitemap(response.text)
        page_urls.extend(page_locs)
        queue.extend(c for c in child_sitemaps if c not in visited_sitemaps)

    return page_urls
