"""Assemble the paper evidence pack from the committed records. P5.2 (C4).

    python benchmarks/evidence.py            write docs/paper/evidence.md and the README block
    python benchmarks/evidence.py --check    exit 1 if either would change

The pack is organised by CLAIM (C1-C8). Every table in it is copied verbatim,
line for line, from a committed record (docs/results/P5-*.md, written by
benchmarks/run.py and benchmarks/render.py), never retyped; each block names
its record, section, the commit the record measured, and the machine.

Which record: for each claim, the NEWEST record (by its "Started (UTC)") that
contains the claim's section. A record named P5-local*.md is the owner's
machine; every other record is the sandbox, labelled as such. So once the
owner commits a newer run (docs/RUNBOOK.md), re-running this script moves the
overhead and accuracy evidence to it, and the README's numbers follow.

It also rewrites the block between the README's evidence markers, and nothing
else in the README: three to five headline rows, every number in them copied
out of the pack's own tables.

Deterministic: the output depends only on the records' text, so running it
twice gives the same bytes. Standard library only.
"""

import argparse
import dataclasses
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "results"
OUT = ROOT / "docs" / "paper" / "evidence.md"
README = ROOT / "README.md"
START = "<!-- evidence:summary:start -->"
END = "<!-- evidence:summary:end -->"

_HEADING = re.compile(r"^(#{1,6}) (.*)$")
_ROW = re.compile(r"^\| (.+?) \| (.*) \|$")


@dataclasses.dataclass
class Record:
    name: str
    lines: list[str]
    started: str | None
    commit: str | None
    dirty: str | None
    os_name: str | None
    cpu: str | None

    @property
    def owner(self) -> bool:
        return self.name.startswith("P5-local")

    def machine(self) -> str:
        where = "the owner's machine" if self.owner else "the sandbox (a cloud VM)"
        details = [d for d in (self.os_name, self.cpu) if d]
        return where + (f": {'; '.join(details)}" if details else "")


def _cell(lines: list[str], label: str) -> str | None:
    """The last cell of the first environment row named `label`."""
    for line in lines:
        match = _ROW.match(line)
        if match and match.group(1) == label:
            return match.group(2).split(" | ")[-1].strip().strip("`")
    return None


def parse(name: str, text: str) -> Record:
    lines = text.replace("\r\n", "\n").split("\n")
    head = lines[:40]  # the environment table is at the top of every record
    return Record(
        name=name,
        lines=lines,
        started=_cell(head, "Started (UTC)"),
        commit=_cell(head, "Git commit"),
        dirty=_cell(head, "Working tree dirty"),
        os_name=_cell(head, "OS"),
        cpu=_cell(head, "CPU"),
    )


def load(results: pathlib.Path) -> list[Record]:
    return [
        parse(path.name, path.read_text(encoding="utf-8"))
        for path in sorted(results.glob("P5-*.md"))
    ]


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, title) of every heading outside code blocks."""
    out, fenced = [], False
    for index, line in enumerate(lines):
        if line.startswith("```"):
            fenced = not fenced
            continue
        match = None if fenced else _HEADING.match(line)
        if match:
            out.append((index, len(match.group(1)), match.group(2)))
    return out


def section(lines: list[str], *titles: str) -> list[str] | None:
    """The lines of the section reached by `titles`, each a heading title
    prefix nested in the previous one, from its heading up to the next heading
    of the same or a higher level. None if there is no such section."""
    start, end = 0, len(lines)
    for title in titles:
        found = None
        for index, level, text in headings(lines[start:end]):
            if text.startswith(title):
                found = (start + index, level)
                break
        if found is None:
            return None
        start, level = found
        stop = end
        for index, other, _text in headings(lines[start + 1 : end]):
            if other <= level:
                stop = start + 1 + index
                break
        end = stop
    return lines[start:end]


def tables(lines: list[str]) -> list[list[str]]:
    """Every markdown table in `lines`, as its lines."""
    out, current = [], []
    for line in lines + [""]:
        if line.startswith("|"):
            current.append(line)
        elif current:
            out.append(current)
            current = []
    return out


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split(" | ")]


def rows_where(table: list[str], column: str, keep) -> list[str]:
    """The table's header, separator and the rows whose `column` passes `keep`."""
    header = cells(table[0])
    index = header.index(column)
    return table[:2] + [row for row in table[2:] if keep(cells(row)[index])]


def newest(records: list[Record], has) -> Record | None:
    """The newest record (by start time, then name) for which `has` holds."""
    found = [r for r in records if r.started and has(r)]
    return max(found, key=lambda r: (r.started, r.name)) if found else None


def demote(lines: list[str]) -> list[str]:
    """A record's headings become bold labels, so the pack keeps its own outline."""
    out, fenced = [], False
    for line in lines:
        if line.startswith("```"):
            fenced = not fenced
        match = None if fenced else _HEADING.match(line)
        out.append(f"**{match.group(2)}**" if match else line)
    return out


# --- The claims ------------------------------------------------------------------


@dataclasses.dataclass
class Block:
    record: Record
    where: str  # the record's section, as a readable path
    lines: list[str]


@dataclasses.dataclass
class Claim:
    key: str
    title: str
    statement: str
    blocks: list[Block]
    missing: str | None = None


def _source_line(block: Block) -> str:
    r = block.record
    dirty = f", working tree dirty: {r.dirty}" if r.dirty is not None else ""
    return (
        f"Source: [`{r.name}`](../results/{r.name}), section *{block.where}*; "
        f"measured on commit `{r.commit}`{dirty}, started {r.started}, on {r.machine()}."
    )


def _scale_live_or_replay(
    lines: list[str], live: str, replay: str
) -> tuple[str, list[str]]:
    """The live subsection, or replay when live was skipped: (its heading, lines)."""
    sub = section(lines, live)
    if sub is None or any(line.startswith("Skipped:") for line in sub):
        sub = section(lines, replay) or []
    return (sub[0] if sub else replay), sub


SCALE = "Ground truth at scale"
STRESS = "Ground truth: the stress set"
PER_PROCESS = "| OpenLineage core (per process) |"
OL_METHODS = (
    "DCP run-level",
    "OpenLineage core",
    "OpenLineage core (per process)",
    "OpenLineage + dcp facet",
)


def claims(records: list[Record]) -> list[Claim]:
    out = []

    def strip(title: str) -> str:
        return title.lstrip("#").strip()

    # C1 Coverage
    rec = newest(records, lambda r: section(r.lines, "Adversarial") is not None)
    c = Claim(
        "C1",
        "C1 Coverage",
        "Movements with no lineage code in them (an ad-hoc script, a notebook, a shared "
        "topic) are captured by DCP live, while the OpenLineage client, installed and "
        "configured, emits nothing for them; its positive control shows the client works.",
        [],
    )
    if rec:
        c.blocks.append(Block(rec, "Adversarial", section(rec.lines, "Adversarial")))
    out.append(c)

    # C2 Accuracy, hand-written keys
    workloads = ("dark_zone", "job_granularity", "notebook", "topic_fan_in")

    def has_live(r):
        live = section(r.lines, "Ground truth: live")
        return live is not None and all(section(live, w) is not None for w in workloads)

    rec = newest(records, has_live)
    c = Claim(
        "C2",
        "C2 Accuracy, hand-written keys",
        "Live (real Postgres and Kafka, separate OS processes), DCP's graph matches every "
        "hand-written answer key at every level; the dataset-level baseline and "
        "OpenLineage's core model over-approximate where the keys were built to show it.",
        [],
    )
    if rec:
        c.blocks.append(
            Block(rec, "Ground truth: live", section(rec.lines, "Ground truth: live"))
        )
    out.append(c)

    # C3 Accuracy at scale, both OpenLineage mappings
    def has_scale(r):
        s = section(r.lines, SCALE)
        return s is not None and any(line.startswith(PER_PROCESS) for line in s)

    rec = newest(records, has_scale)
    c = Claim(
        "C3",
        "C3 Accuracy at scale",
        "On the generated keys (ten 30-job seeds micro-averaged, and a 100-job key on its "
        "own), DCP loses no expected item at any level; every extra item it reports is a "
        "distractor read (job-level parenting). OpenLineage's core model is shown under "
        "both run mappings: one run per (trace, process), and one run per process.",
        [],
    )
    if rec:
        scale = section(rec.lines, SCALE)
        where, sub = _scale_live_or_replay(scale, "Live", "Replay")
        c.blocks.append(
            Block(
                rec,
                f"{strip(scale[0])} › keys",
                tables(scale[: scale.index("### Replay")])[0],
            )
        )
        c.blocks.append(Block(rec, f"{strip(scale[0])} › {strip(where)}", sub))
    out.append(c)

    # C4 Failure modes: the stress set
    rec = newest(records, lambda r: section(r.lines, STRESS) is not None)
    c = Claim(
        "C4",
        "C4 Failure modes",
        "On the stress set, which exercises DCP's two documented failure modes "
        "(multi-record consumers; store-mediated reads), DCP's provenance recall drops, "
        "and every miss is explained by one of those two causes; the per-cause table "
        "counts them. Dataset-level lineage keeps full recall there at lower precision.",
        [],
    )
    if rec:
        stress = section(rec.lines, STRESS)
        where, sub = _scale_live_or_replay(
            stress, "Stress set: live", "Stress set: replay"
        )
        c.blocks.append(
            Block(
                rec,
                f"{strip(stress[0])} › keys",
                tables(stress[: stress.index("### Stress set: replay")])[0],
            )
        )
        c.blocks.append(Block(rec, f"{strip(stress[0])} › {strip(where)}", sub))
    out.append(c)

    # C5 Representation loss: OpenLineage core (both mappings) vs the dcp facet
    c = Claim(
        "C5",
        "C5 Representation loss",
        "Translated to OpenLineage, DCP's events keep their precision only with the `dcp` "
        "run facet: read through OpenLineage's core model (inputs × outputs per run), "
        "precision falls under both run mappings, while the facet reader rebuilds DCP's "
        "graph exactly (and so also its misses on the stress set).",
        [],
    )
    for claim_key, title, live, replay in (
        ("C3", SCALE, "Live", "Replay"),
        ("C4", STRESS, "Stress set: live", "Stress set: replay"),
    ):
        done = next((x for x in out if x.key == claim_key and x.blocks), None)
        if done is None:
            continue
        source = done.blocks[0].record
        whole = section(source.lines, title)
        where, sub = _scale_live_or_replay(whole, live, replay)
        for label in [line for line in sub if line.startswith("#### ")]:
            table = tables(section(sub, label[5:]) or [])
            if not table:
                continue
            c.blocks.append(
                Block(
                    source,
                    f"{strip(whole[0])} › {strip(where)} › {strip(label)}",
                    rows_where(
                        table[0],
                        "Method",
                        lambda m: m in OL_METHODS[1:] or m == OL_METHODS[0],
                    ),
                )
            )
    # Keep only the provenance and dataset-edge rows: the levels both readings have.
    for block in c.blocks:
        block.lines = block.lines[:2] + [
            row
            for row in block.lines[2:]
            if cells(row)[1] in ("dataset edges", "provenance")
        ]
    out.append(c)

    # C6 Overhead
    def has_overhead(r):
        return section(r.lines, "Overhead: live (4b)") is not None

    rec = newest(records, has_overhead)
    c = Claim(
        "C6",
        "C6 Overhead",
        "Added latency per call against the < 1 ms p99 target, for every T tier "
        "(parameterised, parse-cache hits) and L tier (inlined literals, cache-hostile), "
        "with verdicts, and the attribution of the added cost.",
        [],
    )
    if rec:
        overhead = section(rec.lines, "Overhead: live (4b)")
        for _index, level, title in headings(overhead):
            if level == 3 and re.match(r"[TL]\d ", title):
                sub = section(overhead, f"{title}")
                c.blocks.append(
                    Block(
                        rec,
                        f"Overhead: live (4b) › {title}",
                        [*sub[:1], "", *tables(sub)[-1]],
                    )
                )
        attribution = section(overhead, "Attribution of the added cost")
        if attribution:
            c.blocks.append(
                Block(
                    rec, f"Overhead: live (4b) › {strip(attribution[0])}", attribution
                )
            )
    out.append(c)

    # C7 Start-up
    c = Claim(
        "C7",
        "C7 Start-up",
        "Process start-up under `dcp-instrument`, before and after P5.1's lazy patching, "
        "and in the newest overhead run.",
        [],
    )
    rec = newest(
        records, lambda r: section(r.lines, "Process start-up (ms)") is not None
    )
    if rec:
        c.blocks.append(
            Block(
                rec,
                "Process start-up (ms), before and after",
                section(rec.lines, "Process start-up (ms)"),
            )
        )
    rec = newest(
        records,
        lambda r: (
            section(r.lines, "Overhead: live (4b)", "Process start-up") is not None
        ),
    )
    if rec:
        c.blocks.append(
            Block(
                rec,
                "Overhead: live (4b) › Process start-up",
                section(rec.lines, "Overhead: live (4b)", "Process start-up"),
            )
        )
    out.append(c)

    # C8 Throughput model
    fixed = "### The fixed cost per call and the < 2% throughput target"
    rec = newest(records, lambda r: any(line.startswith(fixed) for line in r.lines))
    c = Claim(
        "C8",
        "C8 Throughput model",
        "The < 2% throughput target is not met against sub-millisecond queries. As a "
        "fixed cost per call (implied by the throughput change), DCP's cost is under 2% "
        "of a query's throughput once the query is slower than the latency the table "
        "gives for each tier and configuration.",
        [],
    )
    if rec:
        title = next(line for line in rec.lines if line.startswith(fixed))
        c.blocks.append(
            Block(rec, title.lstrip("# "), section(rec.lines, title.lstrip("# ")))
        )
    out.append(c)

    for claim in out:
        if not claim.blocks:
            claim.missing = "No committed record contains this evidence yet."
    return out


# --- Output ---------------------------------------------------------------------


def slug(title: str) -> str:
    """The anchor GitHub gives a heading."""
    text = re.sub(r"[^\w\- ]", "", title.lower())
    return text.replace(" ", "-")


def render(records: list[Record]) -> str:
    cs = claims(records)
    lines = [
        "# Paper evidence pack (v1)",
        "",
        (
            "Generated by `python benchmarks/evidence.py` from the committed records in "
            "[`docs/results/`](../results/). **Do not edit by hand**: re-run the script. Every "
            "table below is copied verbatim, line for line, from the record named above it; "
            "nothing is retyped. For each claim the script takes the newest record that holds "
            "its evidence, and labels the machine: a record named `P5-local*.md` is the "
            "owner's machine, every other one this project's sandbox (a cloud VM). The "
            "record's headings are shown in bold. C5 and C6 keep only some rows or tables "
            "of a section (named in its source line); a kept line is never altered."
        ),
        "",
        "## Sources",
        "",
        "| Claim | Record | Section | Measured on commit | Started (UTC) | Machine |",
        "|---|---|---|---|---|---|",
    ]
    for c in cs:
        if c.missing:
            lines.append(f"| [{c.key}](#{slug(c.title)}) | none | | | | |")
        for b in c.blocks:
            r = b.record
            lines.append(
                f"| [{c.key}](#{slug(c.title)}) | [`{r.name}`](../results/{r.name}) | {b.where} "
                f"| `{r.commit}` | {r.started} | {'owner' if r.owner else 'sandbox'} |"
            )
    lines.append("")
    for c in cs:
        lines += [f"## {c.title}", "", f"**Claim.** {c.statement}", ""]
        if c.missing:
            lines += [f"*{c.missing}*", ""]
        for b in c.blocks:
            lines += [_source_line(b), "", *demote(b.lines), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def _find_row(table: list[str], column: str, value: str) -> dict | None:
    header = cells(table[0])
    for row in table[2:]:
        values = cells(row)
        if values[header.index(column)] == value:
            return dict(zip(header, values, strict=False))
    return None


def summary(records: list[Record]) -> list[str]:
    """Three to five headline rows, every value copied out of the pack's tables."""
    cs = {c.key: c for c in claims(records)}
    rows = []

    def link(c):
        return f"[{c.key}](docs/paper/evidence.md#{slug(c.title)})"

    def where(b):
        return f"[`{b.record.name}`](docs/results/{b.record.name}), {'owner' if b.record.owner else 'sandbox'}"

    c = cs["C1"]
    if c.blocks:
        b = c.blocks[0]
        ts = tables(b.lines)
        cases = [cells(r) for r in ts[0][2:]]
        baseline = _find_row(
            ts[1], "Measurement", "Events received from the uninstrumented programs"
        )
        text = "; ".join(f"case {x[0]} ({x[1]}): {x[3]}" for x in cases)
        if baseline:
            text += f". OpenLineage events from the same programs without DCP: {baseline['Value']}"
        rows.append([link(c), "Coverage, live", text, where(b)])

    for key, label in (
        ("C3", "Accuracy at scale, provenance"),
        ("C4", "Failure modes (stress set), provenance"),
    ):
        c = cs[key]
        if len(c.blocks) < 2:
            continue
        b = c.blocks[1]
        seeds = next((t for t in tables(b.lines) if "Keys" in cells(t[0])), None)
        if seeds is None:
            continue
        wanted = (
            ("DCP run-level", "OpenLineage core (per process)")
            if key == "C3"
            else ("DCP run-level", "dataset-level baseline")
        )
        parts = []
        for method in wanted:
            for row in seeds[2:]:
                v = cells(row)
                if v[0] == method and v[1] == "provenance":
                    parts.append(f"{method}: precision {v[2]}, recall {v[3]}")
        rows.append([link(c), label, "; ".join(parts), where(b)])

    c = cs["C6"]
    verdicts = []
    for b in c.blocks:
        if "›" not in b.where or "Attribution" in b.where:
            continue
        table = tables(b.lines)
        row = _find_row(table[0], "Config", "file") if table else None
        if row and "< 1 ms p99 added" in row:
            verdicts.append(
                f"{b.where.split(' › ')[-1].split(' ')[0]} {row['< 1 ms p99 added']}"
            )
    if verdicts:
        rows.append(
            [
                link(c),
                "< 1 ms p99 added, `file` sink",
                ", ".join(verdicts),
                where(c.blocks[0]),
            ]
        )

    c = cs["C8"]
    if c.blocks:
        b = c.blocks[0]
        table = tables(b.lines)[0]
        found = [
            dict(zip(cells(table[0]), cells(r), strict=False))
            for r in table[2:]
            if cells(r)[1] == "file" and cells(r)[0].startswith(("T1 ", "L5 "))
        ]
        text = "; ".join(
            f"{f['Tier']}: {f['Implied µs/call [95% CI]']} µs per call, under 2% for queries "
            f"slower than {f['Loss < 2% for queries slower than (µs)']} µs"
            for f in found
        )
        rows.append(
            [
                link(c),
                "Throughput, as a fixed cost per call (`file` sink)",
                text,
                where(b),
            ]
        )

    out = [
        START,
        "",
        (
            "Copied from [`docs/paper/evidence.md`](docs/paper/evidence.md) by "
            "`python benchmarks/evidence.py`; do not edit by hand."
        ),
        "",
        "| Claim | What | Result | Record |",
        "|---|---|---|---|",
        *["| " + " | ".join(r) + " |" for r in rows],
        "",
        END,
    ]
    return out


def rewrite_readme(text: str, block: list[str]) -> str:
    if START not in text or END not in text:
        raise ValueError(f"README.md has no {START} ... {END} block")
    before, rest = text.split(START, 1)
    _old, after = rest.split(END, 1)
    return before + "\n".join(block) + after


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if anything would change"
    )
    parser.add_argument("--results", type=pathlib.Path, default=RESULTS)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    parser.add_argument("--readme", type=pathlib.Path, default=README)
    args = parser.parse_args(argv)
    records = load(args.results)
    pack = render(records)
    readme_text = args.readme.read_text(encoding="utf-8")
    readme = rewrite_readme(readme_text, summary(records))
    current = args.out.read_text(encoding="utf-8") if args.out.exists() else None
    if args.check:
        stale = [
            p
            for p, new, old in (
                (args.out, pack, current),
                (args.readme, readme, readme_text),
            )
            if new != old
        ]
        for path in stale:
            print(
                f"{path}: out of date; run python benchmarks/evidence.py",
                file=sys.stderr,
            )
        return 1 if stale else 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for path, text in ((args.out, pack), (args.readme, readme)):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    claims_found = sum(1 for c in claims(records) if not c.missing)
    print(
        f"wrote {args.out} ({claims_found} of 8 claims with evidence) and the README block"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
