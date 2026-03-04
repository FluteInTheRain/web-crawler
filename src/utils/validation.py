from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer


def validate_url(url: str) -> str:
    """
    Validate that a URL is properly formatted with a supported scheme and domain.

    :param url: Raw URL string provided by the user.
    :returns: The original URL if valid.
    :raises typer.BadParameter: When the URL is malformed or uses an unsupported scheme.
    """
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


def validate_output_file(output: Optional[str]) -> Optional[Path]:
    """
    Validate an output file path and ensure its parent directory exists.

    :param output: Raw path string provided by the user, or None to skip.
    :returns: Resolved Path object, or None when no path was supplied.
    :raises typer.BadParameter: When the parent directory does not exist.
    """
    if not output:
        return None

    try:
        output_path = Path(output)
        if not output_path.parent.exists():
            raise typer.BadParameter(
                f"Output directory does not exist: {output_path.parent}"
            )
        return output_path
    except typer.BadParameter:
        raise
    except Exception as e:
        raise typer.BadParameter(f"Invalid output path: {str(e)}")


def validate_output_dir(output_dir: Optional[str]) -> Optional[Path]:
    """
    Validate and resolve a directory path for Markdown output.

    The directory is created automatically if it does not yet exist.

    :param output_dir: Raw directory path string provided by the user, or None to skip.
    :returns: Resolved Path object, or None when no path was supplied.
    :raises typer.BadParameter: When the path cannot be created or resolved.
    """
    if not output_dir:
        return None

    try:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        return out
    except Exception as e:
        raise typer.BadParameter(f"Invalid output directory: {str(e)}")
