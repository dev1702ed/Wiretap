# Times the dark-zone demo, cold and warm, and writes its own record:
# docs/results/demo-local.md. docs/RUNBOOK.md, step 7.
#
#   .\examples\dark-zone\time-demo.ps1             cold, then warm
#   .\examples\dark-zone\time-demo.ps1 -SkipCold   warm only
#   .\examples\dark-zone\time-demo.ps1 -Down       remove the stack at the end
#
# Run from the repository root, in the project's virtualenv, with Docker Desktop
# running and examples/marquez stopped (both publish ports 3000 and 5000).
# All the logic (timing, the Marquez API check, the record) is in
# time_demo.py, next to this file, which is tested in
# benchmarks/tests/test_bench_demo_timing.py.
param(
    [switch]$SkipCold,
    [switch]$Down
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root
$arguments = @("examples/dark-zone/time_demo.py", "--out", "docs/results/demo-local.md")
if ($SkipCold) { $arguments += "--skip-cold" }
if ($Down) { $arguments += "--down" }
python @arguments
exit $LASTEXITCODE
