# Contributing to MolTrace

Thanks for your interest in MolTrace.

First, an important clarification about what this repository is:

> **MolTrace is source-available, not open source.** The code is published under
> the **Business Source License 1.1** (see [`LICENSE`](LICENSE)) so that
> customers, security reviewers, and evaluators can read, audit, test, and
> learn from it. It is a **commercial product**: production use requires a
> commercial license, and copyright in the first-party code is held by MolTrace.

Because of that, contribution works a little differently than in a typical
open-source project.

## What we welcome

- **Bug reports.** Open a GitHub issue with a clear description, the affected
  area (backend / frontend), a commit SHA or version, and reproduction steps.
- **Feature requests and feedback.** Issues and discussions are great for this.
- **Security reports.** Please **do not** use public issues — follow
  [`SECURITY.md`](SECURITY.md) for private disclosure.
- **Documentation corrections.** Small doc fixes are easy to accept (see CLA
  note below).

## Code contributions and the CLA

We do accept code contributions, but to keep MolTrace's licensing coherent —
including the ability to offer commercial licenses and to relicense the work to
the Change License on the Change Date — **all non-trivial code contributions
require a signed Contributor License Agreement (CLA)** assigning the necessary
rights to MolTrace.

If you would like to contribute code:

1. **Open an issue first** to discuss the change, so we can confirm it fits the
   roadmap before you invest time.
2. We will share the CLA to sign before a pull request can be merged.
3. Keep pull requests focused and accompanied by tests where applicable.

If you are not able or willing to sign a CLA, we can still act on your bug
report or design suggestion — we will just implement it ourselves.

## Development conventions (for accepted contributions)

- **Backend** (`moltrace_backend/`, package `nmrcheck`): Python, FastAPI,
  SQLAlchemy. Lint/format with `ruff`, type-check with `mypy`, test with
  `pytest`. The CI runs the suite across a shard matrix; new code needs tests.
- **Frontend** (`moltrace_frontend/`): Next.js / React / TypeScript, `pnpm`,
  `vitest`. Run `pnpm lint`, `pnpm test`, and `pnpm build` before submitting.
- **Contracts first.** For any change that crosses the frontend/backend
  boundary, update the FastAPI routes/models and regenerate the typed schema
  before touching the frontend — the generated `schema.d.ts` is the binding
  contract.
- **Conventional commits.** Follow the existing commit-message style in the
  history (`type(scope): summary`).

## Code of conduct

Be respectful and professional in issues, discussions, and reviews. Harassment
or abusive behavior is not tolerated.

## Questions

For licensing or commercial-use questions, contact
[licensing@moltrace.co](mailto:licensing@moltrace.co). For security, see
[`SECURITY.md`](SECURITY.md).
