"""Prove P5.2's "additive only" rule (§2 rule 2, §4 item 2), by script.

    python benchmarks/check_identity.py --base-worktree PATH

PATH is a checkout of the base commit (`git worktree add PATH main`). Three checks,
each reporting its differences; the script exits 1 if any check finds one:

1. score.py's replay output: every line the base code prints is printed by this
   branch too, unchanged and in the same order (the branch only adds lines).
2. The records: every line of docs/results/P5-p51-ground-truth-after.md appears,
   unchanged and in order, in docs/results/P5-p52-mapping.md, except the lines
   that name the run itself (its label, command, times, commit, server version,
   run ids and stage durations), which are listed.
3. The committed generated keys: all eleven regenerate byte for byte with the
   P5.2 parameters at their defaults, and with both passed explicitly as 0.
"""

import argparse
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
GROUND_TRUTH = ROOT / "benchmarks" / "ground_truth"
OLD_RECORD = ROOT / "docs" / "results" / "P5-p51-ground-truth-after.md"
NEW_RECORD = ROOT / "docs" / "results" / "P5-p52-mapping.md"
# Lines that describe the run, not a result: they differ between any two runs.
RUN_SPECIFIC = (
    r"^# P5 results: `",
    r"^\| (Label|Command|Started \(UTC\)|Finished \(UTC\)|Git commit|PostgreSQL server) \|",
    r"^\| (replay|live|adversarial|scale|overhead|cpu) \| ran \| [\d.]+ \|",
    r"run id `[0-9a-f]{8}`",
)


def subsequence(old: list[str], new: list[str], skip=()) -> tuple[list[str], list[str]]:
    """(old lines not found in order in `new`, old lines skipped as run-specific)."""
    missing, skipped, position = [], [], 0
    for line in old:
        if any(re.search(pattern, line) for pattern in skip):
            skipped.append(line)
            continue
        try:
            position = new.index(line, position) + 1
        except ValueError:
            missing.append(line)
    return missing, skipped


def score_output(root: pathlib.Path) -> list[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        str(root / p) for p in ("sdk-python", "backend", "bridges/openlineage")
    )
    script = root / "benchmarks" / "ground_truth" / "score.py"
    out = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return out.stdout.split("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-worktree", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    failures = 0

    base, branch = score_output(args.base_worktree.resolve()), score_output(ROOT)
    missing, _ = subsequence(base, branch)
    print(
        f"1. score.py replay output: base {len(base)} lines, branch {len(branch)} lines; "
        f"base lines missing or changed on the branch: {len(missing)}; "
        f"lines added by the branch: {len(branch) - len(base) + len(missing)}"
    )
    for line in missing:
        print(f"   - {line}")
    failures += len(missing)

    old = OLD_RECORD.read_text(encoding="utf-8").split("\n")
    new = NEW_RECORD.read_text(encoding="utf-8").split("\n")
    missing, skipped = subsequence(old, new, RUN_SPECIFIC)
    print(
        f"2. {OLD_RECORD.name} ({len(old)} lines) against {NEW_RECORD.name} ({len(new)} lines): "
        f"{len(old) - len(skipped) - len(missing)} lines identical and in order, "
        f"{len(skipped)} run-specific lines skipped, {len(missing)} lines missing or changed"
    )
    for line in skipped:
        print(f"   skipped (run-specific): {line[:120]}")
    for line in missing:
        print(f"   - {line}")
    failures += len(missing)

    sys.path.insert(0, str(GROUND_TRUTH))
    import generate

    stale = []
    for name, (seed, overrides) in sorted(generate.KEYS.items()):
        committed = generate.path_for(name).read_bytes()
        default = generate.dumps(generate.generate(name, seed, **overrides)).encode(
            "utf-8"
        )
        explicit = generate.dumps(
            generate.generate(
                name, seed, p_multi_record=0.0, p_store_read=0.0, **overrides
            )
        ).encode("utf-8")
        if default != committed or explicit != committed:
            stale.append(name)
    print(
        f"3. committed generated keys: {len(generate.KEYS)} regenerated with the P5.2 "
        f"parameters off (defaults, and explicit 0); differing: {len(stale)}"
        + (f" ({', '.join(stale)})" if stale else "")
    )
    failures += len(stale)
    print(f"total differences: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
