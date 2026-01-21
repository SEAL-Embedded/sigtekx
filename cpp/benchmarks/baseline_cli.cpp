/**
 * @file baseline_cli.cpp
 * @brief CLI helper for C++ baseline management.
 *
 * Standalone executable for baseline operations (save, list, compare, delete).
 * Integrates with PowerShell CLI via JSON I/O for clean separation.
 *
 * Commands:
 *   baseline_cli save <name> [--message "..."]
 *   baseline_cli list [--preset <preset>]
 *   baseline_cli compare <name1> <name2>
 *   baseline_cli delete <name> [--force]
 */

#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <iomanip>

#include "core/config.hpp"
#include "core/persistence.hpp"
#include "core/results.hpp"
#include "utils/baseline_comparison.hpp"

using namespace sigtekx::benchmark;

// ============================================================================
// Command Handlers
// ============================================================================

/**
 * @brief List all baselines with optional filtering.
 *
 * @param preset_filter Optional preset filter (empty = show all)
 * @return Exit code (0 = success, 1 = error)
 */
int cmd_list(const std::string& preset_filter) {
  try {
    auto manifest = load_manifest();

    if (manifest.baselines.empty()) {
      std::cout << "No baselines found.\n";
      return 0;
    }

    // Filter by preset if specified
    std::vector<ManifestEntry> filtered = manifest.baselines;
    if (!preset_filter.empty()) {
      filtered.erase(
        std::remove_if(filtered.begin(), filtered.end(),
          [&](const ManifestEntry& entry) { return entry.preset != preset_filter; }),
        filtered.end()
      );
    }

    if (filtered.empty()) {
      std::cout << "No baselines found matching preset: " << preset_filter << "\n";
      return 0;
    }

    // Print table
    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  C++ Baselines\n";
    std::cout << "========================================\n\n";

    std::cout << std::left << std::setw(30) << "Name"
              << std::setw(15) << "Preset"
              << std::setw(12) << "Mode"
              << std::setw(10) << "Variant"
              << std::setw(20) << "Created" << "\n";
    std::cout << std::string(87, '-') << "\n";

    for (const auto& entry : filtered) {
      std::cout << std::left << std::setw(30) << entry.name
                << std::setw(15) << entry.preset
                << std::setw(12) << entry.mode
                << std::setw(10) << entry.iono_variant
                << std::setw(20) << entry.created << "\n";
    }

    std::cout << "\n";
    std::cout << "Total: " << filtered.size() << " baseline(s)\n\n";

    return 0;
  } catch (const std::exception& ex) {
    std::cerr << "Error listing baselines: " << ex.what() << "\n";
    return 1;
  }
}

/**
 * @brief Compare two baselines.
 *
 * @param name1 First baseline name
 * @param name2 Second baseline name
 * @return Exit code (0 = success, 1 = error)
 */
int cmd_compare(const std::string& name1, const std::string& name2) {
  try {
    auto manifest = load_manifest();

    // Find baselines in manifest
    auto it1 = std::find_if(manifest.baselines.begin(), manifest.baselines.end(),
      [&](const ManifestEntry& e) { return e.name == name1; });
    auto it2 = std::find_if(manifest.baselines.begin(), manifest.baselines.end(),
      [&](const ManifestEntry& e) { return e.name == name2; });

    if (it1 == manifest.baselines.end()) {
      std::cerr << "Baseline not found: " << name1 << "\n";
      return 1;
    }
    if (it2 == manifest.baselines.end()) {
      std::cerr << "Baseline not found: " << name2 << "\n";
      return 1;
    }

    // Check if presets match
    if (it1->preset != it2->preset) {
      std::cerr << "Cannot compare baselines with different presets: "
                << it1->preset << " vs " << it2->preset << "\n";
      return 1;
    }

    // Load results based on preset type
    std::string preset = it1->preset;
    auto baselines_root = get_baseline_root();

    if (preset == "latency") {
      auto results1 = load_latency_from_directory(baselines_root / name1);
      auto results2 = load_latency_from_directory(baselines_root / name2);
      auto summary = compare_latency(results1, results2, name1, name2);
      print_comparison(summary);
      return summary.overall_regression ? 1 : 0;
    } else if (preset == "throughput") {
      auto results1 = load_throughput_from_directory(baselines_root / name1);
      auto results2 = load_throughput_from_directory(baselines_root / name2);
      auto summary = compare_throughput(results1, results2, name1, name2);
      print_comparison(summary);
      return summary.overall_regression ? 1 : 0;
    } else if (preset == "realtime") {
      auto results1 = load_realtime_from_directory(baselines_root / name1);
      auto results2 = load_realtime_from_directory(baselines_root / name2);
      auto summary = compare_realtime(results1, results2, name1, name2);
      print_comparison(summary);
      return summary.overall_regression ? 1 : 0;
    } else if (preset == "accuracy") {
      auto results1 = load_accuracy_from_directory(baselines_root / name1);
      auto results2 = load_accuracy_from_directory(baselines_root / name2);
      auto summary = compare_accuracy(results1, results2, name1, name2);
      print_comparison(summary);
      return summary.overall_regression ? 1 : 0;
    } else {
      std::cerr << "Unknown preset type: " << preset << "\n";
      return 1;
    }
  } catch (const std::exception& ex) {
    std::cerr << "Error comparing baselines: " << ex.what() << "\n";
    return 1;
  }
}

/**
 * @brief Save last benchmark run as a named baseline.
 *
 * @param name Baseline name
 * @param message Optional description message
 * @return Exit code (0 = success, 1 = error)
 */
int cmd_save(const std::string& name, const std::string& message) {
  try {
    auto last_run_root = get_last_run_root();

    // Detect which preset was last run by checking .last_run directories
    std::string preset;
    std::filesystem::path source_dir;

    for (const auto& preset_name : {"latency", "throughput", "realtime", "accuracy"}) {
      auto dir = last_run_root / preset_name;
      if (std::filesystem::exists(dir / "results.json")) {
        preset = preset_name;
        source_dir = dir;
        break;
      }
    }

    if (preset.empty()) {
      std::cerr << "No recent benchmark run found in .last_run/\n";
      std::cerr << "Run a benchmark first: sigxc bench --preset <name>\n";
      return 1;
    }

    // Check if baseline with this name already exists
    auto manifest = load_manifest();
    for (const auto& entry : manifest.baselines) {
      if (entry.name == name) {
        std::cerr << "Baseline '" << name << "' already exists.\n";
        std::cerr << "Use a different name or delete the existing baseline first.\n";
        return 1;
      }
    }

    // Copy .last_run/{preset}/ to baselines/cpp/{name}/
    auto dest_dir = get_baseline_root() / name;
    std::filesystem::create_directories(dest_dir);

    std::filesystem::copy(source_dir / "results.json", dest_dir / "results.json",
                          std::filesystem::copy_options::overwrite_existing);
    std::filesystem::copy(source_dir / "metadata.json", dest_dir / "metadata.json",
                          std::filesystem::copy_options::overwrite_existing);
    std::filesystem::copy(source_dir / "results.csv", dest_dir / "results.csv",
                          std::filesystem::copy_options::overwrite_existing);

    // TODO: Update metadata.json to include name and message (requires JSON parsing/editing)
    // For now, the metadata will just have the original values from .last_run

    // Add to manifest
    ManifestEntry entry;
    entry.name = name;
    entry.created = get_timestamp();
    entry.preset = preset;
    entry.message = message;
    // TODO: Parse mode and iono_variant from metadata.json
    entry.mode = "full";  // Placeholder
    entry.iono_variant = "none";  // Placeholder

    // Update manifest (file-locked)
    FileLock lock(get_manifest_lock_path());
    auto updated_manifest = load_manifest();
    updated_manifest.baselines.push_back(entry);
    save_manifest(updated_manifest);

    std::cout << "Baseline '" << name << "' created successfully from " << preset << " run.\n";
    if (!message.empty()) {
      std::cout << "Message: " << message << "\n";
    }
    std::cout << "Location: " << dest_dir << "\n";

    return 0;
  } catch (const std::exception& ex) {
    std::cerr << "Error saving baseline: " << ex.what() << "\n";
    return 1;
  }
}

/**
 * @brief Delete a baseline.
 *
 * @param name Baseline name
 * @param force Skip confirmation
 * @return Exit code (0 = success, 1 = error)
 */
int cmd_delete(const std::string& name, bool force) {
  try {
    auto manifest = load_manifest();

    // Check if baseline exists
    auto it = std::find_if(manifest.baselines.begin(), manifest.baselines.end(),
      [&](const ManifestEntry& e) { return e.name == name; });

    if (it == manifest.baselines.end()) {
      std::cerr << "Baseline not found: " << name << "\n";
      return 1;
    }

    // Confirmation (if not forced)
    if (!force) {
      std::cout << "Delete baseline '" << name << "' (preset: " << it->preset << ")? [y/N]: ";
      std::string response;
      std::getline(std::cin, response);

      if (response != "y" && response != "Y") {
        std::cout << "Aborted.\n";
        return 0;
      }
    }

    // Delete directory
    auto baseline_dir = get_baseline_root() / name;
    if (std::filesystem::exists(baseline_dir)) {
      std::filesystem::remove_all(baseline_dir);
      std::cout << "Deleted: " << baseline_dir << "\n";
    }

    // Remove from manifest (file-locked)
    remove_from_manifest(name);

    std::cout << "Baseline '" << name << "' deleted successfully.\n";
    return 0;
  } catch (const std::exception& ex) {
    std::cerr << "Error deleting baseline: " << ex.what() << "\n";
    return 1;
  }
}

// ============================================================================
// Main Entry Point
// ============================================================================

void print_usage() {
  std::cout << "Usage: baseline_cli <command> [options]\n\n";
  std::cout << "Commands:\n";
  std::cout << "  save <name> [--message <msg>]    Save last benchmark run as named baseline\n";
  std::cout << "  list [--preset <name>]           List all baselines (optionally filtered by preset)\n";
  std::cout << "  compare <name1> <name2>          Compare two baselines\n";
  std::cout << "  delete <name> [--force]          Delete a baseline\n";
  std::cout << "\n";
  std::cout << "Examples:\n";
  std::cout << "  baseline_cli save pre_phase1 --message \"Before optimization\"\n";
  std::cout << "  baseline_cli list\n";
  std::cout << "  baseline_cli list --preset latency\n";
  std::cout << "  baseline_cli compare pre_phase1 post_phase1\n";
  std::cout << "  baseline_cli delete old_baseline\n";
  std::cout << "  baseline_cli delete old_baseline --force\n";
  std::cout << "\n";
}

int main(int argc, char* argv[]) {
  if (argc < 2) {
    print_usage();
    return 1;
  }

  std::string command = argv[1];

  try {
    if (command == "save") {
      if (argc < 3) {
        std::cerr << "Error: save requires a baseline name\n";
        print_usage();
        return 1;
      }
      std::string name = argv[2];
      std::string message;
      if (argc >= 5 && std::string(argv[3]) == "--message") {
        message = argv[4];
      }
      return cmd_save(name, message);
    } else if (command == "list") {
      std::string preset_filter;
      if (argc >= 4 && std::string(argv[2]) == "--preset") {
        preset_filter = argv[3];
      }
      return cmd_list(preset_filter);
    } else if (command == "compare") {
      if (argc < 4) {
        std::cerr << "Error: compare requires two baseline names\n";
        print_usage();
        return 1;
      }
      return cmd_compare(argv[2], argv[3]);
    } else if (command == "delete") {
      if (argc < 3) {
        std::cerr << "Error: delete requires a baseline name\n";
        print_usage();
        return 1;
      }
      bool force = (argc >= 4 && std::string(argv[3]) == "--force");
      return cmd_delete(argv[2], force);
    } else {
      std::cerr << "Unknown command: " << command << "\n\n";
      print_usage();
      return 1;
    }
  } catch (const std::exception& ex) {
    std::cerr << "Fatal error: " << ex.what() << "\n";
    return 1;
  }
}
