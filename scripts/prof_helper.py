#!/usr/bin/env python
"""
Robust GPU Profiling Helper for ionosense-hpc
Provides clean progress tracking and smart profiling modes
"""

import subprocess
import sys
import time
import argparse
import json
from pathlib import Path
from datetime import datetime
import re
import shutil
from typing import Optional, List, Dict, Any
import threading
import queue


class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


class ProfileSession:
    """Manages a profiling session with progress tracking"""
    
    def __init__(self, tool: str, target: str, mode: str = "quick"):
        self.tool = tool.lower()
        self.target = target
        self.mode = mode
        self.start_time = None
        self.report_path = None
        self.kernel_progress = {}
        self.current_kernel = None
        self.total_passes = 0
        
        # Setup paths
        self.project_root = Path(__file__).parent.parent
        self.build_dir = self.project_root / "build"
        self.reports_dir = self.build_dir / "nsight_reports"
        
        # Create report directories
        self.nsys_dir = self.reports_dir / "nsys_reports"
        self.ncu_dir = self.reports_dir / "ncu_reports"
        self.nsys_dir.mkdir(parents=True, exist_ok=True)
        self.ncu_dir.mkdir(parents=True, exist_ok=True)
    
    def print_header(self):
        """Print a clean session header"""
        print(f"\n{Colors.CYAN}┌─────────────────────────────────────────────────────────┐{Colors.RESET}")
        print(f"{Colors.CYAN}│{Colors.RESET}  {Colors.MAGENTA}🎯 PROFILING SESSION{Colors.RESET}                                   {Colors.CYAN}│{Colors.RESET}")
        print(f"{Colors.CYAN}├─────────────────────────────────────────────────────────┤{Colors.RESET}")
        print(f"{Colors.CYAN}│{Colors.RESET}  Tool:     {Colors.YELLOW}{self.tool.upper()}{Colors.RESET} [{self.mode} mode]")
        print(f"{Colors.CYAN}│{Colors.RESET}  Target:   {Colors.YELLOW}{self.target}{Colors.RESET}")
        print(f"{Colors.CYAN}│{Colors.RESET}  Time:     {Colors.WHITE}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
        print(f"{Colors.CYAN}└─────────────────────────────────────────────────────────┘{Colors.RESET}\n")
    
    def format_time(self, seconds: float) -> str:
        """Format elapsed time nicely"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds/3600:.1f}h"
    
    def format_size(self, bytes: int) -> str:
        """Format file size nicely"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024.0:
                return f"{bytes:.1f}{unit}"
            bytes /= 1024.0
        return f"{bytes:.1f}TB"
    
    def monitor_ncu_progress(self, process):
        """Monitor NCU output and show progress"""
        kernel_count = 0
        current_kernel = ""
        current_passes = 0
        max_passes = 43 if self.mode == "full" else 5
        
        for line in iter(process.stdout.readline, ''):
            if process.poll() is not None:
                break
                
            # Parse NCU progress lines
            if "Profiling" in line:
                match = re.search(r'Profiling "([^"]+)" - (\d+):', line)
                if match:
                    kernel_name = match.group(1)
                    
                    if kernel_name != current_kernel:
                        if current_kernel:
                            print(f"\r  {Colors.GREEN}✓{Colors.RESET} [{kernel_count}] {current_kernel[:40]:<40} ({current_passes} passes)")
                        kernel_count += 1
                        current_kernel = kernel_name
                        current_passes = 0
                        self.kernel_progress[kernel_name] = 0
                        print(f"\n  {Colors.YELLOW}⚡{Colors.RESET} [{kernel_count}] Profiling: {Colors.CYAN}{kernel_name[:40]}{Colors.RESET}")
            
            # Update progress bar
            if "%" in line:
                match = re.search(r'(\d+)%', line)
                if match:
                    pct = int(match.group(1))
                    bar_width = 30
                    filled = int(bar_width * pct / 100)
                    bar = '█' * filled + '░' * (bar_width - filled)
                    
                    # Track passes
                    if pct == 100:
                        current_passes += 1
                    
                    # Show progress with pass counter
                    elapsed = time.time() - self.start_time
                    pass_info = f"Pass {current_passes}/{max_passes}" if self.mode == "full" else ""
                    print(f"\r     {Colors.BLUE}{bar}{Colors.RESET} {pct:3d}% {pass_info} [{self.format_time(elapsed)}]", end='', flush=True)
            
            # Show any important messages
            elif "==WARNING==" in line or "==ERROR==" in line:
                print(f"\n  {Colors.YELLOW}⚠{Colors.RESET}  {line.strip()}")
        
        # Final kernel summary
        if current_kernel:
            print(f"\r  {Colors.GREEN}✓{Colors.RESET} [{kernel_count}] {current_kernel[:40]:<40} ({current_passes} passes)")
        
        print(f"\n{Colors.GREEN}✓ Profiled {kernel_count} unique kernel(s) in {self.format_time(time.time() - self.start_time)}{Colors.RESET}")
    
    def monitor_nsys_progress(self, process):
        """Monitor nsys output and show progress"""
        spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        spin_idx = 0
        
        # Start a thread to read output
        output_queue = queue.Queue()
        
        def read_output():
            for line in iter(process.stdout.readline, ''):
                if line:
                    output_queue.put(line.strip())
            output_queue.put(None)  # Signal end
        
        thread = threading.Thread(target=read_output)
        thread.daemon = True
        thread.start()
        
        # Monitor progress
        while True:
            # Check for output
            try:
                line = output_queue.get_nowait()
                if line is None:
                    break
                if "Generating" in line or "Processing" in line:
                    print(f"\r  {Colors.CYAN}📊{Colors.RESET} {line[:60]:<60}", end='', flush=True)
            except queue.Empty:
                pass
            
            # Update spinner
            if process.poll() is None:
                elapsed = time.time() - self.start_time
                print(f"\r  {Colors.YELLOW}{spinner[spin_idx % len(spinner)]}{Colors.RESET} Profiling in progress... [{self.format_time(elapsed)}]", end='', flush=True)
                spin_idx += 1
                time.sleep(0.1)
            else:
                break
        
        thread.join(timeout=1)
        print(f"\r  {Colors.GREEN}✓ Profiling complete! [{self.format_time(time.time() - self.start_time)}]{Colors.RESET}          ")
    
    def run_nsys(self, target_cmd: List[str], output_name: str, **kwargs):
        """Run Nsight Systems profiling"""
        report_path = self.nsys_dir / output_name
        
        cmd = ["nsys", "profile", "-o", str(report_path), "-f", "true"]
        
        if self.mode == "full":
            print(f"  {Colors.CYAN}🔬 Full mode:{Colors.RESET} All GPU traces + OS runtime")
            cmd.extend(["--trace=cuda,cublas,cusolver,cusparse,nvtx,osrt"])
            cmd.extend(["--cuda-memory-usage=true"])
            cmd.extend(["--gpu-metrics-device=all"])
        else:
            print(f"  {Colors.CYAN}⚡ Quick mode:{Colors.RESET} Essential CUDA + NVTX traces")
            cmd.extend(["--trace=cuda,nvtx"])
        
        # Add duration limit if specified
        if kwargs.get('duration'):
            cmd.extend([f"--duration={kwargs['duration']}"])
            print(f"  {Colors.CYAN}⏱  Duration:{Colors.RESET} {kwargs['duration']} seconds")
        
        cmd.extend(target_cmd)
        
        print(f"\n  {Colors.YELLOW}►{Colors.RESET} Starting Nsight Systems...")
        self.start_time = time.time()
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.monitor_nsys_progress(process)
        
        return_code = process.wait()
        
        # Check results
        expected_file = f"{report_path}.nsys-rep"
        if Path(expected_file).exists():
            size = Path(expected_file).stat().st_size
            print(f"\n  {Colors.GREEN}📄 Report saved:{Colors.RESET} {expected_file}")
            print(f"     Size: {self.format_size(size)}")
            print(f"\n  {Colors.CYAN}📈 View with:{Colors.RESET} nsys-ui \"{expected_file}\"")
            return expected_file
        else:
            print(f"\n  {Colors.RED}❌ Report not found at expected location{Colors.RESET}")
            return None
    
    def run_ncu(self, target_cmd: List[str], output_name: str, **kwargs):
        """Run Nsight Compute profiling"""
        report_path = self.ncu_dir / output_name
        
        cmd = ["ncu", "-o", str(report_path)]
        
        if self.mode == "full":
            print(f"  {Colors.CYAN}🔬 Full mode:{Colors.RESET} Complete kernel analysis (~43 passes per kernel)")
            print(f"  {Colors.YELLOW}⚠  Warning:{Colors.RESET} This will take several minutes...")
            cmd.extend(["--set", "full"])
        else:
            print(f"  {Colors.CYAN}⚡ Quick mode:{Colors.RESET} Essential metrics (~5 passes per kernel)")
            metrics = [
                "sm__throughput.avg.pct_of_peak_sustained_elapsed",
                "dram__throughput.avg.pct_of_peak_sustained_elapsed",
                "gpu__time_duration.sum",
                "sm__warps_active.avg.pct_of_peak_sustained_active"
            ]
            cmd.extend(["--metrics", ",".join(metrics)])
        
        # Add kernel filter if specified
        if kwargs.get('kernel_filter'):
            cmd.extend(["--kernel-name", kwargs['kernel_filter']])
            print(f"  {Colors.CYAN}🎯 Filter:{Colors.RESET} {kwargs['kernel_filter']}")
        
        cmd.extend(["--target-processes", "all"])
        cmd.extend(target_cmd)
        
        print(f"\n  {Colors.YELLOW}►{Colors.RESET} Starting Nsight Compute...")
        self.start_time = time.time()
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.monitor_ncu_progress(process)
        
        return_code = process.wait()
        
        # Check results
        expected_file = f"{report_path}.ncu-rep"
        if Path(expected_file).exists():
            size = Path(expected_file).stat().st_size
            print(f"\n  {Colors.GREEN}📄 Report saved:{Colors.RESET} {expected_file}")
            print(f"     Size: {self.format_size(size)}")
            print(f"\n  {Colors.CYAN}📈 View with:{Colors.RESET} ncu-ui \"{expected_file}\"")
            return expected_file
        else:
            print(f"\n  {Colors.RED}❌ Report not found at expected location{Colors.RESET}")
            return None


def main():
    parser = argparse.ArgumentParser(description="GPU Profiling Helper")
    parser.add_argument("tool", choices=["nsys", "ncu"], help="Profiling tool")
    parser.add_argument("target", help="Target script or module")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick", help="Profiling mode")
    parser.add_argument("--kernel", help="Kernel name filter (NCU only)")
    parser.add_argument("--duration", type=int, help="Duration limit in seconds (nsys only)")
    parser.add_argument("--export", action="store_true", help="Export to CSV/SQLite")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for target")
    
    args = parser.parse_args()
    
    # Setup session
    session = ProfileSession(args.tool, args.target, args.mode)
    session.print_header()
    
    # Build target command
    target_cmd = ["python", "-m", f"ionosense_hpc.benchmarks.{args.target}"]
    if args.args and args.args[0] == "--":
        target_cmd.extend(args.args[1:])
    else:
        target_cmd.extend(args.args)
    
    # Generate output name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"{args.target}_{args.mode}_{timestamp}"
    
    # Run profiling
    if args.tool == "nsys":
        report = session.run_nsys(target_cmd, output_name, duration=args.duration)
    else:
        report = session.run_ncu(target_cmd, output_name, kernel_filter=args.kernel)
    
    # Export if requested
    if args.export and report:
        print(f"\n  {Colors.CYAN}📊 Exporting data...{Colors.RESET}")
        if args.tool == "nsys":
            sqlite_out = str(report).replace('.nsys-rep', '.sqlite')
            subprocess.run(["nsys", "export", "-t", "sqlite", "-o", sqlite_out, report], 
                         capture_output=True)
            print(f"     SQLite: {sqlite_out}")
        else:
            csv_out = str(report).replace('.ncu-rep', '.csv')
            with open(csv_out, 'w') as f:
                subprocess.run(["ncu", "-i", report, "--csv"], stdout=f, stderr=subprocess.DEVNULL)
            print(f"     CSV: {csv_out}")
    
    # Print footer
    print(f"\n{Colors.GRAY}────────────────────────────────────────────────────────{Colors.RESET}")
    print(f"{Colors.CYAN}💾 Reports directory:{Colors.RESET} {session.reports_dir}")
    print(f"{Colors.GRAY}────────────────────────────────────────────────────────{Colors.RESET}")


if __name__ == "__main__":
    main()