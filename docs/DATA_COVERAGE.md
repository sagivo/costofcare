# Public data inventory and update boundaries

This repository contains three different kinds of data. Do not add their counts together or call catalog entries parsed local prices.

1. **Hospital price extractions**: `data/hospitals/`, built by our parser from original hospital MRFs. Current patient-search snapshot: `public/data/dataset.json`. Targeted to the CPT code list in `scripts/target_codes.json`, not every item in each raw file.
2. **Public source catalogs**: `data/catalogs/`. Versioned, gzip-compressed JSONL shards, each bounded below GitHub's file-size limit. They locate data that has NOT necessarily been downloaded or parsed.
3. **Reference benchmarks**: NADAC pharmacy acquisition costs and historical Medicare provider/service payment data. These are not patient retail quotes, current cash offers or insurance eligibility checks. CMS hospital metadata identifies facilities but contains no prices.

## Working sources

- Hospital location discovery: https://oria-data.trillianthealth.com/search-index.json . 7,916 directory records at initial retrieval. Used only to locate original MRF URLs. Directory records may include multiple facilities per file and historical versions.
- Hospital MRF seed: https://referencesource.org/hospital-price-transparency-mrf-index/ . License position listed as unknown. Price extraction uses original hospital files; no wholesale copying of publisher prose.
- Cigna first-party monthly TiC discovery: https://www.cigna.com/static/mrf/latest.json . Script resolves the current table of contents, preserves reporting-plan metadata and source update date, and versions the file locators. Public signed URLs expire, so refresh the index rather than reuse expired links.
- UnitedHealthcare first-party catalog: https://transparency-in-coverage.uhc.com/api/v1/uhc/blobs/ . Includes allowed-amount files, index files and in-network files; catalog size does not mean distinct rates or providers.
- CMS data catalog: https://data.cms.gov/data.json . Filtered price/payment/hospital/drug-related metadata and distributions, including historical vintages and alternative versions. License recorded per distribution.
- CMS hospital directory: https://data.cms.gov/provider-data/dataset/xubh-q36u . Source metadata resolves the current CSV rather than hardcoding a dated download path.
- NADAC: https://data.medicaid.gov/dataset/fbb83258-11c7-47f5-8b18-5f8e79f7e704 . Current metadata resolves the weekly CSV. Latest record per NDC is retained; historical weekly observations are not all vendored. Public-domain license recorded in source metadata. Acquisition cost excludes dispensing fees and retail markup.
- Medicare inpatient and outpatient provider/service aggregates: latest series discovered from CMS catalog. Raw source rows retained in compressed shards. Historical claims payments, not current patient estimates.

## Sources located, integration incomplete

Aetna, Humana and Anthem public landing pages are checked and recorded in `data/catalogs/insurer-landing-pages.json`. A fetched page is not an ingested price feed. Their dynamic file discovery and full rate ingestion remain incomplete. State BCBS publishers, additional insurers, state all-payer claims databases, provider cash lists, drug fee schedules and other open sources are not exhaustively covered.

There is no verified exhaustive central list of every public healthcare price source in this project. The catalog is expandable and the coverage report must remain explicit about misses.

## Updates

- `scripts/refresh_public_sources.py`: daily public catalogs and compact benchmarks; bounded downloads preserve old snapshots on failure. Individual status is in `data/catalogs/status.json`.
- `scripts/discover_sources.py`: incremental hospital MRF URL discovery.
- `scripts/refresh_dataset.py`: primary hospital downloads/parsing, explicit failures and last-good snapshot preservation. Daily schedule is not a guarantee every source is checked within 24 hours.
- `scripts/tic_extract.py`: streaming extraction for an explicitly selected in-network TiC file. Install `scripts/requirements.txt`. Retains provider references and price qualifiers; does not pretend unresolved references are local providers. Output capped by row count and marked incomplete when capped. This parser is fixture-tested, not yet validated on a useful production rate sample. No TiC price rows currently power patient search.

Raw nationwide hospital and insurer data can be terabytes. This repository does not contain all raw files. It stores source locators, provenance, bounded normalized outputs and benchmarks. Expanding to every raw source will require a storage/compute design and measured capacity. No paid storage is provisioned, no spending authorized by this implementation.

## Accuracy-first quality work

`data/quality/report.json` reports actual primary-file success counts, per-state/code coverage, source freshness, unresolved geography, missing byte hashes and anomalous ranges. Passing structural checks does not prove clinical equivalence or hospital accuracy. Wide ranges are flagged for review rather than deleted or replaced with a guessed price.

The legacy summary data is not an analytical gold standard: it loses original payer strings and combines plans/settings/modifiers. `scripts/normalize_mrf.py` begins a row-preserving replacement, with an explicit code filter, complete-file scan status, original header/value alignment, source-row ordinal and SHA-256 of downloaded source bytes. `schemas/normalized-record.schema.json` defines the record contract. AVALA is the first real validated-format pilot; nationwide normalized coverage is not claimed.

Priority order: source provenance and correct semantics, row-preserving ingestion, independently checked fixtures and sampled source readback, geography/provider identity, payer/plan/network identity, freshness and revision history, then breadth and applications. A large count with mixed semantics is not a quality achievement.

## Row-preserving expansion

`refresh_normalized.py` and `normalized.yml` process a bounded tranche of previously parsed primary sources, prioritizing missing/old normalized manifests. Every record preserves original qualifiers and byte hash; incomplete parses, invalid CSV widths and files above the output/download/time budget are failures, not silently partial successes. Failure audit is separate and last-good snapshots survive. JSON is validated by a streaming parser, including truncated-document rejection. Daily tranche refresh is not a promise of whole-corpus daily normalization. Original raw fields are preserved rather than normalized into unverified payer/network/provider identities.

### Encoding failures are held out

Strict UTF-8 errors are audited, not silently decoded with replacement characters. A valid source-encoding declaration or independently checked encoding conversion is needed before accepting these files. They remain in failed-attempt coverage, even where a more permissive summary parser previously produced aggregates. Artifact audit success says nothing about excluded-source completeness.

## Independent source readback sample

`source_readback.py` independently downloads up to five small direct CSV sources and uses Python's CSV reader to compare complete header/value arrays at preserved source ordinals. It does not invoke the extraction parser for those comparisons. The sample is deliberately small and biased toward small files; it is not a representative accuracy percentage and cannot validate hospital-authored prices, clinical comparability or attribution. Failures and changed source hashes remain in the published report.

The initial readback found one header difference caused by extraction trimming header whitespace. The original source values matched exactly. Parser version `row-preserving-1.2` now preserves original header strings while using a separate trimmed lookup for matching; existing 1.1 snapshots retain trimmed headers until refreshed. The readback report distinguishes that known transformation from exact header matches.

## Encoding diagnostics

`diagnose_encoding.py` records bounded original HTTP charset/BOM evidence for six direct CSV failures. Compressed containers are excluded from prefix decoding. No automatic legacy-encoding fallback is inferred from byte values. Even a valid UTF-8 prefix does not validate an entire file; these sources remain excluded from the normalized layer until a full strict parse succeeds with supported encoding evidence.

## Invalid summary quarantine

Whole source summaries with negative/non-finite amounts or inverted ranges are excluded from search and successful coverage counts by a shared fail-closed validity check. Their original extracted evidence stays in `data/hospitals`; `data/quality/report.json` lists `quarantined_sources` and reasons. Quarantine does not repair or endorse source amounts. The row-preserving source layer is separate and can retain original values for review, never as a comparable offer.

## Measured lineage and refresh cadence

`data/quality/lineage-freshness.json` compares the exact downloaded byte hashes of summary and row-preserving snapshots, reports extraction-age buckets, parser versions and failure classes. A missing summary hash is unresolved lineage, not a match. Different byte hashes are version-review candidates, not presumed errors. The daily normalized job refreshes at most 120 files per run, two scheduled runs a day (240 per day at most); a complete rotation of about 2,700 files takes at least 12 days of full runs without manual tranches, and failures/new sources can extend that. Daily automation is not a promise that every source is fresh daily. This report does not infer source update age from download time.

The independent readback sample now covers up to twelve distinct hosts selected by deterministic URL-hash ordering from direct CSVs no larger than 3MB, comparing first/middle/last preserved records. This replaces the initial five-smallest-file sample. It remains biased toward small direct CSVs, excludes compressed/JSON/large files and is not a dataset-wide accuracy estimate. Exact and legacy trimmed-header matches are reported separately.

## Failure remediation (parser 1.3)

Sources that failed strict UTF-8 are retried with a full strict Windows-1252 decode. Success is recorded as an inferred encoding on the manifest (`source_encoding_inferred`, `strict_utf8_failure`) and on every record; the original bytes stay identified by `source_sha256`. This is a reasoned inference, not a source declaration, and affects text fields (descriptions, payer names), not numeric cells. Sources that decode in neither are still withheld. CSV rows whose cell count differs from the header are now preserved verbatim with a `row_width_mismatch` flag (never padded or realigned, code match marked alignment-unverified) instead of rejecting the whole file; semantic QA skips them. A UTF-8 BOM before JSON no longer routes a file to the CSV parser. `retry_failed` and `source_timeout` workflow inputs allow long-running sources up to the per-source limit given. Previously accepted 1.1/1.2 snapshots are unchanged until refreshed.

## Failure remediation outcome and refresh cadence (Oct 22)
After parser 1.3 retries, the row-preserving layer had 2,703 files and 8,511,239 records, with 8 failed attempts (6 old encoding errors awaiting retry, 1 HTTP 403, 1 held HTTP 429 on whs.org). 262 files use the flagged inferred cp1252 encoding and 297,391 records are width-flagged and preserved verbatim. The scheduled normalized job now runs twice daily at up to 120 files per run. These are ceilings: repository growth (.git about 666 MB), source failures and runner time can lower them, and extraction age is not source update age.
