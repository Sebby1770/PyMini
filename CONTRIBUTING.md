# Contributing

Thanks for improving PyMini.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
make install-dev
make verify
```

## Project rules

- Keep parsing and optimization in the shared `pymini.pipeline` path.
- Preserve evaluator behavior unless a documented language change is intentional.
- Add evaluator/VM parity tests when extending the bytecode subset.
- Keep strict mypy and Ruff clean; avoid untyped runtime escape hatches.
- Keep total test coverage at or above the enforced 75% floor.
- Treat PyMini as an educational interpreter, not a security sandbox.
- Record user-visible changes under `Unreleased` in `CHANGELOG.md`.

Pull requests should include examples, tests, verification output, and documentation updates
for language or bytecode changes.
