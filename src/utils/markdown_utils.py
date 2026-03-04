from typing import Dict, List, Optional


def sections_to_markdown(sections: List[Dict]) -> List[str]:
    """
    Convert a list of section dicts into Markdown-formatted lines.

    Heading levels are offset by +1 so h1 becomes ##, h2 becomes ###, etc.

    :param sections: Ordered list of {level, heading, body} dicts.
    :returns: List of Markdown lines.
    """
    lines: List[str] = []
    for section in sections:
        level = section.get("level", 0)
        heading = section.get("heading")
        body = (section.get("body") or "").strip()

        if heading:
            md_heading = "#" * min(level + 1, 6)
            lines.append(f"{md_heading} {heading}")
            lines.append("")

        if body:
            lines.append(body)
            lines.append("")

    return lines


def build_markdown_document(
    title: str,
    description: Optional[str],
    sections: List[Dict],
    source_url: str,
) -> str:
    """
    Assemble a complete Markdown document from page components.

    Structure:
      # <title>
      > <description>   (when present)
      ## / ### ... <section headings and bodies>
      ---
      **Source:** <url>

    :param title: Page title used as the H1 heading.
    :param description: Optional lead paragraph rendered as a blockquote.
    :param sections: Ordered list of section dicts from extract_sections().
    :param source_url: Original URL appended as a citation at the end.
    :returns: Complete Markdown string.
    """
    lines: List[str] = [f"# {title}", ""]

    if description:
        lines.append(f"> {description}")
        lines.append("")

    lines.extend(sections_to_markdown(sections))

    lines.append("---")
    lines.append("")
    lines.append(f"**Source:** [{source_url}]({source_url})")
    lines.append("")

    return "\n".join(lines)
