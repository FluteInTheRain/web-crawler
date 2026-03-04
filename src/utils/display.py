from pathlib import Path
from typing import Dict, List, Optional

import typer


def print_config(
    url: str,
    max_pages: Optional[int],
    output_path: Optional[Path],
    output_dir: Optional[Path],
    verbose: bool,
) -> None:
    """
    Print the resolved crawl configuration before the crawl begins.

    :param url: Validated root URL.
    :param max_pages: Page limit, or None for unlimited.
    :param output_path: JSON output file path, or None.
    :param output_dir: Markdown output directory, or None.
    :param verbose: Whether verbose mode is active.
    """
    typer.echo(f"URL       : {url}")
    typer.echo(f"Max pages : {max_pages if max_pages else 'no limit'}")
    if output_path:
        typer.echo(f"JSON out  : {output_path}")
    if output_dir:
        typer.echo(f"MD out    : {output_dir.resolve()}")
    if verbose:
        typer.echo("Verbose   : on")
    typer.echo("")


def print_summary(results: List[Dict]) -> None:
    """
    Print a one-line summary of crawl results broken down by status.

    :param results: List of result dicts returned by the crawler.
    """
    success = sum(1 for r in results if r.get("status") == "success")
    errors = sum(1 for r in results if r.get("status") == "error")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    typer.echo(
        f"\nResults: {len(results)} pages processed "
        f"({success} OK, {errors} errors, {skipped} skipped)\n"
    )


def format_result_line(result: Dict, verbose: bool, desc_length: int) -> str:
    """
    Build a human-readable multi-line string for a single crawl result.

    :param result: A single result dict from the crawler.
    :param verbose: When True, include description and first H1.
    :param desc_length: Maximum characters to display for the description.
    :returns: Formatted string ready for printing.
    """
    status = result.get("status", "?")
    status_label = {"success": "OK", "error": "ERROR", "skipped": "SKIP"}.get(
        status, status.upper()
    )
    url_display = result.get("url", "")

    if status == "success":
        title = result.get("title") or "(no title)"
        size = result.get("content_length", 0)
        lines = [
            f"[{status_label}] {url_display} [{result.get('code')}] ({size} bytes)"
        ]
        lines.append(f"   Title      : {title}")
        if verbose:
            desc = result.get("description") or ""
            if desc:
                lines.append(f"   Description: {desc[:desc_length]}")
            h1s = result.get("headings", {}).get("h1", [])
            if h1s:
                lines.append(f"   H1         : {h1s[0]}")
        return "\n".join(lines)

    reason = result.get("reason") or result.get("code") or ""
    return f"[{status_label}] {url_display} - {reason}"


def print_results(
    results: List[Dict],
    verbose: bool,
    desc_length: int,
    show_errors: bool,
    show_skipped: bool,
) -> None:
    """
    Print all crawl results, filtered by status flags.

    :param results: List of result dicts returned by the crawler.
    :param verbose: When True, include description and first H1 for each page.
    :param desc_length: Maximum characters to show for meta descriptions.
    :param show_errors: When False, error results are suppressed.
    :param show_skipped: When False, skipped results are suppressed.
    """
    for result in results:
        status = result.get("status")
        if status == "error" and not show_errors:
            continue
        if status == "skipped" and not show_skipped:
            continue
        typer.echo(format_result_line(result, verbose=verbose, desc_length=desc_length))


def save_json(crawler, output_path: Path) -> None:
    """
    Persist all crawl results to a single JSON file.

    :param crawler: Finished WebCrawler instance holding results.
    :param output_path: Destination file path for the JSON output.
    """
    crawler.save_results(output_path)
    typer.echo(f"\nResults saved to {output_path}")


def save_markdown(crawler, output_dir: Path) -> None:
    """
    Save each successfully crawled page as a Markdown file alongside a metadata.json index.

    :param crawler: Finished WebCrawler instance holding results.
    :param output_dir: Directory where Markdown files and metadata.json will be written.
    """
    metadata = crawler.save_as_markdown_dir(output_dir)
    success_count = sum(1 for m in metadata if m["status"] == "success")
    typer.echo(
        f"\nSaved {success_count} Markdown file(s) + metadata.json "
        f"to {output_dir.resolve()}"
    )
