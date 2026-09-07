# SIH 2026 problem statement dataset

Full official problem statement list, kept here so the repo is self-contained.

| | |
|---|---|
| Records | 233 (176 Software, 57 Hardware) |
| Themes | 17 |
| Scraped | **2026-09-03** |
| Deadline on every PS | 30 September 2026 |

## Files

- `sih2026_ps.json` — full records including complete `description` text
- `sih2026_ps.csv` — same data, flat

## Provenance

Mirrored from [`vedantchalke36/sih-2026-problem-statements`](https://github.com/vedantchalke36/sih-2026-problem-statements),
which scrapes the official portal at https://sih.gov.in/sih2026PS.
Dataset licensed **CC BY 4.0** by that repository.

## ⚠️ The `ideas` field is stale

`ideas` (e.g. `"1/500"`) is the submission count at scrape time — **2026-09-03**. It reads near-zero
for almost every statement, which reflects an early capture, not low competition. **Check the live
count on the portal before drawing any conclusion about how contested a PS is.**

## Our selection

**SIH26231 — Digital Companion for Field Drug Testing** (MHA / Narcotics Control Bureau, Software,
MedTech). See [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Quick queries

```bash
# one problem statement, full text
python3 -c "import json;d={x['ps_number']:x for x in json.load(open('data/sih2026_ps.json'))};x=d['SIH26231'];print(x['title'],'\n',x['org'],'\n\n',x['description'])"

# every software PS in a theme
python3 -c "import json;[print(x['ps_number'],x['title']) for x in json.load(open('data/sih2026_ps.json')) if x['category']=='Software' and 'Blockchain' in x['theme']]"

# keyword search across titles and descriptions
python3 -c "import json,sys,re;p=re.compile(sys.argv[1],re.I);[print(x['ps_number'],'|',x['title'][:90]) for x in json.load(open('data/sih2026_ps.json')) if p.search(x['title']+x['description'])]" forensic
```
