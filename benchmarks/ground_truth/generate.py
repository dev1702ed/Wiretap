"""Generate ground-truth workloads at scale, with known truth. P5.1 (B2); P5.2 (B1).

    python benchmarks/ground_truth/generate.py --write    regenerate the committed keys
    python benchmarks/ground_truth/generate.py --check    verify them, byte for byte

The hand-written keys are four small workloads. This generator builds larger
ones from a seed and parameters, in the same answer-key format, and derives
the expected graph FROM ITS OWN CONSTRUCTION: it decides what every generated
program reads, computes and writes, so it knows which inputs each written value
actually came from. It imports nothing that computes lineage (no `dcp`, no
`backend`, no bridge): pure standard-library Python.

What a workload contains (`plan`):

- source tables `gen_src_NN (id int, v int)` with seeded rows;
- script jobs: read tables, then produce records to topics and sometimes
  insert one row (`INSERT ... VALUES`) into a table;
- consumer jobs: consume specific named records, then insert one row;
- multi-statement jobs: several `INSERT ... SELECT` statements;
- notebook jobs: read tables, then insert one row;
- fan-in topics: few topics, many producers;
- distractor reads (probability `p_distractor` per job): the job reads a table
  whose values it then does not use in anything it writes.

Ground truth is real data flow (`derive`). A script's records and its inserted
row carry the sum of `v` over every row of the tables it USES (computed here,
from the seeded rows, and written into the SQL text and the record's name); a
consumer's inserted row carries the sum of the records it consumed. The
expected graph credits only those inputs. A distractor read feeds nothing, so
DCP's job-level parenting, which parents an `INSERT ... VALUES` or a produce to
every earlier read of the job, over-approximates there, and its measured
precision drops below 1.0. That is the point: it measures a known limitation.
Never configure the generator to avoid it.

With its defaults (P5.1), a job never reads a table another generated job
wrote, and a consumer never reads two records from one topic. Those are DCP's
two known failure modes, and P5.2 adds them as two job kinds, each behind a
parameter that DEFAULTS TO OFF (`STRESS_DEFAULTS`):

- `p_multi_record`: each consumer, with this probability, becomes a
  multi-record consumer: it consumes 2-3 named records from ONE topic, each
  from a different producer (so different traces), and writes the sum of all
  of them. Truth: the topic and every consumed record's producer's inputs.
  DCP's job-level parenting keeps only the latest read per dataset, so it
  credits the last record's producer only.
- `p_store_read`: each non-script job, with this probability, becomes a
  store-read job: it reads a table an EARLIER job of the workload wrote (a
  store-mediated read; with probability 1/2 one written by another store-read
  job, giving chains of length 2, never longer), then inserts one row computed
  from it. Truth is transitive through the store: the table read and
  everything upstream of that table's writer. Postgres reads carry no parents
  in DCP, so DCP stops at the table.

Both kinds keep distractor reads. Keys generated with either parameter on are
the stress set (`STRESS_KEYS`, in stress/, reported apart from every other
key) and record GENERATOR_VERSION ("1.1") and their store reads and
multi-record consumers in the `generated` block. With both parameters off the
generator draws exactly the random numbers it drew in 1.0 and writes exactly
the same bytes: every committed 1.0 key (`KEYS`) regenerates byte for byte and
still records VERSION ("1.0").

The keys are generated: `P5.md` §2 rule 3 ("answer keys are read-only")
applies to their seeds and the generator version, never to hand edits. Each key
carries a `generated` block saying so.
"""

import argparse
import json
import pathlib
import random
import sys

GENERATOR = "benchmarks/ground_truth/generate.py"
# The version a key records. A key generated with both P5.2 parameters off is
# byte-identical to generator 1.0's output, so it records VERSION; a key with
# either on records GENERATOR_VERSION, this generator's version.
VERSION = "1.0"
GENERATOR_VERSION = "1.1"
GENERATED = pathlib.Path(__file__).resolve().parent / "generated"
STRESS = pathlib.Path(__file__).resolve().parent / "stress"
PG_NAMESPACE = "postgres://localhost:5432"
KAFKA_NAMESPACE = "kafka://localhost:9092"
DATABASE = "dcp.public"
COLUMNS = "id int, v int"

DEFAULTS = {
    "jobs": 30,
    "p_distractor": 0.3,
    "rows_per_table": 3,
    "mix": {"script": 0.4, "consumer": 0.25, "multi": 0.25, "notebook": 0.1},
    "p_script_insert": 0.5,
}

# P5.2: the failure-mode job kinds. Off by default; an off parameter is never
# recorded, so it cannot change a default key's bytes.
STRESS_DEFAULTS = {"p_multi_record": 0.0, "p_store_read": 0.0}
# A store-read job reads a table another store-read job wrote with this
# probability, when one exists (chains of length 2).
P_STORE_CHAIN = 0.5
MAX_STORE_CHAIN = 2

# The committed keys: name -> (seed, overrides). Fixed: change a seed or the
# VERSION, never a committed file.
KEYS = {f"scale_s{n:02d}": (n, {}) for n in range(1, 11)}
KEYS["scale_large"] = (100, {"jobs": 100})

# The P5.2 stress set (B3), in stress/: fixed before any of them was scored.
STRESS_PARAMETERS = {"p_multi_record": 0.15, "p_store_read": 0.25}
STRESS_KEYS = {
    f"stress_s{n:02d}": (200 + n, dict(STRESS_PARAMETERS)) for n in range(1, 6)
}
STRESS_KEYS["stress_large"] = (300, dict(STRESS_PARAMETERS, jobs=100))


def parameters(**overrides) -> dict:
    params = json.loads(json.dumps(DEFAULTS))
    params.update(overrides)
    for name, off in STRESS_DEFAULTS.items():
        if params.get(name, off) == off:
            params.pop(name, None)  # off: not recorded, so the 1.0 bytes stay
    return params


def stress_on(params: dict) -> bool:
    return any(params.get(name, off) != off for name, off in STRESS_DEFAULTS.items())


def _counts(jobs: int, mix: dict) -> dict:
    counts = {
        kind: round(jobs * share) for kind, share in mix.items() if kind != "script"
    }
    counts["notebook"] = max(1, counts.get("notebook", 0)) if mix.get("notebook") else 0
    counts["script"] = max(1, jobs - sum(counts.values()))
    return counts


def plan(seed: int, params: dict) -> dict:
    """Every random choice, made once: the tables, rows and jobs (in run order)."""
    rng = random.Random(seed)
    jobs = params["jobs"]
    n_sources = max(4, jobs // 3)
    n_topics = max(2, jobs // 10)
    sources = [f"gen_src_{i:02d}" for i in range(1, n_sources + 1)]
    rows = {
        s: [[i, rng.randint(1, 99)] for i in range(1, params["rows_per_table"] + 1)]
        for s in sources
    }
    topics = [f"gen_topic_{i:02d}" for i in range(1, n_topics + 1)]
    counts = _counts(jobs, params["mix"])
    kinds = ["script"] * counts["script"] + ["multi"] * counts["multi"]
    kinds += ["notebook"] * counts["notebook"]
    rng.shuffle(kinds)
    kinds += ["consumer"] * counts["consumer"]  # consumers run after every producer

    outputs = iter(f"gen_out_{i:03d}" for i in range(1, 10_000))
    records: list[dict] = []  # {"id", "topic", "producer"} in production order
    consumed: set[str] = set()
    planned = []
    p_multi = params.get("p_multi_record", STRESS_DEFAULTS["p_multi_record"])
    p_store = params.get("p_store_read", STRESS_DEFAULTS["p_store_read"])
    # P5.2: every table an earlier job wrote -> its store chain length (0: its
    # writer read no written table). Tracked always; drawn from only when
    # p_store > 0, so with both parameters off no random number changes.
    written: dict[str, int] = {}

    def distractor(exclude) -> str | None:
        if rng.random() >= params["p_distractor"]:
            return None
        return rng.choice([s for s in sources if s not in exclude])

    def store_table() -> str | None:
        """A table an earlier job wrote, for a store-read job, or None."""
        eligible = [t for t, n in written.items() if n < MAX_STORE_CHAIN]
        if not eligible:
            return None
        chained = [t for t in eligible if written[t] > 0]
        direct = [t for t in eligible if written[t] == 0]
        if chained and (not direct or rng.random() < P_STORE_CHAIN):
            return rng.choice(chained)
        return rng.choice(direct)

    def multi_records() -> list[dict]:
        """2-3 records from one topic, each from a different producer, or []."""
        fresh = [r for r in records if r["id"] not in consumed]
        pool = fresh if len({r["producer"] for r in fresh}) >= 2 else records
        by_topic: dict[str, dict[str, list]] = {}
        for record in pool:
            by_topic.setdefault(record["topic"], {}).setdefault(
                record["producer"], []
            ).append(record)
        topics_ok = sorted(
            t for t, producers in by_topic.items() if len(producers) >= 2
        )
        if not topics_ok:
            return []
        producers = by_topic[rng.choice(topics_ok)]
        chosen = rng.sample(sorted(producers), min(rng.randint(2, 3), len(producers)))
        picked = [rng.choice(producers[p]) for p in chosen]
        rng.shuffle(picked)  # the consumption order; DCP keeps the last
        return picked

    for index, kind in enumerate(kinds, start=1):
        if p_store > 0 and kind != "script" and rng.random() < p_store:
            table = store_table()
            if table is not None:
                job = f"gen_job_{index:03d}.py"
                extra = distractor([])
                reads = [table] + ([extra] if extra else [])
                rng.shuffle(reads)
                out = next(outputs)
                written[out] = written[table] + 1
                planned.append(
                    {"kind": "store", "job": job, "reads": reads, "used": [table],
                     "out": out}
                )  # fmt: skip
                continue
        if kind in ("script", "notebook"):
            job = f"gen_{'nb' if kind == 'notebook' else 'job'}_{index:03d}"
            job += ".ipynb" if kind == "notebook" else ".py"
            used = rng.sample(sources, rng.randint(1, 2))
            extra = distractor(used)
            reads = used + ([extra] if extra else [])
            rng.shuffle(reads)
            outs = []
            if kind == "script":
                for _ in range(rng.randint(1, 2)):
                    record = {
                        "id": f"r{len(records) + 1:03d}",
                        "topic": rng.choice(topics),
                    }
                    record["producer"] = job
                    records.append(record)
                    outs.append(["produce", record["topic"], record["id"]])
            if kind == "notebook" or rng.random() < params["p_script_insert"]:
                outs.append(["insert", next(outputs)])
                written[outs[-1][1]] = 0
            planned.append(
                {
                    "kind": kind,
                    "job": job,
                    "reads": reads,
                    "used": used,
                    "outputs": outs,
                }
            )
        elif kind == "multi":
            job = f"gen_job_{index:03d}.py"
            steps = []
            for _ in range(rng.randint(2, 3)):
                steps.append(
                    [
                        "insert_select",
                        next(outputs),
                        rng.sample(sources, rng.randint(1, 2)),
                    ]
                )
                written[steps[-1][1]] = 0
            extra = distractor({t for step in steps for t in step[2]})
            if extra:
                steps.insert(rng.randint(0, len(steps)), ["read", extra])
            planned.append({"kind": "multi", "job": job, "steps": steps})
        else:  # consumer
            job = f"gen_job_{index:03d}.py"
            if not records:
                raise ValueError(
                    "a consumer job needs a produced record; add script jobs"
                )
            chosen = []
            if p_multi > 0 and rng.random() < p_multi:
                chosen = multi_records()  # P5.2: several records, one topic
            if not chosen:
                fresh = [r for r in records if r["id"] not in consumed]
                pool = fresh or records
                want, topics_taken = rng.randint(1, 2), set()
                for record in rng.sample(pool, len(pool)):
                    if record["topic"] not in topics_taken:  # one record per topic
                        chosen.append(record)
                        topics_taken.add(record["topic"])
                    if len(chosen) == want:
                        break
            consumed.update(r["id"] for r in chosen)
            steps = [["consume", r["topic"], r["id"]] for r in chosen]
            extra = distractor([])
            if extra:
                steps.insert(rng.randint(0, len(steps)), ["read", extra])
            planned.append(
                {"kind": "consumer", "job": job, "steps": steps, "out": next(outputs)}
            )
            written[planned[-1]["out"]] = 0
    return {"rows": rows, "jobs": planned}


def _select(table: str) -> str:
    return f"SELECT id, v FROM {table}"


def _insert_select(out: str, tables: list[str]) -> str:
    if len(tables) == 1:
        return f"INSERT INTO {out} SELECT id, v FROM {tables[0]}"
    a, b = tables
    return f"INSERT INTO {out} SELECT a.id, a.v + b.v FROM {a} AS a JOIN {b} AS b ON b.id = a.id"


def derive(name: str, planned: dict, generated: dict | None = None) -> dict:
    """The answer key: the programs' steps, and the truth that follows from them."""
    rows = planned["rows"]
    processes, edges, run_edges = [], set(), set()
    feeds: dict[str, set] = {}  # written dataset -> the datasets its data came from
    record_name: dict[str, str] = {}
    record_from: dict[str, tuple[str, set]] = {}  # record id -> (producer, its inputs)
    touched: set[str] = set()
    topics_used: set[str] = set()
    distractors: dict[str, list] = {}
    # P5.2: what every table holds once the jobs so far have run (the seeded
    # rows, then each write), so a store-read job's value is computed from
    # the rows it really reads. Each written table is written exactly once.
    contents: dict[str, list] = {t: [list(r) for r in rs] for t, rs in rows.items()}
    store_reads: dict[str, list] = {}  # job -> the written tables it read
    multi_record: dict[str, list] = {}  # job -> its records, in consumption order

    def payload(tables) -> int:
        return sum(v for t in tables for _id, v in contents[t])

    def selected(tables) -> list[list]:
        """The rows `_insert_select(out, tables)` inserts."""
        if len(tables) == 1:
            return [list(r) for r in contents[tables[0]]]
        a, b = tables
        b_rows = {i: v for i, v in contents[b]}
        return [[i, v + b_rows[i]] for i, v in contents[a] if i in b_rows]

    def credit(target: str, sources: set) -> None:
        feeds.setdefault(target, set()).update(sources)

    for job in planned["jobs"]:
        kind, name_ = job["kind"], job["job"]
        steps = []
        if kind in ("script", "notebook"):
            used = set(job["used"])
            touched.update(job["reads"])
            extra = [t for t in job["reads"] if t not in used]
            if extra:
                distractors[name_] = extra
            steps += [{"sql": _select(t)} for t in job["reads"]]
            value = payload(job["used"])
            for out in job["outputs"]:
                if out[0] == "produce":
                    _, topic, rid = out
                    record = f"{rid}={value}"
                    record_name[rid] = record
                    record_from[rid] = (name_, used)
                    steps.append({"produce": topic, "record": record})
                    topics_used.add(topic)
                    edges.update((u, topic, name_) for u in used)
                    credit(topic, used)
                else:
                    _, table = out
                    touched.add(table)
                    steps.append({"sql": f"INSERT INTO {table} VALUES (1, {value})"})
                    contents[table] = [[1, value]]
                    edges.update((u, table, name_) for u in used)
                    credit(table, used)
        elif kind == "store":  # P5.2: reads a table an earlier job wrote
            (table,) = job["used"]
            touched.update(job["reads"])
            extra = [t for t in job["reads"] if t != table]
            if extra:
                distractors[name_] = extra
            store_reads[name_] = [table]
            steps += [{"sql": _select(t)} for t in job["reads"]]
            value = payload([table])
            out = job["out"]
            touched.add(out)
            steps.append({"sql": f"INSERT INTO {out} VALUES (1, {value})"})
            contents[out] = [[1, value]]
            edges.add((table, out, name_))
            # Transitive through the store: the table, and everything its
            # writer's data came from.
            credit(out, {table} | feeds.get(table, set()))
        elif kind == "multi":
            for step in job["steps"]:
                if step[0] == "read":
                    touched.add(step[1])
                    distractors.setdefault(name_, []).append(step[1])
                    steps.append({"sql": _select(step[1])})
                else:
                    _, out, tables = step
                    touched.update([out, *tables])
                    steps.append({"sql": _insert_select(out, tables)})
                    contents[out] = selected(tables)
                    edges.update((t, out, name_) for t in tables)
                    credit(out, set(tables))
        else:  # consumer
            consumed_value, inputs = 0, set()
            topics_read = [step[1] for step in job["steps"] if step[0] == "consume"]
            if len(topics_read) > len(set(topics_read)):  # P5.2: several from one topic
                multi_record[name_] = [
                    record_name[step[2]]
                    for step in job["steps"]
                    if step[0] == "consume"
                ]
            for step in job["steps"]:
                if step[0] == "read":
                    touched.add(step[1])
                    distractors.setdefault(name_, []).append(step[1])
                    steps.append({"sql": _select(step[1])})
                    continue
                _, topic, rid = step
                record = record_name[rid]
                producer, producer_inputs = record_from[rid]
                consumed_value += int(record.split("=", 1)[1])
                steps.append({"consume": topic, "record": record})
                run_edges.add((producer, name_, topic))
                edges.add((topic, job["out"], name_))
                # The row this consumer writes came from this record, and the
                # record from exactly what its producer used.
                inputs.update({topic} | producer_inputs)
            touched.add(job["out"])
            steps.append(
                {"sql": f"INSERT INTO {job['out']} VALUES (1, {consumed_value})"}
            )
            contents[job["out"]] = [[1, consumed_value]]
            credit(job["out"], inputs)
        processes.append({"job": name_, "kind": "notebook" if kind == "notebook" else "script",
                          "steps": steps})  # fmt: skip

    tables = sorted(touched)
    topics = sorted(topics_used)
    datasets = {
        t: {"namespace": PG_NAMESPACE, "name": f"{DATABASE}.{t}"} for t in tables
    }
    datasets.update({t: {"namespace": KAFKA_NAMESPACE, "name": t} for t in topics})
    key = {"workload": name}
    key["description"] = (
        "GENERATED, not hand-written, by benchmarks/ground_truth/generate.py: script, "
        "consumer, multi-statement and notebook jobs over seeded tables and fan-in topics, "
        "with distractor reads. The truth credits only the inputs each written value "
        "came from. Never edit by hand: regenerate from the seed."
    )
    if store_reads or multi_record:  # P5.2; never in a 1.0 key
        key["description"] += (
            " STRESS SET (P5.2): also multi-record consumers and store-mediated reads, "
            "DCP's two known failure modes; the truth is transitive through the store."
        )
    if generated is not None:
        key["generated"] = dict(generated, distractors=distractors)
        if store_reads or multi_record:
            key["generated"]["store_reads"] = store_reads
            key["generated"]["multi_record"] = multi_record
    key["processes"] = processes
    key["datasets"] = datasets
    key["dataset_edges"] = [{"from": a, "to": b, "job": j} for a, b, j in sorted(edges)]
    key["run_edges"] = [
        {"from_job": a, "to_job": b, "via": v} for a, b, v in sorted(run_edges)
    ]
    key["provenance"] = [
        {"dataset": d, "upstream": sorted(feeds[d])} for d in sorted(feeds)
    ]
    key["tables"] = {t: {"columns": COLUMNS, "rows": rows.get(t, [])} for t in tables}
    key["topics"] = topics
    return key


def generate(name: str, seed: int, **overrides) -> dict:
    params = parameters(**overrides)
    generated = {
        "generator": GENERATOR,
        "version": GENERATOR_VERSION if stress_on(params) else VERSION,
        "seed": seed,
        "parameters": params,
        "hand_written": False,
    }
    return derive(name, plan(seed, params), generated)


def dumps(key: dict) -> str:
    """The committed form: stable key order, LF line endings, one trailing newline."""
    return json.dumps(key, indent=1) + "\n"


def committed() -> dict[str, str]:
    """name -> the exact text the committed key must have: the 1.0 keys, then
    the P5.2 stress set."""
    configured = {**KEYS, **STRESS_KEYS}
    return {
        name: dumps(generate(name, seed, **o)) for name, (seed, o) in configured.items()
    }


def path_for(name: str) -> pathlib.Path:
    """generated/<name>.json, or stress/<name>.json for the P5.2 stress set."""
    return (STRESS if name in STRESS_KEYS else GENERATED) / f"{name}.json"


def load_generated(name: str) -> dict:
    return json.loads(path_for(name).read_text(encoding="utf-8"))


def generated_names() -> list[str]:
    return sorted(p.stem for p in GENERATED.glob("*.json"))


def stress_names() -> list[str]:
    """The committed P5.2 stress keys (stress/), never pooled with the others."""
    return sorted(p.stem for p in STRESS.glob("*.json"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--write", action="store_true", help="regenerate the committed keys"
    )
    group.add_argument("--check", action="store_true", help="verify them byte for byte")
    args = parser.parse_args(argv)
    texts = committed()
    if args.write:
        GENERATED.mkdir(exist_ok=True)
        STRESS.mkdir(exist_ok=True)
        for name, text in texts.items():
            with open(path_for(name), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print(f"wrote {path_for(name)}")
        return 0
    stale = [n for n, text in texts.items() if not path_for(n).exists()
             or path_for(n).read_bytes() != text.encode("utf-8")]  # fmt: skip
    for name in stale:
        print(f"{name}: differs from its seed's output", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
