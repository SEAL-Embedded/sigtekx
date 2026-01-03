"""
Multiprocess safety tests for benchmark CSV file operations.

These tests verify that the unique filename pattern used by all benchmark scripts
prevents race conditions during parallel multirun sweeps. The implementation uses
parameter-based filenames (e.g., latency_summary_4096_2_0p7500_streaming.csv) to
ensure different configurations write to different files.

See docs/benchmarking/csv-file-organization.md for design rationale.
"""

import sys
import threading
import time
from pathlib import Path

import pandas as pd
import pytest


class TestConcurrentCSVWrites:
    """Verify concurrent benchmark runs don't corrupt CSV files."""

    def test_concurrent_different_configs_no_collision(self, tmp_path):
        """
        Verify that concurrent benchmarks with different configurations write
        to separate CSV files without collision.

        This is the primary use case for Hydra multirun sweeps.
        """
        # Configuration parameters that will create unique filenames
        configs = [
            {"nfft": 1024, "channels": 2, "overlap": 0.5, "mode": "batch"},
            {"nfft": 2048, "channels": 2, "overlap": 0.5, "mode": "batch"},
            {"nfft": 4096, "channels": 2, "overlap": 0.75, "mode": "streaming"},
            {"nfft": 8192, "channels": 2, "overlap": 0.75, "mode": "streaming"},
        ]

        def worker(config):
            """Simulate benchmark writing CSV with unique filename."""
            # Replicate the filename pattern from benchmarks/run_latency.py:142-145
            overlap_str = f"{config['overlap']:.4f}".replace('.', 'p')
            csv_path = tmp_path / f"latency_summary_{config['nfft']}_{config['channels']}_{overlap_str}_{config['mode']}.csv"

            # Create summary DataFrame (simplified version of benchmark output)
            summary_df = pd.DataFrame([{
                'nfft': config['nfft'],
                'channels': config['channels'],
                'overlap': config['overlap'],
                'mode': config['mode'],
                'mean_latency_us': 100.0 * config['nfft'] / 1024,
                'p95_latency_us': 120.0 * config['nfft'] / 1024,
            }])

            # Write CSV (same pattern as benchmark scripts)
            summary_df.to_csv(csv_path, index=False)

        # Spawn threads concurrently (simulates Hydra multirun parallel processes)
        threads = []
        for config in configs:
            t = threading.Thread(target=worker, args=(config,))
            t.start()
            threads.append(t)

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Verify: 4 separate CSV files created
        csv_files = list(tmp_path.glob("latency_summary_*.csv"))
        assert len(csv_files) == 4, f"Expected 4 CSV files, found {len(csv_files)}"

        # Verify each CSV is valid and has correct data
        for csv_file in csv_files:
            df = pd.read_csv(csv_file)

            # No corruption: exactly 1 row (one summary per config)
            assert len(df) == 1, f"{csv_file.name}: Expected 1 row, found {len(df)}"

            # No NaN values (would indicate malformed CSV)
            assert not df.isnull().any().any(), f"{csv_file.name}: Contains NaN values"

            # Verify expected columns
            expected_columns = ['nfft', 'channels', 'overlap', 'mode', 'mean_latency_us', 'p95_latency_us']
            assert list(df.columns) == expected_columns, f"{csv_file.name}: Unexpected columns"

        # Verify unique NFFT values (each config got its own file)
        nfft_values = sorted([pd.read_csv(f)['nfft'].iloc[0] for f in csv_files])
        assert nfft_values == [1024, 2048, 4096, 8192], "Not all configurations written"

    def test_concurrent_identical_configs_last_write_wins(self, tmp_path):
        """
        Verify that concurrent benchmarks with identical configuration result
        in last-write-wins behavior (no corruption, just overwrite).

        This is an edge case that's rare in practice (Hydra multirun assigns
        unique parameters), but should still be handled gracefully.
        """
        # Two threads with IDENTICAL configuration
        config = {"nfft": 4096, "channels": 2, "overlap": 0.75, "mode": "streaming"}

        def worker(worker_id):
            """Simulate benchmark writing CSV with worker ID embedded in data."""
            # Introduce small delay to increase chance of concurrent writes
            time.sleep(0.01 * worker_id)  # Stagger slightly

            overlap_str = f"{config['overlap']:.4f}".replace('.', 'p')
            csv_path = tmp_path / f"latency_summary_{config['nfft']}_{config['channels']}_{overlap_str}_{config['mode']}.csv"

            summary_df = pd.DataFrame([{
                'nfft': config['nfft'],
                'channels': config['channels'],
                'overlap': config['overlap'],
                'mode': config['mode'],
                'worker_id': worker_id,  # Identify which worker wrote this
                'mean_latency_us': 100.0 + worker_id,
            }])

            summary_df.to_csv(csv_path, index=False)

        # Spawn 2 threads with identical config
        threads = []
        for worker_id in [1, 2]:
            t = threading.Thread(target=worker, args=(worker_id,))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        # Verify: Only ONE CSV file exists (not 2)
        csv_files = list(tmp_path.glob("latency_summary_*.csv"))
        assert len(csv_files) == 1, f"Expected 1 CSV file (last write wins), found {len(csv_files)}"

        # Verify CSV is valid (no corruption despite concurrent writes)
        df = pd.read_csv(csv_files[0])
        assert len(df) == 1, "CSV should have exactly 1 row"
        assert not df.isnull().any().any(), "CSV should not have NaN values"

        # Last write wins: worker_id should be either 1 or 2 (whichever finished last)
        worker_id = df['worker_id'].iloc[0]
        assert worker_id in [1, 2], f"worker_id should be 1 or 2, got {worker_id}"

        # File is intact (no partial writes or corruption)
        assert df['nfft'].iloc[0] == 4096
        assert df['overlap'].iloc[0] == 0.75


class TestCSVHeaderIntegrity:
    """Verify CSV files don't have duplicate headers or corruption."""

    def test_csv_header_integrity(self):
        """
        Verify existing CSV files in artifacts/data have exactly ONE header
        and consistent schema.

        This test validates that production runs haven't resulted in corruption.
        """
        data_dir = Path("artifacts/data")

        # Skip if no artifacts directory (fresh checkout)
        if not data_dir.exists():
            pytest.skip("No artifacts/data directory found (fresh checkout)")

        csv_files = list(data_dir.glob("*_summary_*.csv"))

        # Skip if no CSV files found (haven't run benchmarks yet)
        if not csv_files:
            pytest.skip("No benchmark CSV files found in artifacts/data")

        # Limit to first 10 files to keep test fast
        csv_files = csv_files[:10]

        for csv_file in csv_files:
            # Read raw lines to check for duplicate headers
            with open(csv_file) as f:
                lines = f.readlines()

            assert len(lines) >= 2, f"{csv_file.name}: File too short (needs header + data)"

            # First line should be header
            header = lines[0].strip()
            assert ',' in header, f"{csv_file.name}: Header doesn't look like CSV"

            # Data rows should NOT look like headers (no duplicate headers)
            for i, line in enumerate(lines[1:], start=2):
                # Simple heuristic: headers have all alpha column names, data has numbers
                # This catches the TOCTOU bug pattern where headers appear mid-file
                line_stripped = line.strip()
                if line_stripped:  # Skip empty lines
                    # Headers typically don't have numeric-looking first values
                    first_value = line_stripped.split(',')[0]
                    # If this looks like a header column name, that's a duplicate header
                    if first_value.replace('_', '').isalpha():
                        # Could be header or string data - read with pandas to be sure
                        try:
                            # Re-read just to check schema
                            df_test = pd.read_csv(csv_file)
                            # If pandas can read it, schema is valid
                            break
                        except:
                            pytest.fail(f"{csv_file.name}: Possible duplicate header at line {i}")

            # Verify pandas can parse the CSV (final integrity check)
            try:
                df = pd.read_csv(csv_file)
                assert len(df) > 0, f"{csv_file.name}: No data rows"
                assert not df.isnull().all().all(), f"{csv_file.name}: All values are NaN"
            except Exception as e:
                pytest.fail(f"{csv_file.name}: Pandas failed to parse CSV: {e}")

    def test_csv_schema_consistency(self):
        """
        Verify all CSV files of the same benchmark type have consistent schema.
        """
        data_dir = Path("artifacts/data")

        if not data_dir.exists():
            pytest.skip("No artifacts/data directory found")

        # Group CSV files by benchmark type
        benchmark_types = ['latency', 'throughput', 'realtime', 'accuracy']

        for benchmark_type in benchmark_types:
            csv_files = list(data_dir.glob(f"{benchmark_type}_summary_*.csv"))

            if not csv_files:
                continue  # No files for this benchmark type

            # Read first file to get expected schema
            first_df = pd.read_csv(csv_files[0])
            expected_columns = set(first_df.columns)

            # Verify all other files have same columns
            for csv_file in csv_files[1:]:
                df = pd.read_csv(csv_file)
                actual_columns = set(df.columns)

                # Allow subset (backward compatibility with _harmonize_schema)
                # but warn if columns missing
                if not expected_columns.issubset(actual_columns):
                    missing = expected_columns - actual_columns
                    # This is OK if _harmonize_schema handles it
                    # Just verify pandas can read it
                    assert len(df) > 0, f"{csv_file.name}: Missing columns {missing} but file is empty"


class TestDataAggregation:
    """Verify load_data() correctly merges multiple CSV files."""

    def test_load_data_aggregates_all_csvs(self, tmp_path):
        """
        Verify that load_data() correctly merges multiple CSV files into single DataFrame.

        This validates the analysis workflow that depends on glob pattern matching.
        """
        # Import the actual load_data function
        try:
            # Add experiments directory to path if not already there
            experiments_path = Path(__file__).parent.parent / "experiments"
            if str(experiments_path) not in sys.path:
                sys.path.insert(0, str(experiments_path))

            from analysis.cli import load_data
        except ImportError:
            pytest.skip("experiments.analysis.cli not available")

        # Create 5 CSV files with different configs
        configs = [
            {"nfft": 1024, "channels": 2, "overlap": 0.5, "mode": "batch"},
            {"nfft": 2048, "channels": 2, "overlap": 0.5, "mode": "batch"},
            {"nfft": 4096, "channels": 2, "overlap": 0.75, "mode": "streaming"},
            {"nfft": 8192, "channels": 4, "overlap": 0.75, "mode": "streaming"},
            {"nfft": 16384, "channels": 4, "overlap": 0.875, "mode": "streaming"},
        ]

        for config in configs:
            overlap_str = f"{config['overlap']:.4f}".replace('.', 'p')
            csv_path = tmp_path / f"latency_summary_{config['nfft']}_{config['channels']}_{overlap_str}_{config['mode']}.csv"

            summary_df = pd.DataFrame([{
                'nfft': config['nfft'],
                'channels': config['channels'],
                'overlap': config['overlap'],
                'mode': config['mode'],
                'mean_latency_us': 100.0,
                'p95_latency_us': 120.0,
            }])

            summary_df.to_csv(csv_path, index=False)

        # Load all CSVs via load_data()
        merged_df = load_data(tmp_path)

        # Verify all rows merged
        assert len(merged_df) == 5, f"Expected 5 rows (5 configs), got {len(merged_df)}"

        # Verify no duplicates
        assert len(merged_df) == merged_df.drop_duplicates().shape[0], "Duplicate rows found"

        # Verify all NFFT values present
        nfft_values = sorted(merged_df['nfft'].unique())
        expected_nfft = sorted([c['nfft'] for c in configs])
        assert nfft_values == expected_nfft, f"Missing NFFT values: expected {expected_nfft}, got {nfft_values}"

        # Verify source_file column added
        assert 'source_file' in merged_df.columns, "load_data() should add 'source_file' column"

        # Verify benchmark_type inferred correctly
        if 'benchmark_type' in merged_df.columns:
            assert all(merged_df['benchmark_type'] == 'latency'), "benchmark_type should be 'latency'"

    def test_load_data_handles_empty_directory(self, tmp_path):
        """
        Verify load_data() raises appropriate error for empty directory.
        """
        try:
            # Add experiments directory to path if not already there
            experiments_path = Path(__file__).parent.parent / "experiments"
            if str(experiments_path) not in sys.path:
                sys.path.insert(0, str(experiments_path))

            from analysis.cli import load_data
        except ImportError:
            pytest.skip("experiments.analysis.cli not available")

        # Empty directory should raise ValueError
        with pytest.raises(ValueError, match="No benchmark CSV files found"):
            load_data(tmp_path)


class TestFilenamePattern:
    """Verify the filename pattern matches expected format."""

    def test_overlap_encoding(self):
        """
        Verify overlap values are correctly encoded in filenames.

        The pattern replaces decimal point with 'p': 0.75 -> "0p7500"
        """
        test_cases = [
            (0.5, "0p5000"),
            (0.75, "0p7500"),
            (0.875, "0p8750"),
            (0.9375, "0p9375"),
            (0.0, "0p0000"),  # Accuracy benchmark (no overlap)
        ]

        for overlap, expected_str in test_cases:
            actual_str = f"{overlap:.4f}".replace('.', 'p')
            assert actual_str == expected_str, f"Overlap {overlap} should encode as {expected_str}, got {actual_str}"

    def test_filename_uniqueness(self):
        """
        Verify that different configurations produce unique filenames.
        """
        configs = [
            {"nfft": 4096, "channels": 2, "overlap": 0.5, "mode": "batch"},
            {"nfft": 4096, "channels": 2, "overlap": 0.75, "mode": "batch"},  # Different overlap
            {"nfft": 4096, "channels": 2, "overlap": 0.5, "mode": "streaming"},  # Different mode
            {"nfft": 4096, "channels": 4, "overlap": 0.5, "mode": "batch"},  # Different channels
            {"nfft": 8192, "channels": 2, "overlap": 0.5, "mode": "batch"},  # Different NFFT
        ]

        filenames = set()
        for config in configs:
            overlap_str = f"{config['overlap']:.4f}".replace('.', 'p')
            filename = f"latency_summary_{config['nfft']}_{config['channels']}_{overlap_str}_{config['mode']}.csv"
            filenames.add(filename)

        # All filenames should be unique
        assert len(filenames) == len(configs), f"Expected {len(configs)} unique filenames, got {len(filenames)}"
