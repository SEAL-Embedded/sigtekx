/**
 * @file hardware_info.hpp
 * @brief Hardware detection for dataset metadata tracking.
 *
 * Provides comprehensive hardware detection including:
 * - GPU: Name, memory, compute capability, CUDA versions
 * - CPU: Brand, cores, threads
 * - System: OS, OS version, RAM
 *
 * DRY Principle: Reuses existing GPU detection from main.cpp
 */

#pragma once

#include <cuda_runtime.h>
#include <sstream>
#include <string>

#ifdef _WIN32
#include <windows.h>
#include <intrin.h>
#else
#include <sys/utsname.h>
#include <unistd.h>
#endif

namespace sigtekx {
namespace benchmark {

// ============================================================================
// Hardware Info Structures
// ============================================================================

/**
 * @brief GPU information.
 */
struct GPUInfo {
  std::string name;
  float memory_gb;
  std::string compute_capability;
  std::string cuda_runtime;
  std::string cuda_driver;
};

/**
 * @brief CPU information.
 */
struct CPUInfo {
  std::string model;
  int cores;
  int threads;
};

/**
 * @brief System information.
 */
struct SystemInfo {
  std::string os;
  std::string os_version;
  float ram_gb;
};

/**
 * @brief Complete hardware information.
 */
struct HardwareInfo {
  GPUInfo gpu;
  CPUInfo cpu;
  SystemInfo system;
};

// ============================================================================
// GPU Detection (Reuses existing CUDA queries)
// ============================================================================

/**
 * @brief Get GPU information.
 *
 * @return GPU info structure
 */
inline GPUInfo get_gpu_info() {
  GPUInfo info;

  // Get device properties
  cudaDeviceProp prop;
  cudaError_t err = cudaGetDeviceProperties(&prop, 0);
  if (err != cudaSuccess) {
    info.name = "Unknown GPU";
    info.memory_gb = 0.0f;
    info.compute_capability = "0.0";
    info.cuda_runtime = "Unknown";
    info.cuda_driver = "Unknown";
    return info;
  }

  // Device name
  info.name = prop.name;

  // Memory size (GB)
  info.memory_gb = static_cast<float>(prop.totalGlobalMem) / (1024.0f * 1024.0f * 1024.0f);

  // Compute capability
  std::ostringstream cc;
  cc << prop.major << "." << prop.minor;
  info.compute_capability = cc.str();

  // CUDA runtime version
  int runtime_version = 0;
  cudaRuntimeGetVersion(&runtime_version);
  std::ostringstream runtime_ss;
  runtime_ss << (runtime_version / 1000) << "." << ((runtime_version % 100) / 10);
  info.cuda_runtime = runtime_ss.str();

  // CUDA driver version
  int driver_version = 0;
  cudaDriverGetVersion(&driver_version);
  std::ostringstream driver_ss;
  driver_ss << (driver_version / 1000) << "." << ((driver_version % 100) / 10);
  info.cuda_driver = driver_ss.str();

  return info;
}

// ============================================================================
// CPU Detection
// ============================================================================

#ifdef _WIN32

/**
 * @brief Get CPU brand string (Windows).
 *
 * @return CPU brand string
 */
inline std::string get_cpu_brand() {
  int cpu_info[4] = {0};
  char brand[0x40] = {0};

  // Get CPU brand string using __cpuid
  __cpuid(cpu_info, 0x80000000);
  unsigned int max_extended = cpu_info[0];

  if (max_extended >= 0x80000004) {
    __cpuid(cpu_info, 0x80000002);
    memcpy(brand, cpu_info, sizeof(cpu_info));
    __cpuid(cpu_info, 0x80000003);
    memcpy(brand + 16, cpu_info, sizeof(cpu_info));
    __cpuid(cpu_info, 0x80000004);
    memcpy(brand + 32, cpu_info, sizeof(cpu_info));
  }

  std::string brand_str(brand);

  // Trim leading/trailing whitespace
  size_t start = brand_str.find_first_not_of(" \t");
  size_t end = brand_str.find_last_not_of(" \t");

  if (start != std::string::npos && end != std::string::npos) {
    return brand_str.substr(start, end - start + 1);
  }

  return "Unknown CPU";
}

/**
 * @brief Get CPU core/thread count (Windows).
 *
 * @param cores Output: physical cores
 * @param threads Output: logical threads
 */
inline void get_cpu_cores(int& cores, int& threads) {
  SYSTEM_INFO sysinfo;
  GetSystemInfo(&sysinfo);
  threads = static_cast<int>(sysinfo.dwNumberOfProcessors);

  // Estimate physical cores (conservative: assume 2 threads per core)
  // This is a heuristic - more accurate detection would require GetLogicalProcessorInformation
  cores = threads / 2;
  if (cores < 1) cores = threads;  // Fallback for single-threaded CPUs
}

#else  // Linux/Unix

/**
 * @brief Get CPU brand string (Linux).
 *
 * @return CPU brand string
 */
inline std::string get_cpu_brand() {
  // Try reading from /proc/cpuinfo
  std::ifstream cpuinfo("/proc/cpuinfo");
  if (cpuinfo.is_open()) {
    std::string line;
    while (std::getline(cpuinfo, line)) {
      if (line.find("model name") != std::string::npos) {
        size_t colon = line.find(':');
        if (colon != std::string::npos) {
          std::string brand = line.substr(colon + 1);
          // Trim leading whitespace
          size_t start = brand.find_first_not_of(" \t");
          if (start != std::string::npos) {
            return brand.substr(start);
          }
        }
      }
    }
  }

  return "Unknown CPU";
}

/**
 * @brief Get CPU core/thread count (Linux).
 *
 * @param cores Output: physical cores
 * @param threads Output: logical threads
 */
inline void get_cpu_cores(int& cores, int& threads) {
  threads = static_cast<int>(sysconf(_SC_NPROCESSORS_ONLN));

  // Try reading from /proc/cpuinfo for physical cores
  std::ifstream cpuinfo("/proc/cpuinfo");
  std::string line;
  int core_ids = 0;

  if (cpuinfo.is_open()) {
    while (std::getline(cpuinfo, line)) {
      if (line.find("cpu cores") != std::string::npos) {
        size_t colon = line.find(':');
        if (colon != std::string::npos) {
          cores = std::stoi(line.substr(colon + 1));
          return;
        }
      }
    }
  }

  // Fallback: assume half threads are cores
  cores = threads / 2;
  if (cores < 1) cores = threads;
}

#endif

/**
 * @brief Get CPU information.
 *
 * @return CPU info structure
 */
inline CPUInfo get_cpu_info() {
  CPUInfo info;
  info.model = get_cpu_brand();
  get_cpu_cores(info.cores, info.threads);
  return info;
}

// ============================================================================
// System Detection
// ============================================================================

#ifdef _WIN32

/**
 * @brief Get Windows version string.
 *
 * @return OS version string
 */
inline std::string get_windows_version() {
  // Use registry to get Windows version (more reliable than deprecated GetVersionEx)
  HKEY hKey;
  char version[256] = "Unknown";
  DWORD size = sizeof(version);

  if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,
                    "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion",
                    0, KEY_READ, &hKey) == ERROR_SUCCESS) {
    // Try ProductName first (e.g., "Windows 11 Pro")
    if (RegQueryValueExA(hKey, "ProductName", nullptr, nullptr,
                         (LPBYTE)version, &size) == ERROR_SUCCESS) {
      RegCloseKey(hKey);
      return std::string(version);
    }
    RegCloseKey(hKey);
  }

  return "Windows (version unknown)";
}

/**
 * @brief Get system RAM size (Windows).
 *
 * @return RAM size in GB
 */
inline float get_ram_size_gb() {
  MEMORYSTATUSEX memInfo;
  memInfo.dwLength = sizeof(MEMORYSTATUSEX);

  if (GlobalMemoryStatusEx(&memInfo)) {
    return static_cast<float>(memInfo.ullTotalPhys) / (1024.0f * 1024.0f * 1024.0f);
  }

  return 0.0f;
}

#else  // Linux/Unix

/**
 * @brief Get Linux version string.
 *
 * @return OS version string
 */
inline std::string get_linux_version() {
  struct utsname buffer;
  if (uname(&buffer) == 0) {
    std::ostringstream oss;
    oss << buffer.sysname << " " << buffer.release;
    return oss.str();
  }

  return "Linux (version unknown)";
}

/**
 * @brief Get system RAM size (Linux).
 *
 * @return RAM size in GB
 */
inline float get_ram_size_gb() {
  long pages = sysconf(_SC_PHYS_PAGES);
  long page_size = sysconf(_SC_PAGE_SIZE);

  if (pages > 0 && page_size > 0) {
    return static_cast<float>(pages * page_size) / (1024.0f * 1024.0f * 1024.0f);
  }

  return 0.0f;
}

#endif

/**
 * @brief Get system information.
 *
 * @return System info structure
 */
inline SystemInfo get_system_info() {
  SystemInfo info;

#ifdef _WIN32
  info.os = "Windows";
  info.os_version = get_windows_version();
#else
  info.os = "Linux";
  info.os_version = get_linux_version();
#endif

  info.ram_gb = get_ram_size_gb();

  return info;
}

// ============================================================================
// Complete Hardware Detection
// ============================================================================

/**
 * @brief Get complete hardware information.
 *
 * @return Hardware info structure with GPU, CPU, and system details
 */
inline HardwareInfo get_hardware_info() {
  HardwareInfo info;
  info.gpu = get_gpu_info();
  info.cpu = get_cpu_info();
  info.system = get_system_info();
  return info;
}

}  // namespace benchmark
}  // namespace sigtekx
