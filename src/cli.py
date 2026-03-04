import typer
from pathlib import Path
from typing import Optional
from src.crawler import WebCrawler
from src.chunker import build_knowledge_base
from src.utils.validation import validate_url, validate_output_file, validate_output_dir
from src.utils.display import (
    print_config,
    print_summary,
    print_results,
    save_json,
    save_markdown,
    print_chunks_saved,
)

app = typer.Typer()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@app.command()
def main(
    url: str = typer.Argument(..., help="Root URL of the website to crawl"),
    max_pages: Optional[int] = typer.Option(
        None,
        "--max-pages",
        "-n",
        help="Maximum number of pages to fetch (no limit when omitted)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Save all results to this JSON file",
    ),
    output_dir: Optional[str] = typer.Option(
        "pages",
        "--output-dir",
        "-d",
        help="Directory to save per-page Markdown files + metadata.json index (default: pages/)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show description and first H1 for each page",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress per-page output; only print the summary",
    ),
    show_errors: bool = typer.Option(
        True,
        "--show-errors/--hide-errors",
        help="Include or suppress error results in the output",
    ),
    show_skipped: bool = typer.Option(
        False,
        "--show-skipped/--hide-skipped",
        help="Include or suppress skipped results in the output",
    ),
    desc_length: int = typer.Option(
        120,
        "--desc-length",
        help="Maximum characters to display for meta descriptions (verbose mode)",
        min=10,
    ),
    concurrency: int = typer.Option(
        1,
        "--concurrency",
        "-c",
        help="Number of parallel threads used to fetch pages",
        min=1,
    ),
    chunks_output: str = typer.Option(
        "ai_knowledge_base.json",
        "--chunks-output",
        help="Destination JSON file for the AI knowledge base chunks",
    ),
    skip_chunks: bool = typer.Option(
        False,
        "--skip-chunks",
        help="Skip the chunking step after saving Markdown files",
    ),
):
    """
    Web crawler that discovers all pages via the site's sitemap, extracts
    title, description, headings, and full content from each page, saves them
    as Markdown files, and chunks the content into an AI knowledge base.

    Markdown pages are written to --output-dir (default: pages/) and chunks
    to --chunks-output (default: ai_knowledge_base.json) automatically.
    Use --skip-chunks to stop after the Markdown step.
    """
    try:
        url = validate_url(url)
        output_path = validate_output_file(output)
        out_dir = validate_output_dir(output_dir)
        chunks_path = Path(chunks_output)

        print_config(
            url,
            max_pages,
            output_path,
            out_dir,
            chunks_path if not skip_chunks else None,
            verbose,
            concurrency,
        )

        typer.echo("Crawling started...\n")
        crawler = WebCrawler(root_url=url, max_pages=max_pages, concurrency=concurrency)
        results = crawler.crawl()

        print_summary(results)

        if not quiet:
            print_results(
                results,
                verbose=verbose,
                desc_length=desc_length,
                show_errors=show_errors,
                show_skipped=show_skipped,
            )

        if output_path:
            save_json(crawler, output_path)

        if out_dir:
            save_markdown(crawler, out_dir)

            if not skip_chunks:
                typer.echo("\nBuilding AI knowledge base...")
                chunks = build_knowledge_base(
                    metadata_path=out_dir / "metadata.json",
                    pages_dir=out_dir,
                    output_path=chunks_path,
                )
                print_chunks_saved(len(chunks), chunks_path)

    except typer.BadParameter as e:
        typer.echo(f"Validation Error: {str(e)}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Unexpected error: {str(e)}", err=True)
        raise typer.Exit(code=1)
