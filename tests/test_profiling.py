# tests/test_profiling.py

import contextlib
import types

import pytest

import ionosense_hpc.utils.profiling as p


class TestBuildNVTXAttrs:
    @pytest.mark.parametrize(
        "color,domain,category,payload,expect",
        [
            (
                p.ProfileColor.PURPLE,
                p.ProfilingDomain.CORE,
                p.ProfileCategory.GPU_COMPUTE,
                42,
                {
                    "color": "purple",
                    "domain": "IONOSENSE_CORE",
                    "category": "GPUCompute",
                    "payload": 42,
                },
            ),
            (
                "blue",
                "custom_domain",
                None,
                None,
                {
                    "color": "blue",
                    "domain": "custom_domain",
                },
            ),
            (
                p.ProfileColor.NVIDIA_BLUE,
                None,
                p.ProfileCategory.HIGH_LEVEL,
                {"k": 1},
                {
                    "color": "blue",
                    "category": "HighLevel",
                    "payload": "{'k': 1}",
                },
            ),
        ],
    )
    def test_variants(self, color, domain, category, payload, expect):
        attrs = p._build_nvtx_attrs("test", color, domain, category, payload)

        assert attrs["message"] == "test"
        assert attrs["color"] == expect["color"]

        if "domain" in expect:
            assert attrs["domain"] == expect["domain"]
        else:
            assert "domain" not in attrs

        if "category" in expect:
            assert attrs["category"] == expect["category"]
        else:
            assert "category" not in attrs

        if "payload" in expect:
            assert attrs["payload"] == expect["payload"]
        else:
            assert "payload" not in attrs


class TestProfilingAPIs:
    def test_range_and_event_build_identical_attrs(self, monkeypatch):
        calls = []

        @contextlib.contextmanager
        def fake_annotate(**kw):
            calls.append(kw.copy())
            yield

        monkeypatch.setattr(p, "NVTX_AVAILABLE", True)
        if p.nvtx is None or not hasattr(p.nvtx, "annotate"):
            p.nvtx = types.SimpleNamespace()
        monkeypatch.setattr(p.nvtx, "annotate", fake_annotate, raising=False)

        kwargs = {
            "color": p.ProfileColor.PURPLE,
            "domain": p.ProfilingDomain.CORE,
            "category": p.ProfileCategory.GPU_COMPUTE,
            "payload": 7,
        }

        with p.nvtx_range("X", **kwargs):
            pass
        p.mark_event("X", **kwargs)

        assert len(calls) == 2
        r, e = calls
        assert r == e

    def test_noop_when_nvtx_unavailable(self, monkeypatch):
        monkeypatch.setattr(p, "NVTX_AVAILABLE", False)
        with p.nvtx_range("noop"):
            pass
        p.mark_event("noop")
