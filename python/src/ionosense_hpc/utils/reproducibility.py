"""Reproducibility helpers for deterministic random number streams."""

from __future__ import annotations

import hashlib
from typing import Dict

import numpy as np

__all__ = ["DeterministicGenerator"]


class DeterministicGenerator:
    """Deterministic random number generator for reproducible benchmarks."""

    def __init__(self, base_seed: int = 42, context: str = "default"):
        """Initialize generator with a base seed and context string."""
        self.base_seed = base_seed
        self.context = context
        self._rng_cache: Dict[str, np.random.Generator] = {}

    def get_rng(self, stream_id: str = "main") -> np.random.Generator:
        """Return a cached generator for the requested stream."""
        if stream_id not in self._rng_cache:
            seed_str = f"{self.context}:{stream_id}:{self.base_seed}"
            seed_hash = hashlib.sha256(seed_str.encode()).digest()
            seed = int.from_bytes(seed_hash[:4], "big") % (2**31)
            self._rng_cache[stream_id] = np.random.default_rng(seed)
        return self._rng_cache[stream_id]

    def reset(self) -> None:
        """Clear the cached generators so streams can be regenerated."""
        self._rng_cache.clear()
