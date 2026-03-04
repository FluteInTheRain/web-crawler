import typer
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional
from src.crawler import WebCrawler

app = typer.Typer()


def validate_url(url: str) -> str:
    """Validate that the URL is properly formatted."""
    try:
        result = urlparse(url)
        if not result.scheme:
            raise ValueError("URL must include a scheme (http/https)")
        if not result.netloc:
            raise ValueError("URL must include a domain")
        if result.scheme not in ["http", "https"]:
            raise ValueError("Only HTTP and HTTPS schemes are supported")
        return url
    except Exception as e:
        raise typer.BadParameter(f"Invalid URL: {str(e)}")


def validate_output(output: Optional[str]) -> Optional[Path]:
    """Validate and return output file path."""
    if not output:
        return None

    try:
        output_path = Path(output)
        if not output_path.parent.exists():
            raise typer.BadParameter(
                f"Output directory does not exist: {output_path.parent}"
            )
        return output_path
    except Exception as e:
        raise typer.BadParameter(f"Invalid output path: {str(e)}")


@app.command()
def main(
    url: str = typer.Argument(..., help="Root URL of the website to crawl"),
    max_pages: Optional[int] = typer.Option(
        None, help="Maximum number of pages to fetch (no limit when omitted)"
    ),
    output: Optional[str] = typer.Option(
        None, help="Save all results to this JSON file"
    ),
    output_dir: Optional[str] = typer.Option(
        None,
        help="Directory to save per-page Markdown files + metadata.json index",
    ),
):
    """
    Web crawler — discovers all pages via the site's sitemap and extracts
    title, description, headings, and full content from each page.

    Use --output-dir to save each page as a Markdown file with a
    metadata.json index, or --output to save everything as a single JSON.
    """
    try:
        url = validate_url(url)
        output_path = validate_output(output)

        typer.echo(f"\u2713 URL: {url}")
        if output_path:
            typer.echo(f"\u2713 Output: {output_path}")

        typer.echo("\n\U0001f577\ufe0f  Crawling started...\n")
        typer.echo(f"\u2713 Max pages: {max_pages if max_pages else 'no limit'}")
        crawler = WebCrawler(root_url=url, max_pages=max_pages)
        results = crawler.crawl()

        # ---- Summary ----
        success = [r for r in results if r.get("status") == "success"]
        errors = [r for r in results if r.get("status") == "error"]
        skipped = [r for r in results if r.get("status") == "skipped"]

        typer.echo(
            f"\n\U0001f4ca Results: {len(results)} pages processed "
            f"({len(success)} OK, {len(errors)} errors, {len(skipped)} skipped)\n"
        )

        for result in results:
            status = result.get("status", "?")
            icon = {"success": "\u2713", "error": "\u2717", "skipped": "\u2298"}.get(
                status, "?"
            )
            url_display = result.get("url", "")

            if status == "success":
                title = result.get("title") or "(no title)"
                desc = result.get("description") or ""
                h1s = result.get("headings", {}).get("h1", [])
                size = result.get("content_length", 0)
                typer.echo(
                    f"{icon} {url_display} [{result.get('code')}] ({size} bytes)"
                )
                typer.echo(f"   Title      : {title}")
                if desc:
                    typer.echo(f"   Description: {desc[:120]}")
                if h1s:
                    typer.echo(f"   H1         : {h1s[0]}")
            else:
                reason = result.get("reason") or result.get("code") or ""
                typer.echo(f"{icon} {url_display} — {reason}")

        if output_path:
            crawler.save_results(output_path)
            typer.echo(f"\n\u2713 Results saved to {output_path}")

        if output_dir:
            out = Path(output_dir)
            metadata = crawler.save_as_markdown_dir(out)
            success_count = sum(1 for m in metadata if m["status"] == "success")
            typer.echo(
                f"\n\u2713 Saved {success_count} Markdown file(s) + metadata.json "
                f"to {out.resolve()}"
            )

    except typer.BadParameter as e:
        typer.echo(f"\u2717 Validation Error: {str(e)}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"\u2717 Unexpected error: {str(e)}", err=True)
        raise typer.Exit(code=1)
