# v1 — frozen as submitted

Read-only copy of the result set behind the submitted manuscript. Do not edit.

- Tag: `v1-submitted` → commit `64859685` (figures rebuilt from this run)
- Measurement run: commit `d8ce50b9`, `config_hash bb85df0d7803`
- `RESULTS.json`: byte copy of `experiments/results/RESULTS.json` at the tag
- `raw/`: exactly the source files named in `experiments/consolidate_results.py:SOURCES`,
  plus `exp1_requests.jsonl` (per-request rows). Paths mirror `experiments/results/`.
- `SHA256SUMS`: verify with `cd results/v1 && sha256sum -c SHA256SUMS`
