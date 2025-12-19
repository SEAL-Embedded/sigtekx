#!/usr/bin/env python
"""Quick progress checker for running experiments."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from analysis.cli import load_data

def check_progress():
    """Check current experiment coverage."""
    data = load_data(Path('../artifacts/data'))

    print('=== EXPERIMENT PROGRESS ===\n')

    streaming_100k = data[
        (data['sample_rate_category'] == '100kHz') &
        (data['engine_mode'] == 'streaming')
    ]

    print(f'100kHz STREAMING total: {len(streaming_100k)} rows\n')

    if 'benchmark_type' in streaming_100k.columns:
        by_type = streaming_100k['benchmark_type'].value_counts().to_dict()

        for btype in ['latency', 'throughput', 'realtime']:
            count = by_type.get(btype, 0)
            status = '✅' if count > 0 else '⏳'
            expected = {
                'latency': 45,    # 5 NFFT × 3 channels × 3 overlap
                'throughput': 45, # 5 NFFT × 3 channels × 3 overlap
                'realtime': 15    # Already complete
            }[btype]
            print(f'{status} {btype:12s}: {count:3d} / {expected} rows')

    print('\n' + '='*30)
    print('Run this script again to check progress:')
    print('  python experiments/check_progress.py')

if __name__ == '__main__':
    check_progress()
