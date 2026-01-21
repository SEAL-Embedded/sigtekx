/**
 * @file git_info.hpp
 * @brief Git repository information for baseline metadata.
 *
 * Provides git commit, branch, and dirty flag detection using
 * cross-platform command execution. Gracefully handles cases
 * where git is not available or not in a git repository.
 */

#pragma once

#include <array>
#include <memory>
#include <string>

#ifdef _WIN32
#define popen _popen
#define pclose _pclose
#endif

namespace sigtekx {
namespace benchmark {

// ============================================================================
// Git Info Structure
// ============================================================================

/**
 * @brief Git repository information.
 */
struct GitInfo {
  std::string commit;   // Full commit hash
  std::string branch;   // Current branch name
  bool dirty;           // True if uncommitted changes exist
};

// ============================================================================
// Command Execution Utilities
// ============================================================================

/**
 * @brief Execute shell command and return output.
 *
 * @param cmd Command to execute
 * @return Command output (trimmed), or empty string on error
 */
inline std::string exec_command(const char* cmd) {
  std::array<char, 128> buffer;
  std::string result;

  // Open pipe to command
  std::unique_ptr<FILE, decltype(&pclose)> pipe(popen(cmd, "r"), pclose);
  if (!pipe) {
    return "";  // Command failed to execute
  }

  // Read output
  while (fgets(buffer.data(), buffer.size(), pipe.get()) != nullptr) {
    result += buffer.data();
  }

  // Trim trailing newline
  if (!result.empty() && result.back() == '\n') {
    result.pop_back();
  }

  // Trim trailing carriage return (Windows)
  if (!result.empty() && result.back() == '\r') {
    result.pop_back();
  }

  return result;
}

// ============================================================================
// Git Information Extraction
// ============================================================================

/**
 * @brief Get git commit hash.
 *
 * @return Full commit hash, or "unknown" if not available
 */
inline std::string get_git_commit() {
  std::string commit = exec_command("git rev-parse HEAD 2>nul");  // Windows: 2>nul suppresses errors

  if (commit.empty() || commit.find("fatal") != std::string::npos) {
    // Try Unix-style error suppression
    commit = exec_command("git rev-parse HEAD 2>/dev/null");
  }

  if (commit.empty() || commit.find("fatal") != std::string::npos) {
    return "unknown";  // Not in a git repo or git not available
  }

  return commit;
}

/**
 * @brief Get current git branch.
 *
 * @return Branch name, or "unknown" if not available
 */
inline std::string get_git_branch() {
  std::string branch = exec_command("git branch --show-current 2>nul");

  if (branch.empty() || branch.find("fatal") != std::string::npos) {
    // Try Unix-style error suppression
    branch = exec_command("git branch --show-current 2>/dev/null");
  }

  if (branch.empty() || branch.find("fatal") != std::string::npos) {
    // Fallback: try rev-parse --abbrev-ref HEAD
    branch = exec_command("git rev-parse --abbrev-ref HEAD 2>nul");

    if (branch.empty() || branch.find("fatal") != std::string::npos) {
      branch = exec_command("git rev-parse --abbrev-ref HEAD 2>/dev/null");
    }
  }

  if (branch.empty() || branch.find("fatal") != std::string::npos) {
    return "unknown";
  }

  return branch;
}

/**
 * @brief Check if repository has uncommitted changes.
 *
 * @return True if dirty (uncommitted changes), false if clean or unknown
 */
inline bool is_git_dirty() {
  std::string status = exec_command("git status --porcelain 2>nul");

  if (status.empty() || status.find("fatal") != std::string::npos) {
    // Try Unix-style error suppression
    status = exec_command("git status --porcelain 2>/dev/null");
  }

  if (status.find("fatal") != std::string::npos) {
    return false;  // Not in a git repo - consider clean
  }

  // If output is non-empty (excluding "fatal" errors), repo is dirty
  return !status.empty();
}

/**
 * @brief Get complete git repository information.
 *
 * @return Git info structure with commit, branch, and dirty flag
 */
inline GitInfo get_git_info() {
  GitInfo info;
  info.commit = get_git_commit();
  info.branch = get_git_branch();
  info.dirty = is_git_dirty();
  return info;
}

}  // namespace benchmark
}  // namespace sigtekx
