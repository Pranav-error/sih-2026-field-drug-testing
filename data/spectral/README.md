# Spectral data — provenance and licence

Measured spectral data underpinning `core/ftr/spectral.py`. **The measurement
files are not committed.** Fetch them:

```sh
python core/tools/fetch_spectral_data.py
```

The script verifies SHA-256 before writing and refuses on a mismatch, so a changed
upstream record is a visible failure rather than a silent difference in results.

## Camera spectral sensitivities

| | |
|---|---|
| Source | Jiang, Liu, Gu & Süsstrunk, *What is the space of spectral sensitivity functions for digital color cameras?* (WACV 2013) |
| Obtained from | Zenodo record [3245883](https://zenodo.org/records/3245883) |
| Files | `camspec_database.txt` (24,473 bytes), `camlist.txt` (848 bytes) |
| SHA-256 | `32a2700478d4f2b6…` / `90fd42186ecb7bc9…` (full values in the fetch script) |
| **Licence** | **CC BY-NC-SA 4.0** |
| Contents | 28 cameras — 22 DSLR, 3 compact, 2 industrial, **1 mobile** (Nokia N900) |
| Measurement | monochromator, integrating sphere, PR655 spectroradiometer |
| Grid | 400–720 nm, 10 nm steps, 33 samples per channel |

### Why it is not vendored

`CC BY-NC-SA` is **non-commercial and share-alike**. Vendoring a share-alike
dataset into a repository whose own licence has not been settled is a decision
nobody on this project has made, and it should not be made by accident through a
`git add`. Fetching it explicitly also keeps the attribution visible instead of
burying a third party's measurement inside our commit history.

**Track E should note the NC clause.** Research and evaluation are clearly fine.
If any of this feeds a deployed system, the licence needs reading — or the
sensitivities need re-measuring, or sourcing from the handset vendors.

Only **one** of the 28 cameras is a mobile sensor, which is the deployment target.
That is a real limitation of this analysis, not a footnote.

## Illuminant spectra and reflectances

From [`colour-science`](https://www.colour-science.org/) (BSD-3-Clause), a
dependency rather than a data file:

- **CIE standard illuminants** — D65, D50, A, FL2, FL11, LED-B3.
- **ColorChecker reflectances** — BabelColor average, 24 patches.
- **CIE 1931 2° standard observer** colour matching functions.

## What is still missing, and it is the important part

There is **no spectral library of NDPS presumptive-test colour developments**, and
no public dataset of colorimetric drug-test strip images. The published
smartphone-colorimetry work (pH strips, peroxide strips, urinalysis, lateral flow)
builds a dataset per study and releases none of it. The problem statement's own
`dataset_link` is empty.

So the "reaction" spectra in every experiment here are **ColorChecker patches
standing in for reagent developments**. They are real measured reflectances of real
surfaces — the *optics* are honest — but they are not chemistry. Substituting NCB
reagent colour standards remains a data change, not an architecture change, and
the submission should say so unprompted.
