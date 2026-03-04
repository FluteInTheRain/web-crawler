from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_title(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract the page title from a <title> element.

    :param soup: Parsed BeautifulSoup document.
    :returns: Title text, or None if not present.
    """
    tag = soup.find("title")
    return tag.get_text(strip=True) if tag else None


def extract_meta_tags(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    """
    Extract description and keywords from <meta> tags (including Open Graph).

    :param soup: Parsed BeautifulSoup document.
    :returns: Dict with keys 'description' and 'keywords' (values may be None).
    """
    description: Optional[str] = None
    keywords: Optional[str] = None

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").lower()
        content = meta.get("content", "")
        if name in ("description", "og:description") and not description:
            description = content
        elif name == "keywords" and not keywords:
            keywords = content

    return {"description": description, "keywords": keywords}


def extract_headings(
    soup: BeautifulSoup,
    levels: Tuple[str, ...] = ("h1", "h2", "h3"),
) -> Dict[str, List[str]]:
    """
    Collect text from heading tags at the specified levels.

    :param soup: Parsed BeautifulSoup document.
    :param levels: Heading tag names to collect, e.g. ('h1', 'h2', 'h3').
    :returns: Dict mapping each level name to a list of heading strings.
    """
    headings: Dict[str, List[str]] = {lvl: [] for lvl in levels}
    for tag in soup.find_all(list(levels)):
        text = tag.get_text(strip=True)
        if text and tag.name in headings:
            headings[tag.name].append(text)
    return headings


def extract_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Collect all unique absolute hyperlinks from <a href> attributes.

    Fragment portions (#anchor) are stripped and duplicates are dropped.

    :param soup: Parsed BeautifulSoup document.
    :param base_url: Base URL used to resolve relative hrefs.
    :returns: Deduplicated list of absolute URL strings.
    """
    links: List[str] = []
    seen: set = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        absolute = urljoin(base_url, href).split("#")[0]
        if absolute and absolute not in seen:
            seen.add(absolute)
            links.append(absolute)
    return links


def remove_boilerplate(
    soup: BeautifulSoup,
    tags: Tuple[str, ...] = (
        "script",
        "style",
        "noscript",
        "nav",
        "footer",
        "header",
        "aside",
    ),
) -> None:
    """
    Remove boilerplate elements from a BeautifulSoup tree in-place.

    :param soup: Parsed BeautifulSoup document (modified in-place).
    :param tags: Tag names to decompose from the document.
    """
    for tag in soup(list(tags)):
        tag.decompose()


def extract_sections(
    soup: BeautifulSoup,
    boilerplate_tags: Tuple[str, ...] = (
        "script",
        "style",
        "noscript",
        "nav",
        "footer",
        "header",
        "aside",
    ),
) -> List[Dict]:
    """
    Walk the cleaned DOM and return an ordered list of content sections.

    Each section dict contains:
      - level   : heading depth (0 = before first heading, 1 = h1, 2 = h2, ...)
      - heading : heading text, or None for level-0 content
      - body    : concatenated paragraph text under that heading

    Boilerplate tags are removed before walking.

    :param soup: Parsed BeautifulSoup document (modified in-place during cleaning).
    :param boilerplate_tags: Tags to strip before walking the DOM.
    :returns: Ordered list of section dicts.
    """
    remove_boilerplate(soup, boilerplate_tags)

    sections: List[Dict] = []
    current: Dict = {"level": 0, "heading": None, "body": []}

    def _flush() -> None:
        """Append the current section buffer to sections and reset state."""
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

    def _walk(node) -> None:
        for child in list(node.children):
            name = getattr(child, "name", None)
            if name is None:
                text = str(child).strip()
                if text:
                    current["body"].append(text)
                continue

            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                _flush()
                current["level"] = int(name[1])
                current["heading"] = child.get_text(strip=True)
                current["body"] = []
            elif name in ("p", "li", "blockquote", "pre", "td", "figcaption"):
                text = child.get_text(separator=" ", strip=True)
                if text:
                    current["body"].append(text)
            else:
                _walk(child)

    body = soup.find("body") or soup
    _walk(body)
    _flush()

    return sections


def extract_plain_text(soup: BeautifulSoup) -> str:
    """
    Extract all visible text from a (pre-cleaned) BeautifulSoup document.

    :param soup: BeautifulSoup document, ideally after boilerplate removal.
    :returns: Single-line string of collapsed whitespace.
    """
    return " ".join(soup.get_text(separator=" ").split())
