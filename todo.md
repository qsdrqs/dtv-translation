# Two-Week NeurIPS Push TODO

Last updated: 2026-04-16

## Goal

- Turn the current DTV project into a NeurIPS-submittable paper package.
- Main claim target: DTV is overall competitive with naive decoding, and its gains concentrate on locally verifiable and locally repairable error families.

## Current state

- JS-to-TS with Qwen 3: done.
- Gemma 4 basic support: done.
- C-to-Rust current code/tests: `./.venv/bin/python -m pytest -q` passes.
- C-to-Rust 50-case calibration on Delta: partial run completed; use it only as a sanity check, not as the main result.

## Submission bar for this two-week sprint

- [ ] C-to-Rust Qwen main result with more than 250 completed cases, with excluded timeout-heavy cases documented.
- [ ] Predefined error-family taxonomy and subgroup analysis.
- [ ] At least one stronger inference baseline beyond naive (`best-of-n` required; tree-search optional).
- [ ] At least one confirmatory Gemma run on C-to-Rust (`DTV` + `naive`; `best-of-n` optional only if time remains).
- [ ] Key ablations for DTV design.
- [ ] Main figures/tables for overall, subgroup, baseline, and ablation results.
- [ ] Draft abstract, intro framing, results section, and limitations section.

## Hard rules

- [ ] Do not change the paper story after the experiment matrix is frozen unless the frozen analysis clearly falsifies the planned story.
- [ ] Do not define the main error-family taxonomy after looking at win/loss outcomes. Exploratory post-hoc splits are allowed only if they are labeled as exploratory.
- [ ] Keep all comparisons compute-matched and budget-matched.
- [ ] Prefer automation over manual analysis. Every repeated analysis step should become a script.
- [ ] Record exact result directories, seeds, model names, command lines, and per-case outcomes for every run.

## Week 1

### Block A - Freeze the experiment contract (Day 1)

- [ ] Create `analysis_contract.md` in the repo root.
- [ ] Freeze the C-to-Rust experiment matrix:
  - [ ] Qwen: `DTV`, `naive`, `best-of-n`.
  - [ ] Gemma: `DTV`, `naive`.
  - [ ] Ablations: `no_feedback`, `no_rollback`, `no_escalate_or_no_bailout`.
- [ ] Freeze the main metrics:
  - [ ] final pass rate
  - [ ] test pass rate
  - [ ] total tokens
  - [ ] elapsed time
  - [ ] verify count
- [ ] Freeze the subgroup rule:
  - [ ] use the first blocking or first non-noise diagnostic family as the case label.
  - [ ] define a fixed mapping from diagnostics to local/nonlocal/semantic families.
- [ ] Write one paragraph in `analysis_contract.md` stating the main claim boundary:
  - [ ] overall comparable
  - [ ] subgroup-strong on local-repair families
  - [ ] weaker on nonlocal structural errors

### Block B - Delta reliability and full Qwen C-to-Rust run (Day 1-3)

- [ ] Audit `run_experiments_c_rust.py` before launching the main run:
  - [ ] list the oracles used by DTV
  - [ ] list the oracles used by naive
  - [ ] verify whether DTV and naive are matched on oracle usage where the comparison is intended to be fair
  - [ ] document any intentional asymmetry
- [ ] Patch the Delta launcher so heavy workers do not timeout.
- [ ] Re-run C-to-Rust Qwen 300-case `DTV` vs `naive` with stable time limits and a target of more than 250 completed cases.
- [ ] Save all result tags under clearly named directories in `result_delta/` or remote `result/`.
- [ ] Merge the 300-case result shards.
- [ ] Produce a one-page summary:
  - [ ] completed case count
  - [ ] no missing shards
  - [ ] no silent timeouts
  - [ ] overall DTV vs naive pass rate

### Block C - Analysis pipeline (Day 2-4, parallel with Delta)

- [ ] Add or update a script that merges shard JSONs into one canonical result file.
- [ ] Add or update a script that computes:
  - [ ] overall pass rate
  - [ ] paired DTV-only / naive-only wins
  - [ ] token/time averages
  - [ ] confidence intervals or paired tests
- [ ] Add or update a script that assigns each case to an error family.
- [ ] Add or update a plotting script for:
  - [ ] overall bar chart
  - [ ] subgroup bar chart
  - [ ] token/pass tradeoff figure
- [ ] Run the full analysis pipeline once on the 50-case calibration result to verify the scripts work end-to-end.

### Block D - Qwen subgroup analysis (Day 4-5)

- [ ] Run subgroup analysis on the completed Qwen 300-case result.
- [ ] Output at least these groups:
  - [ ] local compile errors
  - [ ] nonlocal missing-definition or structure errors
  - [ ] compile-pass but semantic/test failures
- [ ] Generate one table with overall + subgroup pass rates.
- [ ] Generate one table with DTV-only vs naive-only wins by subgroup.
- [ ] Write 5-10 bullet conclusions from the subgroup results.

### Block E - Gemma confirmatory run (Day 5-7)

- [ ] Run Gemma C-to-Rust preflight checks first.
- [ ] Launch Gemma C-to-Rust 100-case confirmatory run first.
- [ ] Compare Gemma results against the same taxonomy and metrics.
- [ ] If the 100-case signal is consistent, launch the Gemma 300-case run.
- [ ] If time is tight, keep Gemma at 100-case and make it explicitly confirmatory in the paper.

## Week 2

### Block F - Stronger baseline (Day 8-9)

- [ ] Implement or finalize a compute-matched `best-of-n` baseline for C-to-Rust.
- [ ] Freeze how `n` is chosen under the same token budget.
- [ ] Run Qwen `best-of-n` on C-to-Rust.
- [ ] If the implementation cost is low, add a small tree-search baseline run as stretch work.
- [ ] Produce a table: `naive` vs `best-of-n` vs `DTV`.

### Block G - Key ablations (Day 9-11)

- [ ] Run `no_feedback` ablation.
- [ ] Run `no_rollback` ablation.
- [ ] Run `no_escalate_or_no_bailout` ablation.
- [ ] Make one ablation table with overall and local-subgroup results.
- [ ] Write one paragraph per ablation explaining what mechanism it tests.

### Block H - Failure analysis and case studies (Day 10-12)

- [ ] Collect 3 representative `DTV-only pass` cases.
- [ ] Collect 2 representative `naive-only pass` cases.
- [ ] For each case, save:
  - [ ] case id
  - [ ] main diagnostic family
  - [ ] tokens/time
  - [ ] one short explanation of why DTV helped or failed
- [ ] Write one short note on the limitation boundary: DTV is weaker when repair is nonlocal.

### Block I - Paper package (Day 11-14)

- [ ] Write abstract v1.
- [ ] Write intro framing around error locality and task dependence.
- [ ] Write methods subsection for DTV loop and oracle setup.
- [ ] Write experiments subsection with dataset/model/budget details.
- [ ] Write results subsection with:
  - [ ] overall result
  - [ ] subgroup result
  - [ ] baseline result
  - [ ] ablation result
- [ ] Write limitations section.
- [ ] Export final figure set for the paper.

## Deliverables checklist

### Experiments

- [ ] `Qwen C-to-Rust >250 completed cases`: merged results
- [ ] `Gemma C-to-Rust 100 or 300`: merged results
- [ ] `best-of-n` baseline results for Qwen
- [ ] ablation result bundle

### Analysis artifacts

- [ ] canonical merged result files
- [ ] error-family label file
- [ ] per-case result record for every run
- [ ] overall summary table
- [ ] subgroup summary table
- [ ] ablation table
- [ ] figure scripts that can be rerun

### Writing artifacts

- [ ] abstract
- [ ] intro framing
- [ ] experiments section draft
- [ ] results section draft
- [ ] limitations section draft

## If time slips

- [ ] Keep `best-of-n`; drop tree-search first.
- [ ] Keep Gemma 100-case confirmatory; drop Gemma 300-case before dropping subgroup analysis.
- [ ] Keep exactly 3 core ablations; do not add extra ablations before the stronger baseline is done.
- [ ] Never drop the predefined subgroup analysis. It is central to the paper story.

## End-of-sprint decision rule

- [ ] Submit to NeurIPS if all of the following hold:
  - [ ] overall DTV is competitive with naive on C-to-Rust
  - [ ] local-repair subgroup shows a clear DTV advantage
  - [ ] the result is not limited to a single model family
  - [ ] stronger baseline does not erase the DTV story
- [ ] Otherwise, downgrade the framing to workshop-level and keep the same analysis package.
