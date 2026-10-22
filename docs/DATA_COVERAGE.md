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
