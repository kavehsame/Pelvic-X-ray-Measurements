# Pelvic X-ray Measurements Pytest Unit Tests

This folder contains fast unit tests that run outside Slicer with `pytest`.

## Scope

The unit tests focus on code that is deterministic and safe to validate in a normal Python environment:

- pure geometry and math helpers,
- formatting helpers,
- MRML role and node-spec naming helpers,
- folder-workflow path helpers,
- replay-bundle utility functions such as CSV comparison and synthetic-scenario generation.

The full-case replay and live interaction checks complement these unit tests and live in:

- `../end_to_end_replay/`

## Run

```bash
python3 Testing/Python/unit/run_pytest_unit.py
```

Each run creates a new timestamped result folder under:

- `../test_runs/`

## Notes

- Routine Python environments do not ship VTK, so the tests intentionally target the VTK-independent parts of the codebase.
- The geometry module is import-safe without VTK, which allows the pure math helpers to be tested directly while leaving VTK-backed helpers for the Slicer replay path.
