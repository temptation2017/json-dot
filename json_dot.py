#!/usr/bin/env python3
"""Flatten nested JSON to dotted-path keys, or unflatten them back."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Sparse arrays larger than this are rejected to avoid huge allocations.
MAX_INDEX = 10000

Json = Union[Dict[str, Any], List[Any], str, int, float, bool, None]


class JsonDotError(Exception):
    """User-facing conversion or input error."""


class _Missing:
    """Placeholder for holes in a sparse array (rendered as JSON null)."""


_MISSING = _Missing()


def _is_index(segment: str) -> bool:
    """True for canonical non-negative integers: 0, 1, 2, ... not 00 or -1."""
    if segment == "0":
        return True
    return segment.isdigit() and not segment.startswith("0")


def flatten(data: Json, sep: str = ".") -> Dict[str, Json]:
    """Turn nested objects/arrays into a flat {dotted.path: leaf} object."""
    if sep == "":
        raise JsonDotError("separator must not be empty")
    if not isinstance(data, (dict, list)):
        raise JsonDotError("top-level JSON must be an object or array")

    result: Dict[str, Json] = {}

    def walk(node: Json, prefix: str) -> None:
        if isinstance(node, dict):
            if not node:
                if prefix:
                    result[prefix] = {}
                return
            for key, value in node.items():
                if not isinstance(key, str):
                    raise JsonDotError(f"object key must be a string, got {type(key).__name__}")
                if key == "":
                    raise JsonDotError("empty key is not allowed")
                if sep in key:
                    raise JsonDotError(
                        f"key {key!r} contains separator {sep!r}; pick another --sep"
                    )
                path = f"{prefix}{sep}{key}" if prefix else key
                walk(value, path)
            return
        if isinstance(node, list):
            if not node:
                if prefix:
                    result[prefix] = []
                return
            for idx, value in enumerate(node):
                path = f"{prefix}{sep}{idx}" if prefix else str(idx)
                walk(value, path)
            return
        if not prefix:
            raise JsonDotError("top-level JSON must be an object or array")
        result[prefix] = node

    walk(data, "")
    return result


def unflatten(flat: Json, sep: str = ".") -> Json:
    """Rebuild nested objects/arrays from a {dotted.path: leaf} object."""
    if sep == "":
        raise JsonDotError("separator must not be empty")
    if not isinstance(flat, dict):
        raise JsonDotError("unflatten input must be a JSON object")

    root: Any = None

    def ensure_root(first: str) -> None:
        nonlocal root
        want_list = _is_index(first)
        if root is None:
            root = [] if want_list else {}
            return
        if want_list and not isinstance(root, list):
            raise JsonDotError("path conflict: root cannot be both object and array")
        if not want_list and not isinstance(root, dict):
            raise JsonDotError("path conflict: root cannot be both array and object")

    def child_container(next_seg: str) -> Any:
        return [] if _is_index(next_seg) else {}

    def check_container(existing: Any, next_seg: str, path: str) -> None:
        want_list = _is_index(next_seg)
        if existing is _MISSING:
            return
        if want_list and not isinstance(existing, list):
            raise JsonDotError(f"path conflict: {path!r} should be an array")
        if not want_list and not isinstance(existing, dict):
            raise JsonDotError(f"path conflict: {path!r} should be an object")

    def set_leaf(parent: Any, seg: str, value: Json, path: str) -> None:
        if isinstance(parent, list):
            if not _is_index(seg):
                raise JsonDotError(f"path conflict: expected array index, got {seg!r}")
            idx = int(seg)
            if idx > MAX_INDEX:
                raise JsonDotError(f"array index too large: {idx} (max {MAX_INDEX})")
            while len(parent) <= idx:
                parent.append(_MISSING)
            existing = parent[idx]
            if existing is not _MISSING and existing != value:
                if isinstance(existing, (dict, list)):
                    raise JsonDotError(f"path conflict: {path!r} is already a container")
                raise JsonDotError(f"path conflict: {path!r} already has a different value")
            parent[idx] = value
            return

        if seg in parent:
            existing = parent[seg]
            if existing != value:
                if isinstance(existing, (dict, list)):
                    raise JsonDotError(f"path conflict: {path!r} is already a container")
                raise JsonDotError(f"path conflict: {path!r} already has a different value")
        parent[seg] = value

    def descend(parent: Any, seg: str, next_seg: str, path: str) -> Any:
        want = child_container(next_seg)
        if isinstance(parent, list):
            if not _is_index(seg):
                raise JsonDotError(f"path conflict: expected array index, got {seg!r}")
            idx = int(seg)
            if idx > MAX_INDEX:
                raise JsonDotError(f"array index too large: {idx} (max {MAX_INDEX})")
            while len(parent) <= idx:
                parent.append(_MISSING)
            existing = parent[idx]
            if existing is _MISSING:
                parent[idx] = want
            else:
                check_container(existing, next_seg, path)
            return parent[idx]

        if seg not in parent:
            parent[seg] = want
        else:
            check_container(parent[seg], next_seg, path)
        return parent[seg]

    for raw_key, value in flat.items():
        if not isinstance(raw_key, str):
            raise JsonDotError(f"object key must be a string, got {type(raw_key).__name__}")
        if raw_key == "":
            raise JsonDotError("empty key is not allowed")
        parts = raw_key.split(sep)
        if any(part == "" for part in parts):
            raise JsonDotError(f"empty path segment in {raw_key!r} (separator {sep!r})")

        ensure_root(parts[0])
        current = root
        built: List[str] = []
        for i, seg in enumerate(parts):
            built.append(seg)
            path = sep.join(built)
            is_last = i == len(parts) - 1
            if is_last:
                set_leaf(current, seg, value, path)
            else:
                current = descend(current, seg, parts[i + 1], path)

    def fill_holes(node: Any) -> None:
        if isinstance(node, list):
            for i, item in enumerate(node):
                if item is _MISSING:
                    node[i] = None
                else:
                    fill_holes(item)
        elif isinstance(node, dict):
            for item in node.values():
                fill_holes(item)

    if root is None:
        return {}
    fill_holes(root)
    return root


def read_json(source: str) -> Json:
    """Load JSON from a file path or stdin (source '-' or empty)."""
    if source in ("", "-"):
        raw = sys.stdin.read()
        label = "stdin"
    else:
        path = Path(source)
        if not path.is_file():
            raise JsonDotError(f"file not found: {source}")
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise JsonDotError(f"{source}: not valid UTF-8: {exc}") from exc
        except OSError as exc:
            raise JsonDotError(f"{source}: {exc}") from exc
        label = source

    if not raw.strip():
        raise JsonDotError(f"{label} is empty")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JsonDotError(f"{label}: invalid JSON: {exc}") from exc


def dumps(data: Json) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="json_dot",
        description="Flatten nested JSON to dotted-path keys, or unflatten them back.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "file",
            nargs="?",
            default="-",
            help="JSON file (default: stdin)",
        )
        sp.add_argument(
            "--sep",
            default=".",
            help="Path separator (default: .)",
        )

    add_common(sub.add_parser("flatten", help="Nested JSON -> dotted keys"))
    add_common(sub.add_parser("unflatten", help="Dotted keys -> nested JSON"))
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        data = read_json(args.file)
        if args.command == "flatten":
            out = flatten(data, sep=args.sep)
        else:
            out = unflatten(data, sep=args.sep)
    except JsonDotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
