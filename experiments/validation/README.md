# Validation Scripts

Quality-check scripts that verify benchmark methodology correctness.

## Current Scripts

### warmup_impact.py

Validates that warmup methodology successfully removes cold-start bias from throughput measurements.

**How to run:**
```bash
python experiments/validation/warmup_impact.py
```

**Expected:** 2-5% throughput improvement (cold-start bias removed)

## Usage from Project Root

All validation scripts should be run from the project root directory:
```bash
# From C:\Users\kevin\Documents\GitHub\sigtekx\
python experiments/validation/warmup_impact.py
```

## Future Expansion

When Phase 4 validation scripts are needed:
- Create `validation/phase4/` subfolder
- Add competitive analysis (CuPy comparison)
- Add custom stage overhead tests
- Add long-duration stability tests

For now, keep it minimal.

---

**Last Updated:** 2025-12-16
**Phase:** 0 → 1 Transition
