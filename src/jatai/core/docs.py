"""
Docs module: Provides in-band documentation delivery via jatai docs [query].

Documentation markdown files are bundled inside the package at jatai/docs/.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional


def _docs_root() -> Path:
    """Return the path to the bundled docs directory."""
    return Path(__file__).parent.parent / "docs"


def _all_doc_files() -> List[Path]:
    """Return all bundled markdown documentation files."""
    root = _docs_root()
    return sorted(root.rglob("*.md"))


def _category_label(doc_path: Path) -> str:
    """Return a human-readable category label for a doc file."""
    root = _docs_root()
    try:
        relative = doc_path.relative_to(root)
        parts = relative.parts
        if len(parts) >= 2:
            return parts[0]  # top-level directory name
    except ValueError:
        pass
    return ""


def build_index() -> str:
    """Build a markdown index of all available documentation files."""
    root = _docs_root()
    files = _all_doc_files()
    if not files:
        return "# Jataí Documentation\n\nNo documentation files found.\n"

    lines: List[str] = ["# Jataí 🐝 Documentation Index\n"]
    current_category = ""
    for doc_path in files:
        category = _category_label(doc_path)
        if category and category != current_category:
            current_category = category
            lines.append(f"\n## {current_category}\n")
        try:
            rel = doc_path.relative_to(root)
        except ValueError:
            rel = doc_path.name  # type: ignore[assignment]
        lines.append(f"- `{rel}` — run `jatai docs {doc_path.stem}` to fetch")
    lines.append("\nUse `jatai docs <query>` to copy matching files into your INBOX.")
    return "\n".join(lines) + "\n"


def search_docs(query: str) -> List[Path]:
    """Return all doc files whose relative path contains the query (case-insensitive)."""
    root = _docs_root()
    query_lower = query.lower()
    results: List[Path] = []
    for doc_path in _all_doc_files():
        try:
            rel_str = str(doc_path.relative_to(root)).lower()
        except ValueError:
            rel_str = doc_path.name.lower()
        if query_lower in rel_str:
            results.append(doc_path)
    return sorted(results)


def deliver_docs(
    query: Optional[str],
    inbox_path: Path,
) -> List[Path]:
    """Copy matching documentation files into the given INBOX directory.

    If query is None, write a category index file instead.

    Returns the list of paths created in inbox_path.
    """
    inbox_path.mkdir(parents=True, exist_ok=True)

    if query is None:
        index_path = inbox_path / "jatai-docs-index.md"
        index_path.write_text(build_index(), encoding="utf-8")
        return [index_path]

    matches = search_docs(query)
    if not matches:
        return []

    delivered: List[Path] = []
    for doc_path in matches:
        dest = inbox_path / doc_path.name
        # Resolve collision
        if dest.exists():
            stem = doc_path.stem
            suffix = doc_path.suffix
            counter = 1
            while dest.exists():
                dest = inbox_path / f"{stem} ({counter}){suffix}"
                counter += 1
        shutil.copy2(doc_path, dest)
        delivered.append(dest)
    return delivered
