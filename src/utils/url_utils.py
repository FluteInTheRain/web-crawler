import re
from typing import Callable, List
from urllib.parse import urlparse


def normalise_domain(netloc: str) -> str:
    """
    Strip a leading 'www.' prefix for consistent domain comparison.

    :param netloc: Network location component of a parsed URL.
    :returns: Domain string with 'www.' removed.
    """
    return netloc.removeprefix("www.")


def sanitize_filename(url: str, max_length: int = 120) -> str:
    """
    Derive a readable, filesystem-safe filename stem from a URL path.

    :param url: Full URL to derive the stem from.
    :param max_length: Maximum length of the returned stem.
    :returns: Filesystem-safe string usable as a filename stem.
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "_") or "index"
    return re.sub(r"[^0-9A-Za-z._-]", "_", path)[:max_length]


def deduplicate_urls(
    urls: List[str], is_same_domain_fn: Callable[[str], bool]
) -> List[str]:
    """
    Remove duplicate and fragment-only URLs, keeping same-domain entries only.

    :param urls: Raw list of discovered URLs (may include duplicates and fragments).
    :param is_same_domain_fn: Callable(url: str) -> bool that filters by domain.
    :returns: Deduplicated, domain-filtered list of URLs.
    """
    seen: set = set()
    result: List[str] = []
    for url in urls:
        clean = url.split("#")[0].rstrip("/") or url
        if clean and clean not in seen and is_same_domain_fn(clean):
            seen.add(clean)
            result.append(clean)
    return result


def strip_xml_namespace(tag: str) -> str:
    """
    Remove an XML namespace prefix from a tag name.

    :param tag: Raw tag string, e.g. '{http://...}urlset'.
    :returns: Local tag name without namespace, e.g. 'urlset'.
    """
    return tag.split("}")[-1] if "}" in tag else tag
