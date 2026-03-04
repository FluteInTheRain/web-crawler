import json
from pathlib import Path


def write_json(data, path: Path, indent: int = 2, ensure_ascii: bool = False) -> None:
    """
    Write a JSON-serializable object to a file.

    :param data: Python object to serialize.
    :param path: Destination file path.
    :param indent: JSON indentation level.
    :param ensure_ascii: When True, escape non-ASCII characters.
    """
    Path(path).write_text(
        json.dumps(data, indent=indent, ensure_ascii=ensure_ascii),
        encoding="utf-8",
    )


def read_json(path: Path):
    """
    Read and deserialize a JSON file.

    :param path: Source file path.
    :returns: Deserialized Python object.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))
