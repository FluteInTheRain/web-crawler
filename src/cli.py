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


def validate_depth(depth: int) -> int:
    """Validate that depth is a non-negative integer."""
    if depth < 0:
        raise typer.BadParameter("Depth must be >= 0")
    if depth > 10:
        raise typer.BadParameter("Depth must be <= 10 (too deep)")
    return depth


def validate_output(output: Optional[str]) -> Optional[Path]:
    """Validate and return output file path."""
    if not output:
        return None

    try:
        output_path = Path(output)
        # Check if parent directory exists
        if not output_path.parent.exists():
            raise typer.BadParameter(
                f"Output directory does not exist: {output_path.parent}"
            )
        return output_path
    except Exception as e:
        raise typer.BadParameter(f"Invalid output path: {str(e)}")


@app.command()
def main(
    url: str = typer.Argument(..., help="URL to crawl"),
    depth: int = typer.Option(0, help="Maximum crawl depth (0-10)"),
    output: Optional[str] = typer.Option(None, help="Output file path"),
):
    """
    Web crawler CLI - crawl a website up to a specified depth.
    """
    try:
        # Validate inputs
        url = validate_url(url)
        depth = validate_depth(depth)
        output_path = validate_output(output)

        # Display configuration
        typer.echo(f"✓ URL: {url}")
        typer.echo(f"✓ Depth: {depth}")
        if output_path:
            typer.echo(f"✓ Output: {output_path}")

        # Initialize and run crawler
        typer.echo("\n🕷️  Crawling started...\n")
        crawler = WebCrawler(start_url=url, max_depth=depth)
        results = crawler.crawl()

        # Display results
        typer.echo(f"\n📊 Crawl Results ({len(results)} URLs processed):\n")
        for result in results:
            status_icon = {"success": "✓", "error": "✗", "skipped": "⊘"}.get(
                result.get("status"), "?"
            )

            url_display = result.get("url", "")
            reason = result.get("reason", "")
            code = result.get("code", "")

            if result.get("status") == "success":
                content_type = result.get("content_type", "")
                typer.echo(
                    f"{status_icon} {url_display} [{result.get('code')}] "
                    f"({result.get('content_length')} bytes)"
                )
            else:
                error_msg = reason or code or ""
                typer.echo(f"{status_icon} {url_display} {error_msg}")

        # Save results if output specified
        if output_path:
            crawler.save_results(output_path)
            typer.echo(f"\n✓ Results saved to {output_path}")

    except typer.BadParameter as e:
        typer.echo(f"✗ Validation Error: {str(e)}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"✗ Unexpected error: {str(e)}", err=True)
        raise typer.Exit(code=1)
