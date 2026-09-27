# ReviewRing

**A fake review looks like any other review. A batch of them doesn't.** Paste a Google Maps link and ReviewRing finds groups of reviewer accounts that reviewed the same unrelated businesses in distant cities, then shows what the rating looks like without them.

> Work in progress for the SerpApi India Hackathon 2026 (Knowledge & Public Interest track). This README is a stub; the full version comes at the end of the build.

## Status

| Part | State |
|---|---|
| SerpApi gateway (cache, ledger, budget guard, key redaction) | done |
| Command-line interface: `budget`, `resolve`, `probe`, `dry-run`, `ledger`, `purge-data` | done |
| Analysis engine, web app, Chrome extension, demo mode | in progress |

## Setup (backend)

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env          # add SERPAPI_API_KEY; the file is gitignored
cd backend
uv sync
uv run pytest                 # never touches the network
uv run reviewring budget      # free Account API call: shows searches left
```

Every command that could spend searches shows the estimated cost and the remaining budget, and does nothing without `--yes`. `uv run reviewring dry-run <maps link>` lists exactly what an analysis would request, using only the local cache.

## Local data and privacy

The cache in `data/` holds reviewer names and other personal data from Google Maps. It is gitignored and never committed. Delete it at any time with:

```bash
uv run reviewring purge-data --yes
```

API keys live only in `.env` and in the backend process. They are never logged, returned by an endpoint or sent to the browser.

## Contributing

```bash
pre-commit install            # gitleaks + the fixture leak check run on every commit
```

## License

MIT
