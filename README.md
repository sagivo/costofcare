# CostOfCare

Search-first healthcare price explorer, built with Astro and deployed to Cloudflare Pages through GitHub.

## Dataset

Our Python pipeline downloads hospital-published machine-readable files. JSON, CMS wide/tall CSV, gzip and ZIP are supported. Only explicit published dollar amounts are used; percentage/algorithm rates are not converted into invented dollar estimates. Primary-source URLs, source update dates, extraction timestamps and download failures are retained.

`data/registry.json` contains source discovery records, not proof of parsed hospital coverage. ReferenceSource and Trilliant Health Oria are used as URL discovery leads, not copied price datasets. Multi-location files are counted once. Search coverage is currently far smaller than the thousands-of-hospitals goal.

`public/data/dataset.json` is the downloadable search snapshot. The original Austin-only secondary-source pages are retained under `/service/` as legacy pages; they are not included in new primary-source search.

## Run

```
npm ci
npm run dev
python3 scripts/test_parser.py
python3 scripts/discover_sources.py
python3 scripts/refresh_dataset.py --limit 10 --workers 4 --max-mb 700 --registry data/registry.json
python3 scripts/build_dataset.py
npm run build
```

## Daily refresh

`.github/workflows/refresh.yml` runs once a day. It expands URL discovery incrementally, attempts discovered primary files, and commits successful extraction snapshots and failure audits. It has a 5-hour cap and 700MB per-source download cap; files above that cap are explicitly failed. A daily job is not a guarantee all sources were refreshed daily. Previous good data survives failures. No paid service is provisioned.

Insurance rates are not patient out-of-pocket estimates or evidence of network eligibility. Ranges may span settings, billing classes, modifiers and plans. No medical advice. Verify exact code and all-in estimate with the provider.

## Expanded public sources

See [data coverage and limitations](docs/DATA_COVERAGE.md). `scripts/refresh_public_sources.py` and the separate daily public-sources workflow refresh insurer file catalogs, hospital locators, CMS price/payment catalog metadata, the CMS facility directory, NADAC latest-per-NDC benchmarks, and historical Medicare inpatient/outpatient provider/service rows. These are distinct data layers, not additional local price coverage. Large catalogs use normal gzip JSONL shards with manifests. No hacks or giant raw files.
