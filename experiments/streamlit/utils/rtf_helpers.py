"""
RTF Analysis Helpers
=====================

Shared constants and helper functions for Real-Time Factor analysis across dashboard pages.
Follows DRY principles by centralizing RTF thresholds and interpretation logic.
"""

import pandas as pd

# =============================================================================
# RTF Thresholds (Academic Convention - Lower is Better)
# =============================================================================

# Production thresholds
RTF_PRODUCTION_TARGET = 0.40  # ASR industry standard (2.5× faster than real-time)
RTF_AGGRESSIVE_TARGET = 0.33  # Production with thermal margin (3× faster)
RTF_EXCELLENT = 0.20  # Current SigTekX performance (5× faster)
RTF_EXCEPTIONAL = 0.10  # 10× faster than real-time

# Real-time limits
RTF_REALTIME_LIMIT = 1.0  # Theoretical limit (exactly real-time)
RTF_MARGINAL = 0.50  # Approaching real-time (limited headroom)

# Color scale settings for heatmaps
RTF_HEATMAP_COLORSCALE = 'RdYlGn_r'  # Reversed: Red=high=bad, Green=low=good
RTF_HEATMAP_MIDPOINT = RTF_PRODUCTION_TARGET  # Anchor yellow at production target
RTF_HEATMAP_RANGE = (0.0, 1.0)  # Cap at real-time limit


# =============================================================================
# Helper Functions
# =============================================================================

def calculate_rtf_statistics(data: pd.DataFrame, rtf_col: str = 'rtf') -> dict:
    """
    Calculate comprehensive RTF statistics.

    Args:
        data: DataFrame with RTF column
        rtf_col: Name of RTF column (default: 'rtf')

    Returns:
        Dictionary with statistics:
        - mean, median, min, max, std
        - realtime_capable_count, realtime_capable_pct
        - production_ready_count, production_ready_pct (RTF ≤ 0.40)
        - aggressive_count, aggressive_pct (RTF ≤ 0.33)
        - excellent_count, excellent_pct (RTF ≤ 0.20)
    """
    if rtf_col not in data.columns or data[rtf_col].isna().all():
        return {}

    rtf_data = data[rtf_col].dropna()
    total = len(rtf_data)

    stats = {
        'mean': rtf_data.mean(),
        'median': rtf_data.median(),
        'min': rtf_data.min(),
        'max': rtf_data.max(),
        'std': rtf_data.std(),
        'total_count': total,
    }

    # Capability counts and percentages
    stats['realtime_capable_count'] = (rtf_data <= RTF_REALTIME_LIMIT).sum()
    stats['realtime_capable_pct'] = (stats['realtime_capable_count'] / total * 100) if total > 0 else 0

    stats['production_ready_count'] = (rtf_data <= RTF_PRODUCTION_TARGET).sum()
    stats['production_ready_pct'] = (stats['production_ready_count'] / total * 100) if total > 0 else 0

    stats['aggressive_count'] = (rtf_data <= RTF_AGGRESSIVE_TARGET).sum()
    stats['aggressive_pct'] = (stats['aggressive_count'] / total * 100) if total > 0 else 0

    stats['excellent_count'] = (rtf_data <= RTF_EXCELLENT).sum()
    stats['excellent_pct'] = (stats['excellent_count'] / total * 100) if total > 0 else 0

    return stats


def get_rtf_interpretation_text() -> str:
    """
    Get standard RTF interpretation text for academic convention.

    Returns:
        Markdown-formatted interpretation text
    """
    return f"""
**Interpretation (Academic Convention - Lower is Better):**
- **RTF ≤ {RTF_EXCEPTIONAL}**: Exceptional (10× faster than real-time)
- **RTF ≤ {RTF_EXCELLENT}**: Excellent (5× faster, current SigTekX performance)
- **RTF ≤ {RTF_AGGRESSIVE_TARGET}**: Production target (3× faster, thermal margin)
- **RTF ≤ {RTF_PRODUCTION_TARGET}**: ASR industry standard (2.5× faster)
- **RTF ≤ {RTF_MARGINAL}**: Acceptable (2× faster, minimal headroom)
- **RTF ≤ {RTF_REALTIME_LIMIT}**: Real-time capable (faster than real-time)
- **RTF > {RTF_REALTIME_LIMIT}**: Cannot keep up (offline processing only)
"""


def get_rtf_heatmap_interpretation_text() -> str:
    """
    Get standard heatmap color interpretation text for RTF heatmaps.

    Returns:
        Markdown-formatted heatmap interpretation text
    """
    return f"""
**Interpretation (Academic Convention - Lower is Better):**
- **Green regions**: RTF ≤{RTF_AGGRESSIVE_TARGET} (ideal for production, 3× faster than real-time)
- **Yellow regions**: RTF {RTF_AGGRESSIVE_TARGET}-{RTF_MARGINAL} (acceptable, 2-3× faster than real-time)
- **Orange/Red regions**: RTF >{RTF_MARGINAL} (approaching real-time limit, limited headroom)
- **Deep Red**: RTF ≥{RTF_REALTIME_LIMIT} (cannot keep up with real-time)
"""


def classify_rtf_performance(rtf: float) -> tuple[str, str]:
    """
    Classify RTF performance level using academic convention.

    Args:
        rtf: Real-Time Factor value

    Returns:
        Tuple of (category, description):
        - category: 'exceptional', 'excellent', 'very_good', 'good', 'acceptable', 'marginal', 'poor', 'failure'
        - description: Human-readable description
    """
    if rtf <= RTF_EXCEPTIONAL:
        return ('exceptional', f'Exceptional (RTF ≤{RTF_EXCEPTIONAL}: 10× faster)')
    elif rtf <= RTF_EXCELLENT:
        return ('excellent', f'Excellent (RTF ≤{RTF_EXCELLENT}: 5× faster)')
    elif rtf <= RTF_AGGRESSIVE_TARGET:
        return ('very_good', f'Very Good (RTF ≤{RTF_AGGRESSIVE_TARGET}: 3× faster)')
    elif rtf <= RTF_PRODUCTION_TARGET:
        return ('good', f'Good (RTF ≤{RTF_PRODUCTION_TARGET}: 2.5× faster)')
    elif rtf <= RTF_MARGINAL:
        return ('acceptable', f'Acceptable (RTF ≤{RTF_MARGINAL}: 2× faster)')
    elif rtf <= RTF_REALTIME_LIMIT:
        return ('marginal', f'Marginal (RTF ≤{RTF_REALTIME_LIMIT}: barely real-time)')
    else:
        return ('failure', f'Cannot keep up (RTF >{RTF_REALTIME_LIMIT})')


def add_rtf_threshold_lines(fig, show_production: bool = True, show_aggressive: bool = True,
                            show_realtime: bool = True):
    """
    Add standard RTF threshold lines to a Plotly figure.

    Args:
        fig: Plotly figure object
        show_production: Show production target line (RTF = 0.40)
        show_aggressive: Show aggressive target line (RTF = 0.33)
        show_realtime: Show real-time limit line (RTF = 1.0)

    Returns:
        Modified figure object
    """
    if show_aggressive:
        fig.add_hline(
            y=RTF_AGGRESSIVE_TARGET,
            line_dash="dash",
            line_color="green",
            annotation_text=f"Production Target (RTF={RTF_AGGRESSIVE_TARGET})",
            annotation_position="top left"
        )

    if show_production:
        fig.add_hline(
            y=RTF_PRODUCTION_TARGET,
            line_dash="dash",
            line_color="yellow",
            annotation_text=f"ASR Standard (RTF={RTF_PRODUCTION_TARGET})",
            annotation_position="top left"
        )

    if show_realtime:
        fig.add_hline(
            y=RTF_REALTIME_LIMIT,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Real-time Limit (RTF={RTF_REALTIME_LIMIT})",
            annotation_position="top right"
        )

    return fig
