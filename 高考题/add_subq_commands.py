#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path


MARKER_PATTERN = r"（(?:\d+|[ivxIVX]+)）"
LINE_MARKER_RE = re.compile(rf"^([ \t]*)({MARKER_PATTERN})(.*)$")
IMMEDIATE_MARKER_RE = re.compile(rf"^([ \t]*)({MARKER_PATTERN})(.*)$")
INLINE_MARKER_RE = re.compile(rf"([；. ]\s*)({MARKER_PATTERN})")


def split_marker_line(line: str) -> list[tuple[str, str, str]] | None:
    text = line.rstrip("\n")
    match = LINE_MARKER_RE.match(text)
    if not match:
        return None

    indent, label, remainder = match.groups()
    segments: list[tuple[str, str, str]] = []

    while True:
        immediate = IMMEDIATE_MARKER_RE.match(remainder)
        if immediate and not immediate.group(1).strip():
            segments.append((indent, label, immediate.group(1)))
            label = immediate.group(2)
            remainder = immediate.group(3)
            continue

        inline = INLINE_MARKER_RE.search(remainder)
        if inline:
            segments.append((indent, label, remainder[: inline.start(2)]))
            label = inline.group(2)
            remainder = remainder[inline.end(2) :]
            continue

        segments.append((indent, label, remainder))
        return segments


def render_subq(indent: str, label: str, body: str) -> str:
    body = re.sub(r"^[ \t]+", "", body)
    body = body.rstrip()

    if "\n" in body:
        return f"{indent}\\subq{{{label}}}{{{body}\n{indent}}}\n"
    return f"{indent}\\subq{{{label}}}{{{body}}}\n"


def process_examanswers_block(block: str) -> str:
    lines = block.splitlines(keepends=True)
    output: list[str] = []
    current: dict[str, object] | None = None
    pending_blank_lines: list[str] = []

    def flush_current(include_pending_in_body: bool) -> None:
        nonlocal current, pending_blank_lines
        if current is None:
            return

        body_parts = list(current["body_parts"])  # type: ignore[index]
        if include_pending_in_body:
            body_parts.extend(pending_blank_lines)
            pending_blank_lines = []

        output.append(
            render_subq(
                current["indent"],  # type: ignore[index]
                current["label"],  # type: ignore[index]
                "".join(body_parts),
            )
        )
        current = None

    for line in lines:
        line_stripped = line.lstrip()
        marker_segments = None if line_stripped.startswith("\\subq{") else split_marker_line(line)
        is_boundary = (
            marker_segments is not None
            or line_stripped.startswith("\\item")
            or line_stripped.startswith("\\subq{")
            or line_stripped.startswith("\\end{minipage}")
        )

        if current is not None:
            if is_boundary:
                flush_current(include_pending_in_body=False)
                output.extend(pending_blank_lines)
                pending_blank_lines = []
            elif not line.strip():
                pending_blank_lines.append(line)
                continue
            else:
                current["body_parts"].extend(pending_blank_lines)  # type: ignore[index]
                pending_blank_lines = []
                current["body_parts"].append(line)  # type: ignore[index]
                continue

        if marker_segments is not None:
            for indent, label, body in marker_segments[:-1]:
                output.append(render_subq(indent, label, body))

            indent, label, body = marker_segments[-1]
            body_parts = [body] if body else []
            current = {
                "indent": indent,
                "label": label,
                "body_parts": body_parts,
            }
        else:
            output.append(line)

    if current is not None:
        flush_current(include_pending_in_body=True)
    output.extend(pending_blank_lines)
    return "".join(output)


def process_file(path: Path, write: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    examanswers_re = re.compile(
        r"(\\begin\{examanswers\}(?:\[[^\]]*\])?\n)(.*?)(\\end\{examanswers\})",
        flags=re.DOTALL,
    )
    transformed = examanswers_re.sub(
        lambda match: (
            match.group(1)
            + process_examanswers_block(match.group(2))
            + match.group(3)
        ),
        original,
    )

    # 个别旧文件没有 examanswers 环境，解答题仍放在 examquestions 中. 
    if transformed == original and "\\begin{examanswers}" not in original:
        examquestions_re = re.compile(
            r"(\\begin\{examquestions\}(?:\[[^\]]*\])?\n)(.*?)(\\end\{examquestions\})",
            flags=re.DOTALL,
        )
        transformed = examquestions_re.sub(
            lambda match: (
                match.group(1)
                + process_examanswers_block(match.group(2))
                + match.group(3)
            ),
            original,
        )

    if transformed == original:
        return False

    if write:
        path.write_text(transformed, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="为解答题小问补齐 \\subq{...}{...} 命令. "
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="直接写回文件；默认只统计会变更的文件. ",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="要扫描的目录或文件，默认当前目录. ",
    )
    args = parser.parse_args()

    tex_files: list[Path] = []
    for raw_path in args.paths:
        path = Path(raw_path)
        if path.is_file() and path.suffix == ".tex":
            tex_files.append(path)
        elif path.is_dir():
            tex_files.extend(sorted(path.rglob("*.tex")))

    changed_files = [path for path in tex_files if process_file(path, write=args.write)]

    mode = "已修改" if args.write else "将修改"
    print(f"{mode} {len(changed_files)} 个 .tex 文件. ")
    for path in changed_files:
        print(path)


if __name__ == "__main__":
    main()
