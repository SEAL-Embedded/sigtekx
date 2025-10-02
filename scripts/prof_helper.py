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
import platform
import webbrowser


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
        self.artifacts_dir = self.project_root / "artifacts"
        self.reports_dir = self.artifacts_dir / "profiling"

        # Create report directories
        self.nsys_dir = self.reports_dir / "nsys"
        self.ncu_dir = self.reports_dir / "ncu"
        self.nsys_dir.mkdir(parents=True, exist_ok=True)
        self.ncu_dir.mkdir(parents=True, exist_ok=True)
    
    def print_header(self):
        """Print a clean session header"""
        print(f"\n{Colors.CYAN}+-------------------------------------------------------------+{Colors.RESET}")
        print(f"{Colors.CYAN}|{Colors.RESET}  {Colors.MAGENTA}GPU PROFILING SESSION{Colors.RESET}                                    {Colors.CYAN}|{Colors.RESET}")
        print(f"{Colors.CYAN}+-------------------------------------------------------------+{Colors.RESET}")
        print(f"{Colors.CYAN}|{Colors.RESET}  Tool:     {Colors.YELLOW}{self.tool.upper()}{Colors.RESET} [{self.mode} mode]")
        print(f"{Colors.CYAN}|{Colors.RESET}  Target:   {Colors.YELLOW}{self.target}{Colors.RESET}")
        print(f"{Colors.CYAN}|{Colors.RESET}  Time:     {Colors.WHITE}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}")
        print(f"{Colors.CYAN}+-------------------------------------------------------------+{Colors.RESET}\n")
    
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
                            print(f"\r  {Colors.GREEN}[OK]{Colors.RESET} [{kernel_count}] {current_kernel[:40]:<40} ({current_passes} passes)")
                        kernel_count += 1
                        current_kernel = kernel_name
                        current_passes = 0
                        self.kernel_progress[kernel_name] = 0
                        print(f"\n  {Colors.YELLOW}[*]{Colors.RESET} [{kernel_count}] Profiling: {Colors.CYAN}{kernel_name[:40]}{Colors.RESET}")
            
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
                print(f"\n  {Colors.YELLOW}[WARN]{Colors.RESET}  {line.strip()}")
        
        # Final kernel summary
        if current_kernel:
            print(f"\r  {Colors.GREEN}[OK]{Colors.RESET} [{kernel_count}] {current_kernel[:40]:<40} ({current_passes} passes)")
        
        print(f"\n{Colors.GREEN}[OK] Profiled {kernel_count} unique kernel(s) in {self.format_time(time.time() - self.start_time)}{Colors.RESET}")

    def open_file_location(self, file_path: str):
        """Open file location in system file manager"""
        print(f"  {Colors.CYAN}[EXEC] open_file_location() executing for: {file_path}{Colors.RESET}")
        try:
            file_path = Path(file_path)
            if platform.system() == "Windows":
                # Open in Explorer and select the file
                print(f"  {Colors.CYAN}[EXEC] Running: explorer /select, {file_path}{Colors.RESET}")
                subprocess.run(["explorer", "/select,", str(file_path)], check=False)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", "-R", str(file_path)], check=False)
            else:  # Linux
                subprocess.run(["xdg-open", str(file_path.parent)], check=False)
            return True
        except Exception as e:
            print(f"  {Colors.YELLOW}[WARN] Could not open file location: {e}{Colors.RESET}")
            return False

    def discover_gui_tool_path(self, tool: str) -> Optional[str]:
        """Discover the actual path to the GUI tool executable"""
        print(f"  {Colors.CYAN}[DISCOVERY] Searching for {tool} GUI executable...{Colors.RESET}")

        try:
            # First, find the command-line tool to get installation directory
            if tool == "nsys":
                cmd_result = subprocess.run(["where", "nsys"], capture_output=True, text=True, timeout=5)
                if cmd_result.returncode == 0:
                    nsys_path = Path(cmd_result.stdout.strip().split('\n')[0])
                    print(f"  {Colors.CYAN}[DISCOVERY] Found nsys at: {nsys_path}{Colors.RESET}")

                    # Navigate to installation root and look for GUI in host directory
                    install_root = nsys_path.parent.parent  # Go up from target-windows-x64 to root
                    gui_candidates = [
                        install_root / "host-windows-x64" / "nsys-ui.exe",
                        install_root / "host" / "windows-x64" / "nsys-ui.exe",
                        install_root / "host" / "nsys-ui.exe"
                    ]

                    for candidate in gui_candidates:
                        if candidate.exists():
                            print(f"  {Colors.GREEN}[DISCOVERY] Found nsys-ui at: {candidate}{Colors.RESET}")
                            return str(candidate)

            elif tool == "ncu":
                cmd_result = subprocess.run(["where", "ncu"], capture_output=True, text=True, timeout=5)
                if cmd_result.returncode == 0:
                    ncu_paths = cmd_result.stdout.strip().split('\n')
                    # Look for the .bat file first (it's in the root directory)
                    for ncu_path in ncu_paths:
                        if ncu_path.endswith('.bat'):
                            install_root = Path(ncu_path).parent
                            print(f"  {Colors.CYAN}[DISCOVERY] Found ncu installation at: {install_root}{Colors.RESET}")

                            # Check for ncu-ui.bat first (simpler)
                            ncu_ui_bat = install_root / "ncu-ui.bat"
                            if ncu_ui_bat.exists():
                                print(f"  {Colors.GREEN}[DISCOVERY] Found ncu-ui.bat at: {ncu_ui_bat}{Colors.RESET}")
                                return str(ncu_ui_bat)

                            # Check for executable in host directory
                            gui_candidates = [
                                install_root / "host" / "windows-desktop-win7-x64" / "ncu-ui.exe",
                                install_root / "host" / "windows-x64" / "ncu-ui.exe",
                                install_root / "host" / "ncu-ui.exe"
                            ]

                            for candidate in gui_candidates:
                                if candidate.exists():
                                    print(f"  {Colors.GREEN}[DISCOVERY] Found ncu-ui at: {candidate}{Colors.RESET}")
                                    return str(candidate)
                            break

            # Fallback: Search common NVIDIA installation directories
            print(f"  {Colors.YELLOW}[DISCOVERY] Trying fallback search in common NVIDIA directories...{Colors.RESET}")
            program_files = Path("C:/Program Files/NVIDIA Corporation")
            if program_files.exists():
                if tool == "nsys":
                    for nsys_dir in program_files.glob("Nsight Systems*"):
                        for gui_path in nsys_dir.rglob("nsys-ui.exe"):
                            print(f"  {Colors.GREEN}[DISCOVERY] Found nsys-ui via fallback: {gui_path}{Colors.RESET}")
                            return str(gui_path)
                elif tool == "ncu":
                    for ncu_dir in program_files.glob("Nsight Compute*"):
                        ncu_ui_bat = ncu_dir / "ncu-ui.bat"
                        if ncu_ui_bat.exists():
                            print(f"  {Colors.GREEN}[DISCOVERY] Found ncu-ui.bat via fallback: {ncu_ui_bat}{Colors.RESET}")
                            return str(ncu_ui_bat)
                        for gui_path in ncu_dir.rglob("ncu-ui.exe"):
                            print(f"  {Colors.GREEN}[DISCOVERY] Found ncu-ui.exe via fallback: {gui_path}{Colors.RESET}")
                            return str(gui_path)

            print(f"  {Colors.RED}[DISCOVERY] Could not find {tool} GUI tool anywhere{Colors.RESET}")
            return None

        except Exception as e:
            print(f"  {Colors.YELLOW}[DISCOVERY] Error during discovery: {e}{Colors.RESET}")
            return None

    def launch_nsight_gui(self, file_path: str, tool: str):
        """Launch appropriate Nsight GUI tool"""
        print(f"  {Colors.CYAN}[EXEC] launch_nsight_gui() executing for: {file_path} with tool: {tool}{Colors.RESET}")
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                print(f"  {Colors.RED}[ERROR] Report file not found: {file_path}{Colors.RESET}")
                return False

            # Discover the actual GUI tool path
            gui_path = self.discover_gui_tool_path(tool)
            if not gui_path:
                print(f"  {Colors.RED}[ERROR] {tool.upper()} GUI tool not found. Please install NVIDIA Nsight tools.{Colors.RESET}")
                print(f"  {Colors.YELLOW}[HINT] Expected locations:{Colors.RESET}")
                if tool == "nsys":
                    print(f"    • C:/Program Files/NVIDIA Corporation/Nsight Systems*/host-*/nsys-ui.exe")
                elif tool == "ncu":
                    print(f"    • C:/Program Files/NVIDIA Corporation/Nsight Compute*/ncu-ui.bat")
                    print(f"    • C:/Program Files/NVIDIA Corporation/Nsight Compute*/host/*/ncu-ui.exe")
                return False

            print(f"  {Colors.CYAN}[LAUNCH] Starting {tool} GUI...{Colors.RESET}")
            print(f"  {Colors.CYAN}[EXEC] Running: {gui_path} {file_path}{Colors.RESET}")

            # Ensure file path is absolute and properly formatted
            abs_file_path = str(Path(file_path).resolve())
            print(f"  {Colors.CYAN}[DEBUG] Absolute path: {abs_file_path}{Colors.RESET}")

            # Launch GUI in background with safer parameters
            if platform.system() == "Windows":
                # Use simpler approach without complex creation flags
                try:
                    subprocess.Popen([gui_path, abs_file_path],
                                   shell=False,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                    print(f"  {Colors.GREEN}[DEBUG] Process launched successfully{Colors.RESET}")
                except Exception as launch_error:
                    print(f"  {Colors.YELLOW}[DEBUG] Primary launch failed: {launch_error}{Colors.RESET}")
                    # Fallback: try with shell=True
                    try:
                        cmd = f'"{gui_path}" "{abs_file_path}"'
                        print(f"  {Colors.CYAN}[DEBUG] Trying fallback: {cmd}{Colors.RESET}")
                        subprocess.Popen(cmd, shell=True,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
                        print(f"  {Colors.GREEN}[DEBUG] Fallback launch successful{Colors.RESET}")
                    except Exception as fallback_error:
                        print(f"  {Colors.RED}[DEBUG] Fallback also failed: {fallback_error}{Colors.RESET}")
                        raise fallback_error
            else:
                subprocess.Popen([gui_path, abs_file_path],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            return True
        except Exception as e:
            print(f"  {Colors.YELLOW}[WARN] Could not launch {tool} GUI: {e}{Colors.RESET}")
            return False

    def print_clickable_path(self, file_path: str):
        """Print clickable file path for terminals that support it"""
        try:
            file_path = Path(file_path).resolve()
            if platform.system() == "Windows":
                # Windows Terminal supports file:// links
                path_str = str(file_path).replace('\\', '/')
                clickable = f"file:///{path_str}"
            else:
                clickable = f"file://{file_path}"

            print(f"  {Colors.CYAN}[PATH] Open location:{Colors.RESET} {clickable}")
            print(f"     {Colors.GRAY}(Ctrl+Click to open in file manager){Colors.RESET}")
        except Exception:
            # Fallback to regular path
            print(f"  {Colors.CYAN}[PATH] File location:{Colors.RESET} {file_path}")
    
    def monitor_nsys_progress(self, process):
        """Monitor nsys output and show progress"""
        spinner = ['|', '/', '-', '\\', '|', '/', '-', '\\']
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
                    print(f"\r  {Colors.CYAN}[INFO]{Colors.RESET} {line[:60]:<60}", end='', flush=True)
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
        print(f"\r  {Colors.GREEN}[OK] Profiling complete! [{self.format_time(time.time() - self.start_time)}]{Colors.RESET}          ")
    
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
            print(f"  {Colors.CYAN}[*] Quick mode:{Colors.RESET} Essential CUDA + NVTX traces")
            cmd.extend(["--trace=cuda,nvtx"])
        
        # Add duration limit if specified
        if kwargs.get('duration'):
            cmd.extend([f"--duration={kwargs['duration']}"])
            print(f"  {Colors.CYAN}⏱  Duration:{Colors.RESET} {kwargs['duration']} seconds")
        
        cmd.extend(target_cmd)
        
        print(f"\n  {Colors.YELLOW}[>]{Colors.RESET} Starting Nsight Systems...")
        self.start_time = time.time()
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.monitor_nsys_progress(process)
        
        return_code = process.wait()
        
        # Check results
        expected_file = f"{report_path}.nsys-rep"
        if Path(expected_file).exists():
            size = Path(expected_file).stat().st_size
            print(f"\n  {Colors.GREEN}[FILE] Report saved:{Colors.RESET} {expected_file}")
            print(f"     Size: {self.format_size(size)}")

            # Print clickable path
            self.print_clickable_path(expected_file)

            # Offer to launch GUI
            print(f"\n  {Colors.CYAN}[LAUNCH] Launch options:{Colors.RESET}")
            print(f"     • Nsight Systems GUI: nsys-ui \"{expected_file}\"")

            return expected_file
        else:
            print(f"\n  {Colors.RED}[ERROR] Report not found at expected location{Colors.RESET}")
            return None
    
    def run_ncu(self, target_cmd: List[str], output_name: str, **kwargs):
        """Run Nsight Compute profiling"""
        report_path = self.ncu_dir / output_name
        
        cmd = ["ncu", "-o", str(report_path)]
        
        if self.mode == "full":
            print(f"  {Colors.CYAN}🔬 Full mode:{Colors.RESET} Complete kernel analysis (~43 passes per kernel)")
            print(f"  {Colors.YELLOW}[WARN]  Warning:{Colors.RESET} This will take several minutes...")
            cmd.extend(["--set", "full"])
        else:
            print(f"  {Colors.CYAN}[*] Quick mode:{Colors.RESET} Essential metrics (~5 passes per kernel)")
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
        
        print(f"\n  {Colors.YELLOW}[>]{Colors.RESET} Starting Nsight Compute...")
        self.start_time = time.time()
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.monitor_ncu_progress(process)
        
        return_code = process.wait()
        
        # Check results
        expected_file = f"{report_path}.ncu-rep"
        if Path(expected_file).exists():
            size = Path(expected_file).stat().st_size
            print(f"\n  {Colors.GREEN}[FILE] Report saved:{Colors.RESET} {expected_file}")
            print(f"     Size: {self.format_size(size)}")

            # Print clickable path
            self.print_clickable_path(expected_file)

            # Offer to launch GUI
            print(f"\n  {Colors.CYAN}[LAUNCH] Launch options:{Colors.RESET}")
            print(f"     • Nsight Compute GUI: ncu-ui \"{expected_file}\"")

            return expected_file
        else:
            print(f"\n  {Colors.RED}[ERROR] Report not found at expected location{Colors.RESET}")
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

    # Safety measures and validation - FAIL FAST
    print(f"  {Colors.CYAN}[VALIDATE] Running comprehensive profiling setup validation...{Colors.RESET}")
    validation_errors = []

    # 1. Check Python environment
    try:
        import sys
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(f"  {Colors.GREEN}[OK] Python {python_version} detected{Colors.RESET}")
    except Exception as e:
        validation_errors.append(f"Python environment issue: {e}")

    # 2. Check for CUDA availability
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            # Extract GPU info from nvidia-smi
            lines = result.stdout.split('\n')
            gpu_line = next((line for line in lines if 'NVIDIA' in line and 'Driver Version' in line), None)
            if gpu_line:
                print(f"  {Colors.GREEN}[OK] CUDA GPU detected{Colors.RESET}")
            else:
                print(f"  {Colors.YELLOW}[WARN] nvidia-smi responded but no GPU info found{Colors.RESET}")
        else:
            validation_errors.append("nvidia-smi command failed - CUDA may not be available")
    except subprocess.TimeoutExpired:
        validation_errors.append("nvidia-smi command timed out - system may be unresponsive")
    except FileNotFoundError:
        validation_errors.append("nvidia-smi not found - NVIDIA drivers may not be installed")

    # 3. Check for profiling tool availability with detailed validation
    tool_cmd = args.tool
    try:
        result = subprocess.run([tool_cmd, "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_info = result.stdout.strip()
            print(f"  {Colors.GREEN}[OK] {tool_cmd.upper()} available: {version_info.split()[-1] if version_info else 'version unknown'}{Colors.RESET}")
        else:
            validation_errors.append(f"{tool_cmd.upper()} version check failed (exit code: {result.returncode})")
    except subprocess.TimeoutExpired:
        validation_errors.append(f"{tool_cmd.upper()} command timed out - tool may be unresponsive")
    except FileNotFoundError:
        validation_errors.append(f"{tool_cmd.upper()} not found in PATH - please install NVIDIA Nsight tools")

    # 3.5. Check GUI tool availability (informational - not critical)
    gui_path = session.discover_gui_tool_path(tool_cmd)
    if gui_path:
        print(f"  {Colors.GREEN}[OK] {tool_cmd.upper()} GUI tool discovered: {Path(gui_path).name}{Colors.RESET}")
    else:
        print(f"  {Colors.YELLOW}[WARN] {tool_cmd.upper()} GUI tool not found - command-line profiling will work, but GUI launch will fail{Colors.RESET}")

    # 4. Check write permissions for output directory
    try:
        session.reports_dir.mkdir(parents=True, exist_ok=True)
        test_file = session.reports_dir / ".test_write"
        test_file.write_text("test")
        test_file.unlink()
        print(f"  {Colors.GREEN}[OK] Write permissions verified for: {session.reports_dir}{Colors.RESET}")
    except Exception as e:
        validation_errors.append(f"Cannot write to reports directory {session.reports_dir}: {e}")

    # FAIL FAST: Stop immediately if critical issues found
    if validation_errors:
        print(f"\n  {Colors.RED}[FATAL] Validation failed! Found {len(validation_errors)} critical issues:{Colors.RESET}")
        for i, error in enumerate(validation_errors, 1):
            print(f"    {i}. {error}")
        print(f"\n  {Colors.YELLOW}[ACTION] Please fix these issues before profiling:{Colors.RESET}")
        print(f"    • Install NVIDIA drivers and CUDA toolkit")
        print(f"    • Install NVIDIA Nsight tools (nsys, ncu)")
        print(f"    • Ensure sufficient disk space and permissions")
        print(f"    • Check system stability (no hanging processes)")
        exit(1)
    
    # Build target command
    preset_targets = ["latency", "throughput", "accuracy", "realtime"]

    if args.target in preset_targets:
        # Use simple direct Engine approach - bypass complex Hydra system
        target_cmd = ["python", "generate_demo_data.py"]
        if args.args and args.args[0] == "--":
            target_cmd.extend(args.args[1:])
        else:
            target_cmd.extend(args.args)
    elif args.target == "custom" and args.args:
        # Custom script path provided
        script_path = args.args[0] if args.args else "custom_script.py"
        target_cmd = ["python", script_path]
        if len(args.args) > 1:
            target_cmd.extend(args.args[1:])
    else:
        # Legacy format or module-based target
        if "." in args.target or "/" in args.target or "\\" in args.target:
            # Looks like a file path
            target_cmd = ["python", args.target]
        else:
            # Module format
            target_cmd = ["python", "-m", f"ionosense_hpc.benchmarks.{args.target}"]

        if args.args and args.args[0] == "--":
            target_cmd.extend(args.args[1:])
        else:
            target_cmd.extend(args.args)

    # Validate target script exists for preset targets
    if args.target in preset_targets:
        project_root = Path(__file__).parent.parent
        script_path = project_root / "benchmarks" / f"run_{args.target}.py"
        if not script_path.exists():
            print(f"  {Colors.RED}[X] Benchmark script not found: {script_path}{Colors.RESET}")
            exit(1)
        else:
            print(f"  {Colors.GREEN}[OK] Target script found: run_{args.target}.py{Colors.RESET}")

    print(f"  {Colors.GREEN}[OK] Validation complete{Colors.RESET}\n")

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

    # Post-profiling actions
    if report:
        print(f"\n{Colors.CYAN}[OPTIONS] Post-profiling actions:{Colors.RESET}")

        # Offer to open file location
        try:
            response = input(f"Open file location in explorer? (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                print(f"  {Colors.CYAN}[DEBUG] Calling open_file_location() for: {report}{Colors.RESET}")
                success = session.open_file_location(report)
                if success:
                    print(f"  {Colors.GREEN}[OK] File location opened in Windows Explorer{Colors.RESET}")
                else:
                    print(f"  {Colors.RED}[ERROR] Failed to open file location{Colors.RESET}")
        except (KeyboardInterrupt, EOFError):
            print()  # Clean newline

        # Offer to launch GUI
        try:
            response = input(f"Launch {args.tool.upper()} GUI? (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                print(f"  {Colors.CYAN}[DEBUG] Calling launch_nsight_gui() for: {report} with tool: {args.tool}{Colors.RESET}")
                success = session.launch_nsight_gui(report, args.tool)
                if success:
                    print(f"  {Colors.GREEN}[OK] {args.tool.upper()} GUI launched successfully{Colors.RESET}")
                else:
                    print(f"  {Colors.RED}[ERROR] Failed to launch {args.tool.upper()} GUI{Colors.RESET}")
        except (KeyboardInterrupt, EOFError):
            print()  # Clean newline

    # Print footer
    print(f"\n{Colors.GRAY}{'='*60}{Colors.RESET}")
    print(f"{Colors.CYAN}[REPORTS] Directory:{Colors.RESET} {session.reports_dir}")
    print(f"{Colors.GRAY}{'='*60}{Colors.RESET}")


if __name__ == "__main__":
    main()