"""Streamlit-side dataset registry.

Discovers persistent datasets under ``datasets/`` and exposes the live
``artifacts/data/`` directory as a synthetic ``"live"`` entry so the dashboard
always has something to show, even before anything has been snapshotted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import streamlit as st


def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root."""
    start = Path(__file__).resolve()
    for parent in [start, *start.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return start.parents[3]


REPO_ROOT = _find_repo_root()
DATASETS_DIR = REPO_ROOT / "datasets"
ARTIFACTS_DATA = REPO_ROOT / "artifacts" / "data"


@dataclass(frozen=True)
class DatasetEntry:
    """A dataset the dashboard can load."""

    name: str
    display_name: str
    data_path: Path
    manifest: dict[str, Any] = field(default_factory=dict)
    is_live: bool = False

    def has_csvs(self) -> bool:
        if not self.data_path.exists():
            return False
        return any(self.data_path.glob("*_summary_*.csv"))


@st.cache_data(ttl=60, show_spinner=False)
def list_datasets() -> list[DatasetEntry]:
    """Return all selectable datasets, newest first, with ``live`` prepended.

    Skips the ``datasets/cpp/`` subtree — that's managed by the ``sigxc`` tool
    and has a different CSV schema.
    """
    entries: list[DatasetEntry] = []

    live = DatasetEntry(
        name="live",
        display_name="live (artifacts/data)",
        data_path=ARTIFACTS_DATA,
        manifest={"source": "local-live", "message": "Current scratchpad run."},
        is_live=True,
    )
    entries.append(live)

    if DATASETS_DIR.exists():
        candidates: list[tuple[str, DatasetEntry]] = []
        for child in DATASETS_DIR.iterdir():
            if not child.is_dir() or child.name == "cpp" or child.name.startswith("."):
                continue

            manifest_path = child / "manifest.json"
            manifest: dict[str, Any] = {}
            if manifest_path.exists():
                try:
                    with manifest_path.open(encoding="utf-8") as f:
                        manifest = json.load(f)
                except (OSError, json.JSONDecodeError):
                    manifest = {}

            data_path = child / "data"
            source = manifest.get("source", "unknown")
            display = f"{child.name} ({source})" if source else child.name
            entry = DatasetEntry(
                name=child.name,
                display_name=display,
                data_path=data_path,
                manifest=manifest,
                is_live=False,
            )
            created = manifest.get("created", "")
            candidates.append((created, entry))

        candidates.sort(key=lambda pair: pair[0], reverse=True)
        entries.extend(entry for _, entry in candidates)

    return entries


def get_entry_by_name(name: str) -> DatasetEntry | None:
    for entry in list_datasets():
        if entry.name == name:
            return entry
    return None


def get_primary_dataset() -> DatasetEntry:
    """Read the selected primary dataset from session state, defaulting to ``live``."""
    name = st.session_state.get("primary_dataset", "live")
    entry = get_entry_by_name(name)
    if entry is None:
        entry = list_datasets()[0]
    return entry


def get_compare_datasets() -> list[DatasetEntry]:
    """Read the optional compare-with datasets from session state."""
    names = st.session_state.get("compare_datasets", []) or []
    primary = st.session_state.get("primary_dataset", "live")
    result: list[DatasetEntry] = []
    for name in names:
        if name == primary:
            continue
        entry = get_entry_by_name(name)
        if entry is not None:
            result.append(entry)
    return result


def render_sidebar_picker() -> tuple[DatasetEntry, list[DatasetEntry]]:
    """Render the dataset picker in the sidebar and return the selection.

    Must be called on every page (top of page body) so the selection persists
    and pages stay in sync.
    """
    datasets = list_datasets()
    with st.sidebar:
        st.markdown("### Dataset")
        name_to_entry = {e.name: e for e in datasets}
        display_options = [e.name for e in datasets]

        primary_default = st.session_state.get("primary_dataset", "live")
        if primary_default not in name_to_entry:
            primary_default = "live"

        primary_name = st.selectbox(
            "Primary",
            display_options,
            index=display_options.index(primary_default),
            format_func=lambda n: name_to_entry[n].display_name,
            key="primary_dataset",
            help="Dataset shown on every chart and metric.",
        )

        compare_options = [e.name for e in datasets if e.name != primary_name]
        compare_default = [
            n for n in st.session_state.get("compare_datasets", []) if n in compare_options
        ]
        compare_names = st.multiselect(
            "Compare with",
            compare_options,
            default=compare_default,
            format_func=lambda n: name_to_entry[n].display_name,
            key="compare_datasets",
            help="Overlay additional datasets on charts and show deltas.",
        )

        primary_entry = name_to_entry[primary_name]
        compare_entries = [name_to_entry[n] for n in compare_names]

        manifest = primary_entry.manifest or {}
        with st.expander("Primary dataset info", expanded=False):
            st.write(f"**Source**: {manifest.get('source', 'unknown')}")
            st.write(f"**Created**: {manifest.get('created', '—')}")
            st.write(f"**Git**: {(manifest.get('git_commit') or '—')[:12]}")
            hw = manifest.get("hardware", {}) or {}
            if hw:
                st.write(f"**GPU**: {hw.get('gpu_name', '—')}")
                st.write(f"**CPU**: {hw.get('cpu', '—')}")
            if manifest.get("message"):
                st.caption(manifest["message"])

    return primary_entry, compare_entries
