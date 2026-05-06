# DTV: Decoding Time Verification for Code Translation

DTV integrates deterministic program verifiers (compilers, type checkers,
differential tests) into the decoding loop of a fixed pretrained code LLM. The
model is used as a black-box generator; no training is involved. Two
translation tasks are supported:

- **C -> Rust**: `rustc` compile oracle + program-level differential testing.
- **JS -> TS**: `tsc` compile oracle (strict: false) + ESLint
  (`@typescript-eslint/typedef`).

This README focuses on running the two experiment drivers
[`run_experiments_js_ts.py`](run_experiments_js_ts.py) and
[`run_experiments_c_rust.py`](run_experiments_c_rust.py). For architecture
details and invariants, see [`AGENTS.md`](AGENTS.md).

## 1. Environment

Python is pinned to 3.13.3 via [`pyproject.toml`](pyproject.toml). The
recommended setup uses `uv` (managed Python) plus the system toolchains for
`rustc`, `tsc`, `eslint`, and `node`.

### Option A: Nix flake

```bash
nix develop                       # python3, uv, rustup, nodejs, tsc
uv sync                           # install Python deps into .venv
npm install                       # install eslint + typescript-eslint
rustup toolchain install stable
```

### Option B: Plain uv

System prerequisites: `nodejs` (>=20), `rustup`, `gcc`.

```bash
uv sync
npm install
rustup toolchain install stable
```

### Option C: Container

A reproducible Apptainer/Docker image is defined by
[`Dockerfile`](Dockerfile) and [`dtv.def`](dtv.def).

### Sanity check

```bash
./.venv/bin/python -m pytest -q
```

## 2. Datasets

Both task datasets ship with the repository; no external download is
required to reproduce the paper.

### C -> Rust (`dataset/`)

300 case directories, sourced from
[IBM Project CodeNet](https://github.com/IBM/Project_CodeNet) (Apache 2.0;
see [`dataset/LICENSE`](dataset/LICENSE) and
[`dataset/NOTICE`](dataset/NOTICE) for full attribution and selection
criteria). Per-case layout:

```
dataset/<case_id>/
  source.c           Original C program.
  testcases/         Differential-testing stdin payloads (input_000, input_001, ...).
  metadata.json      Construction record (tool versions, parameters, counts).
```

Differential test inputs are generated via a hybrid LLM-seeded AFL++
pipeline (paper Appendix E). The pipeline lives in a separate repository
(`agent_fuzz`); per-case AFL build artifacts (`afl_corpus/`, `afl_out/`,
`coverage/`, `llm_seeds/`, `min_corpus/`, `prog_*`) are not tracked here
since `source.c` + `testcases/*` are sufficient for differential testing.

### JS -> TS (`dataset_js_ts/`)

196 packages from [TypeWeaver](https://doi.org/10.4230/LIPIcs.ECOOP.2023.37),
rollup-bundled. Per-case layout:

```
dataset_js_ts/<package>/
  source.js          Single-file rollup bundle (ES module).
  metadata.json      Bundling record.
  LICENSE            Per-package license, retained from upstream npm.
```

Each package retains its original npm license; see
[`dataset_js_ts/LICENSE.md`](dataset_js_ts/LICENSE.md) for the per-package
license summary. To rebuild this dataset from a fresh TypeWeaver release,
point [`js_ts/dataset/filter_typeweaver.py`](js_ts/dataset/filter_typeweaver.py)
at the TypeWeaver `data/full/original/` tree.

### Custom dataset locations

The runners default to the in-repo paths shown above and respect the
following environment overrides:

| Variable | Runner | Default |
|----------|--------|---------|
| `DTV_DATASET_DIR` | `run_experiments_c_rust.py` | `dataset` |
| `DTV_JS_TS_DATASET_DIR` | `run_experiments_js_ts.py` | `dataset_js_ts` |

`run_experiments_js_ts.py` additionally accepts `--dataset-dir PATH`.

## 3. Sample lists

The five paper cohorts are checked in at the repository root:

| File | Cohort |
|------|--------|
| [`300_samples_seed20260416.txt`](300_samples_seed20260416.txt) | Full C->Rust eval (n=300; RQ1, RQ3). |
| [`150_samples_seed20260416_js_ts.txt`](150_samples_seed20260416_js_ts.txt) | Full JS->TS eval (n=150; RQ1, RQ3). |
| [`100_samples_seed20260416_head.txt`](100_samples_seed20260416_head.txt) | First 100 of 300 (RQ2 ablation; head of the cost-matched n=200 split). |
| [`100_samples_part2_seed20260416.txt`](100_samples_part2_seed20260416.txt) | Cases 101-200 of 300 (cost-matched complement; head + part2 = n=200). |
| [`100_samples_seed20260416_js_ts_head.txt`](100_samples_seed20260416_js_ts_head.txt) | First 100 of 150 (cost-matched JS->TS n=100). |

## 4. Running experiments

Both runners take a required `--strategy` and run one strategy per
invocation. To produce A/B comparisons, invoke twice with different
`--output` paths.

### C -> Rust

```bash
./.venv/bin/python run_experiments_c_rust.py \
    --strategy dtv \
    --budget-k 16 \
    --output result/c_rust_dtv.json \
    $(cat 300_samples_seed20260416.txt)
```

Matched naive baseline:

```bash
./.venv/bin/python run_experiments_c_rust.py \
    --strategy naive \
    --budget-k 16 \
    --output result/c_rust_naive.json \
    $(cat 300_samples_seed20260416.txt)
```

Strategies: `naive`, `dtv`, `bon-nsr`, `s_star`, plus three RQ2 ablations:
`dtv-no-feedback`, `dtv-no-escalation`, `dtv-detect-and-abort`.

### JS -> TS

```bash
./.venv/bin/python run_experiments_js_ts.py \
    --strategy dtv \
    --budget-k 16 \
    --output result/js_ts_dtv.json \
    $(cat 150_samples_seed20260416_js_ts.txt)
```

Strategies: `naive`, `dtv`, `bon-nsr`, `s_star`.

### Common flags

| Flag | Default | Notes |
|------|---------|-------|
| `--strategy` | required | See per-task lists above. |
| `case_ids ...` (positional) | built-in smoke set | Pass an explicit list (typically `$(cat <sample_list>.txt)`). |
| `--output PATH` | runner-specific | JSON list of per-case results, saved incrementally; existing entries are resumed. |
| `--backend {qwen,gemma}` | `qwen` | Generator backend. |
| `--model-name NAME` | backend default | Must match `--backend`. |
| `--token-budget N` | `6144` | Fixed per-case generation budget. |
| `--budget-k K` | unset | Per-case budget = `K * source_tokens` (overrides `--token-budget`; paper uses `K=16`). |
| `--greedy` | off | `do_sample=False`. |
| `--bon-n N` | unset | Required when `--strategy=bon-nsr`. |
| `--s-star-n N` | `8` | Parallel samples for `s_star`. |
| `--s-star-num-rounds N` | `3` | Self-debug rounds for `s_star` (1 initial + 2 debug; matches S* paper R=2). |

`run_experiments_js_ts.py` additionally accepts `--dataset-dir PATH` and
the `--all` flag (run every directory under the dataset root containing a
`source.js`).

### Per-case eval (debugging)

For inspecting a single case end to end:

- [`run_single_c_rust_eval.py`](run_single_c_rust_eval.py)
- [`run_single_js_ts_eval.py`](run_single_js_ts_eval.py)
- [`run_single_js_ts_eval_naive.py`](run_single_js_ts_eval_naive.py)

## 5. Outputs

Each runner writes:

- `--output` (JSON): list of `RunResult` entries, one per case; saved
  incrementally so a preempted job can resume.
- `<output_stem>_pass_outputs/{dtv,naive}/<case_id>.{rs,ts}`: final
  passing translation when the case passes.
- A console A/B summary table when matched DTV and naive `--output` paths
  share a parent directory.

## 6. Citation and license

Source code is released under the Apache License 2.0
(see [`LICENSE`](LICENSE)).

Datasets retain their upstream licenses:

- `dataset/` (C -> Rust): Apache 2.0 (Project CodeNet); see
  [`dataset/LICENSE`](dataset/LICENSE) and [`dataset/NOTICE`](dataset/NOTICE).
- `dataset_js_ts/` (JS -> TS): per-package licenses retained from each
  npm package's upstream distribution; see
  [`dataset_js_ts/LICENSE.md`](dataset_js_ts/LICENSE.md) and the
  `LICENSE` file inside each `dataset_js_ts/<package>/`.

Citation BibTeX will be added after publication.
