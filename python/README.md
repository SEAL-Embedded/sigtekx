# Ionosense-HPC Python API

Python interface for high-performance CUDA FFT processing.

## Installation

### From Source

```bash
cd ionosense-hpc-lib
./scripts/cli.sh build    # build the CUDA extension
cd python
pip install -e .
```

### Development Shell (Windows)

```powershell
cd ionosense-hpc-lib
.\scripts\open_dev_pwsh.ps1
ib   # build
ip   # run python tests
```

## Quick Start

```python
from ionosense_hpc import Engine, Presets
import numpy as np

config = Presets.validation()
frame = np.random.randn(config.nfft * config.batch).astype(np.float32)

with Engine(config) as engine:
    spectrum = engine.process(frame)
    print(spectrum.shape)  # (batch, nfft // 2 + 1)
```

## Advanced Usage

```python
from ionosense_hpc import Engine, Presets

engine = Engine(
    config=Presets.throughput(),
    validate_inputs=False,
    profile_mode=True,
    stream_count=4,
)

try:
    for frame in dataloader:
        spectrum = engine.process(frame)
        analyse(spectrum)
finally:
    engine.close()
```

## Convenience Helpers

```python
from ionosense_hpc import process_signal, benchmark_latency

spectrum = process_signal(frame, "realtime")
stats = benchmark_latency("realtime", iterations=25)
```

## Configuration

`EngineConfig` lives in `ionosense_hpc.config`.  Use presets or construct one directly.

```python
from ionosense_hpc.config import EngineConfig

config = EngineConfig(nfft=2048, batch=4, overlap=0.25)
engine = Engine(config)
```

## Diagnostics

```python
from ionosense_hpc import show_versions, self_test

show_versions()
assert self_test()
```

## More Information

* `docs/API.md` – detailed API reference
* `docs/INSTALL.md` – full environment setup
* `docs/DEVELOPMENT.md` – contribution workflow and debugging aids
