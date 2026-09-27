# Decisions

One line of reasoning per decision not fixed by IMPLEMENTATION.md.

- **Backend layout:** `backend/` is a uv project with a `src/reviewring` package and `tests/`; the CLI entry point is `reviewring`. Standard uv layout.
- **Tunables file:** all *(tunable)* values live in `config/reviewring.toml`; a gitignored `data/config.toml` may override any of them locally. One committed source of truth, per spec section 0.
- **Ledger status column:** the ledger also records each request's outcome (`ok`, `empty`, `error`); only `ok` and `empty` count toward the local caps, because SerpApi bills neither errors nor failures but does bill empty results.
- **Account email:** it is stripped before anything is stored (Rule 4). The leak check therefore rejects any email address at all, which covers the account email without keeping a copy of it.
- **Raw responses for errors:** HTTP errors (401/429/5xx) are stored in `raw_responses` with status `error` for debugging but are never served as cache hits.
