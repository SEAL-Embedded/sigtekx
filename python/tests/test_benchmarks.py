"""
python/tests/test_benchmarks.py
--------------------------------------------------------------------------------
Comprehensive test suite for the research-grade benchmark infrastructure.
Tests all aspects of benchmarking, reporting, and workflow orchestration.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import yaml

from ionosense_hpc.benchmarks import (
    BaseBenchmark,
    BenchmarkConfig,
    BenchmarkContext,
    BenchmarkResult,
    BenchmarkSuite,
    ParameterSweep,
    calculate_statistics,
    load_benchmark_config,
    save_benchmark_results,
)
from ionosense_hpc.benchmarks.research_workflow import (
    ResearchWorkflow,
    WorkflowStage,
    create_research_workflow,
)
from ionosense_hpc.config.schemas import ExperimentMetadata, ResearchConfig
from ionosense_hpc.exceptions import (
    BenchmarkError,
    BenchmarkTimeoutError,
    BenchmarkValidationError,
    ReproducibilityError,
)


# ============================================================================
# Test BaseBenchmark Infrastructure
# ============================================================================

class TestBaseBenchmark:
    """Test the BaseBenchmark abstract class and core functionality."""
    
    def test_benchmark_config_validation(self):
        """Test BenchmarkConfig validation and defaults."""
        # Valid config
        config = BenchmarkConfig(name="test", iterations=100)
        assert config.name == "test"
        assert config.iterations == 100
        assert config.confidence_level == 0.95
        
        # Invalid iterations
        with pytest.raises(ValueError):
            BenchmarkConfig(name="test", iterations=-1)
            
        # Invalid confidence level
        with pytest.raises(ValueError):
            BenchmarkConfig(name="test", confidence_level=1.5)
            
    def test_benchmark_context_creation(self):
        """Test BenchmarkContext captures environment correctly."""
        context = BenchmarkContext()
        
        assert context.timestamp is not None
        assert context.hostname is not None
        assert context.platform_info is not None
        assert 'python_version' in context.platform_info
        assert context.environment_hash is not None
        
        # Test serialization
        context_dict = context.to_dict()
        assert isinstance(context_dict, dict)
        assert 'timestamp' in context_dict
        
    def test_benchmark_result_statistics(self):
        """Test BenchmarkResult automatic statistics calculation."""
        measurements = np.random.randn(100) * 10 + 50
        
        result = BenchmarkResult(
            name="test",
            config={},
            context=BenchmarkContext(),
            measurements=measurements
        )
        
        assert 'mean' in result.statistics
        assert 'std' in result.statistics
        assert 'p99' in result.statistics
        assert abs(result.statistics['mean'] - 50) < 5  # Should be close to 50
        
    def test_calculate_statistics(self):
        """Test statistical calculation with outlier removal."""
        # Data with outliers
        data = np.concatenate([
            np.random.randn(95) * 5 + 100,  # Normal data
            [1000, 2000, 3000, -1000, -2000]  # Outliers
        ])
        
        config = BenchmarkConfig(name="test", outlier_threshold=3.0)
        stats = calculate_statistics(data, config)
        
        assert stats['n'] == 100
        assert stats['n_outliers'] > 0
        assert abs(stats['mean'] - 100) < 10  # Filtered mean should be close to 100
        assert 'ci_lower' in stats
        assert 'ci_upper' in stats
        
    def test_benchmark_implementation(self, benchmark_runner):
        """Test running a concrete benchmark implementation."""
        result = benchmark_runner.run()
        
        assert result.passed
        assert result.name == "test_runner"
        assert len(result.measurements) == 10
        assert result.statistics['n'] == 10
        
    def test_benchmark_validation(self):
        """Test benchmark environment validation."""
        
        class TestBenchmark(BaseBenchmark):
            def setup(self):
                pass
                
            def execute_iteration(self):
                return 1.0
                
            def teardown(self):
                pass
                
            def validate_environment(self):
                # Custom validation that fails
                return False, ["Test validation failure"]
                
        config = BenchmarkConfig(name="test", iterations=1)
        benchmark = TestBenchmark(config)
        
        result = benchmark.run()
        assert not result.passed
        assert "Test validation failure" in result.errors
        
    def test_save_and_load_results(self, sample_benchmark_result, temp_data_dir):
        """Test saving and loading benchmark results."""
        # Save result
        result_path = temp_data_dir / "test_result.json"
        save_benchmark_results(sample_benchmark_result, result_path)
        
        assert result_path.exists()
        
        # Load and verify
        with open(result_path) as f:
            loaded = json.load(f)
            
        assert loaded[0]['name'] == sample_benchmark_result.name
        assert 'measurements' in loaded[0]
        assert 'statistics' in loaded[0]
        
    def test_load_benchmark_config_yaml(self, yaml_benchmark_config):
        """Test loading benchmark configuration from YAML."""
        config_dict = load_benchmark_config(yaml_benchmark_config)
        
        assert config_dict['name'] == "test_experiment"
        assert config_dict['iterations'] == 500
        assert 'engine_config' in config_dict


# ============================================================================
# Test Parameter Sweep
# ============================================================================

class TestParameterSweep:
    """Test parameter sweep functionality."""
    
    def test_parameter_spec_generation(self):
        """Test parameter value generation."""
        from ionosense_hpc.benchmarks.sweep import ParameterSpec
        
        # Explicit values
        spec1 = ParameterSpec(name="param1", values=[1, 2, 3])
        assert spec1.generate_values() == [1, 2, 3]
        
        # Integer range
        spec2 = ParameterSpec(
            name="param2",
            type="int",
            range={"start": 0, "stop": 5, "step": 2}
        )
        assert spec2.generate_values() == [0, 2, 4]
        
        # Float range with step
        spec3 = ParameterSpec(
            name="param3",
            type="float",
            range={"start": 0.0, "stop": 1.0, "step": 0.5}
        )
        assert spec3.generate_values() == [0.0, 0.5, 1.0]
        
    def test_grid_sweep_generation(self, yaml_sweep_config):
        """Test grid parameter sweep generation."""
        sweep = ParameterSweep(str(yaml_sweep_config))
        
        # Generate parameter grid
        param_grid = list(sweep.generate_parameter_grid())
        
        # Should have 3 nfft values * 3 batch values = 9 combinations
        assert len(param_grid) == 9
        
        # Check all combinations are present
        nfft_values = {p['engine_config.nfft'] for p in param_grid}
        batch_values = {p['engine_config.batch'] for p in param_grid}
        
        assert nfft_values == {256, 512, 1024}
        assert batch_values == {1, 2, 3}
        
    @patch('ionosense_hpc.benchmarks.sweep.ParameterSweep._get_benchmark_class')
    def test_sweep_execution(self, mock_get_class, yaml_sweep_config, temp_benchmark_dir):
        """Test parameter sweep execution."""
        # Mock benchmark class
        mock_benchmark = MagicMock()
        mock_benchmark.return_value.run.return_value = BenchmarkResult(
            name="test",
            config={},
            context=BenchmarkContext(),
            measurements=np.array([1.0]),
            passed=True
        )
        mock_get_class.return_value = mock_benchmark
        
        # Run sweep
        sweep = ParameterSweep(str(yaml_sweep_config))
        sweep.config.output_dir = str(temp_benchmark_dir)
        sweep.config.save_interval = 100  # Don't save intermediate
        
        results = sweep.run()
        
        assert len(results) == 9  # Grid size
        assert all(r.result is not None for r in results)
        
    def test_random_sweep_generation(self):
        """Test random sampling parameter sweep."""
        from ionosense_hpc.benchmarks.sweep import ExperimentConfig, ParameterSpec
        
        config = ExperimentConfig(
            name="test",
            benchmark_class="test.Benchmark",
            sweep_type="random",
            n_samples=10,
            parameters=[
                ParameterSpec(name="p1", values=[1, 2, 3, 4, 5]),
                ParameterSpec(name="p2", values=[0.1, 0.2, 0.3])
            ]
        )
        
        sweep = ParameterSweep(config)
        param_grid = list(sweep.generate_parameter_grid())
        
        assert len(param_grid) == 10  # n_samples
        # All values should be from the specified sets
        for params in param_grid:
            assert params['p1'] in [1, 2, 3, 4, 5]
            assert params['p2'] in [0.1, 0.2, 0.3]


# ============================================================================
# Test Benchmark Suite
# ============================================================================

class TestBenchmarkSuite:
    """Test benchmark suite orchestration."""
    
    @patch('ionosense_hpc.benchmarks.suite.BenchmarkSuite.BENCHMARK_REGISTRY')
    def test_suite_creation(self, mock_registry):
        """Test suite initialization and configuration."""
        from ionosense_hpc.benchmarks.suite import SuiteConfig
        
        config = SuiteConfig(
            name="test_suite",
            benchmarks=["test1", "test2"]
        )
        
        # Mock registry
        mock_registry.return_value = {
            "test1": MagicMock,
            "test2": MagicMock
        }
        
        suite = BenchmarkSuite(config)
        
        assert suite.config.name == "test_suite"
        assert len(suite.config.benchmarks) == 2
        assert suite.output_dir.exists()
        
    def test_suite_benchmark_selection(self):
        """Test benchmark selection and exclusion."""
        from ionosense_hpc.benchmarks.suite import SuiteConfig
        
        config = SuiteConfig(
            name="test",
            benchmarks=["latency", "throughput", "accuracy"],
            exclude=["accuracy"]
        )
        
        suite = BenchmarkSuite(config)
        benchmarks = suite._get_benchmarks_to_run()
        
        assert "latency" in benchmarks
        assert "throughput" in benchmarks
        assert "accuracy" not in benchmarks


# ============================================================================
# Test Research Workflow
# ============================================================================

class TestResearchWorkflow:
    """Test research workflow orchestration."""
    
    def test_workflow_creation(self):
        """Test workflow initialization."""
        metadata = ExperimentMetadata(
            experiment_id="test_exp",
            name="Test Experiment",
            researcher="Test User"
        )
        
        config = ResearchConfig(metadata=metadata)
        workflow = ResearchWorkflow(config)
        
        assert workflow.workflow_id.startswith("test_exp")
        assert workflow.base_dir.exists()
        assert (workflow.base_dir / "configs").exists()
        
    def test_workflow_stage_dependencies(self):
        """Test workflow stage dependency validation."""
        workflow = create_research_workflow("test")
        
        # Add stage with valid dependency
        workflow.add_stage("stage1", "setup", {})
        workflow.add_stage("stage2", "benchmark", {}, dependencies=["stage1"])
        
        # Try to add stage with invalid dependency
        with pytest.raises(WorkflowError):
            workflow.add_stage("stage3", "analysis", {}, dependencies=["nonexistent"])
            
    def test_environment_capture(self, temp_data_dir):
        """Test environment capture for reproducibility."""
        metadata = ExperimentMetadata(
            experiment_id="test",
            name="Test"
        )
        
        config = ResearchConfig(metadata=metadata)
        config.output_settings['output_dir'] = str(temp_data_dir)
        
        workflow = ResearchWorkflow(config)
        env = workflow.capture_environment()
        
        assert 'python_version' in env
        assert 'platform' in env
        assert 'cwd' in env
        
    @patch('subprocess.run')
    @patch('subprocess.check_output')
    def test_reproducibility_verification(self, mock_check_output, mock_run):
        """Test reproducibility verification."""
        # Mock git info
        mock_check_output.side_effect = [
            b"abc123\n",  # commit
            b"main\n",    # branch
            b""           # clean status
        ]
        
        workflow = create_research_workflow("test")
        
        # Capture reference environment
        ref_env = workflow.capture_environment()
        
        # Verify against same environment (should pass)
        assert workflow.verify_reproducibility(ref_env)
        
        # Modify environment and verify (should fail)
        ref_env['python_version'] = "2.7.0"
        
        with pytest.raises(ReproducibilityError):
            workflow.verify_reproducibility(ref_env)
            
    def test_workflow_checkpoint_saving(self, temp_data_dir):
        """Test workflow checkpoint creation."""
        metadata = ExperimentMetadata(
            experiment_id="test",
            name="Test"
        )
        
        config = ResearchConfig(metadata=metadata)
        workflow = ResearchWorkflow(config)
        
        stage = WorkflowStage(
            name="test_stage",
            stage_type="setup",
            config={}
        )
        stage.status = "completed"
        
        workflow._save_checkpoint(stage)
        
        checkpoint_path = workflow.base_dir / "checkpoints" / "test_stage.json"
        assert checkpoint_path.exists()
        
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
            
        assert checkpoint['stage'] == "test_stage"
        assert 'timestamp' in checkpoint


# ============================================================================
# Test Reporting
# ============================================================================

class TestReporting:
    """Test report generation functionality."""
    
    @pytest.mark.skipif(not pytest.importorskip("matplotlib"), reason="matplotlib not installed")
    def test_report_generation(self, mock_benchmark_results, temp_benchmark_dir):
        """Test PDF report generation."""
        from ionosense_hpc.benchmarks.reporting import BenchmarkReport, ReportConfig
        
        # Load mock results
        results = []
        for result_path in mock_benchmark_results:
            with open(result_path) as f:
                data = json.load(f)
                # Create BenchmarkResult objects
                result = BenchmarkResult(
                    name=data['name'],
                    config=data['config'],
                    context=BenchmarkContext(),
                    measurements=np.array(data['measurements']),
                    statistics=data['statistics']
                )
                results.append(result)
                
        # Generate report
        config = ReportConfig(
            title="Test Report",
            output_format="pdf",
            include_violin_plots=False,  # Faster
            include_histograms=False
        )
        
        report = BenchmarkReport(results, config)
        report_path = temp_benchmark_dir / "test_report.pdf"
        
        # Mock the PDF generation to avoid matplotlib backend issues in CI
        with patch('matplotlib.pyplot.savefig'):
            with patch('matplotlib.backends.backend_pdf.PdfPages'):
                report._generate_pdf(report_path)
                
    def test_comparative_report_generation(self, mock_benchmark_results, temp_benchmark_dir):
        """Test comparative report generation from directory."""
        from ionosense_hpc.benchmarks.reporting import generate_comparative_report, ReportConfig
        
        config = ReportConfig(
            title="Comparative Report",
            output_format="markdown"  # Simpler format for testing
        )
        
        output_path = temp_benchmark_dir / "report.md"
        
        # This should handle the directory of results
        with patch('ionosense_hpc.benchmarks.reporting.BenchmarkReport.generate'):
            generate_comparative_report(
                temp_benchmark_dir / "results",
                output_path,
                config
            )


# ============================================================================
# Test Integration
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""
    
    @pytest.mark.slow
    def test_end_to_end_workflow(self, temp_benchmark_dir):
        """Test complete research workflow execution."""
        # Create minimal workflow
        workflow = create_research_workflow(
            name="Integration Test",
            researcher="Test Suite"
        )
        
        # Override output directory
        workflow.base_dir = temp_benchmark_dir / "integration_test"
        workflow.setup_directories()
        
        # Add simple test stage
        workflow.add_stage("test_setup", "setup", {})
        
        # Mock the stage execution
        with patch.object(workflow, '_run_setup_stage', return_value={}):
            result = workflow.run(stages=["test_setup"])
            
        assert result.success
        assert len(result.stages) >= 1
        assert result.workflow_id is not None
        
    @pytest.mark.parametrize("sweep_type", ["grid", "random"])
    def test_sweep_integration(self, sweep_type, temp_benchmark_dir):
        """Test parameter sweep with different strategies."""
        from ionosense_hpc.benchmarks.sweep import ExperimentConfig, ParameterSpec
        
        config = ExperimentConfig(
            name=f"test_{sweep_type}",
            benchmark_class="ionosense_hpc.benchmarks.latency.LatencyBenchmark",
            sweep_type=sweep_type,
            n_samples=4,
            parameters=[
                ParameterSpec(name="iterations", values=[10, 20])
            ],
            output_dir=str(temp_benchmark_dir)
        )
        
        sweep = ParameterSweep(config)
        
        # Mock benchmark execution
        with patch.object(sweep, 'run_single') as mock_run:
            mock_run.return_value = MagicMock(
                result=BenchmarkResult(
                    name="test",
                    config={},
                    context=BenchmarkContext(),
                    measurements=np.array([1.0]),
                    passed=True
                ),
                error=None
            )
            
            results = sweep.run()
            
        expected_count = 2 if sweep_type == "grid" else 4
        assert len(results) == expected_count


# ============================================================================
# Test Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling and recovery."""
    
    def test_benchmark_timeout_error(self):
        """Test benchmark timeout detection."""
        
        class SlowBenchmark(BaseBenchmark):
            def setup(self):
                pass
                
            def execute_iteration(self):
                import time
                time.sleep(2)  # Exceed timeout
                return 1.0
                
            def teardown(self):
                pass
                
        config = BenchmarkConfig(
            name="slow",
            iterations=1,
            timeout_seconds=0.1
        )
        
        benchmark = SlowBenchmark(config)
        
        # Should handle timeout gracefully
        with patch('time.perf_counter', side_effect=[0, 0, 3]):  # Simulate timeout
            result = benchmark.run()
            
        assert not result.passed
        assert any("timeout" in str(e).lower() for e in result.errors)
        
    def test_validation_error_handling(self):
        """Test handling of validation errors."""
        with pytest.raises(BenchmarkValidationError):
            raise BenchmarkValidationError(
                benchmark_name="test",
                reason="Test validation failure",
                metrics={"accuracy": 0.5}
            )
            
    def test_workflow_error_recovery(self):
        """Test workflow error recovery with continue_on_error."""
        workflow = create_research_workflow("test")
        workflow.config.output_settings['continue_on_error'] = True
        
        # Add failing stage
        stage = WorkflowStage(
            name="failing_stage",
            stage_type="invalid_type",
            config={}
        )
        workflow.stages.append(stage)
        
        # Should continue despite error
        with patch.object(workflow, 'capture_environment', return_value={}):
            result = workflow.run(stages=["failing_stage"])
            
        assert not result.success
        assert stage.status == "failed"
        assert stage.error is not None