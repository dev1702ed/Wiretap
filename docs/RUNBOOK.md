# Owner's runbook: closing v1

**This is the only owner-facing checklist.** It replaces every earlier runbook
(`P5.md` §14, `P5.1.md` §14). Work through it in order, on your Windows machine, in
**Windows PowerShell** (5.1 or 7), from the repository root. Every step gives the exact
commands, what you should see, and what to check if you see something else.

Steps 1-6 and 8 were rehearsed on Linux in the P5.2 sandbox, in a fresh virtualenv
with only shell and path syntax adapted (the log is in
[`docs/results/P5.2.md`](results/P5.2.md#2-verification-log), item 9). Step 7's logic
(the timing, the Marquez API check and the record it writes) is tested in
`benchmarks/tests/test_bench_demo_timing.py`; steps 9-11 are account actions on Zenodo,
GitHub and PyPI that no sandbox can take.

**Before you start.** You need: Git for Windows; Python 3.14 (`py -3.14 --version`);
Docker Desktop, running; about 5 GB of free disk; and roughly 90 minutes, most of it
step 4.

---

## Step 1 — Pull, and install the pinned environment in a fresh virtualenv

```powershell
cd C:\path\to\Wiretap            # your clone
git switch main
git pull
git status                        # expect: "nothing to commit, working tree clean"
py -3.14 -m venv .venv-v1
.\.venv-v1\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -c benchmarks/constraints.txt -e "./sdk-python[dev]" -e "./backend[dev]" -e "./bridges/openlineage[dev]" -r benchmarks/requirements.txt
python -m ipykernel install --user --name python3
python -c "import dcp, dcp_openlineage, matplotlib, psycopg, confluent_kafka; print(dcp.__version__, dcp_openlineage.__version__, matplotlib.__version__)"
```

**Expect:** `pip install` ends with `Successfully installed ...`, a list that includes
`dcp-0.1.0`, `dcp-backend-0.1.0`, `dcp-openlineage-0.1.0` and `matplotlib-3.11.2`. The
kernel line prints `Installed kernelspec python3 in ...`. The last line prints
`0.1.0 0.1.0 3.11.2`.

**If not:**

- `Activate.ps1 cannot be loaded because running scripts is disabled`: run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer `Y`, and activate again.
- `No matching distribution found` or a resolver conflict: check `python --version` says
  3.14 inside the venv. The pins cover Python 3.10 and 3.12+; 3.11 cannot install the
  pinned `networkx` ([`LIMITATIONS.md`](LIMITATIONS.md#5-the-evaluation-itself)).
- `git status` lists changes: commit or stash them first. Every record notes the working
  tree's dirty flag.

## Step 2 — The unit tests and lint, on all four test directories

```powershell
pytest sdk-python/tests -q -rs
pytest backend/tests -q -rs
pytest bridges/openlineage/tests -q -rs
pytest benchmarks/tests -q -rs
ruff check sdk-python backend benchmarks bridges
ruff format --check sdk-python backend benchmarks bridges
```

**Expect** the final summary lines below (the counts the CI `windows` job, Python 3.14
on `windows-latest`, reported on this release's code; only the timings differ):

| Directory | Summary line on Windows |
|---|---|
| `sdk-python/tests` | `726 passed, 3 skipped, 1 xfailed` |
| `backend/tests` | `80 passed` |
| `bridges/openlineage/tests` | `68 passed` |
| `benchmarks/tests` | `330 passed, 1 skipped` |

Then `All checks passed!` and `... files already formatted`.

The skips, all expected, are listed by `-rs`:

- SDK: two `os.fork is not available here` (Windows has no `fork`), and
  `test_propagation.py`'s live-Postgres test (set `DCP_TEST_PG` to run it);
- benchmarks: `test_b2_10_live_replay_of_a_tiny_stress_key` (opt-in with
  `DCP_TEST_LIVE=1`, because it drops and re-creates `gen_*` tables).

The xfail is the documented thread-pool limitation (`test_threads.py`).

**If not:** any other failure or skip is a bug: note the test name and the message, and
stop. A failure in `test_bench_evidence.py::test_the_committed_pack_and_readme_block_are_up_to_date`
on a clean pull means a record was committed without re-running step 5; run
`python benchmarks/evidence.py` and look at `git diff`.

## Step 3 — Prepare the machine and start Postgres and Kafka

1. Power: plugged in, Windows power mode **Best performance**.
2. Pause OneDrive (system tray → OneDrive → Pause syncing → 24 hours).
3. Close your editor, browsers and anything heavy. Use a standalone PowerShell window,
   not an editor's terminal.
4. Start the two containers and set the variables:

```powershell
docker start dcp-postgres dcp-kafka
docker ps --format "{{.Names}} {{.Status}}"
Test-NetConnection localhost -Port 5432 | Select-Object TcpTestSucceeded
Test-NetConnection localhost -Port 9092 | Select-Object TcpTestSucceeded
$env:DCP_PG_PASSWORD = "<your postgres password>"   # the default is dcp
$env:DCP_BENCH_KAFKA_VERSION = "3.8.0"
```

**Expect:** `docker start` echoes `dcp-postgres` and `dcp-kafka`; `docker ps` shows both
`Up ...`; both connection tests print `True`.

**If not:**

- `No such container`: create them once, then start again:

  ```powershell
  docker run -d --name dcp-postgres -e POSTGRES_PASSWORD=dcp -e POSTGRES_DB=dcp -p 5432:5432 postgres:16
  docker run -d --name dcp-kafka -p 9092:9092 apache/kafka:3.8.0
  ```

  (`apache/kafka`'s default single-node config listens on and advertises
  `localhost:9092`, which the benchmarks need.)
- A port test prints `False`: wait 20 seconds (Kafka starts slowly) and test again;
  then check `docker logs dcp-kafka` and that nothing else holds the port.

## Step 4 — The one final full run

> **Warning: seeding is destructive.** The `live`, `adversarial`, `scale` and `overhead`
> stages **drop and re-create** the tables `orders`, `refunds`, `summary`,
> `refund_summary` and `daily_revenue`, and every `gen_src_*` and `gen_out_*` table, in
> the **`dcp`** database, and **delete and re-create** the Kafka topics
> `enriched_orders`, `overhead_bench` and every `gen_topic_*`. Don't point them at data
> you want to keep.

```powershell
python benchmarks/run.py --label local-final
$LASTEXITCODE
python benchmarks/render.py --fixed-cost benchmarks/results/local-final/results.json docs/results/P5-local-final-fixed-cost.md
Select-String -Path docs/results/P5-local-final.md -Pattern '^\| (replay|live|adversarial|scale|overhead|cpu) \|'
Select-String -Path docs/results/P5-local-final.md -Pattern 'Unexplained|agrees with replay' -Context 0,20 | Select-Object -First 3
```

Optional, as in P5.1: `--cpu-python C:\path\to\another\python.exe` (repeatable) measures
the CPU stage on other interpreters too.

**Expect:**

- It takes roughly an hour: `overhead` is the longest stage (P5's run took about 11
  minutes before P5.1 added the L tiers and two configurations); `scale` runs the 11
  generated keys and the 6 stress keys live, about 650 processes.
- The last stderr lines are `raw results: ...\benchmarks\results\local-final\results.json`
  and `rendered:    ...\docs\results\P5-local-final.md`; `$LASTEXITCODE` prints `0`.
- The `Select-String` on stages prints six lines, **every one `ran`**:
  `replay`, `live`, `adversarial`, `scale`, `overhead`, `cpu`.
- In `P5-local-final.md`: the environment table's `Pinned versions` row says
  `all 32 pins match`; the scale section's and the stress section's live tables say
  `yes` in *Every row agrees with replay* for every key; every *Unexplained extras* and
  *Unexplained misses* cell says `none`; the per-cause table's *Unexplained* column is
  `0`.
- `docs\results\P5-local-final-fixed-cost.md` exists and has a table titled
  `The fixed cost per call and the < 2% throughput target`.

**If not:**

- A stage is `skipped`: its *Detail* cell says why (usually a service is not reachable:
  back to step 3, or a library is missing: back to step 1).
- A stage is `failed`: the record shows the traceback under `` `<stage>` failed ``. Note
  it and stop.
- `Pinned versions` lists mismatches: not fatal (it is recorded), but say so when you
  report the results.
- Any `NO` in *Every row agrees with replay*, or anything other than `none` in an
  *Unexplained* column: that is a finding to report, not something to re-run until it
  goes away.

**Alternative, if you already have an overhead record from the final code**
(`docs/results/P5-local-p51.md`, from P5.1's runbook, with its raw JSON still in
`benchmarks\results\local-p51\`): skip the overhead and CPU stages, and render the
fixed-cost record from that run instead.

```powershell
python benchmarks/run.py --label local-final --only replay,live,adversarial,scale
python benchmarks/render.py --fixed-cost benchmarks/results/local-p51/results.json docs/results/P5-local-p51-fixed-cost.md
```

Then the `Select-String` above prints `ran` for the four requested stages and `not
requested` for `overhead` and `cpu`; in steps 6 and 8, use `local-p51` wherever the
overhead data is meant (its raw JSON, its records).

## Step 5 — The evidence pack picks up your records

```powershell
python benchmarks/evidence.py
python benchmarks/evidence.py --check
$LASTEXITCODE
Select-String -Path docs/paper/evidence.md -Pattern '^\| \[C' | Select-Object -First 20
git diff --stat
```

**Expect:** `wrote ...\docs\paper\evidence.md (8 of 8 claims with evidence) and the README
block`; `--check` exits `0`. In the *Sources* table, the claims C1-C4 and C6-C8 now name
`P5-local-final.md` (and C8 `P5-local-final-fixed-cost.md`) with `owner` in the
*Machine* column; C5 names `P5-local-final.md` too; C7's first row stays
`P5-p51-final-comparison.md` (the before/after pair, sandbox) and its second row is
yours. `git diff --stat` shows `README.md` and `docs/paper/evidence.md` changed, and in
`README.md` only the lines between `<!-- evidence:summary:start -->` and
`<!-- evidence:summary:end -->`.

**If not:** a claim still naming a sandbox record means your record lacks that section
(its stage did not run: step 4). `README.md has no ... block` means the markers were
edited away: restore them from `git show HEAD:README.md`.

## Step 6 — Figures F3-F5 from your raw data, and the raw data itself

```powershell
New-Item -ItemType Directory -Force docs/results/data/local-final | Out-Null
Copy-Item benchmarks/results/local-final/results.json docs/results/data/local-final/results.json
python benchmarks/figures.py
```

**Expect** ten lines, `wrote ...\docs\paper\figures\F1-scale-accuracy.pdf` through
`F5-startup.png`. Open `docs\paper\figures\F3-added-p99.png`: its footer reads
`Source: docs/results/data/local-final/results.json, run ``local-final`` on the owner's
machine, ...`; F1 and F2 now come from your run too (it is the newest raw JSON with the
stress group), and F4 and F5 say the same source.

**If not:** a footer naming `P5-p51-after-final.md (rendered record, parsed by code ...)`
means no raw JSON with an overhead stage was found under `docs\results\data\`: check the
copy above. With the step 4 alternative, copy `benchmarks\results\local-p51\results.json`
to `docs\results\data\local-p51\results.json` as well.

## Step 7 — Time the dark-zone demo, cold and warm, and check Marquez

```powershell
docker compose -f examples/marquez/docker-compose.yml down     # it shares ports 3000 and 5000
./examples/dark-zone/time-demo.ps1
$LASTEXITCODE
Get-Content docs/results/demo-local.md
Start-Process "http://localhost:3000"
```

`time-demo.ps1` runs `examples/dark-zone/time_demo.py`, which, for the **cold** run,
removes the demo's containers, volumes and images (an image another container uses, such
as `postgres:16` under `dcp-postgres`, stays and is listed), then times
`docker compose up -d --build` until **Marquez's API** shows `nightly_enrich.py` writing
`enriched_orders` and `warehouse_loader.py` reading it; then the **warm** run, with every
image cached. It writes its own record, `docs/results/demo-local.md`: the cold and warm
seconds, whether each was under 5 minutes, the demo container's exit code, the API check,
the image tags and IDs, and the UTC timestamp.

**Expect:** about 5-15 minutes in all; the script prints `== cold run`, `== warm run`,
`wrote ...\docs\results\demo-local.md`; `$LASTEXITCODE` is `0`. In the record, both rows
say `yes` in *Both jobs linked through `enriched_orders` (Marquez API)* and `0` as the
demo exit code. In the web UI, namespace `dcp://dark-zone-demo`, you see
`dcp.public.orders → nightly_enrich.py → enriched_orders → warehouse_loader.py →
dcp.public.daily_revenue`. Then clean up:

```powershell
docker compose -f examples/dark-zone/docker-compose.yml down -v
```

**If not:**

- Exit code `1` and `not reached` in the record: the graph never appeared within 15
  minutes. Look at `docker compose -f examples/dark-zone/docker-compose.yml logs demo`
  and `... logs marquez`; the record is still written, commit it as it is.
- `toomanyrequests` from Docker Hub: log in (`docker login`) and run it again.
- Port 3000 or 5000 in use: something else (often `examples/marquez`) is running.

## Step 8 — Commit the records, evidence, figures and data (exact paths only)

Never `git add -A` or `git add .`.

```powershell
pytest benchmarks/tests -q             # the evidence pack must be up to date: as in step 2
git add docs/results/P5-local-final.md docs/results/P5-local-final-fixed-cost.md docs/results/data/local-final/results.json docs/results/demo-local.md
git add docs/paper/evidence.md README.md
git add docs/paper/figures/F1-scale-accuracy.pdf docs/paper/figures/F1-scale-accuracy.png docs/paper/figures/F2-stress-accuracy.pdf docs/paper/figures/F2-stress-accuracy.png docs/paper/figures/F3-added-p99.pdf docs/paper/figures/F3-added-p99.png docs/paper/figures/F4-fixed-cost.pdf docs/paper/figures/F4-fixed-cost.png docs/paper/figures/F5-startup.pdf docs/paper/figures/F5-startup.png
git status
git commit -m "v1: the owner's final run, demo timing, evidence pack and figures"
git push
```

**Expect:** `git status` lists exactly those files under *Changes to be committed* and
nothing under *Changes not staged* except, possibly, nothing at all. (With the step 4
alternative, add `docs/results/P5-local-p51-fixed-cost.md` and
`docs/results/data/local-p51/results.json` as well.) `benchmarks\results\` is ignored by
git and stays local.

**If not:** an unexpected modified file means something wrote where it should not: look
at `git diff` before committing. `rejected ... fetch first` on push: `git pull` first.

## Step 9 — Your name in `CITATION.cff`

Open `CITATION.cff` and replace **both** `REPLACE_WITH_OWNER_NAME` values with your
family name and given names (add an `orcid:` line under them if you have one). Then:

```powershell
Select-String -Path CITATION.cff -Pattern REPLACE
pytest benchmarks/tests/test_bench_release.py -q
git add CITATION.cff
git commit -m "CITATION.cff: author"
git push
```

**Expect:** `Select-String` prints nothing; the tests print `4 passed`. Optionally
validate the file: `pip install cffconvert` then `cffconvert --validate` prints
`Citation metadata are valid according to schema version 1.2.0.`

## Step 10 — Release v0.1.0 with a DOI (Zenodo first)

1. **Zenodo first**, or the release gets no DOI: sign in at https://zenodo.org with
   GitHub, open *Account → GitHub*, press *Sync now*, and switch **`dev1702ed/Wiretap`**
   on.
2. If you want the release date to be the day you release, edit `date-released` in
   `CITATION.cff` (format `"YYYY-MM-DD"`), commit and push.
3. Tag and release. The notes are the `0.1.0` section of `CHANGELOG.md`:

```powershell
git switch main; git pull
git tag -a v0.1.0 -m "DCP v0.1.0"
git push origin v0.1.0
$notes = (Get-Content CHANGELOG.md -Raw) -split '(?m)^## ' | Where-Object { $_ -like '`[0.1.0`]*' }
Set-Content -Path release-notes.md -Value ("## " + $notes) -Encoding utf8
gh release create v0.1.0 --title "DCP v0.1.0" --notes-file release-notes.md
Remove-Item release-notes.md
```

   Without the GitHub CLI: on github.com, *Releases → Draft a new release*, choose the tag
   `v0.1.0`, title `DCP v0.1.0`, paste the `## [0.1.0]` section of `CHANGELOG.md`, and
   *Publish release*.
4. **Confirm the DOI:** within a few minutes Zenodo's *Account → GitHub* page shows the
   release with a DOI badge (`10.5281/zenodo.<number>`).
5. Add the badge to the README, on the line under its title (outside the evidence block),
   and the DOI to `CITATION.cff` (a line `doi: 10.5281/zenodo.<number>` under
   `version:`):

```powershell
# README.md, line 2:
# [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.<number>.svg)](https://doi.org/10.5281/zenodo.<number>)
git add README.md CITATION.cff
git commit -m "README and CITATION.cff: DOI"
git push
```

**If not:** no release appears on Zenodo: the repository was not switched on before the
release was published. Switch it on, then delete and re-create the GitHub release (the tag
can stay).

## Step 11 — Optional: TestPyPI, then PyPI

Only if the names are available. **`dcp` is taken on PyPI** (checked in P5.1 and again in
P5.2, see [`V1.md`](results/V1.md#packaging-c2)); `dcp-backend` and `dcp-openlineage`
were free. Publishing the SDK therefore needs a different distribution name first (for
example `dcp-lineage`, free when checked): change `name = "dcp"` in
`sdk-python/pyproject.toml` and the install line in `README.md`, run step 2's tests, and
commit. The import name stays `dcp`.

```powershell
python -m pip install build twine
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
python -m build sdk-python --outdir dist
python -m build backend --outdir dist
python -m build bridges/openlineage --outdir dist
twine check dist/*
twine upload --repository testpypi dist/*
py -3.14 -m venv $env:TEMP\dcp-testpypi
& $env:TEMP\dcp-testpypi\Scripts\python.exe -m pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple "dcp-lineage==0.1.0"
& $env:TEMP\dcp-testpypi\Scripts\dcp-instrument.exe python -c "print('ok')"
twine upload dist/*
```

**Expect:** six `Successfully built` names and six `PASSED` lines from `twine check`;
the TestPyPI install succeeds and prints `ok`; the final upload prints a
`View at: https://pypi.org/project/...` line per package.

**If not:** `403 ... isn't allowed to upload to project`: the name is taken; choose
another. `twine` asks for credentials: use an API token (user `__token__`).
