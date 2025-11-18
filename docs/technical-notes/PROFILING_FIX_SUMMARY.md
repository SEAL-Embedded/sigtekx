# Python Profiling Hydra Passthrough - Bug Fixes

## Summary

Fixed critical bugs preventing Hydra configuration overrides from working in Python profiling with Nsight tools.

## Root Causes

### Bug 1: Argument Order Issue (cli.ps1)
**Problem**: Flags were added AFTER positional arguments when building prof_helper.py command.

```powershell
# WRONG (old code):
$args = @($Tool, $Target, "--mode", $Mode, "--", "engine.nfft=8192")
# Resulted in: python prof_helper.py nsys latency --mode quick -- engine.nfft=8192
```

**Why it failed**:
- argparse with `nargs=REMAINDER` captures everything after positionals
- The `--mode quick` flag was captured into REMAINDER instead of being parsed
- Result: `args.args = ['--mode', 'quick', '--', 'engine.nfft=8192']`

**Fix**: Reordered to put flags BEFORE positionals (argparse standard):

```powershell
# CORRECT (new code):
$args = @("--mode", $Mode, $Tool, $Target, "--", "engine.nfft=8192")
# Results in: python prof_helper.py --mode quick nsys latency -- engine.nfft=8192
```

**Location**: `scripts/cli.ps1` lines 596-611

---

### Bug 2: Argument Parsing Logic Issue (prof_helper.py)
**Problem**: Code checked for `--` separator in `args.args`, but argparse **consumes** the separator.

```python
# WRONG (old code):
if args.args and args.args[0] == "--":
    target_cmd.extend(args.args[1:])  # Skip the "--"
else:
    # Use defaults (THIS ALWAYS HAPPENED!)
```

**Why it failed**:
- argparse removes the `--` separator when using REMAINDER
- `args.args` would be `['engine.nfft=8192']` not `['--', 'engine.nfft=8192']`
- Condition `args.args[0] == "--"` was always False
- Custom args were never recognized, always fell back to defaults

**Fix**: Simplified to just check if args.args is non-empty:

```python
# CORRECT (new code):
if not args.args:
    # Use profiling defaults
    target_cmd.extend(["experiment=profiling", "+benchmark=profiling"])
else:
    # User provided custom args (argparse already removed the '--')
    target_cmd.extend(args.args)
```

**Location**: `scripts/prof_helper.py` lines 595-614

---

### Bug 3: Benchmark Structure Not Loaded
**Problem**: When providing custom overrides, no benchmark config was loaded, so `benchmark.*` parameters didn't exist.

```python
# WRONG (old code):
if args.args:
    target_cmd.extend(args.args)  # Only user args, no benchmark config!
# Resulted in: python run_latency.py engine.nfft=8192 benchmark.iterations=50
# Error: Key 'benchmark' is not in struct
```

**Why it failed**:
- Hydra requires a config group to be loaded before you can override its parameters
- Without `+benchmark=profiling`, there's no `benchmark` structure
- Overrides like `benchmark.iterations=50` fail because `benchmark` doesn't exist

**Fix**: Always load default benchmark config unless user provides their own:

```python
# CORRECT (new code):
user_has_benchmark = any(arg.startswith('+benchmark=') for arg in args.args)

if not user_has_benchmark:
    # Load default profiling benchmark config (defines benchmark.* structure)
    target_cmd.extend(["experiment=profiling", "+benchmark=profiling"])

# Then add user overrides (will override default values)
if args.args:
    target_cmd.extend(args.args)

# Resulted in: python run_latency.py +benchmark=profiling engine.nfft=8192 benchmark.iterations=50
```

**Location**: `scripts/prof_helper.py` lines 598-614

---

## Industry Standard Pattern

### Python argparse with REMAINDER

The correct pattern for argument passing with argparse REMAINDER:

```python
# Wrapper script (prof_helper.py)
parser.add_argument("--mode", ...)      # Named args FIRST
parser.add_argument("--kernel", ...)
parser.add_argument("tool")             # Then positionals
parser.add_argument("target")
parser.add_argument("args", nargs=argparse.REMAINDER)  # Finally REMAINDER
```

**Key behaviors**:
1. **Flags must come before positionals** when using REMAINDER
2. **`--` separator is consumed** by argparse, never appears in REMAINDER args
3. **Everything after positionals** goes into REMAINDER (unless preceded by `--`)

### Why This Differs from C++ Profiling

C++ profiling is simpler - just pass-through to the executable:

```cpp
// C++ - direct pass-through
int main(int argc, char** argv) {
    // No parsing, just pass flags directly
}
```

Python with Hydra + Nsight requires:
1. **Wrapper layer** (prof_helper.py) to handle Nsight-specific flags
2. **Argument segregation** (Nsight flags vs Hydra configs)
3. **Correct ordering** for argparse compatibility
4. **Config group loading** for Hydra override structure

---

## Testing

### Test Cases

```bash
# Test 1: Simple engine override
iprof nsys latency engine.nfft=8192
# Expected: Loads +benchmark=profiling, overrides engine.nfft

# Test 2: Benchmark parameter override
iprof nsys latency benchmark.iterations=100
# Expected: Loads +benchmark=profiling, overrides benchmark.iterations

# Test 3: Multiple overrides
iprof nsys latency engine.nfft=4096 benchmark.iterations=50
# Expected: Loads +benchmark=profiling, applies both overrides

# Test 4: Custom benchmark config
iprof nsys latency +benchmark=latency benchmark.lock_gpu_clocks=true
# Expected: Loads +benchmark=latency (production), overrides lock_gpu_clocks

# Test 5: Full custom config
iprof nsys latency experiment=ionosphere_hires +benchmark=profiling
# Expected: Uses ionosphere_hires experiment + profiling benchmark
```

### Validation

Run `python scripts/prof_helper.py --help` to see comprehensive documentation.

---

## Files Changed

1. **scripts/cli.ps1** (lines 596-611)
   - Reordered argument construction (flags before positionals)
   - Removed debug output

2. **scripts/prof_helper.py** (lines 461-523, 595-614, 658-664)
   - Fixed argument parsing logic (removed `--` check)
   - Added auto-loading of default benchmark config
   - Updated comprehensive help documentation

3. **CLAUDE.md** (lines 457-506)
   - Updated profiling examples
   - Documented how override system works
   - Clarified simple vs custom config usage

---

## Documentation Updates

- **prof_helper.py --help**: Comprehensive argument order explanation + examples
- **iono help**: Quick reference with common override patterns
- **CLAUDE.md**: Full profiling workflow documentation

---

## Date

2025-11-15
