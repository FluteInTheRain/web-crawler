import re


def strip_nav_prefix(text: str) -> str:
    """
    Remove all content that appears before the first Markdown heading.

    This discards navigation menus and other boilerplate that precedes
    the main article body.

    :param text: Raw Markdown string.
    :returns: Text starting from the first top-level heading, or the
              original text when no heading is found.
    """
    match = re.search(r"^#\s+", text, re.MULTILINE)
    return text[match.start() :] if match else text


def strip_markdown_images(text: str) -> str:
    """
    Remove Markdown image syntax ``![alt](url)`` from text.

    :param text: Markdown string potentially containing images.
    :returns: Text with image syntax removed.
    """
    return re.sub(r"!\[.*?\]\(.*?\)", "", text)


def inline_markdown_links(text: str) -> str:
    """
    Replace Markdown link syntax ``[label](url)`` with the label text only.

    :param text: Markdown string potentially containing hyperlinks.
    :returns: Text with hyperlink URLs removed, labels preserved.
    """
    return re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)


def collapse_blank_lines(text: str, max_consecutive: int = 2) -> str:
    """
    Collapse runs of more than *max_consecutive* blank lines into exactly that many.

    :param text: Input text.
    :param max_consecutive: Maximum allowed consecutive blank lines.
    :returns: Text with excessive blank lines collapsed.
    """
    pattern = r"\n{" + str(max_consecutive + 1) + r",}"
    replacement = "\n" * max_consecutive
    return re.sub(pattern, replacement, text)


def clean_markdown(
    text: str,
    strip_images: bool = True,
    strip_links: bool = True,
    max_blank_lines: int = 2,
) -> str:
    """
    Remove common web-scraping artifacts from a Markdown string.

    Steps applied (each configurable):
      1. Drop content before the first heading (navigation / menus).
      2. Remove image syntax.
      3. Collapse link syntax to label-only text.
      4. Normalize whitespace by collapsing excessive blank lines.

    :param text: Raw Markdown string.
    :param strip_images: When True, remove ``![alt](url)`` syntax.
    :param strip_links: When True, replace ``[label](url)`` with label only.
    :param max_blank_lines: Cap on consecutive blank lines in the output.
    :returns: Cleaned Markdown string.
    """
    text = strip_nav_prefix(text)
    if strip_images:
        text = strip_markdown_images(text)
    if strip_links:
        text = inline_markdown_links(text)
    text = collapse_blank_lines(text, max_blank_lines)
    return text.strip()
