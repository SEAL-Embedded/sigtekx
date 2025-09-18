"""Validation helpers for benchmark result analysis."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

__all__ = ["ValidationHelper"]


class ValidationHelper:
    """Collection of statistical validation utilities for benchmarks."""

    @staticmethod
    def validate_measurements(
        data: np.ndarray,
        name: str = "measurement",
        min_samples: int = 30,
        max_cv: float = 0.5,
        check_outliers: bool = True,
    ) -> Dict[str, Any]:
        """Validate a set of measurements and return diagnostics."""
        results: Dict[str, Any] = {
            "name": name,
            "valid": True,
            "warnings": [],
            "errors": [],
        }

        if len(data) < min_samples:
            results["errors"].append(
                f"Insufficient samples: {len(data)} < {min_samples}"
            )
            results["valid"] = False

        if np.any(np.isnan(data)):
            results["errors"].append("Data contains NaN values")
            results["valid"] = False

        if np.any(np.isinf(data)):
            results["errors"].append("Data contains Inf values")
            results["valid"] = False

        if not results["valid"]:
            return results

        mean = float(np.mean(data))
        std = float(np.std(data))
        cv = std / mean if mean != 0 else float("inf")

        if cv > max_cv:
            results["warnings"].append(
                f"High variability: CV={cv:.2f} > {max_cv}"
            )

        if check_outliers:
            z_scores = np.abs((data - mean) / (std + 1e-10))
            n_outliers = int(np.sum(z_scores > 3))
            if n_outliers > len(data) * 0.05:
                results["warnings"].append(
                    f"Many outliers detected: {n_outliers}/{len(data)}"
                )

        try:
            from scipy import stats

            _, p_value = stats.normaltest(data)
            if p_value < 0.01:
                results["warnings"].append(
                    f"Non-normal distribution (p={p_value:.4f})"
                )

            hist, _ = np.histogram(data, bins="auto")
            peaks = ValidationHelper._find_peaks(hist)
            if len(peaks) > 1:
                results["warnings"].append(
                    f"Multimodal distribution detected ({len(peaks)} peaks)"
                )
        except ImportError:
            pass

        results["statistics"] = {
            "mean": mean,
            "std": std,
            "cv": cv,
            "min": float(np.min(data)),
            "max": float(np.max(data)),
            "n_samples": len(data),
        }
        return results

    @staticmethod
    def _find_peaks(data: np.ndarray, min_height: float = 0.1) -> List[int]:
        """Detect peaks above a threshold in a histogram array."""
        threshold = float(np.max(data)) * min_height
        peaks: List[int] = []
        for idx in range(1, len(data) - 1):
            if data[idx] > threshold and data[idx] > data[idx - 1] and data[idx] > data[idx + 1]:
                peaks.append(idx)
        return peaks

    @staticmethod
    def compare_distributions(
        data1: np.ndarray,
        data2: np.ndarray,
        test: str = "ks",
    ) -> Dict[str, Any]:
        """Compare two datasets using statistical hypothesis tests."""
        try:
            from scipy import stats

            if test == "ks":
                statistic, p_value = stats.ks_2samp(data1, data2)
                test_name = "Kolmogorov-Smirnov"
            elif test == "mw":
                statistic, p_value = stats.mannwhitneyu(data1, data2)
                test_name = "Mann-Whitney U"
            elif test == "ttest":
                statistic, p_value = stats.ttest_ind(data1, data2)
                test_name = "Student's t"
            else:
                raise ValueError(f"Unknown test: {test}")

            return {
                "test": test_name,
                "statistic": float(statistic),
                "p_value": float(p_value),
                "significant": p_value < 0.05,
                "interpretation": "Different" if p_value < 0.05 else "Similar",
            }
        except ImportError:
            mean1, mean2 = float(np.mean(data1)), float(np.mean(data2))
            std1, std2 = float(np.std(data1)), float(np.std(data2))
            diff = abs(mean1 - mean2)
            pooled_std = float(np.sqrt((std1**2 + std2**2) / 2))
            return {
                "test": "mean_comparison",
                "mean_diff": diff,
                "pooled_std": pooled_std,
                "significant": diff > 2 * pooled_std,
                "interpretation": "Different" if diff > 2 * pooled_std else "Similar",
            }
