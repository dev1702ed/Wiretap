"""Check that every relative link in the v1 documents resolves. P5.2 (§4, item 9).

    python benchmarks/check_links.py [FILE.md ...]

A link resolves when its file (or directory) exists and, if it names a heading
(`#anchor`), that file has a heading with that GitHub anchor. Absolute URLs
(http, https, mailto) are not checked; links inside fenced code blocks are not
links. Exits 1 and lists every broken link. Standard library only.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "README.md",
    "CHANGELOG.md",
    "docs/results/V1.md",
    "docs/LIMITATIONS.md",
    "docs/RUNBOOK.md",
    "docs/paper/evidence.md",
    "docs/results/P5.2.md",
    "docs/decisions/openlineage-mapping.md",
    "CONTRIBUTING.md",
    "ROADMAP.md",
    "benchmarks/ground_truth/README.md",
    "benchmarks/adversarial/README.md",
    "bridges/openlineage/README.md",
)
_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6} (.*)$")


def slug(title: str) -> str:
    """The anchor GitHub gives a heading (before de-duplication)."""
    text = re.sub(r"[^\w\- ]", "", title.strip().lower())
    return text.replace(" ", "-")


def _outside_code(text: str) -> list[str]:
    lines, fenced = [], False
    for line in text.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line)
    return lines


def anchors(path: pathlib.Path) -> set[str]:
    seen: dict[str, int] = {}
    out = set()
    for line in _outside_code(path.read_text(encoding="utf-8")):
        match = _HEADING.match(line)
        if not match:
            continue
        base = slug(re.sub(r"`", "", match.group(1)))
        n = seen.get(base, 0)
        out.add(base if n == 0 else f"{base}-{n}")
        seen[base] = n + 1
    return out


def links(path: pathlib.Path) -> list[str]:
    text = "\n".join(_outside_code(path.read_text(encoding="utf-8")))
    text = re.sub(r"`[^`\n]*`", "", text)  # inline code holds no links
    return [m.group(1) for m in _LINK.finditer(text)]


def broken(path: pathlib.Path) -> list[str]:
    out = []
    for target in links(path):
        if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # http:, https:, mailto:
            continue
        file_part, _, anchor = target.partition("#")
        resolved = (path.parent / file_part).resolve() if file_part else path
        if not resolved.exists():
            out.append(f"{path.relative_to(ROOT)}: {target} (no such file)")
            continue
        if anchor and (resolved.is_dir() or anchor not in anchors(resolved)):
            out.append(f"{path.relative_to(ROOT)}: {target} (no such heading)")
    return out


def main(argv=None) -> int:
    names = (argv if argv is not None else sys.argv[1:]) or DOCUMENTS
    checked, problems = 0, []
    for name in names:
        path = ROOT / name
        if not path.exists():
            problems.append(f"{name}: the document itself is missing")
            continue
        checked += len(links(path))
        problems += broken(path)
    for problem in problems:
        print(problem)
    print(f"{checked} links in {len(names)} documents checked; {len(problems)} broken")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
