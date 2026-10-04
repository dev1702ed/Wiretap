"""The paper's figures, from raw results JSON. P5.2 (C5).

    python benchmarks/figures.py [--scale RESULTS.json] [--overhead RESULTS.json]
                                 [--out docs/paper/figures]

Writes each figure as PDF (for the paper) and PNG (for the README):

    F1  precision and recall by method and level, the scale keys (scale_s01..s10)
    F2  the same for the stress set (stress_s01..s05)
    F3  added p99 per tier and configuration, with 95% CIs, against the 1 ms line
    F4  the fixed-cost model: throughput loss against query latency, for each
        tier's measured cost per call (`file` sink), with the 2% line
    F5  process start-up times

Every plotted number is read from a results JSON (benchmarks/run.py's output),
never typed in. Defaults: F1 and F2 from the newest committed raw JSON under
docs/results/data/ that has the stress group; F3-F5 from the newest raw JSON
there that has an `overhead` stage (the owner copies theirs in: RUNBOOK step 6).
If no committed raw JSON has overhead data, F3-F5 fall back to the newest
committed overhead RECORD (docs/results/P5-*.md), whose tables are parsed by
code (evidence.py's extraction), never retyped; each figure says which.

Deterministic: a fixed style, no timestamps or software versions in the files,
so the same inputs and the pinned matplotlib give the same bytes.
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "results" / "data"
RESULTS = ROOT / "docs" / "results"
OUT = ROOT / "docs" / "paper" / "figures"
sys.path.insert(0, str(ROOT / "benchmarks"))

METHOD_ORDER = (
    "DCP run-level",
    "dataset-level baseline",
    "OpenLineage core",
    "OpenLineage core (per process)",
    "OpenLineage + dcp facet",
)
LEVEL_ORDER = ("nodes", "dataset edges", "run edges", "provenance")
CONFIG_ORDER = (
    "file",
    "http",
    "http-down",
    "file+sqlcomment",
    "wrap-only",
    "capture-null",
)
# Colours from matplotlib's colour-blind-safe "tableau-colorblind10" style.
COLOURS = ("#006BA4", "#FF800E", "#ABABAB", "#595959", "#5F9ED1", "#C85200", "#898989")
P99_TARGET_US = 1000.0
THROUGHPUT_TARGET = 0.02

STYLE = {
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "figure.dpi": 100,
    "savefig.dpi": 200,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "pdf.fonttype": 42,
    "svg.hashsalt": "dcp",
    "path.simplify": False,
}


# --- Inputs ---------------------------------------------------------------------


def source_label(path: pathlib.Path, results: dict) -> str:
    env = results.get("environment", {})
    owner = results.get("label", "").startswith("local")
    machine = "the owner's machine" if owner else "the sandbox (a cloud VM)"
    try:
        shown = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        shown = path.name
    return (
        f"Source: {shown}, run `{results.get('label')}` on {machine}, "
        f"commit {str(env.get('git_commit'))[:12]}, started {env.get('timestamp_utc')}"
    )


def committed_runs(data: pathlib.Path = DATA) -> list[tuple[pathlib.Path, dict]]:
    """Every committed raw results JSON, oldest first."""
    runs = []
    for path in sorted(data.glob("*/results.json")):
        results = json.loads(path.read_text(encoding="utf-8"))
        runs.append((path, results))
    runs.sort(
        key=lambda pr: (
            pr[1].get("environment", {}).get("timestamp_utc") or "",
            str(pr[0]),
        )
    )
    return runs


def newest_with(runs, has) -> tuple[pathlib.Path, dict] | None:
    found = [pr for pr in runs if has(pr[1])]
    return found[-1] if found else None


def accuracy(results: dict, group: str) -> list[dict]:
    """The micro-averaged rows of the seeds of `group` ("scale" or "stress"),
    live if it ran, else replay."""
    scale = results["scale"]
    data = scale if group == "scale" else scale["stress"]
    live = data.get("live", {})
    part = live if "summary" in live else data["replay"]
    return part["summary"]["seeds"]["aggregate"]


def _triple(text: str) -> dict:
    """ "+187.1 [+142.6, +226.5]" -> {estimate, low, high}."""
    match = re.fullmatch(
        r"([+-]?[\d.]+)%? \[([+-]?[\d.]+), ([+-]?[\d.]+)\]", text.strip()
    )
    if not match:
        raise ValueError(f"not an estimate with an interval: {text!r}")
    est, low, high = (float(g) for g in match.groups())
    return {"estimate": est, "low": low, "high": high}


def overhead_from_results(results: dict) -> dict:
    """The overhead numbers the figures need, from a results JSON."""
    o = results["overhead"]
    tiers = {}
    for tier_id, tier in o["postgres"]["tiers"].items():
        tiers[f"{tier_id} {tier['label']}".replace(" (added in P5.1)", "")] = {
            config: {
                "added_p99_us": v["added_p99_us"],
                "implied_added_us": v.get("implied_added_us"),
            }
            for config, v in tier["versus_base"].items()
        }
    startup = {
        cmd: {"p50": s["p50"], "p95": s["p95"]} for cmd, s in o["startup"]["ms"].items()
    }
    return {"tiers": tiers, "startup": startup}


def overhead_from_record(name: str, lines: list[str]) -> dict:
    """The same numbers, parsed by code from a committed rendered record."""
    import evidence

    section = evidence.section(lines, "Overhead: live (4b)")
    tiers = {}
    for _index, level, title in evidence.headings(section):
        if level != 3 or not re.match(r"[TL]\d ", title):
            continue
        table = evidence.tables(evidence.section(section, title))[-1]
        header = evidence.cells(table[0])
        configs = {}
        for row in table[2:]:
            values = dict(zip(header, evidence.cells(row), strict=False))
            implied = values.get("Implied added µs/call [95% CI]")
            configs[values["Config"]] = {
                "added_p99_us": _triple(values["Added p99 µs [95% CI]"]),
                "implied_added_us": _triple(implied) if implied else None,
            }
        tiers[title.replace(" (added in P5.1)", "")] = configs
    startup_table = evidence.tables(evidence.section(section, "Process start-up"))[0]
    startup = {}
    for row in startup_table[2:]:
        command, p50, p95, *_rest = evidence.cells(row)
        startup[command] = {"p50": float(p50), "p95": float(p95)}
    return {"tiers": tiers, "startup": startup}


def overhead_source(
    data: pathlib.Path = DATA, results_dir: pathlib.Path = RESULTS
) -> tuple[dict, str] | None:
    """(overhead numbers, source label): the newest committed raw JSON with an
    overhead stage, else the newest committed overhead record, parsed."""
    found = newest_with(committed_runs(data), lambda r: "overhead" in r)
    if found:
        path, results = found
        return overhead_from_results(results), source_label(path, results)
    import evidence

    records = evidence.load(results_dir)
    record = evidence.newest(
        records, lambda r: evidence.section(r.lines, "Overhead: live (4b)") is not None
    )
    if record is None:
        return None
    machine = "the owner's machine" if record.owner else "the sandbox (a cloud VM)"
    label = (
        f"Source: docs/results/{record.name} (rendered record, parsed by code; its raw "
        f"JSON was not committed) on {machine}, commit {str(record.commit)[:12]}, "
        f"started {record.started}"
    )
    return overhead_from_record(record.name, record.lines), label


# --- Figures --------------------------------------------------------------------


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcdefaults()
    plt.rcParams.update(STYLE)
    return plt


def _footer(fig, text: str) -> None:
    fig.text(
        0.01,
        0.005,
        text,
        fontsize=5.5,
        color="#444444",
        ha="left",
        va="bottom",
        wrap=True,
    )


def save(fig, out: pathlib.Path, name: str) -> list[pathlib.Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / f"{name}.pdf", out / f"{name}.png"]
    fig.savefig(
        paths[0],
        metadata={
            "Creator": None,
            "Producer": None,
            "CreationDate": None,
            "ModDate": None,
        },
    )
    fig.savefig(paths[1], metadata={"Software": None})
    return paths


def figure_accuracy(
    rows: list[dict], title: str, source: str, out: pathlib.Path, name: str
):
    plt = _plt()
    methods = [m for m in METHOD_ORDER if any(r["method"] == m for r in rows)]
    levels = [lv for lv in LEVEL_ORDER if any(r["level"] == lv for r in rows)]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), sharey=True)
    width = 0.8 / len(methods)
    for ax, metric in zip(axes, ("precision", "recall"), strict=True):
        for i, method in enumerate(methods):
            xs, ys = [], []
            for j, level in enumerate(levels):
                cell = next(
                    (r for r in rows if r["method"] == method and r["level"] == level),
                    None,
                )
                if cell is not None and cell[metric] is not None:
                    xs.append(j - 0.4 + width * (i + 0.5))
                    ys.append(cell[metric])
            ax.bar(xs, ys, width=width * 0.92, color=COLOURS[i], label=method)
        ax.set_xticks(range(len(levels)), levels)
        ax.set_ylim(0, 1.05)
        ax.set_title(metric.capitalize())
        ax.grid(axis="y", color="#DDDDDD", linewidth=0.5)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("micro-averaged over the keys")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False)
    fig.suptitle(title, y=0.85, fontsize=9)
    fig.subplots_adjust(top=0.7, bottom=0.2, left=0.08, right=0.99, wspace=0.08)
    _footer(fig, source)
    paths = save(fig, out, name)
    plt.close(fig)
    return paths


def figure_p99(overhead: dict, source: str, out: pathlib.Path):
    plt = _plt()
    tiers = list(overhead["tiers"])
    configs = [c for c in CONFIG_ORDER if any(c in overhead["tiers"][t] for t in tiers)]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    width = 0.8 / len(configs)
    for i, config in enumerate(configs):
        xs, ys, lo, hi = [], [], [], []
        for j, tier in enumerate(tiers):
            v = overhead["tiers"][tier].get(config)
            if v is None:
                continue
            p99 = v["added_p99_us"]
            xs.append(j - 0.4 + width * (i + 0.5))
            ys.append(p99["estimate"])
            lo.append(p99["estimate"] - p99["low"])
            hi.append(p99["high"] - p99["estimate"])
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="o", ms=3, capsize=2, lw=0.8,
                    color=COLOURS[i], label=config)  # fmt: skip
    ax.axhline(P99_TARGET_US, color="#C00000", ls="--", lw=0.8, label="1 ms target")
    ax.axhline(0, color="#888888", lw=0.5)
    ax.set_xticks(range(len(tiers)), [t.split(" ")[0] for t in tiers])
    ax.set_ylabel("added p99 latency per call (µs), 95% CI")
    ax.set_title(
        "Added p99 latency per tier and configuration (T: parameterised; L: literal)"
    )
    ax.legend(ncol=7, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.5)
    fig.subplots_adjust(bottom=0.26, left=0.09, right=0.99, top=0.9)
    _footer(fig, source)
    paths = save(fig, out, "F3-added-p99")
    plt.close(fig)
    return paths


def figure_fixed_cost(
    overhead: dict, source: str, out: pathlib.Path, config: str = "file"
):
    plt = _plt()
    import numpy as np

    q_ms = np.logspace(-1, 3, 200)
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    i = 0
    for tier, configs in overhead["tiers"].items():
        implied = (configs.get(config) or {}).get("implied_added_us")
        if not implied:
            continue
        cost = implied["estimate"]
        loss = 100 * cost / (q_ms * 1000 + cost)
        ax.plot(q_ms, loss, color=COLOURS[i % len(COLOURS)], lw=1,
                ls="-" if tier.startswith("T") else "--",
                label=f"{tier.split(' ')[0]}: {cost:.1f} µs/call")  # fmt: skip
        i += 1
    ax.axhline(
        100 * THROUGHPUT_TARGET, color="#C00000", ls=":", lw=0.8, label="2% target"
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("the query's own latency (ms)")
    ax.set_ylabel("throughput lost (%) = c / (q + c)")
    ax.set_title(f"Fixed cost per call c, measured per tier (`{config}` sink)")
    ax.legend(ncol=3, frameon=False, fontsize=6)
    ax.grid(color="#EEEEEE", linewidth=0.5)
    fig.subplots_adjust(bottom=0.2, left=0.09, right=0.99, top=0.9)
    _footer(fig, source)
    paths = save(fig, out, "F4-fixed-cost")
    plt.close(fig)
    return paths


def figure_startup(overhead: dict, source: str, out: pathlib.Path):
    plt = _plt()
    commands = list(overhead["startup"])
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    p50 = [overhead["startup"][c]["p50"] for c in commands]
    p95 = [overhead["startup"][c]["p95"] for c in commands]
    ys = range(len(commands))
    ax.barh(ys, p50, color=COLOURS[0], label="p50")
    ax.scatter(p95, ys, color=COLOURS[1], marker="|", s=80, label="p95", zorder=3)
    ax.set_yticks(list(ys), [c.replace(" (added in P5.1)", "") for c in commands])
    ax.invert_yaxis()
    ax.set_xlabel("start-up of `-c pass` (ms)")
    ax.set_title("Process start-up")
    ax.legend(frameon=False, loc="upper right")
    fig.subplots_adjust(left=0.5, bottom=0.22, right=0.98, top=0.88)
    _footer(fig, source)
    paths = save(fig, out, "F5-startup")
    plt.close(fig)
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--scale", type=pathlib.Path, help="raw results JSON for F1 and F2"
    )
    parser.add_argument(
        "--overhead", type=pathlib.Path, help="raw results JSON for F3-F5"
    )
    parser.add_argument("--data", type=pathlib.Path, default=DATA)
    parser.add_argument("--results", type=pathlib.Path, default=RESULTS)
    parser.add_argument("--out", type=pathlib.Path, default=OUT)
    args = parser.parse_args(argv)
    written = []

    if args.scale:
        scale = (args.scale, json.loads(args.scale.read_text(encoding="utf-8")))
    else:
        scale = newest_with(
            committed_runs(args.data), lambda r: "stress" in r.get("scale", {})
        )
    if scale is None:
        print(
            "F1, F2: no results JSON with the scale stage and the stress group",
            file=sys.stderr,
        )
    else:
        path, results = scale
        label = source_label(path, results)
        written += figure_accuracy(
            accuracy(results, "scale"),
            "F1. Generated keys scale_s01..s10: precision and recall by method and level",
            label,
            args.out,
            "F1-scale-accuracy",
        )
        written += figure_accuracy(
            accuracy(results, "stress"),
            "F2. Stress set stress_s01..s05 (DCP's known failure modes): precision and recall",
            label,
            args.out,
            "F2-stress-accuracy",
        )

    if args.overhead:
        results = json.loads(args.overhead.read_text(encoding="utf-8"))
        source = (overhead_from_results(results), source_label(args.overhead, results))
    else:
        source = overhead_source(args.data, args.results)
    if source is None:
        print("F3-F5: no overhead data", file=sys.stderr)
    else:
        overhead, label = source
        written += figure_p99(overhead, label, args.out)
        written += figure_fixed_cost(overhead, label, args.out)
        written += figure_startup(overhead, label, args.out)

    for path in written:
        print(f"wrote {path}")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
