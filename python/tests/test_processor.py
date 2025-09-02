"""Tests for the Processor class."""

import pytest
import numpy as np

from ionosense_hpc import Processor, Presets, EngineConfig
from ionosense_hpc.exceptions import EngineStateError
from ionosense_hpc.utils import make_test_batch


# REVISED: Replaced the complex skipif with a simple, declarative marker.
# These tests will now run by default and be skipped only with --no-gpu.
@pytest.mark.gpu
class TestProcessor:
    """Test Processor functionality."""
    
    def test_context_manager(self):
        """Test processor as context manager."""
        config = Presets.validation()
        
        with Processor(config) as proc:
            assert proc.is_initialized
            # Process some data
            test_data = np.zeros(config.nfft * config.batch, dtype=np.float32)
            output = proc.process(test_data)
            assert output.shape == (config.batch, config.num_output_bins)
        
        # After context exit, should still be initialized but synchronized
        assert proc.is_initialized
    
    def test_initialization(self):
        """Test processor initialization."""
        # Auto-init with config
        proc = Processor(Presets.validation(), auto_init=True)
        assert proc.is_initialized
        proc.reset()
        
        # Manual init
        proc = Processor(auto_init=False)
        assert not proc.is_initialized
        proc.initialize(Presets.validation())
        assert proc.is_initialized
        proc.reset()
    
    def test_preset_string(self):
        """Test initialization with preset string."""
        proc = Processor('validation')
        assert proc.is_initialized
        assert proc.config.nfft == 256  # Validation preset
        proc.reset()
        
        # Invalid preset
        with pytest.raises(ValueError):
            Processor('invalid_preset')
    
    def test_process_basic(self):
        """Test basic processing."""
        config = Presets.validation()
        test_data = make_test_batch(config.nfft, config.batch, seed=42)
        
        with Processor(config) as proc:
            output = proc.process(test_data)
            
            # Check output shape
            assert output.shape == (config.batch, config.num_output_bins)
            
            # Check output is float32
            assert output.dtype == np.float32
            
            # Check no NaN/Inf
            assert not np.any(np.isnan(output))
            assert not np.any(np.isinf(output))
    
    def test_process_list_input(self):
        """Test processing with list input."""
        config = Presets.validation()
        test_data = list(range(config.nfft * config.batch))
        
        with Processor(config) as proc:
            output = proc.process(test_data)
            assert output.shape == (config.batch, config.num_output_bins)
    
    def test_process_not_initialized(self):
        """Test error when processing without initialization."""
        proc = Processor(auto_init=False)
        test_data = np.zeros(256, dtype=np.float32)
        
        with pytest.raises(EngineStateError):
            proc.process(test_data)
    
    def test_process_stream(self):
        """Test stream processing."""
        config = Presets.validation()
        
        # Create a generator of test frames
        def data_generator():
            for i in range(5):
                yield make_test_batch(config.nfft, config.batch, seed=i)
        
        with Processor(config) as proc:
            outputs = proc.process_stream(data_generator(), max_frames=3)
            
            # Should process only 3 frames
            assert len(outputs) == 3
            
            # Each output should have correct shape
            for output in outputs:
                assert output.shape == (config.batch, config.num_output_bins)
    
    def test_benchmark(self):
        """Test built-in benchmark function."""
        config = Presets.validation()
        
        with Processor(config) as proc:
            results = proc.benchmark(n_iterations=10)
            
            # Check expected keys
            assert 'n_iterations' in results
            assert 'mean_latency_us' in results
            assert 'p99_latency_us' in results
            
            # Values should be positive
            assert results['mean_latency_us'] > 0
            assert results['p99_latency_us'] > 0
            assert results['p99_latency_us'] >= results['mean_latency_us']
    
    def test_stats_tracking(self):
        """Test statistics tracking."""
        config = Presets.validation()
        test_data = make_test_batch(config.nfft, config.batch, seed=42)
        
        with Processor(config) as proc:
            # Process multiple frames
            for i in range(5):
                proc.process(test_data)
            
            stats = proc.get_stats()
            
            # Check stats
            assert stats['total_processed'] == 5
            assert 'recent_avg_latency_us' in stats
            
            # Check history
            history = proc.history
            assert len(history) == 5
            assert all('latency_us' in h for h in history)
    
    def test_reset(self):
        """Test processor reset."""
        config = Presets.validation()
        
        proc = Processor(config)
        assert proc.is_initialized
        
        # Process some data
        test_data = np.zeros(config.nfft * config.batch, dtype=np.float32)
        proc.process(test_data)
        assert len(proc.history) > 0
        
        # Reset
        proc.reset()
        assert not proc.is_initialized
        assert len(proc.history) == 0
    
    def test_print_status(self, capsys):
        """Test status printing."""
        config = Presets.validation()
        
        with Processor(config) as proc:
            proc.print_status()
            
            captured = capsys.readouterr()
            assert "Processor Status:" in captured.out
            assert "Initialized: True" in captured.out


class TestProcessorErrorHandling:
    """Test error handling in Processor."""
    
    @pytest.mark.gpu
    def test_invalid_input_size(self):
        """Test error with wrong input size."""
        config = Presets.validation()
        
        with Processor(config) as proc:
            # Wrong size
            wrong_data = np.zeros(100, dtype=np.float32)
            
            with pytest.raises(Exception):  # Could be ValidationError or EngineRuntimeError
                proc.process(wrong_data)
    
    @pytest.mark.gpu
    def test_exception_in_context(self):
        """Test exception handling in context manager."""
        config = Presets.validation()
        
        try:
            with Processor(config) as proc:
                # Cause an error
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected
        
        # Processor should have handled cleanup
        # (checking this doesn't crash)
        assert proc.is_initialized
