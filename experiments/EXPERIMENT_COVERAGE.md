# Experiment Coverage Status

**Last Updated:** 2025-12-18

## Current Coverage

### BATCH Mode
- ✅ **100kHz latency**: Complete
- ✅ **100kHz throughput**: Complete
- ✅ **48kHz latency**: Complete
- ✅ **48kHz throughput**: Complete

### STREAMING Mode
- ⚠️ **100kHz latency**: **MISSING** (0 rows)
- ❌ **100kHz throughput**: **MISSING** (0 rows)
- ✅ **100kHz realtime**: Complete (15 rows)
- ✅ **48kHz latency**: Complete (5 rows)
- ✅ **48kHz realtime**: Complete

## Critical Gaps for Methods Paper

The Methods Paper (Tab 2: BATCH vs STREAMING) needs:
1. ❌ **100kHz STREAMING latency** - for overhead comparison
2. ❌ **100kHz STREAMING throughput** - for sustained FPS comparison

Currently, 100kHz STREAMING only has realtime data, which:
- ✅ Has p99_latency_us (median: 6912.7 μs)
- ✅ Has calculated FPS (max: 194.6)
- ❌ Missing proper latency benchmark data
- ❌ Missing proper throughput benchmark data

## Quick Fix Commands

### Fill Critical Gaps (~10 minutes)
```bash
# Run BOTH missing 100kHz STREAMING experiments
snakemake --cores 4 --snakefile experiments/Snakefile \
  run_baseline_streaming_100k_latency \
  run_baseline_streaming_100k_throughput
```

### Verify After Running
```bash
# Check coverage
cd experiments
python -c "
from pathlib import Path
from analysis.cli import load_data

data = load_data(Path('../artifacts/data'))
streaming_100k = data[(data['sample_rate_category'] == '100kHz') & (data['engine_mode'] == 'streaming')]

print(f'100kHz STREAMING total: {len(streaming_100k)} rows')
print(f'By benchmark: {streaming_100k[\"benchmark_type\"].value_counts().to_dict()}')
print(f'\nExpected: latency, throughput, realtime')
"
```

## Dashboard Access

```bash
# Preferred command (direct)
streamlit run experiments/streamlit/app.py --server.port 8501

# Alternative (via CLI)
sigx dashboard

# Open in browser
http://localhost:8501
```

## Expected Results After Fix

After running the missing experiments, you should see:
- **STREAMING Mode section** (Methods Paper Tab 2):
  - ✅ P99 Latency: ~6913 μs (currently showing)
  - ✅ Sustained FPS: ~194.6 (currently showing)
  - ✅ Latency comparison chart: BATCH vs STREAMING (p99)
  - ✅ All tabs functional with complete data

## Experiment Matrix (Complete)

| Sample Rate | Mode | Benchmark | Status | Rows |
|-------------|------|-----------|--------|------|
| 100kHz | BATCH | latency | ✅ Complete | Many |
| 100kHz | BATCH | throughput | ✅ Complete | Many |
| 100kHz | STREAMING | latency | ❌ **MISSING** | 0 |
| 100kHz | STREAMING | throughput | ❌ **MISSING** | 0 |
| 100kHz | STREAMING | realtime | ✅ Complete | 15 |
| 48kHz | BATCH | latency | ✅ Complete | Many |
| 48kHz | BATCH | throughput | ✅ Complete | Many |
| 48kHz | STREAMING | latency | ✅ Complete | 5 |
| 48kHz | STREAMING | realtime | ✅ Complete | Many |

## Notes

- **Realtime benchmarks** track deadline compliance, RTF, jitter
- **Latency benchmarks** track mean/p99 latency with detailed distributions
- **Throughput benchmarks** track sustained FPS, bandwidth, GPU utilization
- All three are needed for complete STREAMING mode characterization
