"""Pre-configured engine settings for common use cases."""

from typing import Dict, Any
from .schemas import EngineConfig


class Presets:
    """Collection of pre-configured engine settings."""
    
    @staticmethod
    def realtime() -> EngineConfig:
        """Configuration for real-time processing with minimal latency.
        
        Optimized for <200μs latency with dual-channel ULF/VLF signals.
        """
        return EngineConfig(
            nfft=1024,
            batch=2,  # Dual-channel
            overlap=0.5,
            sample_rate_hz=48000,
            stream_count=3,  # H2D, compute, D2H
            pinned_buffer_count=2,  # Double buffering
            warmup_iters=10,  # Stabilize clocks
            timeout_ms=100,  # Tight timeout for real-time
            use_cuda_graphs=False,  # Future optimization
            enable_profiling=False  # Minimize overhead
        )
    
    @staticmethod
    def throughput() -> EngineConfig:
        """Configuration for maximum throughput batch processing.
        
        Optimized for processing large datasets offline.
        """
        return EngineConfig(
            nfft=4096,
            batch=32,  # Large batch
            overlap=0.5,
            sample_rate_hz=48000,
            stream_count=4,
            pinned_buffer_count=4,  # More buffers for pipelining
            warmup_iters=1,
            timeout_ms=5000,
            use_cuda_graphs=False,
            enable_profiling=False
        )
    
    @staticmethod
    def validation() -> EngineConfig:
        """Configuration for accuracy validation and testing.
        
        Small sizes for debugging and numerical validation.
        """
        return EngineConfig(
            nfft=256,
            batch=1,
            overlap=0.0,  # No overlap for simple validation
            sample_rate_hz=1000,  # Simple rate for testing
            stream_count=1,  # Single stream for determinism
            pinned_buffer_count=2,
            warmup_iters=0,  # No warmup for testing
            timeout_ms=10000,
            use_cuda_graphs=False,
            enable_profiling=True  # Enable for debugging
        )
    
    @staticmethod
    def profiling() -> EngineConfig:
        """Configuration optimized for profiling and benchmarking.
        
        Balanced settings to expose both compute and memory patterns.
        """
        return EngineConfig(
            nfft=2048,
            batch=8,
            overlap=0.5,
            sample_rate_hz=48000,
            stream_count=3,
            pinned_buffer_count=3,
            warmup_iters=5,
            timeout_ms=2000,
            use_cuda_graphs=False,
            enable_profiling=True
        )
    
    @staticmethod
    def custom(**kwargs: Any) -> EngineConfig:
        """Create a custom configuration starting from realtime preset.
        
        Args:
            **kwargs: Parameters to override
            
        Returns:
            Custom EngineConfig
            
        Example:
            >>> config = Presets.custom(nfft=2048, batch=4)
        """
        base = Presets.realtime()
        for key, value in kwargs.items():
            if hasattr(base, key):
                setattr(base, key, value)
            else:
                raise ValueError(f"Unknown parameter: {key}")
        return base
    
    @classmethod
    def list_presets(cls) -> Dict[str, EngineConfig]:
        """Get all available presets.
        
        Returns:
            Dictionary mapping preset names to configurations
        """
        return {
            'realtime': cls.realtime(),
            'throughput': cls.throughput(),
            'validation': cls.validation(),
            'profiling': cls.profiling()
        }