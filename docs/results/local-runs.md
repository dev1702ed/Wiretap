# The owner's runs

Every benchmark run on the owner's machine, with its protocol status against
[`RUNBOOK.md`](../RUNBOOK.md). Results are in the records, not here.

**Rule:** one rerun, justified by a documented deviation before it was run; both records
kept.

The rerun was run under the same label; the first run's record is archived byte-for-byte.

| Label | Record | Started (UTC) | What it was for | Protocol status |
|---|---|---|---|---|
| `local` | [`P5-local.md`](P5-local.md) | 2026-10-03T17:04:50+00:00 | P5: the owner's full-mode run | Compliant |
| `local-final` (first run) | [`P5-local-final.md` at `9e7b704`](https://github.com/dev1702ed/Wiretap/blob/9e7b704cf09e625c7cd362970ab9263c067d5086/docs/results/P5-local-final.md); archived: [`archive/P5-local-final-first-run.md`](archive/P5-local-final-first-run.md) (raw JSON: [`archive/data/local-final-first-run.json`](archive/data/local-final-first-run.json)) | 2026-10-05T17:09:06+00:00 | Runbook step 4: the one final full run, on the final code | **Deviated from runbook step 3**: OneDrive was syncing and the editor was open during the run. Kept, and disclosed |
| `local-final` (rerun) | [`P5-local-final.md`](P5-local-final.md) | 2026-10-06T14:54:47+00:00 | The one compliant rerun of `local-final` | Compliant. Run under the same label, so its record replaced the first run's file; the first run's record is kept in git history and in the archive (linked above) |

## The demo

| Label | Record | Started (UTC) | What it was for | Protocol status |
|---|---|---|---|---|
| `demo-local` | [`demo-local.md`](demo-local.md) | 2026-10-05T17:41:38+00:00 | Runbook step 7: the dark-zone demo, timed cold and warm, with Marquez's API checked | Compliant. Its *Working tree dirty: True* is the known file-mode noise on `examples/dark-zone/run-demo.sh` and `examples/marquez/init-db.sh`, not a code change. The cold run reused the locally present `apache/kafka:3.8.0` and `postgres:16` images (the record's *Before the run* cell) |
