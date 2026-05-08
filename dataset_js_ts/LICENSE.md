# DTV JS-to-TS Translation Dataset: License Information

This directory contains rollup-bundled JavaScript files and associated
metadata for the JavaScript-to-TypeScript evaluation of the DTV (Decoding
Time Verification) framework.

## Per-case contents

For each package directory `<package>/`:

- `source.js` - Single-file rollup-bundled JavaScript derived from the
  original npm package's source tree.
- `metadata.json` - Bundling record (subset, original entry, file count,
  bundled LOC, baseline `tsc` error count, original source path).
- `LICENSE` - The license file shipped with the original npm package, copied
  verbatim from the upstream distribution where available. For the small
  number of packages that ship without a `LICENSE` file, a stub LICENSE is
  generated from the `license` field of the upstream `package.json` and
  marked as such.

## Provenance

The packages are drawn from the TypeWeaver release:

> Ming-Ho Yee and Arjun Guha.
> *Do Machine Learning Models Produce TypeScript Types That Type Check?*
> ECOOP 2023, LIPIcs Vol. 263, 37:1-37:28.
> https://doi.org/10.4230/LIPIcs.ECOOP.2023.37

Filtering applied for this dataset (Appendix E of the DTV paper):

1. Start from the TypeWeaver subsets `top1k-typed-nodeps-es6` and
   `top1k-untyped-nodeps-es6`.
2. Bundle each package via `rollup` in ES module format on the package's
   declared main entry.
3. Discard packages whose bundled output falls outside [30, 1000] lines of
   code, and packages that already pass `tsc` under strict mode without
   modification.

The 196 packages retained after filtering are checked into this directory.
The 150 packages used in the paper's evaluation are listed in
`../150_samples_seed20260416_js_ts.txt`.

## Licensing

**Each package retains the license under which it was originally
distributed on npm.** The `<package>/LICENSE` file in this repository is the
authoritative license for that package's `source.js`. Across the 196
packages the declared licenses (per upstream `package.json`) break down
roughly as: 158 MIT, 20 ISC, 6 BSD-3-Clause, 5 BSD-2-Clause, 4 Apache-2.0,
1 dual `AFL-2.1 OR BSD-3-Clause` (`json-schema`), and 2 packages whose
upstream `package.json` did not declare a license but did ship an MIT-text
`LICENSE` file (`console-browserify`, `exit`); consult each per-package
`LICENSE` for exact terms.

This per-package license also covers `source.js` (a rollup-bundled
derivative work of the package source) and `metadata.json` (a thin
descriptor of the bundling step).

The aggregation of package directories into this dataset, and the bundling
script that produced `source.js` (`../js_ts/dataset/filter_typeweaver.py`),
are released under the same license as the rest of this repository.

## Reconstruction

To rebuild this dataset from a fresh TypeWeaver release, point
`../js_ts/dataset/filter_typeweaver.py` at the TypeWeaver `data/full/original/`
tree. The 196-package output is deterministic given the same TypeWeaver
release and `rollup` version.
