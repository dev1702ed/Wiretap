"""Score the generated keys at scale. P5.1 (B3).

Each generated key is scored with score.py's own row functions, exactly as a
hand-written key is (`score_workload`). This module only groups the rows:

    method                    levels it has rows for
    DCP run-level             nodes, dataset edges, run edges, provenance
    dataset-level baseline    provenance
    OpenLineage core          dataset edges, provenance
    OpenLineage + dcp facet   provenance
    OpenLineage core (per process)   dataset edges, provenance    (P5.2)

and micro-averages them: precision = sum of hits / sum of found, recall = sum
of hits / sum of expected, over every row of every key in a group, per method
and level. The per-key values give the distribution (min, median, max).

Generated keys are always scored and reported apart from the hand-written ones,
never pooled with them.
"""

from statistics import median

METHODS = (
    "DCP run-level",
    "dataset-level baseline",
    "OpenLineage core",
    "OpenLineage + dcp facet",
    "OpenLineage core (per process)",  # P5.2: the bridge's `process` run scope
)
PER_PROCESS = "OpenLineage core (per process)"
LEVELS = ("nodes", "dataset edges", "run edges", "provenance")


def method_level(label: str) -> tuple[str, str]:
    """Which method and level a score row belongs to, from its label."""
    if label in ("nodes", "dataset edges", "run edges"):
        return "DCP run-level", label
    if label.endswith(" run-level"):
        return "DCP run-level", "provenance"
    if label.endswith(" dataset-level baseline"):
        return "dataset-level baseline", "provenance"
    if label == "openlineage (per process) dataset edges":
        return PER_PROCESS, "dataset edges"
    if label.startswith("openlineage (per process) provenance("):
        return PER_PROCESS, "provenance"
    if label == "openlineage dataset edges":
        return "OpenLineage core", "dataset edges"
    if label.startswith("openlineage + dcp facet provenance("):
        return "OpenLineage + dcp facet", "provenance"
    if label.startswith("openlineage provenance("):
        return "OpenLineage core", "provenance"
    raise ValueError(f"unknown score row: {label!r}")


def _ratio(hits: int, total: int) -> float | None:
    return hits / total if total else None


def all_rows(scored: dict) -> list[dict]:
    """Every score row of one key: DCP's graph, then the OpenLineage
    translation, then (P5.2, when scored) the per-process translation."""
    return (
        scored["dcp"]
        + scored["openlineage"]
        + scored.get("openlineage_per_process", [])
    )


def totals(scored: dict) -> dict[tuple[str, str], dict]:
    """(method, level) -> summed hits, found, expected, for one scored key."""
    out: dict = {}
    for row in all_rows(scored):
        cell = out.setdefault(
            method_level(row["label"]), {"hits": 0, "found": 0, "expected": 0}
        )
        for k in ("hits", "found", "expected"):
            cell[k] += row[k]
    return out


def _spread(values: list) -> dict | None:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"min": min(values), "median": median(values), "max": max(values)}


def aggregate(scored_keys: list[dict]) -> list[dict]:
    """Micro-averaged precision and recall per method and level, with the
    per-key distribution."""
    per_key = [totals(s) for s in scored_keys]
    out = []
    for method in METHODS:
        for level in LEVELS:
            cells = [t[(method, level)] for t in per_key if (method, level) in t]
            if not cells:
                continue
            hits = sum(c["hits"] for c in cells)
            found = sum(c["found"] for c in cells)
            expected = sum(c["expected"] for c in cells)
            out.append(
                {
                    "method": method,
                    "level": level,
                    "keys": len(cells),
                    "hits": hits,
                    "found": found,
                    "expected": expected,
                    "precision": _ratio(hits, found),
                    "recall": _ratio(hits, expected),
                    "per_key_precision": _spread(
                        [_ratio(c["hits"], c["found"]) for c in cells]
                    ),
                    "per_key_recall": _spread(
                        [_ratio(c["hits"], c["expected"]) for c in cells]
                    ),
                }
            )
    return out


def explain_extras(key: dict, scored: dict) -> dict:
    """Every item DCP's own graph found beyond the truth, checked against the
    generator's distractor reads. A provenance extra is explained if it is a
    table some job read as a distractor; a dataset-edge extra `a->b (job)` is
    explained if `job` read `a` as a distractor. Anything else is unexplained,
    and is a bug to investigate."""
    distractors = key.get("generated", {}).get("distractors", {})
    tables = {t for read in distractors.values() for t in read}
    extras = explained = 0
    unexplained = []
    for row in scored["dcp"]:
        method, level = method_level(row["label"])
        if method != "DCP run-level":
            continue
        for note in row["notes"]:
            if not note.startswith("+"):
                continue
            extras += 1
            item = note[1:]
            ok = False
            if level == "provenance":
                ok = item in tables
            elif level == "dataset edges" and "->" in item and " (" in item:
                source = item.split("->", 1)[0]
                job = item.rsplit(" (", 1)[1].rstrip(")")
                ok = source in distractors.get(job, [])
            if ok:
                explained += 1
            else:
                unexplained.append(f"{row['label']}: {note}")
    return {
        "extras": extras,
        "explained_by_distractors": explained,
        "unexplained": unexplained,
    }


def misses(scored: dict) -> list[str]:
    """Every expected item some method did not find: recall below 1.0."""
    return [
        f"{row['label']}: {note}"
        for row in all_rows(scored)
        for note in row["notes"]
        if note.startswith("-")
    ]


def split_jobs(events: list[dict]) -> list[str]:
    """Jobs whose events carry more than one trace_id. A consumer adopts the
    trace of each record it reads, so one that reads records from two producers
    joins two traces, and the P4 bridge, which maps one OpenLineage run per
    (trace, process), splits it into two runs."""
    traces: dict = {}
    for event in events:
        traces.setdefault(event["job"]["name"], set()).add(event["trace_id"])
    return sorted(job for job, ids in traces.items() if len(ids) > 1)


def explain_misses(key: dict, scored: dict, split: list[str]) -> dict:
    """Every expected item a method missed, checked against split runs. Only
    OpenLineage's core model (inputs x outputs per run) over the default
    trace-process run scope can lose an item to a split run; any other miss,
    or a core miss no split run explains, is a bug. That includes every miss
    of the per-process mapping (P5.2), which has no split runs."""
    writers: dict = {}
    for edge in key["dataset_edges"]:
        writers.setdefault(edge["to"], set()).add(edge["job"])
    split = set(split)
    total = explained = 0
    unexplained = []
    for row in all_rows(scored):
        method, level = method_level(row["label"])
        for note in row["notes"]:
            if not note.startswith("-"):
                continue
            total += 1
            item, ok = note[1:], False
            if (
                method == "OpenLineage core"
                and level == "dataset edges"
                and " (" in item
            ):
                ok = item.rsplit(" (", 1)[1].rstrip(")") in split
            elif method == "OpenLineage core" and level == "provenance":
                target = row["label"][len("openlineage provenance(") : -1]
                ok = bool(writers.get(target, set()) & split)
            if ok:
                explained += 1
            else:
                unexplained.append(f"{row['label']}: {note}")
    return {
        "misses": total,
        "explained_by_split_runs": explained,
        "unexplained": unexplained,
    }


def describe(key: dict) -> dict:
    """What a generated key contains, for the report."""
    kinds: dict = {}
    for p in key["processes"]:
        steps = p["steps"]
        if p.get("kind") == "notebook":
            kind = "notebook"
        elif any("consume" in s for s in steps):
            kind = "consumer"
        elif any("produce" in s for s in steps):
            kind = "script"
        else:
            kind = "multi-statement"
        kinds[kind] = kinds.get(kind, 0) + 1
    producers: dict = {}
    for p in key["processes"]:
        for s in p["steps"]:
            if "produce" in s:
                producers.setdefault(s["produce"], set()).add(p["job"])
    generated = key.get("generated", {})
    return {
        "workload": key["workload"],
        "seed": generated.get("seed"),
        "version": generated.get("version"),
        "jobs": len(key["processes"]),
        "kinds": kinds,
        "jobs_with_distractors": len(generated.get("distractors", {})),
        "fan_in_topics": sum(1 for jobs in producers.values() if len(jobs) > 1),
        "datasets": len(key["datasets"]),
        "provenance_entries": len(key["provenance"]),
    }


def is_seed(name: str) -> bool:
    """The ~30-job seeds scale_s01..s10, as opposed to scale_large."""
    return name.startswith("scale_s")


def summarize(
    keys: dict[str, dict], scored: dict[str, dict], split: dict[str, list]
) -> dict:
    """Aggregates for the seeds and for scale_large, kept apart, plus checks.
    `split` is each key's split_jobs(events)."""
    seeds = [n for n in scored if is_seed(n)]
    others = [n for n in scored if not is_seed(n)]
    return {
        "keys": [dict(describe(keys[n]), split_jobs=len(split[n])) for n in scored],
        "seeds": {"names": seeds, "aggregate": aggregate([scored[n] for n in seeds])},
        "others": {n: aggregate([scored[n]]) for n in others},
        "extras": {n: explain_extras(keys[n], scored[n]) for n in scored},
        "misses": {n: explain_misses(keys[n], scored[n], split[n]) for n in scored},
        "per_process_misses": {n: per_process_misses(scored[n]) for n in scored},
    }


def per_process_misses(scored: dict) -> list[str]:
    """Every expected item the per-process mapping (P5.2) missed. Expected:
    none. A per-process run is never split, so none is explained."""
    return [
        f"{row['label']}: {note}"
        for row in scored.get("openlineage_per_process", [])
        for note in row["notes"]
        if note.startswith("-")
    ]


# --- P5.2 (B4): the stress set -------------------------------------------------
#
# The stress keys (generate.STRESS_KEYS, in stress/) exercise DCP's two known
# failure modes. They are summarised here, apart from every other key, and
# every miss is checked against a named cause, mechanically.

CAUSE_SPLIT = "split run"
CAUSE_MULTI = (
    "multi-record consumer: earlier record's parent dropped "
    "(job-level keeps the latest read per dataset)"
)
CAUSE_STORE = "store-mediated: Postgres read carries no parents"
CAUSES = (CAUSE_MULTI, CAUSE_STORE, CAUSE_SPLIT)
# The methods whose graph is DCP's own events: DCP, and the facet reader.
DCP_GRAPH_METHODS = ("DCP run-level", "OpenLineage + dcp facet")


def _provenance_label_target(label: str) -> str:
    """The dataset alias a provenance row is about, from its label."""
    return label[label.index("(") + 1 : label.rindex(")")]


def predicted_losses(key: dict) -> dict[str, dict[str, set]]:
    """written dataset -> {cause: the upstream items DCP is predicted to lose}.

    Derived from the key alone (its truth and its `generated` block), never
    from DCP's output:

    - a multi-record consumer's write: DCP parents it to the latest read of
      the topic only, so it loses every input of the earlier records'
      producers that the last record's producer did not also use;
    - a store-read job's write: the Postgres read of the table carries no
      parents, so DCP loses everything upstream of the table.
    """
    g = key.get("generated", {})
    prov = {p["dataset"]: set(p["upstream"]) for p in key["provenance"]}
    writer = {e["to"]: e["job"] for e in key["dataset_edges"]}
    producer: dict[str, tuple[str, str]] = {}  # record -> (job, topic)
    for process in key["processes"]:
        for step in process["steps"]:
            if "produce" in step:
                producer[step["record"]] = (process["job"], step["produce"])
    used: dict[tuple[str, str], set] = {}  # (job, topic) -> the job's inputs to it
    for edge in key["dataset_edges"]:
        used.setdefault((edge["job"], edge["to"]), set()).add(edge["from"])

    def record_inputs(record: str) -> set:
        found = set(used.get(producer[record], set()))
        for upstream in list(found):
            found |= prov.get(upstream, set())
        return found

    out: dict[str, dict[str, set]] = {}
    for dataset, job in writer.items():
        if job in g.get("multi_record", {}):
            records = g["multi_record"][job]
            earlier = set().union(*(record_inputs(r) for r in records[:-1]))
            out.setdefault(dataset, {})[CAUSE_MULTI] = earlier - record_inputs(
                records[-1]
            )
        if job in g.get("store_reads", {}):
            lost = set().union(*(prov.get(t, set()) for t in g["store_reads"][job]))
            out.setdefault(dataset, {})[CAUSE_STORE] = lost
    return out


def split_losses(key: dict, split: list[str]) -> dict[str, set]:
    """written dataset -> the upstream items a split run can cost OpenLineage's
    core model (trace-process mapping) on it.

    A split job J loses the link from an input in one of its runs to an output
    in another, so reachability can lose anything upstream of a dataset Y that
    J writes, and so of every dataset downstream of Y. For a dataset D, every Y
    in D and its truth provenance written by a split job contributes Y's
    provenance. P5.1's rule (explain_misses) looks at D's own writer only; on
    the stress set a store read can put the split job further upstream.
    """
    split = set(split)
    prov = {p["dataset"]: set(p["upstream"]) for p in key["provenance"]}
    writers: dict[str, set] = {}
    for edge in key["dataset_edges"]:
        writers.setdefault(edge["to"], set()).add(edge["job"])
    out = {}
    for dataset, upstream in prov.items():
        lost: set = set()
        for y in {dataset} | upstream:
            if writers.get(y, set()) & split:
                lost |= prov.get(y, set())
        out[dataset] = lost
    return out


def explain_stress_misses(key: dict, scored: dict, split: list[str]) -> dict:
    """Every expected item any method missed on a stress key, with its cause.

    - OpenLineage core (trace-process): a split run. A dataset edge `a->b
      (job)` if `job` is split; a provenance item if `split_losses` names it;
    - DCP run-level and OpenLineage + dcp facet, provenance: the cause
      `predicted_losses` names for that dataset and item;
    - anything else, including any miss of the dataset-level baseline or of
      OpenLineage core per process, is unexplained: a bug to investigate.
    """
    predicted = predicted_losses(key)
    by_split = split_losses(key, split)
    total = 0
    by_method: dict[str, dict[str, int]] = {}
    unexplained = []
    for row in all_rows(scored):
        method, level = method_level(row["label"])
        for note in row["notes"]:
            if not note.startswith("-"):
                continue
            total += 1
            item, cause = note[1:], None
            if (
                method == "OpenLineage core"
                and level == "dataset edges"
                and " (" in item
            ):
                if item.rsplit(" (", 1)[1].rstrip(")") in split:
                    cause = CAUSE_SPLIT
            elif method == "OpenLineage core" and level == "provenance":
                if item in by_split.get(_provenance_label_target(row["label"]), set()):
                    cause = CAUSE_SPLIT
            elif method in DCP_GRAPH_METHODS and level == "provenance":
                losses = predicted.get(_provenance_label_target(row["label"]), {})
                cause = next((c for c in CAUSES if item in losses.get(c, set())), None)
            if cause is None:
                unexplained.append(f"{row['label']}: {note}")
                continue
            cell = by_method.setdefault(method, dict.fromkeys(CAUSES, 0))
            cell[cause] += 1
    return {"misses": total, "by_method": by_method, "unexplained": unexplained}


def describe_stress(key: dict, split: list[str]) -> dict:
    """What a stress key contains, for the report."""
    g = key.get("generated", {})
    store = g.get("store_reads", {})
    writer = {e["to"]: e["job"] for e in key["dataset_edges"]}
    chain2 = sum(
        1 for tables in store.values() if any(writer.get(t) in store for t in tables)
    )
    base = describe(key)
    kinds = dict(base["kinds"])
    # describe() counts a store-read job (SELECT, then INSERT ... VALUES) as
    # multi-statement; name it.
    kinds["multi-statement"] = kinds.get("multi-statement", 0) - len(store)
    kinds = {k: n for k, n in kinds.items() if n}
    kinds["store-read"] = len(store)
    return dict(
        base,
        kinds=kinds,
        parameters={
            k: g.get("parameters", {}).get(k)
            for k in ("p_multi_record", "p_store_read")
        },
        multi_record_consumers=len(g.get("multi_record", {})),
        records_consumed_by_them=sum(
            len(r) for r in g.get("multi_record", {}).values()
        ),
        store_read_jobs=len(store),
        store_chains_of_two=chain2,
        split_jobs=len(split),
    )


def is_stress_seed(name: str) -> bool:
    """The ~30-job stress keys stress_s01..s05, as opposed to stress_large."""
    return name.startswith("stress_s")


def summarize_stress(
    keys: dict[str, dict], scored: dict[str, dict], split: dict[str, list]
) -> dict:
    """The stress group, reported on its own: the seeds micro-averaged,
    stress_large on its own, every extra and miss explained, and how many
    misses each cause produced per key and method."""
    seeds = [n for n in scored if is_stress_seed(n)]
    others = [n for n in scored if not is_stress_seed(n)]
    return {
        "keys": [describe_stress(keys[n], split[n]) for n in scored],
        "seeds": {"names": seeds, "aggregate": aggregate([scored[n] for n in seeds])},
        "others": {n: aggregate([scored[n]]) for n in others},
        "extras": {n: explain_extras(keys[n], scored[n]) for n in scored},
        "misses": {
            n: explain_stress_misses(keys[n], scored[n], split[n]) for n in scored
        },
    }
