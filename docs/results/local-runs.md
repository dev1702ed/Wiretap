# The owner's runs

Every benchmark run on the owner's machine, with its protocol status against
[`RUNBOOK.md`](../RUNBOOK.md). Results are in the records, not here.

**Rule:** one rerun, justified by a documented deviation before it was run; both records
kept.

| Label | Record | Started (UTC) | What it was for | Protocol status |
|---|---|---|---|---|
| `local` | [`P5-local.md`](P5-local.md) | 2026-10-03T17:04:50+00:00 | P5: the owner's full-mode run | Compliant |
| `local-final` (first run) | [`P5-local-final.md` at `9e7b704`](https://github.com/dev1702ed/Wiretap/blob/9e7b704cf09e625c7cd362970ab9263c067d5086/docs/results/P5-local-final.md) | 2026-10-05T17:09:06+00:00 | Runbook step 4: the one final full run, on the final code | **Deviated from runbook step 3**: OneDrive was syncing and the editor was open during the run. Kept, and disclosed |
| `local-final` (rerun) | [`P5-local-final.md`](P5-local-final.md) | 2026-10-06T14:54:47+00:00 | The one compliant rerun of `local-final` | Compliant. Run under the same label, so its record replaced the first run's file; the first run's record is kept in git history (linked above) |
