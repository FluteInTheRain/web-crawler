"""
CLI entry points for the web-crawler + RAG pipeline.

Commands
--------
ingest  Daily pipeline: crawl → chunk → load into vector DB.
query   Interactive question-answering session backed by the vector DB.
"""

import typer
from pathlib import Path
from typing import Optional

from config import CONCURRENCY, KB_JSON_PATH, MAX_PAGES, PAGES_DIR, TARGET_URL
from src.crawler import WebCrawler
from src.chunker import build_knowledge_base
from src.load_to_vector_db import load_to_vector_db
from src.utils.validation import validate_url, validate_output_dir
from src.utils.display import (
    print_config,
    print_summary,
    print_results,
    save_markdown,
    print_chunks_saved,
)

app = typer.Typer(
    help="Web-crawler + RAG knowledge-base toolkit.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# ingest — daily data pipeline
# ---------------------------------------------------------------------------


@app.command("ingest")
def ingest_command(
    url: str = typer.Option(
        TARGET_URL,
        "--url",
        "-u",
        help="Root URL of the website to crawl (default from TARGET_URL env var)",
    ),
    max_pages: Optional[int] = typer.Option(
        MAX_PAGES,
        "--max-pages",
        "-n",
        help="Maximum pages to fetch (default: no limit)",
    ),
    concurrency: int = typer.Option(
        CONCURRENCY,
        "--concurrency",
        "-c",
        min=1,
        help="Parallel worker threads for fetching",
    ),
    pages_dir: str = typer.Option(
        str(PAGES_DIR),
        "--pages-dir",
        "-d",
        help="Directory to write Markdown pages + metadata.json",
    ),
    kb_json: str = typer.Option(
        str(KB_JSON_PATH),
        "--kb-json",
        help="Destination JSON file for knowledge-base chunks",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose page output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress per-page output"),
    show_errors: bool = typer.Option(
        True, "--show-errors/--hide-errors", help="Show error pages in output"
    ),
    show_skipped: bool = typer.Option(
        False, "--show-skipped/--hide-skipped", help="Show skipped pages in output"
    ),
    desc_length: int = typer.Option(
        120, "--desc-length", min=10, help="Max chars for meta descriptions (verbose)"
    ),
    skip_vector_db: bool = typer.Option(
        False,
        "--skip-vector-db",
        help="Stop after chunking; do not load into vector database",
    ),
):
    """
    Daily ingestion pipeline:

    \b
    1. Crawl the target website and save pages as Markdown.
    2. Chunk pages into a knowledge-base JSON file.
    3. Upsert chunks into the vector database (safe to re-run).

    All options default to values in config.py / .env so a plain
    ``python main.py ingest`` works for most scheduled runs.
    """
    try:
        validated_url = validate_url(url)
        out_dir = validate_output_dir(pages_dir)
        kb_path = Path(kb_json)

        print_config(
            validated_url,
            max_pages,
            output_path=None,
            output_dir=out_dir,
            chunks_output=kb_path,
            verbose=verbose,
            concurrency=concurrency,
        )

        # ── Step 1: Crawl ────────────────────────────────────────────────
        typer.echo("[1/3] Crawling...\n")
        crawler = WebCrawler(
            root_url=validated_url, max_pages=max_pages, concurrency=concurrency
        )
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

        save_markdown(crawler, out_dir)

        # ── Step 2: Chunk ────────────────────────────────────────────────
        typer.echo("\n[2/3] Chunking pages into knowledge base...")
        chunks = build_knowledge_base(
            metadata_path=out_dir / "metadata.json",
            pages_dir=out_dir,
            output_path=kb_path,
        )
        print_chunks_saved(len(chunks), kb_path)

        # ── Step 3: Load into vector DB ──────────────────────────────────
        if not skip_vector_db:
            typer.echo("\n[3/3] Loading chunks into vector database...")
            load_to_vector_db(kb_json_path=kb_path)

        typer.echo("\nIngestion complete. Knowledge base is up to date.")

    except typer.BadParameter as exc:
        typer.echo(f"Validation Error: {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Unexpected error: {exc}", err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# query — interactive RAG session
# ---------------------------------------------------------------------------


@app.command("query")
def query_command(
    n_results: int = typer.Option(
        4,
        "--results",
        "-n",
        min=1,
        help="Number of source chunks to retrieve per question",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Override the OpenAI model (default from LLM_MODEL env var / config)",
    ),
):
    """
    Start an interactive question-answering session.

    Retrieves relevant chunks from the vector database and uses an LLM to
    generate cited answers.  Type 'exit' or press Ctrl-C to quit.
    """
    # Import lazily — OPENAI_API_KEY validation happens here, not at startup
    from src.rag_engine import create_rag_engine

    try:
        engine = create_rag_engine(n_results=n_results, model=model)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo("RAG query engine ready. Type 'exit' to quit.\n")

    while True:
        try:
            question = typer.prompt("You")
        except (typer.Abort, KeyboardInterrupt, EOFError):
            typer.echo("\nBye!")
            break

        question = question.strip()
        if question.lower() in ("exit", "quit", "q", ""):
            if question:
                typer.echo("Bye!")
                break
            continue

        try:
            result = engine(question)
            typer.echo(f"\nAssistant: {result['answer']}\n")
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
