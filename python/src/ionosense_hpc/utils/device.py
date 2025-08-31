"""
ionosense_hpc.utils.device: CUDA device management and diagnostics.

Provides utilities for querying GPU capabilities, managing device selection,
and ensuring CUDA availability for the processing pipeline.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple, Dict, Any, List, Optional
import os
import platform
import subprocess

from ..core.exceptions import CudaError


@dataclass
class DeviceInfo:
    """
    CUDA device information.
    
    Attributes:
        id: Device ID (0-based index).
        name: Device name string.
        compute_capability: (major, minor) compute capability.
        total_memory_mb: Total global memory in MB.
        multiprocessors: Number of streaming multiprocessors.
        cuda_cores: Estimated total CUDA cores.
        clock_rate_mhz: GPU clock rate in MHz.
        memory_bandwidth_gb: Memory bandwidth in GB/s.
    """
    id: int
    name: str
    compute_capability: Tuple[int, int]
    total_memory_mb: float
    multiprocessors: int
    cuda_cores: int
    clock_rate_mhz: float = 0.0
    memory_bandwidth_gb: float = 0.0
    
    def meets_requirements(self, min_cc: Tuple[int, int] = (7, 0)) -> bool:
        """Check if device meets minimum compute capability."""
        major, minor = self.compute_capability
        min_major, min_minor = min_cc
        return (major > min_major or 
                (major == min_major and minor >= min_minor))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "compute_capability": f"{self.compute_capability[0]}.{self.compute_capability[1]}",
            "total_memory_mb": self.total_memory_mb,
            "multiprocessors": self.multiprocessors,
            "cuda_cores": self.cuda_cores,
            "clock_rate_mhz": self.clock_rate_mhz,
            "memory_bandwidth_gb": self.memory_bandwidth_gb,
        }
    
    def __str__(self) -> str:
        """Human-readable device summary."""
        cc_str = f"{self.compute_capability[0]}.{self.compute_capability[1]}"
        return (
            f"GPU {self.id}: {self.name}\n"
            f"  Compute Capability: {cc_str}\n"
            f"  Memory: {self.total_memory_mb:.0f} MB\n"
            f"  SMs: {self.multiprocessors}, CUDA Cores: {self.cuda_cores}\n"
            f"  Clock: {self.clock_rate_mhz:.0f} MHz"
        )


def ensure_cuda_available() -> None:
    """
    Verify CUDA engine is available and functional.
    
    Raises:
        CudaError: If CUDA is not available or engine import fails.
    """
    try:
        from ..core import _engine
        # Test instantiation of a basic config object
        cfg = _engine.ProcessingConfig()
        cfg.nfft = 1024  # Minimal test
    except (ImportError, AttributeError, RuntimeError) as e:
        raise CudaError(
            "CUDA engine not available. Ensure:\n"
            "  1. CUDA Toolkit >= 12.0 is installed\n"
            "  2. Compatible GPU is present\n"
            "  3. Library was built: ./scripts/cli.sh build\n"
            f"Error: {e}"
        )


def get_device_info(device_id: int = 0) -> DeviceInfo:
    """
    Get detailed information about a CUDA device.
    
    Args:
        device_id: Device index (0-based).
    
    Returns:
        DeviceInfo object with device details.
    
    Raises:
        CudaError: If device query fails.
    """
    try:
        # Try using pynvml for detailed info
        import pynvml
        pynvml.nvmlInit()
        
        handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)
        name = pynvml.nvmlDeviceGetName(handle).decode('utf-8')
        
        # Memory info
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_memory_mb = mem_info.total / (1024 ** 2)
        
        # Compute capability
        major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
        
        # Clock rates
        try:
            clock_mhz = pynvml.nvmlDeviceGetClockInfo(
                handle, pynvml.NVML_CLOCK_GRAPHICS
            )
        except:
            clock_mhz = 0
        
        # Multiprocessor count
        mp_count = pynvml.nvmlDeviceGetNumGpuCores(handle) // get_cores_per_sm(major, minor)
        
        pynvml.nvmlShutdown()
        
        return DeviceInfo(
            id=device_id,
            name=name,
            compute_capability=(major, minor),
            total_memory_mb=total_memory_mb,
            multiprocessors=mp_count,
            cuda_cores=mp_count * get_cores_per_sm(major, minor),
            clock_rate_mhz=clock_mhz,
        )
        
    except ImportError:
        # Fallback: Try nvidia-smi
        return _get_device_info_nvidia_smi(device_id)
    except Exception as e:
        raise CudaError(f"Failed to query device {device_id}: {e}")


def _get_device_info_nvidia_smi(device_id: int) -> DeviceInfo:
    """Fallback device query using nvidia-smi."""
    try:
        # Query basic info via nvidia-smi
        cmd = [
            "nvidia-smi",
            f"--id={device_id}",
            "--query-gpu=name,memory.total,compute_cap",
            "--format=csv,noheader,nounits"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        parts = result.stdout.strip().split(', ')
        
        if len(parts) >= 3:
            name = parts[0]
            memory_mb = float(parts[1])
            cc_parts = parts[2].split('.')
            cc = (int(cc_parts[0]), int(cc_parts[1]))
            
            # Estimate multiprocessors based on GPU generation
            mp_count = estimate_multiprocessors(name)
            
            return DeviceInfo(
                id=device_id,
                name=name,
                compute_capability=cc,
                total_memory_mb=memory_mb,
                multiprocessors=mp_count,
                cuda_cores=mp_count * get_cores_per_sm(cc[0], cc[1]),
            )
    except:
        pass
    
    # Ultimate fallback
    return DeviceInfo(
        id=device_id,
        name="Unknown GPU",
        compute_capability=(0, 0),
        total_memory_mb=0,
        multiprocessors=0,
        cuda_cores=0,
    )


def get_cores_per_sm(major: int, minor: int) -> int:
    """
    Get CUDA cores per streaming multiprocessor for a compute capability.
    
    Args:
        major: Major compute capability.
        minor: Minor compute capability.
    
    Returns:
        Number of CUDA cores per SM.
    """
    # Based on NVIDIA architecture specifications
    cores_map = {
        (8, 9): 128,  # Ada Lovelace (RTX 4090)
        (8, 6): 128,  # Ampere (RTX 3090)
        (8, 0): 64,   # Ampere (A100)
        (7, 5): 64,   # Turing (RTX 2080)
        (7, 0): 64,   # Volta (V100)
        (6, 1): 128,  # Pascal (GTX 1080)
        (6, 0): 64,   # Pascal (P100)
    }
    
    return cores_map.get((major, minor), 128)  # Default for future archs


def estimate_multiprocessors(gpu_name: str) -> int:
    """Estimate SM count from GPU name."""
    gpu_sm_map = {
        "RTX 4090": 128,
        "RTX 4080": 76,
        "RTX 4070": 46,
        "RTX 3090": 82,
        "RTX 3080": 68,
        "RTX 3070": 46,
        "RTX 2080": 46,
        "A100": 108,
        "V100": 80,
    }
    
    for key, value in gpu_sm_map.items():
        if key in gpu_name:
            return value
    
    return 30  # Conservative default


def list_devices() -> List[DeviceInfo]:
    """
    List all available CUDA devices.
    
    Returns:
        List of DeviceInfo objects.
    """
    devices = []
    device_count = get_device_count()
    
    for i in range(device_count):
        try:
            devices.append(get_device_info(i))
        except CudaError:
            continue
    
    return devices


def get_device_count() -> int:
    """
    Get the number of CUDA devices.
    
    Returns:
        Number of available CUDA devices.
    """
    try:
        import pynvml
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        pynvml.nvmlShutdown()
        return count
    except:
        # Fallback to nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "-L"],
                capture_output=True,
                text=True,
                check=True
            )
            return len(result.stdout.strip().split('\n'))
        except:
            return 0


def get_cuda_version() -> Tuple[int, int]:
    """
    Get CUDA runtime version.
    
    Returns:
        (major, minor) version tuple.
    """
    try:
        import pynvml
        pynvml.nvmlInit()
        version = pynvml.nvmlSystemGetCudaDriverVersion()
        pynvml.nvmlShutdown()
        
        major = version // 1000
        minor = (version % 1000) // 10
        return (major, minor)
    except:
        # Try nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse CUDA version from output
            import re
            match = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", result.stdout)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        except:
            pass
    
    return (0, 0)


def set_device(device_id: int) -> None:
    """
    Set the active CUDA device.
    
    Args:
        device_id: Device index to activate.
    
    Raises:
        CudaError: If device selection fails.
    """
    # Set environment variable for CUDA
    os.environ['CUDA_VISIBLE_DEVICES'] = str(device_id)
    
    # Verify it worked
    try:
        info = get_device_info(0)  # Should now be the selected device
        if info.id != 0:  # After setting, it should appear as device 0
            raise CudaError(f"Failed to set device {device_id}")
    except Exception as e:
        raise CudaError(f"Failed to set CUDA device {device_id}: {e}")


def get_memory_info(device_id: int = 0) -> Dict[str, float]:
    """
    Get current memory usage for a device.
    
    Args:
        device_id: Device to query.
    
    Returns:
        Dictionary with 'total_mb', 'used_mb', 'free_mb' keys.
    """
    try:
        import pynvml
        pynvml.nvmlInit()
        
        handle = pynvml.nvmlDeviceGetHandleByIndex(device_id)
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        
        pynvml.nvmlShutdown()
        
        return {
            'total_mb': mem_info.total / (1024 ** 2),
            'used_mb': mem_info.used / (1024 ** 2),
            'free_mb': mem_info.free / (1024 ** 2),
            'utilization_percent': (mem_info.used / mem_info.total) * 100
        }
    except:
        return {
            'total_mb': 0,
            'used_mb': 0,
            'free_mb': 0,
            'utilization_percent': 0
        }


def print_device_summary() -> None:
    """Print a summary of all available CUDA devices."""
    devices = list_devices()
    
    if not devices:
        print("No CUDA devices found")
        return
    
    cuda_version = get_cuda_version()
    print(f"CUDA Version: {cuda_version[0]}.{cuda_version[1]}")
    print(f"Found {len(devices)} device(s):\n")
    
    for device in devices:
        print(device)
        
        # Memory usage
        mem_info = get_memory_info(device.id)
        if mem_info['total_mb'] > 0:
            print(f"  Memory Usage: {mem_info['used_mb']:.0f}/{mem_info['total_mb']:.0f} MB "
                  f"({mem_info['utilization_percent']:.1f}%)")
        print()