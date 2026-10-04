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


P51_TIERS_NOTE = (
    "**Added in P5.1, after P5's results were seen:** the L tiers inline a literal "
    "that differs on every call, so the query text never repeats and every call "
    "misses the parse cache (the ad-hoc-script shape). They make the benchmark "
    "harder; T1–T5 are unchanged."
)
P51_CONFIGS_NOTE = (
    "**Added in P5.1, after P5's results were seen:** the L tiers (cache-hostile: "
    "a different inlined literal on every call) and the diagnostic configurations "
    "`wrap-only` (`DCP_CAPTURE=off`: the wrappers alone) and `capture-null` "
    "(`null://`: capture and event construction, no delivery), which exist to "
    "attribute the per-call cost. The column *Implied added µs/call* is "
    "`1e6/throughput_instrumented − 1e6/throughput_base`, paired by round with a "
    "bootstrap interval: the fixed cost per call that the throughput change implies."
)
NORMALIZE_NOTE = (
    "*normalise* (P5.1, O1): the literal-normalisation pass alone, which builds the "
    "parse cache's second-level key on an exact-text miss. A parameterised tier pays "
    "it only on its first call; a literal tier pays it on every call."
)
PROFILE_NOTE = (
    "One extra round per instrumented configuration, under `cProfile`, timed loop "
    "only; never used for any timing. Functions reached from DCP's psycopg wrapper "
    "(`execute` in `dcp/interceptors/postgres.py`, which also calls the original "
    "`execute`), ranked by cumulative time, per timed call. **cProfile inflates "
    "absolute times, most where many small functions run: read these for "
    "attribution, not magnitude.**"
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


SCALE_NOTE = (
    "**Generated keys, added in P5.1** (`benchmarks/ground_truth/generate.py`): "
    "generated from fixed seeds, not hand-written, with truth derived from the "
    "generator's own construction. Scored with the same row functions as the "
    "hand-written keys, and **reported apart from them, never pooled**. "
    "Precision and recall are micro-averaged: summed hits over summed found (or "
    "expected), over every row of every key in the group; the per-key columns give "
    "each key's own micro-average, as min / median / max."
)


def _r(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _spread(s) -> str:
    return (
        "n/a" if s is None else f"{_r(s['min'])} / {_r(s['median'])} / {_r(s['max'])}"
    )


def _scale_table(rows: list[dict], per_key: bool) -> list[str]:
    header = ["Method", "Level", "Precision", "Recall"]
    if per_key:
        header += [
            "Keys",
            "Per-key precision min / median / max",
            "Per-key recall min / median / max",
        ]
    out = []
    for a in rows:
        row = [
            a["method"],
            a["level"],
            f"{a['hits']}/{a['found']} = {_r(a['precision'])}",
            f"{a['hits']}/{a['expected']} = {_r(a['recall'])}",
        ]
        if per_key:
            row += [
                a["keys"],
                _spread(a["per_key_precision"]),
                _spread(a["per_key_recall"]),
            ]
        out.append(row)
    return table(header, out)


def _scale_summary(summary: dict) -> list[str]:
    out = []
    if summary["seeds"]["names"]:
        names = summary["seeds"]["names"]
        out += [
            f"#### {names[0]} … {names[-1]} ({len(names)} keys), micro-averaged",
            "",
            *_scale_table(summary["seeds"]["aggregate"], per_key=True),
            "",
        ]
    for name, rows in summary["others"].items():
        out += [f"#### {name}, on its own", "", *_scale_table(rows, per_key=False), ""]
    rows = []
    for name, e in summary["extras"].items():
        m = summary["misses"][name]
        rows.append(
            [
                name,
                e["extras"],
                e["explained_by_distractors"],
                "; ".join(e["unexplained"]) or "none",
                m["misses"],
                m["explained_by_split_runs"],
                "; ".join(m["unexplained"]) or "none",
            ]
        )
    out += [
        (
            "Every item DCP's own graph found beyond the truth, checked against the "
            "generator's distractor reads; and every expected item any method missed "
            "(recall below 1.0), checked against split runs: a consumer that reads "
            "records from two producers joins two traces, and the P4 bridge maps one "
            "OpenLineage run per (trace, process), so OpenLineage's core model sees two "
            "runs where there was one process. Anything unexplained is a bug."
        ),
        "",
        *table(
            [
                "Key",
                "DCP extras",
                "Explained by a distractor read",
                "Unexplained extras",
                "Missed items",
                "Explained by a split run",
                "Unexplained misses",
            ],
            rows,
        ),
        "",
    ]
    return out


def _scale(results: dict) -> list[str]:
    if "scale" not in results:
        return []
    s = results["scale"]
    rows = [
        [
            k["workload"],
            k["seed"],
            k["jobs"],
            ", ".join(f"{n} {kind}" for kind, n in sorted(k["kinds"].items())),
            k["jobs_with_distractors"],
            k["fan_in_topics"],
            k.get("split_jobs", "n/a"),
            k["datasets"],
            k["provenance_entries"],
        ]
        for k in s["replay"]["summary"]["keys"]
    ]
    out = [
        "## Ground truth at scale: generated keys (added in P5.1)",
        "",
        SCALE_NOTE,
        "",
        f"Generator version {s['generator_version']}.",
        "",
        *table(
            [
                "Key",
                "Seed",
                "Jobs",
                "Job kinds",
                "Jobs with a distractor read",
                "Fan-in topics",
                "Jobs on two traces (split runs)",
                "Datasets",
                "Provenance entries",
            ],
            rows,
        ),
        "",
        "### Replay",
        "",
        "DCP's real capture code with faked I/O, as for the hand-written keys.",
        "",
        *_scale_summary(s["replay"]["summary"]),
    ]
    live = s.get("live", {})
    out += ["### Live", ""]
    if "skipped" in live:
        return out + [f"Skipped: {live['skipped']}", ""]
    rows = [
        [
            name,
            r["processes"],
            ", ".join(map(str, r["exit_codes"])),
            r["events"],
            r["manifest_records"],
            "yes" if r["agrees_with_replay"] else "**NO**",
        ]
        for name, r in live["records"].items()
    ]
    out += [
        (
            f"Real PostgreSQL and Kafka, every process a separate OS process under "
            f"`dcp-instrument`, consumers reading their named record by exact offset "
            f"(run id `{live['run_id']}`; {live['mode']})."
        ),
        "",
        *table(
            [
                "Key",
                "Processes",
                "Exit codes",
                "DCP events",
                "Records in the run manifest",
                "Every row agrees with replay",
            ],
            rows,
        ),
        "",
        *_scale_summary(live["summary"]),
    ]
    return out


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
    if any(
        "(added in P5.1)" in tier["label"]
        for py in results["cpu"]["pythons"]
        for tier in py.get("tiers", {}).values()
    ):
        out += [P51_TIERS_NOTE, ""]
    if any(
        "normalize_us" in tier
        for py in results["cpu"]["pythons"]
        for tier in py.get("tiers", {}).values()
    ):
        out += [NORMALIZE_NOTE, ""]
    for py in results["cpu"]["pythons"]:
        if "error" in py:
            out += [
                f"### `{py['executable']}`: failed",
                "",
                *code(py["error"].splitlines()),
                "",
            ]
            continue
        normalize = any("normalize_us" in tier for tier in py["tiers"].values())
        rows = []
        for name, tier in py["tiers"].items():
            c, k = tier["capture_us"], tier["classify_us"]
            row = [
                f"{name} {tier['label']}",
                us(c["p50"]),
                us(c["p95"]),
                us(c["p99"]),
                us(c["p99.9"]),
                us(k["p50"]),
                us(k["p99"]),
            ]
            if normalize:
                n = tier.get("normalize_us") or {}
                row += [us(n.get("p50")), us(n.get("p99"))]
            rows.append(row)
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
                    *(["normalise p50", "normalise p99"] if normalize else []),
                ],
                rows,
            ),
            "",
        ]
    return out


def _has_implied(versus: dict) -> bool:
    return any("implied_added_us" in v for v in versus.values())


def _verdict_rows(versus: dict) -> list[list]:
    implied = _has_implied(versus)
    rows = []
    for config, v in versus.items():
        row = [
            config,
            ci(v["added_p50_us"]),
            ci(v["added_p99_us"]),
            pct(v["throughput_change_pct"]),
        ]
        if implied:
            row.append(ci(v["implied_added_us"]))
        rows.append(row + [v["latency_verdict"], v["throughput_verdict"]])
    return rows


def _verdict_table(versus: dict) -> list[str]:
    header = VERDICT_HEADER
    if _has_implied(versus):
        header = [
            *VERDICT_HEADER[:4],
            "Implied added µs/call [95% CI]",
            *VERDICT_HEADER[4:],
        ]
    return table(header, _verdict_rows(versus))


def _attribution(tiers: dict, kafka: dict | None) -> list[str]:
    """A3's attribution (P5.1): the added cost split into components."""
    blocks = [
        (name, f"{name} {tier['label']}", tier["attribution"])
        for name, tier in tiers.items()
        if tier.get("attribution")
    ]
    if kafka and kafka.get("attribution"):
        blocks.append(("Kafka", "Kafka `produce()`", kafka["attribution"]))
    if not blocks:
        return []
    out = [
        "### Attribution of the added cost (added in P5.1)",
        "",
        (
            "Each component is the difference between two configurations, paired by "
            "round (so `base` cancels), with a 95% bootstrap interval: by per-round p50 "
            "latency, and by the mean cost per call that throughput implies. Microseconds."
        ),
        "",
    ]
    for _name, title, rows in blocks:
        out += [
            f"#### {title}",
            "",
            *table(
                [
                    "Component",
                    "Measured as",
                    "p50 µs [95% CI]",
                    "Implied µs/call [95% CI]",
                ],
                [
                    [
                        r["component"],
                        f"`{r['measured_as']}`",
                        ci(r["p50_us"]),
                        ci(r["implied_us"]),
                    ]
                    for r in rows
                ],
            ),
            "",
        ]
    return out


def _profile(profile: dict | None) -> list[str]:
    if not profile:
        return []
    out = ["### Profiling round (added in P5.1)", "", PROFILE_NOTE, ""]
    for config, tiers in profile["configs"].items():
        for tier, s in tiers.items():
            if not s.get("wrapper_found"):
                out += [
                    f"#### `{config}`, {tier}: DCP's wrapper not found in the profile",
                    "",
                ]
                continue
            header = [
                "Function",
                "Calls per call",
                "Own µs",
                "Cumulative µs",
                "Share of wrapper",
            ]
            out += [
                (
                    f"#### `{config}`, {tier}: wrapper {us(s['wrapper_cumulative_us_per_call'])} "
                    f"µs per call under cProfile, of which the original `execute` "
                    f"{us(s.get('original_cumulative_us_per_call'))} µs ({s['calls']} calls)"
                ),
                "",
                "The whole call path:",
                "",
                *table(header, _profile_rows(s["top"])),
                "",
            ]
            if s.get("dcp_top"):
                out += [
                    "DCP's part only (not through the original `execute`):",
                    "",
                    *table(header, _profile_rows(s["dcp_top"])),
                    "",
                ]
    return out


def _profile_rows(rows: list[dict]) -> list[list]:
    return [
        [
            f"`{r['function']}`",
            f"{r['calls_per_call']:.2f}",
            us(r["own_us_per_call"]),
            us(r["cumulative_us_per_call"]),
            "n/a"
            if r["share_of_wrapper_pct"] is None
            else f"{r['share_of_wrapper_pct']:.1f}%",
        ]
        for r in rows
    ]


def _delivery_shown(d: dict) -> str:
    delivered = d["delivered_per_round"]
    if "note" in d:
        return d["note"]
    if all(x is None for x in delivered):
        return "not measurable (nothing listens)"
    return ", ".join(map(str, delivered))


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
    if "added_in_p51" in o:
        out += [P51_CONFIGS_NOTE, ""]
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
            *_verdict_table(tier["versus_base"]),
            "",
        ]
    rows = []
    for config, d in o["postgres"]["delivery"].items():
        rows.append([config, d["expected_per_round"], _delivery_shown(d)])
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
        [c, d["expected_per_round"], _delivery_shown(d)]
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
        *_verdict_table(k["versus_base"]),
        "",
        *table(["Config", "Emitted per round", "Delivered, per round"], kd),
        "",
        *_attribution(o["postgres"]["tiers"], k),
        *_profile(o["postgres"].get("profile")),
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
        *_scale(results),
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


def _is_p51(results: dict) -> bool:
    tiers = results.get("overhead", {}).get("postgres", {}).get("tiers", {})
    return any(_has_implied(t["versus_base"]) for t in tiers.values())


def _cmp(before, after, fmt) -> list[str]:
    return [
        fmt(before) if before is not None else "n/a",
        fmt(after) if after is not None else "n/a",
    ]


def _compare_rows_p51(before: dict, after: dict) -> list[str]:
    """P5.1's comparison: every tier and configuration, the implied cost, the
    attribution, Kafka and start-up. Every row, whichever way it moved."""
    out = []
    pythons_b = {
        p["python"]: p for p in before.get("cpu", {}).get("pythons", []) if "tiers" in p
    }
    pythons_a = {
        p["python"]: p for p in after.get("cpu", {}).get("pythons", []) if "tiers" in p
    }
    for version in sorted(set(pythons_b) & set(pythons_a)):
        tb, ta = pythons_b[version]["tiers"], pythons_a[version]["tiers"]
        rows = []
        for name in [n for n in tb if n in ta]:
            rows.append(
                [
                    f"{name} {tb[name]['label']}",
                    *_cmp(
                        tb[name]["capture_us"]["p50"], ta[name]["capture_us"]["p50"], us
                    ),
                    *_cmp(
                        tb[name]["capture_us"]["p99"], ta[name]["capture_us"]["p99"], us
                    ),
                    *_cmp(
                        tb[name]["classify_us"]["p50"],
                        ta[name]["classify_us"]["p50"],
                        us,
                    ),
                ]
            )
        out += [
            f"### 4a, Python {version}: `_capture` and `_classify` (µs)",
            "",
            *table(
                [
                    "Tier",
                    "capture p50 before",
                    "after",
                    "capture p99 before",
                    "after",
                    "classify p50 before",
                    "after",
                ],
                rows,
            ),
            "",
        ]
        if any("normalize_us" in tier for tier in ta.values()):
            rows = [
                [
                    f"{name} {tier['label']}",
                    us(tier["normalize_us"]["p50"]),
                    us(tier["normalize_us"]["p99"]),
                ]
                for name, tier in ta.items()
                if "normalize_us" in tier
            ]
            out += [
                f"#### 4a, Python {version}: the cache-key normalisation pass alone, after (µs)",
                "",
                *table(["Tier", "p50", "p99"], rows),
                "",
            ]
    sections = [
        (
            f"{name} {tier['label']}",
            tier,
            after["overhead"]["postgres"]["tiers"].get(name),
        )
        for name, tier in before.get("overhead", {})
        .get("postgres", {})
        .get("tiers", {})
        .items()
    ]
    if "kafka" in before.get("overhead", {}) and "kafka" in after.get("overhead", {}):
        sections.append(
            (
                "Kafka `produce()`",
                before["overhead"]["kafka"],
                after["overhead"]["kafka"],
            )
        )
    for title, tb, ta in sections:
        if ta is None:
            out += [f"### 4b, {title}", "", "Not in the after run.", ""]
            continue
        rows = []
        for config, vb in tb["versus_base"].items():
            va = ta["versus_base"].get(config)
            if va is None:
                continue
            rows.append(
                [
                    config,
                    *_cmp(vb["added_p50_us"], va["added_p50_us"], ci),
                    *_cmp(vb["added_p99_us"], va["added_p99_us"], ci),
                    f"{vb['latency_verdict']} → {va['latency_verdict']}",
                    *_cmp(
                        vb["throughput_change_pct"], va["throughput_change_pct"], pct
                    ),
                    f"{vb['throughput_verdict']} → {va['throughput_verdict']}",
                    *_cmp(vb.get("implied_added_us"), va.get("implied_added_us"), ci),
                ]
            )
        out += [
            f"### 4b, {title}",
            "",
            *table(
                [
                    "Config",
                    "Added p50 µs before",
                    "after",
                    "Added p99 µs before",
                    "after",
                    "p99 verdict",
                    "Throughput Δ before",
                    "after",
                    "throughput verdict",
                    "Implied µs/call before",
                    "after",
                ],
                rows,
            ),
            "",
        ]
        attr_b = {r["component"]: r for r in tb.get("attribution", [])}
        attr_a = {r["component"]: r for r in ta.get("attribution", [])}
        rows = [
            [
                name,
                f"`{attr_b[name]['measured_as']}`",
                *_cmp(attr_b[name]["p50_us"], attr_a[name]["p50_us"], ci),
                *_cmp(attr_b[name]["implied_us"], attr_a[name]["implied_us"], ci),
            ]
            for name in attr_b
            if name in attr_a
        ]
        if rows:
            out += [
                f"#### Attribution, {title}",
                "",
                *table(
                    [
                        "Component",
                        "Measured as",
                        "p50 µs before",
                        "after",
                        "Implied µs/call before",
                        "after",
                    ],
                    rows,
                ),
                "",
            ]
    out += _fixed_cost(after)
    sb = before.get("overhead", {}).get("startup")
    sa = after.get("overhead", {}).get("startup")
    if sb and sa:
        rows = [
            [
                name,
                *_cmp(v["p50"], sa["ms"].get(name, {}).get("p50"), ms),
                *_cmp(v["p95"], sa["ms"].get(name, {}).get("p95"), ms),
            ]
            for name, v in sb["ms"].items()
        ]
        out += [
            "### Process start-up (ms)",
            "",
            *table(["Command", "p50 before", "after", "p95 before", "after"], rows),
            "",
        ]
    return out


REPRESENTATIVE_QUERY_MS = (1, 10, 100)
THROUGHPUT_TARGET = 0.02


def loss_pct(cost_us: float, query_us: float) -> float:
    """Throughput lost to a fixed cost per call: c / (query + c)."""
    return 100 * cost_us / (query_us + cost_us)


def _fixed_cost(results: dict) -> list[str]:
    """What the implied fixed cost per call means for the < 2% target."""
    tiers = results.get("overhead", {}).get("postgres", {}).get("tiers", {})
    sections = [(f"{n} {tier['label']}", tier) for n, tier in tiers.items()]
    kafka = results.get("overhead", {}).get("kafka")
    if kafka:
        sections.append(("Kafka `produce()`", kafka))
    rows = []
    for title, tier in sections:
        for config, v in tier["versus_base"].items():
            implied = v.get("implied_added_us")
            if implied is None or config in ("wrap-only", "capture-null"):
                continue
            cost = implied["estimate"]
            row = [title, config, ci(implied)]
            row.append(
                us(cost * (1 - THROUGHPUT_TARGET) / THROUGHPUT_TARGET)
                if cost > 0
                else "any"
            )
            row += [
                f"{loss_pct(cost, ms * 1000):.2f}%" for ms in REPRESENTATIVE_QUERY_MS
            ]
            rows.append(row)
    if not rows:
        return []
    return [
        "### The fixed cost per call and the < 2% throughput target (after)",
        "",
        (
            "From the after run's implied added µs per call (point estimate). A fixed cost "
            "c per call takes c / (q + c) of the throughput of a query whose own latency is "
            "q, so the loss is under 2% once q > 49 × c. The last columns apply each cost to "
            "representative query latencies."
        ),
        "",
        *table(
            [
                "Tier",
                "Config",
                "Implied µs/call [95% CI]",
                "Loss < 2% for queries slower than (µs)",
                *[f"Loss at a {ms} ms query" for ms in REPRESENTATIVE_QUERY_MS],
            ],
            rows,
        ),
        "",
    ]


COMPARISON_TITLE = "P5 Stage 5: parse cache"


def render_comparison(before: dict, after: dict, title: str = COMPARISON_TITLE) -> str:
    lines = [
        (f"# {title}, before (`{before['label']}`) and after (`{after['label']}`)"),
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
        *(
            _compare_rows_p51(before, after)
            if _is_p51(before) and _is_p51(after)
            else _compare_rows(before, after)
        ),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None) -> int:
    import json

    parser = argparse.ArgumentParser(description="Render P5 results JSON as markdown")
    parser.add_argument(
        "--compare", action="store_true", help="BEFORE.json AFTER.json OUT.md"
    )
    parser.add_argument(
        "--title", default=COMPARISON_TITLE, help="the comparison's title"
    )
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)

    def load(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    if args.compare:
        before, after, out = args.paths
        text = render_comparison(load(before), load(after), args.title)
    else:
        source, out = args.paths
        text = render(load(source))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
