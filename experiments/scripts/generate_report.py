#!/usr/bin/env python
"""
HTML Report Generator for Ionosphere HPC Experiments
==================================================

Creates comprehensive HTML reports from experiment data and figures.
Combines statistics, visualizations, and analysis into a single document.

Usage:
    python generate_report.py

Input:
    - artifacts/data/summary_statistics.csv
    - artifacts/figures/*.png
Output:
    - artifacts/reports/final_report.html
"""

import base64
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')


def encode_image_to_base64(image_path: Path) -> str | None:
    """Convert image file to base64 string for embedding in HTML."""
    try:
        if image_path.suffix.lower() == '.svg':
            # SVG files can be read as text and embedded directly
            with open(image_path, encoding='utf-8') as svg_file:
                svg_content = svg_file.read()
                encoded = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
                return f"data:image/svg+xml;base64,{encoded}"
        else:
            # PNG and other binary image formats
            with open(image_path, 'rb') as img_file:
                encoded = base64.b64encode(img_file.read()).decode('utf-8')
                return f"data:image/png;base64,{encoded}"
    except Exception as e:
        print(f"Warning: Could not encode image {image_path}: {e}")
        return None


def load_summary_data(data_path: str = "artifacts/data/summary_statistics.csv") -> pd.DataFrame:
    """Load experiment summary data."""
    try:
        df = pd.read_csv(data_path)
        print(f"Loaded summary data: {len(df)} measurements")
        return df
    except Exception as e:
        print(f"Warning: Could not load summary data from {data_path}: {e}")
        return pd.DataFrame()


def find_generated_figures(figures_dir: str = "artifacts/figures") -> dict[str, Path]:
    """Find all generated figure files, preferring SVG over PNG."""
    figures_path = Path(figures_dir)

    figure_files = {}
    if figures_path.exists():
        # First pass: collect PNG files
        for fig_path in figures_path.glob("*.png"):
            name = fig_path.stem
            if "throughput" in name.lower():
                figure_files["throughput"] = fig_path
            elif "latency" in name.lower():
                figure_files["latency"] = fig_path
            elif "accuracy" in name.lower():
                figure_files["accuracy"] = fig_path
            elif "combined" in name.lower() or "overview" in name.lower():
                figure_files["overview"] = fig_path
            else:
                figure_files[name] = fig_path

        # Second pass: prefer SVG files if they exist
        for fig_path in figures_path.glob("*.svg"):
            name = fig_path.stem
            if "throughput" in name.lower():
                figure_files["throughput"] = fig_path
            elif "latency" in name.lower():
                figure_files["latency"] = fig_path
            elif "accuracy" in name.lower():
                figure_files["accuracy"] = fig_path
            elif "combined" in name.lower() or "overview" in name.lower():
                figure_files["overview"] = fig_path
            else:
                figure_files[name] = fig_path

    print(f"Found {len(figure_files)} figure files")

    # Report format breakdown
    svg_count = sum(1 for path in figure_files.values() if path.suffix == '.svg')
    png_count = len(figure_files) - svg_count
    if svg_count > 0:
        print(f"  Format breakdown: {svg_count} SVG, {png_count} PNG (preferring SVG)")
    else:
        print(f"  Format breakdown: {png_count} PNG")

    return figure_files


def generate_executive_summary(df: pd.DataFrame) -> str:
    """Generate executive summary from data."""
    if df.empty:
        return "<p>No experiment data available.</p>"

    summary_parts = []

    # Basic statistics
    total_measurements = len(df)
    benchmark_types = df['benchmark_type'].nunique() if 'benchmark_type' in df.columns else 0
    unique_configs = df[['engine_nfft', 'engine_batch']].drop_duplicates().shape[0] if all(col in df.columns for col in ['engine_nfft', 'engine_batch']) else 0

    summary_parts.append(f"""
    <div class="summary-stats">
        <h3>Experiment Overview</h3>
        <ul>
            <li><strong>Total Measurements:</strong> {total_measurements}</li>
            <li><strong>Benchmark Types:</strong> {benchmark_types}</li>
            <li><strong>Engine Configurations:</strong> {unique_configs}</li>
            <li><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
        </ul>
    </div>
    """)

    # Performance highlights
    if 'benchmark_type' in df.columns:
        for benchmark_type in df['benchmark_type'].unique():
            subset = df[df['benchmark_type'] == benchmark_type]

            if benchmark_type == 'throughput' and 'frames_per_second' in subset.columns:
                max_fps = subset['frames_per_second'].max()
                best_config = subset.loc[subset['frames_per_second'].idxmax()]
                summary_parts.append(f"""
                <div class="performance-highlight">
                    <h4>Throughput Performance</h4>
                    <p><strong>Peak Performance:</strong> {max_fps:.1f} FPS</p>
                    <p><strong>Best Configuration:</strong> NFFT={int(best_config['engine_nfft'])}, Batch={int(best_config['engine_batch'])}</p>
                </div>
                """)

            elif benchmark_type == 'latency' and 'mean_latency_us' in subset.columns:
                min_latency = subset['mean_latency_us'].min()
                best_config = subset.loc[subset['mean_latency_us'].idxmin()]
                summary_parts.append(f"""
                <div class="performance-highlight">
                    <h4>Latency Performance</h4>
                    <p><strong>Lowest Latency:</strong> {min_latency:.1f} μs</p>
                    <p><strong>Best Configuration:</strong> NFFT={int(best_config['engine_nfft'])}, Batch={int(best_config['engine_batch'])}</p>
                </div>
                """)

            elif benchmark_type == 'accuracy' and 'pass_rate' in subset.columns:
                max_accuracy = subset['pass_rate'].max()
                best_config = subset.loc[subset['pass_rate'].idxmax()]
                summary_parts.append(f"""
                <div class="performance-highlight">
                    <h4>Accuracy Performance</h4>
                    <p><strong>Best Pass Rate:</strong> {max_accuracy:.1%}</p>
                    <p><strong>Best Configuration:</strong> NFFT={int(best_config['engine_nfft'])}, Batch={int(best_config['engine_batch'])}</p>
                </div>
                """)

    return '\n'.join(summary_parts)


def generate_detailed_tables(df: pd.DataFrame) -> str:
    """Generate detailed data tables."""
    if df.empty:
        return "<p>No detailed data available.</p>"

    tables_html = []

    if 'benchmark_type' in df.columns:
        for benchmark_type in df['benchmark_type'].unique():
            subset = df[df['benchmark_type'] == benchmark_type].copy()

            # Format the data for display
            if benchmark_type == 'throughput':
                display_cols = ['engine_nfft', 'engine_batch', 'frames_per_second', 'gb_per_second']
                col_names = ['NFFT', 'Batch Size', 'FPS', 'GB/s']
            elif benchmark_type == 'latency':
                display_cols = ['engine_nfft', 'engine_batch', 'mean_latency_us', 'p95_latency_us']
                col_names = ['NFFT', 'Batch Size', 'Mean Latency (μs)', 'P95 Latency (μs)']
            elif benchmark_type == 'accuracy':
                display_cols = ['engine_nfft', 'engine_batch', 'pass_rate', 'mean_snr_db']
                col_names = ['NFFT', 'Batch Size', 'Pass Rate', 'Mean SNR (dB)']
            else:
                continue

            # Filter to available columns
            available_cols = [col for col in display_cols if col in subset.columns]
            if len(available_cols) < 2:
                continue

            subset_display = subset[available_cols].copy()

            # Format numeric values
            for col in subset_display.columns:
                if col in ['frames_per_second', 'gb_per_second', 'mean_latency_us', 'p95_latency_us', 'mean_snr_db']:
                    subset_display[col] = subset_display[col].round(2)
                elif col == 'pass_rate':
                    subset_display[col] = (subset_display[col] * 100).round(1).astype(str) + '%'

            # Create HTML table
            table_html = f"""
            <div class="data-table">
                <h3>{benchmark_type.title()} Results</h3>
                <table>
                    <thead>
                        <tr>
                            {''.join(f'<th>{name}</th>' for name in col_names[:len(available_cols)])}
                        </tr>
                    </thead>
                    <tbody>
            """

            for _, row in subset_display.iterrows():
                table_html += "<tr>"
                for col in available_cols:
                    table_html += f"<td>{row[col]}</td>"
                table_html += "</tr>"

            table_html += """
                    </tbody>
                </table>
            </div>
            """

            tables_html.append(table_html)

    return '\n'.join(tables_html)


def generate_figures_section(figure_files: dict[str, Path]) -> str:
    """Generate figures section with embedded images."""
    if not figure_files:
        return "<p>No figures available.</p>"

    figures_html = []

    # Define section order and titles
    section_order = [
        ('overview', 'Performance Overview'),
        ('throughput', 'Throughput Analysis'),
        ('latency', 'Latency Analysis'),
        ('accuracy', 'Accuracy Analysis')
    ]

    for section_key, section_title in section_order:
        if section_key in figure_files:
            image_data = encode_image_to_base64(figure_files[section_key])
            if image_data:
                figures_html.append(f"""
                <div class="figure-section">
                    <h3>{section_title}</h3>
                    <img src="{image_data}" alt="{section_title}" class="figure-image">
                    <p class="figure-caption">Figure: {section_title} results from ionosphere HPC experiments.</p>
                </div>
                """)

    # Add any remaining figures
    for name, path in figure_files.items():
        if name not in [s[0] for s in section_order]:
            image_data = encode_image_to_base64(path)
            if image_data:
                figures_html.append(f"""
                <div class="figure-section">
                    <h3>{name.replace('_', ' ').title()}</h3>
                    <img src="{image_data}" alt="{name}" class="figure-image">
                    <p class="figure-caption">Figure: {name.replace('_', ' ')} analysis.</p>
                </div>
                """)

    return '\n'.join(figures_html)


def generate_html_report(df: pd.DataFrame, figure_files: dict[str, Path]) -> str:
    """Generate complete HTML report."""

    executive_summary = generate_executive_summary(df)
    detailed_tables = generate_detailed_tables(df)
    figures_section = generate_figures_section(figure_files)

    html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ionosphere HPC Experiment Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            text-align: center;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 5px;
        }}
        h3 {{
            color: #2980b9;
        }}
        .summary-stats {{
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .performance-highlight {{
            background-color: #e8f5e8;
            padding: 15px;
            border-left: 4px solid #27ae60;
            margin: 15px 0;
        }}
        .data-table {{
            margin: 20px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
        }}
        tr:nth-child(even) {{
            background-color: #f2f2f2;
        }}
        .figure-section {{
            margin: 30px 0;
            text-align: center;
        }}
        .figure-image {{
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            margin: 10px 0;
        }}
        .figure-caption {{
            font-style: italic;
            color: #666;
            margin-top: 10px;
        }}
        .section {{
            margin: 40px 0;
        }}
        .timestamp {{
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
            margin-top: 30px;
            border-top: 1px solid #ecf0f1;
            padding-top: 15px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Ionosphere HPC Experiment Report</h1>

        <div class="section">
            <h2>Executive Summary</h2>
            {executive_summary}
        </div>

        <div class="section">
            <h2>Detailed Results</h2>
            {detailed_tables}
        </div>

        <div class="section">
            <h2>Performance Analysis</h2>
            {figures_section}
        </div>

        <div class="timestamp">
            Report generated on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""

    return html_template


def main():
    """Main report generation function."""
    print("=" * 60)
    print("Ionosphere HPC Experiment Report Generator")
    print("=" * 60)

    # Load experiment data
    print("\n>> Loading experiment data...")
    df = load_summary_data()

    # Find generated figures
    print(">> Finding generated figures...")
    figure_files = find_generated_figures()

    if df.empty and not figure_files:
        print("Warning: No data or figures found!")
        print("Make sure you've run experiments and generated figures first.")
        return

    # Generate HTML report
    print(">> Generating HTML report...")
    html_content = generate_html_report(df, figure_files)

    # Save report
    output_dir = Path("artifacts/reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "final_report.html"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f">> Report saved to: {output_path}")
    print(">> Report includes:")
    print(f"   - {len(df)} measurements" if not df.empty else "   - No measurement data")
    print(f"   - {len(figure_files)} figures" if figure_files else "   - No figures")

    print("\n>> To view your report:")
    print(f"   Open {output_path} in your web browser")
    print("\n>> Report generation complete!")


if __name__ == "__main__":
    main()
