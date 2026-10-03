"""Render benchmarks/run.py's results JSON as markdown. P5.

    python benchmarks/render.py benchmarks/results/<label>/results.json OUT.md
    python benchmarks/render.py --compare BEFORE.json AFTER.json OUT.md

The ONLY code that writes numbers into markdown. Pure and deterministic: the
output depends on the JSON alone, so a results file always re-renders to the
same bytes.
"""

import argparse
import os
import sys

_GROUND_TRUTH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ground_truth")
if _GROUND_TRUTH not in sys.path:
    sys.path.insert(0, _GROUND_TRUTH)

from score import format_table

LATENCY_TRIGGER_US = 500.0  # Stage 5: _capture p99 above this on any tier
FILE_ADDED_TRIGGER_US = 1000.0  # Stage 5: `file` added p99 at or above this on any tier
CI_NOTE = (
    "**These overhead numbers come from a CI runner: a shared VM, noisy, and not "
    "the authoritative overhead source.** The authoritative full-mode numbers come "
    "from the owner's machine (`docs/results/P5-local.md`)."
)


def us(value) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def ms(value) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def ci(result: dict, unit: str = "") -> str:
    return (
        f"{result['estimate']:+.1f}{unit} [{result['low']:+.1f}, {result['high']:+.1f}]"
    )


def pct(result: dict) -> str:
    return f"{result['estimate']:+.2f}% [{result['low']:+.2f}, {result['high']:+.2f}]"


def table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return lines


def code(lines: list[str]) -> list[str]:
    return ["```", *lines, "```"]


def _environment(results: dict) -> list[str]:
    env = results["environment"]
    rows = [
        [
            "Label",
            f"`{results['label']}`" + (" (quick mode)" if results["quick"] else ""),
        ],
        ["Command", f"`{env['command']}`"],
        ["Started (UTC)", env["timestamp_utc"]],
        ["Finished (UTC)", env.get("finished_utc", "n/a")],
        ["Git commit", f"`{env['git_commit']}`"],
        ["Working tree dirty", env["git_dirty"]],
        ["Python", f"{env['python']} ({env['python_implementation']})"],
        ["OS", env["os"]],
        ["CPU", f"{env['cpu_model']}, {env['cpu_count']} logical cores"],
        ["CI runner", env["ci"]],
        ["PostgreSQL server", env["postgres_server_version"] or "not reached"],
        [
            "Kafka broker",
            env["kafka_broker_version"] or env["kafka_broker_version_note"],
        ],
        [
            "DCP configuration",
            "; ".join(f"{k}: {v}" for k, v in env["dcp_configuration"].items()),
        ],
    ]
    packages = ", ".join(f"{k} {v}" for k, v in env["packages"].items() if v)
    rows.append(["Packages", packages])
    if "pins" in env:
        rows.append(["Pinned versions", _pins(env["pins"])])
    return ["## Environment", "", *table(["", ""], rows), ""]


def _pins(pins: dict) -> str:
    """The A1 check: installed versions against benchmarks/requirements.txt and
    constraints.txt. A mismatch is recorded, never fatal."""
    if "error" in pins:
        return f"not checked ({pins['error']})"
    files = " and ".join(f"`{f}`" for f in pins["files"])
    if not pins["mismatches"]:
        return f"all {pins['checked']} pins match ({files})"
    shown = ", ".join(
        f"{m['package']} {m['installed'] or 'not installed'} (pinned {m['pinned']})"
        for m in pins["mismatches"]
    )
    return f"**{len(pins['mismatches'])} of {pins['checked']} differ from the pins** ({files}): {shown}"


def _stages(results: dict) -> list[str]:
    rows = []
    for s in results["stages"]:
        detail = s.get("reason") or ""
        if s["status"] == "failed":
            detail = "see the error below"
        seconds = f"{s['seconds']}" if "seconds" in s else ""
        rows.append([s["stage"], s["status"], seconds, detail])
    out = ["## Stages", "", *table(["Stage", "Status", "Seconds", "Detail"], rows), ""]
    for s in results["stages"]:
        if s["status"] == "failed":
            out += [
                f"### `{s['stage']}` failed",
                "",
                *code(s["error"].splitlines()),
                "",
            ]
    return out


def _scores(workloads: list[dict]) -> list[str]:
    out = []
    for w in workloads:
        out += [
            f"### {w['workload']}",
            "",
            *code(format_table(w["score"]["dcp"] if "score" in w else w["dcp"])),
            "",
            "OpenLineage translation (core run model, then with the dcp facet):",
            "",
            *code(
                format_table(
                    w["score"]["openlineage"] if "score" in w else w["openlineage"]
                )
            ),
            "",
        ]
    return out


def _replay(results: dict) -> list[str]:
    if "replay" not in results:
        return []
    return [
        "## Ground truth: replay",
        "",
        "DCP's real capture code with faked database and broker I/O; not a live run.",
        "",
        *_scores(results["replay"]["workloads"]),
    ]


def _live(results: dict) -> list[str]:
    if "live" not in results:
        return []
    live = results["live"]
    out = [
        "## Ground truth: live",
        "",
        (
            f"Real PostgreSQL ({live['postgres_server_version']}) and Kafka; every process a "
            "separate OS process under `dcp-instrument`; the programs contain no DCP code "
            f"(run id `{live['run_id']}`)."
        ),
        "",
    ]
    rows = []
    for w in live["workloads"]:
        for p in w["processes"]:
            rows.append(
                [w["workload"], p["job"], p["kind"], p["exit_code"], p["events"]]
            )
    out += [*table(["Workload", "Job", "Kind", "Exit code", "DCP events"], rows), ""]
    return out + _scores(live["workloads"])


def _adversarial(results: dict) -> list[str]:
    if "adversarial" not in results:
        return []
    adv = results["adversarial"]
    rows = []
    for c in adv["cases"]:
        evidence = []
        if "dcp_perfect" in c:
            evidence.append(
                "DCP graph matches the key" if c["dcp_perfect"] else "DCP graph DIFFERS"
            )
        if c.get("dataset_level_over_approximates") is not None:
            evidence.append(
                "dataset-level baseline over-approximates"
                if c["dataset_level_over_approximates"]
                else "dataset-level baseline does NOT over-approximate"
            )
        if c.get("consumer_checked_record") is not None:
            evidence.append(
                "consumer read producer A's record (checked)"
                if c["consumer_checked_record"]
                else "consumer record check FAILED"
            )
        if "openlineage_events_without_dcp" in c:
            evidence.append(
                f"OpenLineage events without DCP: {c['openlineage_events_without_dcp']}"
            )
        rows.append(
            [
                c["case"],
                c["title"],
                f"`{c['workload']}`",
                c["status"],
                "; ".join(evidence),
            ]
        )
    b = adv["baseline"]
    control = b["control"]
    programs = ", ".join(f"`{p['workload']}/{p['job']}`" for p in b["programs"])
    return [
        "## Adversarial",
        "",
        *table(["Case", "Movement", "Workload", "Status", "Evidence"], rows),
        "",
        "### OpenLineage baseline, measured",
        "",
        (
            f"`openlineage-python` {b['openlineage_python_version']} installed, `OPENLINEAGE_URL` "
            f"pointing at a counting stub; programs run **without** `dcp-instrument`: {programs}."
        ),
        "",
        *table(
            ["Measurement", "Value"],
            [
                [
                    "Events received from the uninstrumented programs",
                    b["events_received_uninstrumented"],
                ],
                [
                    "Positive control (`manual_emission.py`): exit code",
                    control["exit_code"],
                ],
                ["Positive control: events received", control["events_received"]],
                [
                    "Positive control: event types",
                    ", ".join(map(str, control["event_types"])),
                ],
            ],
        ),
        "",
    ]


def stage5_trigger(results: dict) -> list[str]:
    """Which of Stage 5's trigger conditions fire, from the numbers."""
    fired = []
    for py in results.get("cpu", {}).get("pythons", []):
        for name, tier in py.get("tiers", {}).items():
            if tier["capture_us"]["p99"] > LATENCY_TRIGGER_US:
                fired.append(
                    f"4a, Python {py['python']}, {name}: `_capture` p99 "
                    f"{us(tier['capture_us']['p99'])} µs > {LATENCY_TRIGGER_US:.0f} µs"
                )
    for name, tier in (
        results.get("overhead", {}).get("postgres", {}).get("tiers", {}).items()
    ):
        added = tier["versus_base"]["file"]["added_p99_us"]["estimate"]
        if added >= FILE_ADDED_TRIGGER_US:
            fired.append(
                f"4b, {name}: `file` added p99 {us(added)} µs ≥ {FILE_ADDED_TRIGGER_US:.0f} µs"
            )
    return fired


def _cpu(results: dict) -> list[str]:
    if "cpu" not in results:
        return []
    out = [
        "## Overhead: CPU microbenchmark (4a)",
        "",
        (
            "`_capture` on a fake cursor with a discarding emitter, and `_classify` alone "
            "(sqlglot's share). Per tier: 1,000 warm-up calls, then 10,000 timed calls. "
            "Microseconds."
        ),
        "",
    ]
    for py in results["cpu"]["pythons"]:
        if "error" in py:
            out += [
                f"### `{py['executable']}`: failed",
                "",
                *code(py["error"].splitlines()),
                "",
            ]
            continue
        rows = []
        for name, tier in py["tiers"].items():
            c, k = tier["capture_us"], tier["classify_us"]
            rows.append(
                [
                    f"{name} {tier['label']}",
                    us(c["p50"]),
                    us(c["p95"]),
                    us(c["p99"]),
                    us(c["p99.9"]),
                    us(k["p50"]),
                    us(k["p99"]),
                ]
            )
        out += [
            (
                f"### Python {py['python']} (sqlglot {py['sqlglot']}; {py['warmup']} warm-up, "
                f"{py['timed']} timed)"
            ),
            "",
            *table(
                [
                    "Tier",
                    "capture p50",
                    "p95",
                    "p99",
                    "p99.9",
                    "classify p50",
                    "classify p99",
                ],
                rows,
            ),
            "",
        ]
    return out


def _verdict_rows(versus: dict) -> list[list]:
    rows = []
    for config, v in versus.items():
        rows.append(
            [
                config,
                ci(v["added_p50_us"]),
                ci(v["added_p99_us"]),
                pct(v["throughput_change_pct"]),
                v["latency_verdict"],
                v["throughput_verdict"],
            ]
        )
    return rows


VERDICT_HEADER = [
    "Config",
    "Added p50 µs [95% CI]",
    "Added p99 µs [95% CI]",
    "Throughput Δ [95% CI]",
    "< 1 ms p99 added",
    "< 2% throughput loss",
]


def _overhead(results: dict) -> list[str]:
    if "overhead" not in results:
        return []
    o = results["overhead"]
    mode = o["mode"]
    out = ["## Overhead: live (4b)", ""]
    if results["environment"]["ci"] or results["label"] == "ci":
        out += [CI_NOTE, ""]
    out += [
        (
            f"Mode `{mode['name']}`: {mode['rounds']} rounds × {mode['calls']} calls per tier, "
            f"{mode['warmup']} warm-up calls per tier per round discarded; each configuration a "
            "fresh process per round, in the fixed order "
            f"{', '.join(f'`{c}`' for c in o['configs'])}. Added latency and throughput change "
            "are paired by round against `base`, with 95% bootstrap intervals over rounds "
            "(10,000 resamples, fixed seed). Verdicts: met (interval below the target), "
            "not met (interval at or above it), inconclusive (straddles it). Microseconds."
        ),
        "",
    ]
    for name, tier in o["postgres"]["tiers"].items():
        rows = []
        for config, lat in tier["latency_us"].items():
            tp = tier["throughput_per_s"][config]
            rows.append(
                [
                    config,
                    us(lat["p50"]),
                    us(lat["p95"]),
                    us(lat["p99"]),
                    us(lat["p99.9"]),
                    us(lat["max"]),
                    f"{tp['p50']:.0f}",
                ]
            )
        out += [
            f"### {name} {tier['label']}",
            "",
            *table(
                [
                    "Config",
                    "p50",
                    "p95",
                    "p99",
                    "p99.9",
                    "max",
                    "calls/s (median round)",
                ],
                rows,
            ),
            "",
            *table(VERDICT_HEADER, _verdict_rows(tier["versus_base"])),
            "",
        ]
    rows = []
    for config, d in o["postgres"]["delivery"].items():
        delivered = d["delivered_per_round"]
        shown = (
            "not measurable (nothing listens)"
            if all(x is None for x in delivered)
            else (", ".join(map(str, delivered)))
        )
        rows.append([config, d["expected_per_round"], shown])
    out += [
        "### Events delivered (Postgres rounds)",
        "",
        *table(["Config", "Emitted per round", "Delivered, per round"], rows),
        "",
    ]
    k = o["kafka"]
    rows = []
    for config, lat in k["latency_us"].items():
        tp = k["throughput_per_s"][config]
        rows.append(
            [
                config,
                us(lat["p50"]),
                us(lat["p95"]),
                us(lat["p99"]),
                us(lat["p99.9"]),
                us(lat["max"]),
                f"{tp['p50']:.0f}",
            ]
        )
    kd = [
        [c, d["expected_per_round"], ", ".join(map(str, d["delivered_per_round"]))]
        for c, d in k["delivery"].items()
    ]
    out += [
        f"### Kafka `produce()`, {k['message_bytes']}-byte messages",
        "",
        (
            f"{mode['kafka_messages']} messages per round after {mode['kafka_warmup']} warm-up; "
            "throughput includes the final `flush()`."
        ),
        "",
        *table(
            [
                "Config",
                "p50",
                "p95",
                "p99",
                "p99.9",
                "max",
                "messages/s (median round)",
            ],
            rows,
        ),
        "",
        *table(VERDICT_HEADER, _verdict_rows(k["versus_base"])),
        "",
        *table(["Config", "Emitted per round", "Delivered, per round"], kd),
        "",
    ]
    s = o["startup"]
    rows = [
        [name, ms(v["p50"]), ms(v["p95"]), ms(v["max"])] for name, v in s["ms"].items()
    ]
    out += [
        "### Process start-up (excluded from per-call timing)",
        "",
        f"`-c pass`, {s['reps']} runs each, alternating. Milliseconds.",
        "",
        *table(["Command", "p50", "p95", "max"], rows),
        "",
    ]
    b = o["backpressure"]
    lat = b["latency_us"]
    out += [
        "### Backpressure: `http-down` with a tiny queue (reported, not a target)",
        "",
        *table(
            ["Measurement", "Value"],
            [
                ["Queue size", b["queue_size"]],
                ["Events emitted", b["events_emitted"]],
                ["Events dropped (exact)", b["dropped"]],
                [
                    "Per-call latency p50 / p99 / p99.9 / max (µs)",
                    " / ".join(us(lat[q]) for q in ("p50", "p99", "p99.9", "max")),
                ],
                [
                    f"Bounded: every call under the {b['bound_ms']:.0f} ms retry backoff",
                    "yes" if b["bounded"] else "NO",
                ],
            ],
        ),
        "",
    ]
    return out


def _trigger(results: dict) -> list[str]:
    if "cpu" not in results and "overhead" not in results:
        return []
    fired = stage5_trigger(results)
    out = ["## Stage 5 trigger (parse cache)", ""]
    if fired:
        out += ["Fires:", "", *[f"- {line}" for line in fired], ""]
    else:
        out += ["Does not fire on these results.", ""]
    return out


def render(results: dict) -> str:
    lines = [
        f"# P5 results: `{results['label']}`",
        "",
        (
            "Generated by `benchmarks/run.py` and rendered by `benchmarks/render.py`. "
            "Do not edit by hand: re-run the command below."
        ),
        "",
        *_environment(results),
        *_stages(results),
        *_replay(results),
        *_live(results),
        *_adversarial(results),
        *_cpu(results),
        *_overhead(results),
        *_trigger(results),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _compare_rows(before: dict, after: dict) -> list[str]:
    out = []
    pythons_b = {
        p["python"]: p for p in before.get("cpu", {}).get("pythons", []) if "tiers" in p
    }
    pythons_a = {
        p["python"]: p for p in after.get("cpu", {}).get("pythons", []) if "tiers" in p
    }
    for version in sorted(set(pythons_b) & set(pythons_a)):
        rows = []
        for name, tb in pythons_b[version]["tiers"].items():
            ta = pythons_a[version]["tiers"][name]
            rows.append(
                [
                    f"{name} {tb['label']}",
                    us(tb["capture_us"]["p50"]),
                    us(ta["capture_us"]["p50"]),
                    us(tb["capture_us"]["p99"]),
                    us(ta["capture_us"]["p99"]),
                ]
            )
        out += [
            f"### 4a, Python {version}: `_capture` (µs)",
            "",
            *table(
                ["Tier", "p50 before", "p50 after", "p99 before", "p99 after"], rows
            ),
            "",
        ]
    ob = before.get("overhead", {}).get("postgres", {}).get("tiers", {})
    oa = after.get("overhead", {}).get("postgres", {}).get("tiers", {})
    for name in [n for n in ob if n in oa]:
        rows = []
        for config, vb in ob[name]["versus_base"].items():
            va = oa[name]["versus_base"][config]
            rows.append(
                [
                    config,
                    ci(vb["added_p99_us"]),
                    ci(va["added_p99_us"]),
                    f"{vb['latency_verdict']} → {va['latency_verdict']}",
                    pct(vb["throughput_change_pct"]),
                    pct(va["throughput_change_pct"]),
                    f"{vb['throughput_verdict']} → {va['throughput_verdict']}",
                ]
            )
        out += [
            f"### 4b, {name} {ob[name]['label']}",
            "",
            *table(
                [
                    "Config",
                    "Added p99 µs before",
                    "after",
                    "p99 verdict",
                    "Throughput Δ before",
                    "after",
                    "throughput verdict",
                ],
                rows,
            ),
            "",
        ]
    return out


def render_comparison(before: dict, after: dict) -> str:
    lines = [
        (
            f"# P5 Stage 5: parse cache, before (`{before['label']}`) and after "
            f"(`{after['label']}`)"
        ),
        "",
        (
            "Rendered by `benchmarks/render.py --compare` from the two runs' results JSON. "
            "Do not edit by hand."
        ),
        "",
        *table(
            ["", "Before", "After"],
            [
                [
                    "Git commit",
                    f"`{before['environment']['git_commit']}`",
                    f"`{after['environment']['git_commit']}`",
                ],
                [
                    "Command",
                    f"`{before['environment']['command']}`",
                    f"`{after['environment']['command']}`",
                ],
                [
                    "Started (UTC)",
                    before["environment"]["timestamp_utc"],
                    after["environment"]["timestamp_utc"],
                ],
            ],
        ),
        "",
        *_compare_rows(before, after),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None) -> int:
    import json

    parser = argparse.ArgumentParser(description="Render P5 results JSON as markdown")
    parser.add_argument(
        "--compare", action="store_true", help="BEFORE.json AFTER.json OUT.md"
    )
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)

    def load(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    if args.compare:
        before, after, out = args.paths
        text = render_comparison(load(before), load(after))
    else:
        source, out = args.paths
        text = render(load(source))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
