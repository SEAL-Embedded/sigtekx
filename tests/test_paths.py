"""Tests for paths module."""

import os
from datetime import datetime
from pathlib import Path

import pytest

from ionosense_hpc.utils import paths


@pytest.fixture(autouse=True)
def _reset_nsight_cache(monkeypatch):
    """Ensure Nsight discovery caches do not leak between tests."""
    paths.get_nsight_cli.cache_clear()
    paths.get_nsight_gui.cache_clear()
    yield
    paths.get_nsight_cli.cache_clear()
    paths.get_nsight_gui.cache_clear()


class TestRepoRoot:
    """Test _repo_root() function."""

    def test_repo_root_found(self, monkeypatch, tmp_path: Path):
        """Test that _repo_root successfully finds pyproject.toml."""
        # Create a project structure with pyproject.toml
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "pyproject.toml").touch()

        # Create nested paths.py file
        fake_file = project_root / "src" / "utils" / "paths.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.touch()

        # Patch __file__ to point to our fake paths.py
        monkeypatch.setattr(paths, "__file__", str(fake_file))

        # Should find the project root
        result = paths._repo_root()
        assert result == project_root
        assert (result / "pyproject.toml").exists()

    def test_repo_root_not_found(self, monkeypatch, tmp_path: Path):
        """Test that _repo_root raises FileNotFoundError when pyproject.toml is not found."""
        # Create a fake 'paths.py' file deep inside the temporary directory
        fake_file_path = tmp_path / "fake_project" / "src" / "paths.py"
        fake_file_path.parent.mkdir(parents=True, exist_ok=True)
        fake_file_path.touch()

        # Patch the __file__ attribute
        monkeypatch.setattr(paths, "__file__", str(fake_file_path))

        # Assert that the function raises the expected error
        with pytest.raises(FileNotFoundError, match="Project root not found"):
            paths._repo_root()


class TestSanitizeComponent:
    """Test _sanitize_component() function."""

    def test_alphanumeric_unchanged(self):
        """Test that alphanumeric strings are unchanged."""
        assert paths._sanitize_component("benchmark123") == "benchmark123"
        assert paths._sanitize_component("Test_Name-456") == "Test_Name-456"

    def test_special_chars_replaced(self):
        """Test that special characters are replaced with hyphens."""
        assert paths._sanitize_component("test@benchmark") == "test-benchmark"
        assert paths._sanitize_component("my benchmark!") == "my-benchmark"
        assert paths._sanitize_component("data/analysis") == "data-analysis"

    def test_leading_trailing_stripped(self):
        """Test that leading/trailing hyphens and underscores are stripped."""
        assert paths._sanitize_component("__test__") == "test"
        assert paths._sanitize_component("--benchmark--") == "benchmark"
        assert paths._sanitize_component("_-test-_") == "test"

    def test_empty_string_fallback(self):
        """Test that empty or all-special-char strings fallback to 'benchmark'."""
        assert paths._sanitize_component("") == "benchmark"
        assert paths._sanitize_component("   ") == "benchmark"
        assert paths._sanitize_component("@#$%") == "benchmark"
        assert paths._sanitize_component("---") == "benchmark"

    def test_normalize_benchmark_name(self):
        """Test the normalize_benchmark_name wrapper."""
        assert paths.normalize_benchmark_name("My Test!") == "My-Test"
        assert paths.normalize_benchmark_name("latency/throughput") == "latency-throughput"


class TestEnsure:
    """Test _ensure() function."""

    def test_creates_missing_directory(self, tmp_path: Path):
        """Test that _ensure creates missing directories."""
        test_dir = tmp_path / "new" / "nested" / "dir"
        assert not test_dir.exists()

        result = paths._ensure(test_dir)

        assert result == test_dir
        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_returns_existing_directory(self, tmp_path: Path):
        """Test that _ensure returns existing directories unchanged."""
        test_dir = tmp_path / "existing"
        test_dir.mkdir()

        result = paths._ensure(test_dir)

        assert result == test_dir
        assert test_dir.exists()


class TestArtifactsRoot:
    """Test get_artifacts_root() and get_output_root()."""

    def test_default_artifacts_root(self, monkeypatch, tmp_path: Path):
        """Test default artifacts root location."""
        # Clear any env var
        monkeypatch.delenv("IONO_OUTPUT_ROOT", raising=False)

        # Mock repo root
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "pyproject.toml").touch()
        fake_file = project_root / "src" / "paths.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.touch()
        monkeypatch.setattr(paths, "__file__", str(fake_file))

        result = paths.get_artifacts_root()

        assert result == project_root / "artifacts"
        assert result.exists()

    def test_env_override_artifacts_root(self, monkeypatch, tmp_path: Path):
        """Test that IONO_OUTPUT_ROOT env var overrides default."""
        custom_root = tmp_path / "custom_artifacts"
        monkeypatch.setenv("IONO_OUTPUT_ROOT", str(custom_root))

        result = paths.get_artifacts_root()

        assert result == custom_root
        assert result.exists()

    def test_output_root_alias(self, monkeypatch, tmp_path: Path):
        """Test that get_output_root() is an alias for get_artifacts_root()."""
        custom_root = tmp_path / "output"
        monkeypatch.setenv("IONO_OUTPUT_ROOT", str(custom_root))

        result = paths.get_output_root()

        assert result == paths.get_artifacts_root()


class TestBenchmarksRoot:
    """Test get_benchmarks_root()."""

    def test_default_benchmarks_root(self, monkeypatch, tmp_path: Path):
        """Test default benchmarks root location."""
        monkeypatch.delenv("IONO_BENCH_DIR", raising=False)
        custom_artifacts = tmp_path / "artifacts"
        monkeypatch.setenv("IONO_OUTPUT_ROOT", str(custom_artifacts))

        result = paths.get_benchmarks_root()

        assert result == custom_artifacts / "benchmarks"
        assert result.exists()

    def test_env_override_benchmarks_root(self, monkeypatch, tmp_path: Path):
        """Test that IONO_BENCH_DIR env var overrides default."""
        custom_bench = tmp_path / "custom_benchmarks"
        monkeypatch.setenv("IONO_BENCH_DIR", str(custom_bench))

        result = paths.get_benchmarks_root()

        assert result == custom_bench
        assert result.exists()


class TestBenchmarkRunDir:
    """Test get_benchmark_run_dir()."""

    def test_creates_sanitized_run_dir(self, monkeypatch, tmp_path: Path):
        """Test that run directory is created with sanitized name."""
        custom_bench = tmp_path / "benchmarks"
        monkeypatch.setenv("IONO_BENCH_DIR", str(custom_bench))

        result = paths.get_benchmark_run_dir("latency/test!")

        assert result == custom_bench / "latency-test"
        assert result.exists()

    def test_multiple_calls_same_directory(self, monkeypatch, tmp_path: Path):
        """Test that multiple calls for same benchmark return same directory."""
        custom_bench = tmp_path / "benchmarks"
        monkeypatch.setenv("IONO_BENCH_DIR", str(custom_bench))

        result1 = paths.get_benchmark_run_dir("my_test")
        result2 = paths.get_benchmark_run_dir("my_test")

        assert result1 == result2
        assert result1.exists()


class TestBenchmarkResultPath:
    """Test get_benchmark_result_path()."""

    def test_default_timestamp_json(self, monkeypatch, tmp_path: Path):
        """Test default result path with auto timestamp."""
        custom_bench = tmp_path / "benchmarks"
        monkeypatch.setenv("IONO_BENCH_DIR", str(custom_bench))

        result = paths.get_benchmark_result_path("latency")

        assert result.parent == custom_bench / "latency"
        assert result.name.startswith("latency_")
        assert result.suffix == ".json"
        assert result.parent.exists()

    def test_custom_timestamp(self, monkeypatch, tmp_path: Path):
        """Test result path with custom timestamp."""
        custom_bench = tmp_path / "benchmarks"
        monkeypatch.setenv("IONO_BENCH_DIR", str(custom_bench))

        timestamp = datetime(2025, 1, 15, 10, 30, 45)
        result = paths.get_benchmark_result_path("throughput", timestamp=timestamp)

        assert "20250115_103045" in result.name

    def test_custom_suffix(self, monkeypatch, tmp_path: Path):
        """Test result path with custom suffix."""
        custom_bench = tmp_path / "benchmarks"
        monkeypatch.setenv("IONO_BENCH_DIR", str(custom_bench))

        result = paths.get_benchmark_result_path("test", suffix=".csv")
        assert result.suffix == ".csv"

        result = paths.get_benchmark_result_path("test", suffix="yaml")
        assert result.suffix == ".yaml"

    def test_sanitized_benchmark_name(self, monkeypatch, tmp_path: Path):
        """Test that benchmark name is sanitized in result path."""
        custom_bench = tmp_path / "benchmarks"
        monkeypatch.setenv("IONO_BENCH_DIR", str(custom_bench))

        result = paths.get_benchmark_result_path("my/test benchmark!")

        assert "my-test-benchmark" in result.name
        assert result.parent == custom_bench / "my-test-benchmark"


class TestExperimentsRoot:
    """Test get_experiments_root()."""

    def test_default_experiments_root(self, monkeypatch, tmp_path: Path):
        """Test default experiments root location."""
        monkeypatch.delenv("IONO_EXPERIMENTS_DIR", raising=False)
        custom_artifacts = tmp_path / "artifacts"
        monkeypatch.setenv("IONO_OUTPUT_ROOT", str(custom_artifacts))

        result = paths.get_experiments_root()

        assert result == custom_artifacts / "experiments"
        assert result.exists()

    def test_env_override_experiments_root(self, monkeypatch, tmp_path: Path):
        """Test that IONO_EXPERIMENTS_DIR env var overrides default."""
        custom_exp = tmp_path / "custom_experiments"
        monkeypatch.setenv("IONO_EXPERIMENTS_DIR", str(custom_exp))

        result = paths.get_experiments_root()

        assert result == custom_exp
        assert result.exists()


class TestReportsRoot:
    """Test get_reports_root()."""

    def test_default_reports_root(self, monkeypatch, tmp_path: Path):
        """Test default reports root location."""
        monkeypatch.delenv("IONO_REPORTS_DIR", raising=False)
        custom_artifacts = tmp_path / "artifacts"
        monkeypatch.setenv("IONO_OUTPUT_ROOT", str(custom_artifacts))

        result = paths.get_reports_root()

        assert result == custom_artifacts / "reports"
        assert result.exists()

    def test_env_override_reports_root(self, monkeypatch, tmp_path: Path):
        """Test that IONO_REPORTS_DIR env var overrides default."""
        custom_reports = tmp_path / "custom_reports"
        monkeypatch.setenv("IONO_REPORTS_DIR", str(custom_reports))

        result = paths.get_reports_root()

        assert result == custom_reports
        assert result.exists()

    def test_path_functions_identical_behavior(self):
        """Verify refactored functions behave identically."""
        # Test with env vars unset
        assert paths.get_benchmarks_root() == paths.get_output_root() / "benchmark_results"
        assert paths.get_experiments_root() == paths.get_output_root() / "experiments"
        assert paths.get_reports_root() == paths.get_output_root() / "reports"
        
        # Test with env vars set
        os.environ["IONO_BENCH_DIR"] = "/custom/bench"
        os.environ["IONO_EXPERIMENTS_DIR"] = "/custom/experiments"
        os.environ["IONO_REPORTS_DIR"] = "/custom/reports"
        
        assert paths.get_benchmarks_root() == Path("/custom/bench")
        assert paths.get_experiments_root() == Path("/custom/experiments")
        assert paths.get_reports_root() == Path("/custom/reports")


class TestNsightDiscovery:
    """Tests covering Nsight CLI/GUI discovery helpers."""

    def test_cli_env_override(self, monkeypatch, tmp_path: Path):
        exe = tmp_path / "nsys.exe"
        exe.write_text("")
        monkeypatch.setenv("IONO_NSYS_BIN", str(exe))
        monkeypatch.delenv("IONO_NSIGHT_ROOT", raising=False)

        assert paths.get_nsight_cli("nsys") == exe

    def test_gui_env_override(self, monkeypatch, tmp_path: Path):
        gui = tmp_path / "nsys-ui.exe"
        gui.write_text("")
        monkeypatch.setenv("IONO_NSYS_GUI", str(gui))

        assert paths.get_nsight_gui("nsys") == gui

    def test_discovers_from_nsight_root(self, monkeypatch, tmp_path: Path):
        install_root = tmp_path / "Nsight Systems 2025.3.2"
        cli_dir = install_root / "target-windows-x64"
        gui_dir = install_root / "host-windows-x64"
        cli_dir.mkdir(parents=True)
        gui_dir.mkdir(parents=True)
        cli_path = cli_dir / "nsys.exe"
        gui_path = gui_dir / "nsys-ui.exe"
        cli_path.write_text("")
        gui_path.write_text("")

        monkeypatch.setenv("IONO_NSIGHT_ROOT", str(install_root))
        monkeypatch.delenv("IONO_NSYS_BIN", raising=False)
        monkeypatch.delenv("IONO_NSYS_GUI", raising=False)

        assert paths.get_nsight_cli("nsys") == cli_path
        assert paths.get_nsight_gui("nsys") == gui_path

    def test_gui_infers_from_cli_install(self, monkeypatch, tmp_path: Path):
        install_root = tmp_path / "Nsight Systems 2025.3.2"
        cli_dir = install_root / "target-windows-x64"
        gui_dir = install_root / "host-windows-x64"
        cli_dir.mkdir(parents=True)
        gui_dir.mkdir(parents=True)
        cli_path = cli_dir / "nsys.exe"
        gui_path = gui_dir / "nsys-ui.exe"
        cli_path.write_text("")
        gui_path.write_text("")

        monkeypatch.setenv("IONO_NSYS_BIN", str(cli_path))
        monkeypatch.delenv("IONO_NSYS_GUI", raising=False)
        monkeypatch.delenv("IONO_NSIGHT_ROOT", raising=False)

        assert paths.get_nsight_gui("nsys") == gui_path
