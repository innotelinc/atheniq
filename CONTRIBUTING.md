# Contributing to AthenIQ

Thanks for contributing! Please read the platform docs first —
[docs/stack.md](docs/stack.md) and [docs/Architecture.md](docs/Architecture.md) —
so changes respect the single-responsibility boundaries of the Innotel Platform
Stack.

## Quick rules

1. **Branch naming:** `feature/<slug>`, `fix/<slug>`, `chore/<slug>`.
2. **Commit style:** Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`).
3. **Pull requests:** one logical change per PR, CI green, commit-message policy clean.
4. **Commit messages:** do not include generated-agent attribution or footer text;
   `make check-commits` must pass.
5. Never commit secrets, `.env`, or derived credentials.

## Setup

```bash
./setup.sh              # installs guard hooks, generates .env, preflight checks
make help               # see all targets
```

The attribution guard (`.githooks/` + CI) rejects credit for anyone but the
project owner in commit messages, PR text, and added file lines.

## Verification before opening a PR

```bash
make check-commits
docker compose config --quiet
docker compose --profile gateway --profile openmaic config --quiet
```

Docs changes must keep the [docs/stack.md](docs/stack.md) owns/consumes
boundaries accurate and the landing page in sync.
