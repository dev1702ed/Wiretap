# Local tasks: close the owner's runs (Claude Code, owner's machine)

You are Claude Code in the owner's VS Code, on Windows (PowerShell), in the DCP repo
(`dev1702ed/Wiretap`). v1 is closed. This file finishes the owner's runbook steps
that need edits and commits. Read `docs/RUNBOOK.md` and `docs/results/V1.md` first.

The sheet has three parts:

| Part | Who | When |
|---|---|---|
| A | **You** | Now |
| B | **The owner, by hand, with VS Code closed** | After A |
| C | **You**, in the new clone | After B |

**Stop at the end of each part** and report what you did.

## Rules

1. **Never type a result number by hand.** Copy a table cell verbatim from a record,
   or link to it. Prefer links.
2. **Never edit a generated record:** `docs/results/P5-*.md`,
   `docs/results/demo-local.md`, or `docs/paper/evidence.md` (which is regenerated
   only by `benchmarks/evidence.py`), nor the README block between the
   `evidence:summary` markers.
3. **Never run `benchmarks/run.py` from this session.** An open editor interferes
   with the overhead measurement. Benchmark runs are the owner's job (Part B).
4. **Git:**
   - run `git pull` before editing;
   - check `git status --short` before committing;
   - stage with **exact paths only**, never `git add -A`;
   - **never commit `examples/dark-zone/run-demo.sh` or `examples/marquez/init-db.sh`**.
     They show as modified from file-mode or line-ending noise. If they appear,
     run `git config core.filemode false` and then
     `git checkout -- <those two files>`;
   - never force-push. If you need to undo something, revert.
5. **Committed files mention only DCP.** No other research directions.
6. If anything doesn't match what this file expects, **stop and report**. Don't
   improvise.

---

## Part A — now, in the current repo

### A1. Pre-flight

```powershell
git pull
git status --short
```

Expect a clean tree, apart from the two noisy `.sh` files (rule 4).

### A2. The demo record (runbook step 7)

1. Check that `docs/results/demo-local.md` exists. **If it doesn't,** stop and tell
   the owner that step 7 must be run again. That's
   `./examples/dark-zone/time-demo.ps1`, after
   `docker compose -f examples/marquez/docker-compose.yml down`.
2. Read it, and report **verbatim**, for both the cold and the warm row: the seconds,
   *under 5 minutes*, the demo exit code, and *both jobs linked through
   `enriched_orders` (Marquez API)*.
3. **Commit the record whatever it shows.** It's a record, not a pass/fail gate.
4. Clean up the demo stack:
   `docker compose -f examples/dark-zone/docker-compose.yml down -v`.

### A3. The demo item in the definition of done

In `ROADMAP.md` (the definition-of-done list) and `docs/results/V1.md` (the
definition-of-done table), update the item "`docker-compose up` gives a lineage
graph in Marquez in under 5 minutes", based **only** on the record:

| Record shows | Status to write |
|---|---|
| Cold run under 5 minutes, linked yes, exit 0 | **Met.** Tick it in ROADMAP |
| Only the warm run under 5 minutes | **Met warm, not cold.** Leave unticked, and say what a first-time user experiences |
| Neither | **Not met.** Leave unticked |
| Linked no, or a non-zero exit | **Not met.** Leave unticked, and quote the failing cell |

In every case, link `docs/results/demo-local.md`.

### A4. Interim wording for the overhead claim

The owner's `local-final` run is committed (`docs/results/P5-local-final.md`). The
docs still say the owner's final run is "pending", and `V1.md` says the < 1 ms p99
was met "on every T and L tier in the sandbox".

Make these statements accurate **without numbers**: in the `ROADMAP.md`
definition-of-done bullet and P5.1 row, and in `V1.md`'s overhead row.

- **Sandbox:** < 1 ms p99 added was met on every T and L tier (link
  `P5-p51-after-final.md`).
- **Owner's machine** (`local-final`, link): met in every cell **except four
  write-tier cells**, three with the `http` sink and one with `file`, which are
  **inconclusive** (their 95% CI spans 1 ms). Link evidence claim C6.
- That run **deviated from runbook step 3**: OneDrive was syncing and the editor
  was open. **One compliant rerun, `local-final-2`, is pending.** The wording is
  updated once more after it, whatever it shows.
- Throughput < 2% stays **not met**.

### A5. Index of the owner's runs: `docs/results/local-runs.md` (new, hand-written, no numbers)

A short page listing every owner run, each with: its label, a link to its record,
its date (from the record's environment table), what it was for, and its
**protocol status**.

| Label | Status |
|---|---|
| `local` | P5; compliant |
| `local-final` | Deviated from step 3, with the deviation described as above. Kept, and disclosed |
| `local-final-2` | Pending. To be run once, with full step-3 preparation, and reported whatever it shows |

Add the rule in one line: **one rerun, justified by a documented deviation before
it was run; both records kept.** Link this page from `V1.md`.

### A6. Commit and push

```powershell
git status --short
git add docs/results/demo-local.md docs/results/local-runs.md ROADMAP.md docs/results/V1.md docs/tasks/LOCAL-final.md
git commit -m "Owner runs: demo record, interim overhead wording, runs index"
git push
```

Then report the status of the commit, and **stop**. Tell the owner to do Part B.

---

## Part B — the owner, by hand (VS Code **closed**)

Claude Code doesn't do this part. It's here so the owner has it in one place.

1. **Close VS Code.** Plug the laptop in. Open a **standalone** PowerShell.
2. Make a fresh clone outside OneDrive. (A moved `.venv` breaks, so clone rather
   than move.)
   ```powershell
   git clone https://github.com/dev1702ed/Wiretap.git C:\dev\dcp
   Copy-Item "$env:USERPROFILE\OneDrive\Desktop\DCP\dcp\CLAUDE.md" C:\dev\dcp\CLAUDE.md
   cd C:\dev\dcp
   git config core.filemode false
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```
   `CLAUDE.md` is gitignored, so the clone doesn't get it. The copy line carries it
   over.
3. Do runbook **steps 1–3** in this clone: pinned install, kernel, unit tests,
   machine preparation, `docker start dcp-postgres dcp-kafka`.
4. Run the rerun, **once**:
   ```powershell
   $env:DCP_PG_PASSWORD = "dcp"
   $env:DCP_BENCH_KAFKA_VERSION = "3.8.0"
   python benchmarks/run.py --label local-final-2
   ```
   Don't use the machine during the run (about 30 minutes).
5. From now on, open VS Code on **`C:\dev\dcp`**, and give Claude Code Part C.

---

## Part C — after the rerun, in `C:\dev\dcp`

### C1. Validate `local-final-2`

Open `docs/results/P5-local-final-2.md` and check each of these:

- **Working tree dirty:** False
- every pin matches
- **every stage `ran`**
- every live row agrees with replay
- every *Unexplained* cell is `none` or `0`

**If any check fails,** stop and report. **Do not rerun** (rule 3; the
one-rerun rule).

Then report **verbatim** the < 1 ms p99 verdict for **every** T and L cell, and
**list every cell that isn't `met`.** Put the four cells that were inconclusive in
`local-final` side by side, copied from both records.

### C2. Runbook steps 5–6 for `local-final-2`

```powershell
New-Item -ItemType Directory -Force docs/results/data/local-final-2 | Out-Null
Copy-Item benchmarks/results/local-final-2/results.json docs/results/data/local-final-2/results.json
python benchmarks/evidence.py
python benchmarks/figures.py
```

Check that:
- `evidence.md`'s Sources table now names **`P5-local-final-2.md`** for C1–C4 and
  C6–C8;
- `git diff --stat` shows `README.md` changed only between the
  `evidence:summary` markers;
- the F3–F5 footers name `local-final-2`.

If `figures.py` fails with a permission error, retry once; it's a file lock.

### C3. Final overhead wording, from `local-final-2` only

Replace A4's interim text in `ROADMAP.md` and `V1.md`. Use the matching outcome,
with no numbers, links only:

| C1 shows | Write |
|---|---|
| **Every cell `met`** | < 1 ms p99 added is **met on every T and L tier and configuration on the owner's machine** in a compliant run. An earlier run with documented interference had four inconclusive write-tier cells (link `local-runs.md`) |
| **Some cells still not `met`** | Name **exactly which** tier and configuration cells. State that capture itself (`capture-null`) is met on every tier, if C1 shows that. Then **add an entry to `docs/LIMITATIONS.md`**: the delivery sink can add a tail on write paths, with the measured cells linked and the product follow-up — smaller HTTP batches, or serialisation that doesn't hold the caller's GIL |

Either way:
- update `local-runs.md`: `local-final-2` → compliant, with its link;
- throughput < 2% stays **not met**;
- the P5.1 ROADMAP row stays as it is, except that "owner's `local-p51` run
  pending" becomes "superseded by `local-final-2`".

### C4. Commit and push

```powershell
git status --short
git add docs/results/P5-local-final-2.md docs/results/data/local-final-2/results.json docs/paper/evidence.md docs/paper/figures README.md ROADMAP.md docs/results/V1.md docs/results/local-runs.md
```

Add `docs/LIMITATIONS.md` too, if C3 changed it. Then:

```powershell
git commit -m "Owner's compliant final run (local-final-2): evidence, figures, final overhead wording"
git push
```

Confirm on GitHub that CI is green, and report.

### C5. Release preparation — prepare only; the owner does the release

1. **Ask the owner for the name to cite.** Then replace `REPLACE_WITH_OWNER_NAME` in
   `CITATION.cff`, and set `date-released` to the planned release day.
2. **Optional, metadata only:** `backend/app/main.py` passes
   `version="0.1.0.dev0"` to FastAPI. If the owner agrees, change it to `"0.1.0"`
   and run the backend tests.
3. Draft the GitHub release notes for `v0.1.0` from `CHANGELOG.md`, and show them
   to the owner. Don't create the release.
4. Commit and push 1–2 with exact paths. Then remind the owner of runbook step 10,
   in order:
   1. enable the Zenodo GitHub integration;
   2. create the `v0.1.0` release on GitHub with the drafted notes;
   3. confirm the DOI;
   4. then add the DOI badge to the README.

   **Zenodo must be enabled before the release is created,** or it won't archive
   it. Step 11 (PyPI) stays deferred: the name `dcp` is taken.

Stop and report.
