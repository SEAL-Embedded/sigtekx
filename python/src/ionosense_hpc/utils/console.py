"""
ionosense_hpc.utils.console: Terminal output formatting utilities.

Provides functions for creating clean, professional console output
for benchmarks, progress reporting, and results display.
"""

from __future__ import annotations
import sys
import time
from typing import Optional, List, Dict, Any, TextIO
from contextlib import contextmanager
from datetime import datetime
import shutil


class ConsoleFormatter:
    """
    Professional console output formatter.
    
    Handles Unicode safely, provides consistent formatting, and
    creates visually appealing terminal output.
    """
    
    def __init__(self, file: Optional[TextIO] = None):
        """
        Initialize formatter.
        
        Args:
            file: Output stream (defaults to sys.stdout).
        """
        self.file = file or sys.stdout
        self.terminal_width = shutil.get_terminal_size().columns
        
        # Unicode box drawing characters with ASCII fallbacks
        self._chars = {
            'h_line': '─',
            'v_line': '│',
            'tl_corner': '┌',
            'tr_corner': '┐',
            'bl_corner': '└',
            'br_corner': '┘',
            't_joint': '┬',
            'b_joint': '┴',
            'l_joint': '├',
            'r_joint': '┤',
            'cross': '┼',
            'h_thick': '═',
            'v_thick': '║',
            'check': '✓',
            'cross_mark': '✗',
            'arrow': '→',
        }
        
        # Test Unicode support
        self._unicode_safe = self._test_unicode()
    
    def _test_unicode(self) -> bool:
        """Test if Unicode output is safe."""
        try:
            test_str = '═╔╗║'
            self.file.write('')  # Test write capability
            return True
        except UnicodeEncodeError:
            return False
    
    def _safe_print(self, text: str) -> None:
        """Print with Unicode fallback."""
        try:
            print(text, file=self.file)
        except UnicodeEncodeError:
            # Fallback to ASCII
            safe_text = text.encode('ascii', errors='replace').decode('ascii')
            print(safe_text, file=self.file)
    
    def print_header(self, title: str, level: int = 1) -> None:
        """
        Print a formatted header.
        
        Args:
            title: Header text.
            level: Header level (1=main, 2=section, 3=subsection).
        """
        if level == 1:
            # Main header with thick borders
            border = self._chars['h_thick'] * self.terminal_width
            self._safe_print(f"\n{border}")
            self._safe_print(f" {title.upper()}")
            self._safe_print(border)
        elif level == 2:
            # Section header
            border = self._chars['h_line'] * min(len(title) + 4, self.terminal_width)
            self._safe_print(f"\n{border}")
            self._safe_print(f" {title}")
            self._safe_print(border)
        else:
            # Subsection
            self._safe_print(f"\n{self._chars['arrow']} {title}")
            self._safe_print(self._chars['h_line'] * min(len(title) + 2, self.terminal_width))
    
    def print_separator(self, style: str = 'thin') -> None:
        """Print a horizontal separator."""
        char = self._chars['h_thick'] if style == 'thick' else self._chars['h_line']
        self._safe_print(char * self.terminal_width)
    
    def print_table(
        self,
        headers: List[str],
        rows: List[List[Any]],
        alignments: Optional[List[str]] = None
    ) -> None:
        """
        Print a formatted table.
        
        Args:
            headers: Column headers.
            rows: Table rows.
            alignments: Column alignments ('l', 'r', 'c').
        """
        if not rows:
            return
        
        # Calculate column widths
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        
        # Default alignments
        if alignments is None:
            alignments = ['l'] * len(headers)
        
        # Print header
        header_row = self._format_row(headers, widths, alignments)
        self._safe_print(header_row)
        self._safe_print(self._chars['h_line'] * len(header_row))
        
        # Print rows
        for row in rows:
            self._safe_print(self._format_row(row, widths, alignments))
    
    def _format_row(
        self,
        cells: List[Any],
        widths: List[int],
        alignments: List[str]
    ) -> str:
        """Format a table row."""
        formatted = []
        for cell, width, align in zip(cells, widths, alignments):
            cell_str = str(cell)
            if align == 'r':
                formatted.append(cell_str.rjust(width))
            elif align == 'c':
                formatted.append(cell_str.center(width))
            else:
                formatted.append(cell_str.ljust(width))
        return '  '.join(formatted)
    
    def print_stats(self, stats: Dict[str, Any], title: str = "Statistics") -> None:
        """
        Print formatted statistics.
        
        Args:
            stats: Statistics dictionary.
            title: Section title.
        """
        self.print_header(title, level=3)
        
        max_key_len = max(len(k) for k in stats.keys())
        
        for key, value in stats.items():
            # Format value based on type
            if isinstance(value, float):
                if value < 0.001:
                    value_str = f"{value:.3e}"
                elif value < 1:
                    value_str = f"{value*1000:.3f} μs"
                elif value < 1000:
                    value_str = f"{value:.3f} ms"
                else:
                    value_str = f"{value/1000:.3f} s"
            elif isinstance(value, int):
                value_str = f"{value:,}"
            else:
                value_str = str(value)
            
            self._safe_print(f"  {key.ljust(max_key_len)} : {value_str}")
    
    def print_progress(
        self,
        current: int,
        total: int,
        prefix: str = "Progress",
        suffix: str = "",
        bar_length: int = 50
    ) -> None:
        """
        Print a progress bar.
        
        Args:
            current: Current iteration.
            total: Total iterations.
            prefix: Prefix text.
            suffix: Suffix text.
            bar_length: Length of progress bar.
        """
        percent = current / total
        filled = int(bar_length * percent)
        
        # Build bar
        bar = '█' * filled + '░' * (bar_length - filled)
        
        # Build full line
        line = f"\r{prefix} │{bar}│ {percent*100:.1f}% {suffix}"
        
        # Print with carriage return
        sys.stdout.write(line)
        sys.stdout.flush()
        
        if current >= total:
            sys.stdout.write('\n')
            sys.stdout.flush()


# Global formatter instance
_formatter = ConsoleFormatter()


def print_header(title: str, level: int = 1) -> None:
    """Print a formatted header."""
    _formatter.print_header(title, level)


def print_separator(style: str = 'thin') -> None:
    """Print a separator line."""
    _formatter.print_separator(style)


def print_table(
    headers: List[str],
    rows: List[List[Any]],
    alignments: Optional[List[str]] = None
) -> None:
    """Print a formatted table."""
    _formatter.print_table(headers, rows, alignments)


def print_stats(stats: Dict[str, Any], title: str = "Statistics") -> None:
    """Print formatted statistics."""
    _formatter.print_stats(stats, title)


def format_time(seconds: float) -> str:
    """
    Format time duration intelligently.
    
    Args:
        seconds: Time in seconds.
    
    Returns:
        Formatted time string.
    """
    if seconds < 1e-6:
        return f"{seconds*1e9:.3f} ns"
    elif seconds < 1e-3:
        return f"{seconds*1e6:.3f} μs"
    elif seconds < 1:
        return f"{seconds*1e3:.3f} ms"
    elif seconds < 60:
        return f"{seconds:.3f} s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"


def format_bytes(num_bytes: int) -> str:
    """
    Format byte size with appropriate units.
    
    Args:
        num_bytes: Number of bytes.
    
    Returns:
        Formatted size string.
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def format_number(value: float, precision: int = 3) -> str:
    """
    Format number with intelligent precision.
    
    Args:
        value: Number to format.
        precision: Decimal places for small numbers.
    
    Returns:
        Formatted number string.
    """
    if abs(value) >= 1e6:
        return f"{value:.2e}"
    elif abs(value) >= 1000:
        return f"{value:,.0f}"
    elif abs(value) >= 1:
        return f"{value:.{precision}f}"
    elif abs(value) >= 0.001:
        return f"{value:.{precision}f}"
    else:
        return f"{value:.2e}"


@contextmanager
def timed_section(name: str, verbose: bool = True):
    """
    Context manager for timing code sections.
    
    Args:
        name: Section name.
        verbose: Whether to print timing.
    
    Yields:
        Elapsed time function.
    
    Example:
        >>> with timed_section("Processing"):
        ...     process_data()
    """
    start = time.perf_counter()
    
    def elapsed():
        return time.perf_counter() - start
    
    try:
        yield elapsed
    finally:
        if verbose:
            duration = elapsed()
            print(f"[{name}] {format_time(duration)}")


class ProgressReporter:
    """
    Thread-safe progress reporting for long-running operations.
    """
    
    def __init__(self, total: int, desc: str = "Processing", unit: str = "items"):
        """
        Initialize progress reporter.
        
        Args:
            total: Total number of items.
            desc: Description of operation.
            unit: Unit name for items.
        """
        self.total = total
        self.desc = desc
        self.unit = unit
        self.current = 0
        self.start_time = time.perf_counter()
        self._last_update = 0
    
    def update(self, n: int = 1) -> None:
        """Update progress by n items."""
        self.current += n
        
        # Rate limit updates to 10 Hz
        now = time.perf_counter()
        if now - self._last_update < 0.1 and self.current < self.total:
            return
        
        self._last_update = now
        elapsed = now - self.start_time
        
        # Calculate rate
        rate = self.current / elapsed if elapsed > 0 else 0
        
        # Calculate ETA
        if rate > 0:
            remaining = self.total - self.current
            eta = remaining / rate
            eta_str = format_time(eta)
        else:
            eta_str = "N/A"
        
        # Build suffix
        suffix = f"{self.current}/{self.total} {self.unit} | "
        suffix += f"{rate:.1f} {self.unit}/s | ETA: {eta_str}"
        
        # Print progress
        _formatter.print_progress(
            self.current,
            self.total,
            prefix=self.desc,
            suffix=suffix
        )
    
    def close(self) -> None:
        """Finalize progress reporting."""
        elapsed = time.perf_counter() - self.start_time
        rate = self.total / elapsed if elapsed > 0 else 0
        
        print(f"\n{self.desc} complete: {self.total} {self.unit} in {format_time(elapsed)}")
        print(f"Average rate: {rate:.1f} {self.unit}/s")


def print_benchmark_summary(results: Dict[str, Any]) -> None:
    """
    Print a formatted benchmark summary.
    
    Args:
        results: Benchmark results dictionary.
    """
    print_header("BENCHMARK RESULTS", level=1)
    
    # Configuration
    if 'config' in results:
        print_header("Configuration", level=2)
        print_stats(results['config'])
    
    # Performance metrics
    if 'performance' in results:
        print_header("Performance", level=2)
        perf = results['performance']
        
        metrics = []
        if 'throughput_ops_per_sec' in perf:
            metrics.append(['Throughput', f"{perf['throughput_ops_per_sec']:,.0f} ops/s"])
        if 'avg_latency_ms' in perf:
            metrics.append(['Avg Latency', format_time(perf['avg_latency_ms']/1000)])
        if 'min_latency_ms' in perf:
            metrics.append(['Min Latency', format_time(perf['min_latency_ms']/1000)])
        if 'max_latency_ms' in perf:
            metrics.append(['Max Latency', format_time(perf['max_latency_ms']/1000)])
        
        if metrics:
            print_table(['Metric', 'Value'], metrics, ['l', 'r'])
    
    # Device info
    if 'device' in results:
        print_header("Device", level=2)
        print_stats(results['device'])
    
    print_separator('thick')