# CostOfCare

Know what care costs before you go. Real, published healthcare prices for Austin, TX - hospitals' federally required price-transparency files plus direct-pay lab and imaging rates - compared side by side.

- Plain-English search: type "blood work" or "knee MRI", get the right CPT-coded service
- Provider-by-provider published prices with sources and dates
- Self-pay vs insured (negotiated) rates
- No accounts, no tracking, static site

Stack: Astro static site, deployed on Cloudflare Pages from this repo (auto-deploy on merge to `main`).

## Dev

```
npm install
npm run dev
npm run build   # outputs to dist/
```

## Data

`src/data/` - services (CPT codes), providers, prices. Every price row carries its source. See /about-data on the site for provenance and dates. Prices are information, not quotes.
