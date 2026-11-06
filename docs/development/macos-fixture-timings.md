# macOS fixture timings and coverage evidence

`Build 2 macOS` reports what it selected, what it ran and what it deferred, and
retains the journey timings it observed. This page describes the evidence and
how to turn several runs into a distribution.

## What a run publishes

The lane prints one block, writes it to the job summary, and uploads
`macos-coverage.jsonl` as the artifact `macos-coverage-<run-id>-<attempt>`:

```
macOS coverage lane=pr profile=macos-26 source=b894b3c2292c image=macos26/20261026.0455.2 arch=ARM64
  selected=3 executed=3 passed=3 failed=0 deferred=3 not_selected=30
  deferred test_hades2_view_state_flow.py reason="..." owner="Build 2 macOS workflow_dispatch on the exact SHA"
  inventory=36 deferred_covered=true
  timings=8 journey/profile samples (observation only, no threshold)
  timing profile=macos-26 journey=hades.disclosure samples=1 min=35.4s median=35.4s max=35.4s budget=60s
```

`not_selected` is the honest complement of `selected`: a green pull request
never implies the whole inventory ran.

The JSONL artifact holds three record kinds:

| kind | fields |
| --- | --- |
| `coverage` | lane, selected, executed, passed, failed, deferred, not_selected, inventory, deferred_covered, source, profile, image, architecture |
| `result` | test, status |
| `timing` | journey, profile, budget_seconds, elapsed_seconds, outcome, source, architecture, image, image_version |

`timing` records are **raw observations**, one per fixture launch, not a per-run
aggregate. That is deliberate: a distribution is only meaningful when several
runs can be merged, and an aggregate cannot be merged.

## Building a distribution

Download one artifact per run and pass the merged file as a baseline:

```bash
gh run download <run-id> -n macos-coverage-<run-id>-<attempt> -D evidence/<run-id>
cat evidence/*/macos-coverage.jsonl > /tmp/timings.jsonl
printf 'test_hades_frontend.py\n' > /tmp/selected.txt
printf 'test_hades_frontend.py\tpass\n' > /tmp/results.tsv
python3 Tools/summarize_macos_coverage.py \
  --lane pr --selected /tmp/selected.txt --results /tmp/results.tsv \
  --baseline /tmp/timings.jsonl
```

The report prints `samples`, `min`, `median` and `max` per journey and profile.
It never fails on a slow journey: timing is observation, not a gate. A blocking
regression threshold needs measured stability first, and none is defined.

## What a comparison may and may not claim

Only merge records that share `profile`, `image` and `architecture`. A
distribution built from different source SHAs measures hosted-runner variance
across those revisions; it is not a controlled same-SHA comparison and cannot
attribute a difference to a code change.

Fixture timings are not product performance. A journey that takes longer means
the harness waited longer, which may be runner load, activation, or a genuine
product change. Separating those needs a same-SHA repeat on the same profile.
