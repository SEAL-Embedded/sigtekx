/**
 * @file bindings.cpp
 * @version 0.9.4
 * @date 2025-10-23
 * @author [Kevin Rahsaz]
 *
 * @brief pybind11 wrappers to expose C++ executors to Python.
 *
 * This file creates the Python module `_native` and provides bindings for
 * the pipeline executor architecture. It includes Python-friendly wrapper
 * classes to handle conversions between NumPy arrays and C++ pointers,
 * enabling efficient, zero-copy data exchange where possible.
 */

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <sstream>

#include "sigtekx/core/executor_config.hpp"
#include "sigtekx/core/pipeline_executor.hpp"
#include "sigtekx/core/processing_stage.hpp"
#include "sigtekx/executors/batch_executor.hpp"
#include "sigtekx/executors/streaming_executor.hpp"

namespace py = pybind11;
namespace sigtekx {

/**
 * @class PyExecutor
 * @brief A Python-facing wrapper template for C++ executors.
 *
 * This class adapts the C++ executor's pointer-based API to a more Pythonic,
 * NumPy-based interface. It manages input/output buffers and validates array
 * shapes and sizes to provide a safe and convenient API for Python users.
 */
template <typename ExecutorType>
class PyExecutor {
 public:
  /**
   * @brief Constructs the Python wrapper and the underlying C++ executor.
   */
  PyExecutor() : executor_(std::make_unique<ExecutorType>()) {}

  /**
   * @brief Initializes the executor and pre-allocates Python-side buffers.
   * @param config The executor configuration.
   */
  void initialize(const ExecutorConfig& config) {
    // Create default pipeline stages
    auto stages = StageFactory::create_default_pipeline();

    // Initialize executor with config and stages
    executor_->initialize(config, std::move(stages));
    config_ = config;

    // Allocate all buffers in the pool
    size_t buffer_size = config.num_output_bins() * config.channels;
    for (auto& buffer : output_buffers_) {
      buffer.resize(buffer_size);
    }
    current_buffer_idx_ = 0;
  }

  /**
   * @brief Processes a NumPy array.
   * @param input A 1D NumPy array of floats.
   * @return A 2D NumPy array containing the magnitude spectra.
   * @throws std::runtime_error if input dimensions or size are incorrect.
   */
  py::array_t<float> process(
      py::array_t<float, py::array::c_style | py::array::forcecast> input) {
    if (input.ndim() != 1) {
      throw std::runtime_error("Input must be a 1D NumPy array.");
    }

    size_t expected_size = static_cast<size_t>(config_.nfft) * config_.channels;
    if (static_cast<size_t>(input.size()) != expected_size) {
      std::ostringstream oss;
      oss << "Input size mismatch. Expected " << expected_size
          << " samples, but got " << input.size() << ".";
      throw std::runtime_error(oss.str());
    }

    // Get next buffer from pool (round-robin)
    size_t idx = current_buffer_idx_;
    current_buffer_idx_ = (current_buffer_idx_ + 1) % BUFFER_POOL_SIZE;

    executor_->submit(input.data(), output_buffers_[idx].data(), expected_size);

    // Return zero-copy view using py::array_t constructor
    // This creates a view without copying (reference_internal keeps executor alive)
    std::vector<py::ssize_t> shape = {
        static_cast<py::ssize_t>(config_.channels),
        static_cast<py::ssize_t>(config_.num_output_bins())
    };
    std::vector<py::ssize_t> strides = {
        static_cast<py::ssize_t>(config_.num_output_bins() * sizeof(float)),
        sizeof(float)
    };

    return py::array_t<float>(
        shape,                           // Shape
        strides,                         // Strides (in bytes)
        output_buffers_[idx].data(),     // Data pointer (zero-copy)
        py::cast(*this)                  // Base object (keeps this alive)
    );
  }

  /** @brief Resets the executor to an uninitialized state. */
  void reset() { executor_->reset(); }

  /** @brief Synchronizes all CUDA streams. */
  void synchronize() { executor_->synchronize(); }

  /** @brief Gets the latest processing statistics. */
  ProcessingStats get_stats() const { return executor_->get_stats(); }

  /** @brief Checks if the executor has been initialized. */
  bool is_initialized() const { return executor_->is_initialized(); }

  /** @brief Gets the current executor configuration. */
  ExecutorConfig get_config() const { return config_; }

 private:
  std::unique_ptr<ExecutorType> executor_;
  ExecutorConfig config_;

  // Buffer pool for zero-copy returns (4 buffers for round-robin allocation)
  static constexpr size_t BUFFER_POOL_SIZE = 4;
  std::array<std::vector<float>, BUFFER_POOL_SIZE> output_buffers_;
  size_t current_buffer_idx_ = 0;
};

// Type aliases for Python bindings
using PyBatchExecutor = PyExecutor<BatchExecutor>;
using PyStreamingExecutor = PyExecutor<StreamingExecutor>;

}  // namespace sigtekx

/**
 * @brief The pybind11 module definition.
 *
 * This macro defines the `_native` Python module and binds all the C++
 * classes, methods, and enumerations to make them accessible from Python.
 */
PYBIND11_MODULE(_native, m) {
  m.doc() = R"pbdoc(
        SigTekX CUDA FFT Engine - C++ Core Module (v0.9.3)

        This module provides high-performance CUDA-accelerated signal processing
        with a composable pipeline/executor architecture.

        Architecture (v0.9.3 - executor-direct):
        - BatchExecutor: High-throughput batch processing
        - StreamingExecutor: Low-latency streaming (stub in v0.9.3)
        - ExecutorConfig: Unified configuration with execution mode
        - StageFactory: Pipeline stage construction

        Key classes:
        - BatchExecutor: Direct batch executor (no facade)
        - StreamingExecutor: Direct streaming executor (no facade)
        - ExecutorConfig: Configuration with mode-aware presets
        - StageConfig: Per-stage configuration

        Example:
            >>> import _native
            >>> config = _native.ExecutorConfig()
            >>> config.nfft = 1024
            >>> config.channels = 4
            >>> config.mode = _native.ExecutionMode.BATCH
            >>> executor = _native.BatchExecutor()
            >>> executor.initialize(config)
            >>> output = executor.process(input_data)
    )pbdoc";

  // --- Bind Enums for StageConfig ---
  py::enum_<sigtekx::StageConfig::WindowType>(m, "WindowType")
      .value("RECTANGULAR", sigtekx::StageConfig::WindowType::RECTANGULAR)
      .value("HANN", sigtekx::StageConfig::WindowType::HANN)
      .value("BLACKMAN", sigtekx::StageConfig::WindowType::BLACKMAN)
      .export_values();

  py::enum_<sigtekx::StageConfig::WindowSymmetry>(
      m, "WindowSymmetry",
      "Window symmetry mode (PERIODIC for FFT, SYMMETRIC for time-domain)")
      .value("PERIODIC", sigtekx::StageConfig::WindowSymmetry::PERIODIC,
             "Periodic window (FFT processing, denominator N)")
      .value("SYMMETRIC", sigtekx::StageConfig::WindowSymmetry::SYMMETRIC,
             "Symmetric window (time-domain, denominator N-1)")
      .export_values();

  py::enum_<sigtekx::StageConfig::WindowNorm>(m, "WindowNorm",
                                              "Window normalization scheme")
      .value("UNITY", sigtekx::StageConfig::WindowNorm::UNITY,
             "Unity power/energy gain normalization")
      .value("SQRT", sigtekx::StageConfig::WindowNorm::SQRT,
             "Square root normalization")
      .export_values();

  py::enum_<sigtekx::StageConfig::ScalePolicy>(m, "ScalePolicy")
      .value("NONE", sigtekx::StageConfig::ScalePolicy::NONE)
      .value("ONE_OVER_N", sigtekx::StageConfig::ScalePolicy::ONE_OVER_N)
      .value("ONE_OVER_SQRT_N",
             sigtekx::StageConfig::ScalePolicy::ONE_OVER_SQRT_N)
      .export_values();

  py::enum_<sigtekx::StageConfig::OutputMode>(m, "OutputMode",
                                              "Pipeline output format")
      .value("MAGNITUDE", sigtekx::StageConfig::OutputMode::MAGNITUDE,
             "Real magnitude spectrum")
      .value("COMPLEX_PASSTHROUGH",
             sigtekx::StageConfig::OutputMode::COMPLEX_PASSTHROUGH,
             "Complex FFT output")
      .export_values();

  // --- Bind ExecutorConfig Enums (v0.9.3 architecture) ---
  py::enum_<sigtekx::ExecutorConfig::ExecutionMode>(m, "ExecutionMode",
                                                    "Execution strategy for "
                                                    "pipeline executors")
      .value("BATCH", sigtekx::ExecutorConfig::ExecutionMode::BATCH,
             "Process complete batches with maximum throughput")
      .value("STREAMING", sigtekx::ExecutorConfig::ExecutionMode::STREAMING,
             "Continuous processing with low-latency via ring buffer (v0.9.4+)")
      .export_values();

  // --- Bind Configuration Structs ---
  py::class_<sigtekx::SignalConfig>(m, "SignalConfig")
      .def(py::init<>())
      .def_readwrite("nfft", &sigtekx::SignalConfig::nfft)
      .def_readwrite("channels", &sigtekx::SignalConfig::channels)
      .def_readwrite("overlap", &sigtekx::SignalConfig::overlap)
      .def_readwrite("sample_rate_hz", &sigtekx::SignalConfig::sample_rate_hz)
      .def_readwrite("window_type", &sigtekx::SignalConfig::window_type)
      .def_readwrite("window_symmetry", &sigtekx::SignalConfig::window_symmetry)
      .def_readwrite("window_norm", &sigtekx::SignalConfig::window_norm)
      .def_readwrite("scale_policy", &sigtekx::SignalConfig::scale_policy)
      .def_readwrite("output_mode", &sigtekx::SignalConfig::output_mode)
      .def_readwrite("stream_count", &sigtekx::SignalConfig::stream_count)
      .def_readwrite("pinned_buffer_count",
                     &sigtekx::SignalConfig::pinned_buffer_count)
      .def_readwrite("warmup_iters", &sigtekx::SignalConfig::warmup_iters)
      .def("num_output_bins", &sigtekx::SignalConfig::num_output_bins)
      .def("__repr__", [](const sigtekx::SignalConfig& c) {
        return "<SignalConfig nfft=" + std::to_string(c.nfft) +
               ", channels=" + std::to_string(c.channels) + ">";
      });

  // --- Bind ExecutorConfig (v0.9.3 architecture) ---
  py::class_<sigtekx::ExecutorConfig, sigtekx::SignalConfig>(
      m, "ExecutorConfig",
      "Configuration for pipeline executors (extends SignalConfig)")
      .def(py::init<>())
      .def_readwrite("mode", &sigtekx::ExecutorConfig::mode,
                     "Execution strategy (BATCH/STREAMING)")
      .def_readwrite("max_inflight_batches",
                     &sigtekx::ExecutorConfig::max_inflight_batches,
                     "Maximum concurrent batches (streaming mode, v0.9.4+)")
      .def_readwrite("device_id", &sigtekx::ExecutorConfig::device_id,
                     "CUDA device ID (-1 for auto-select)")
      .def("__repr__", [](const sigtekx::ExecutorConfig& c) {
        std::string mode_str;
        switch (c.mode) {
          case sigtekx::ExecutorConfig::ExecutionMode::BATCH:
            mode_str = "BATCH";
            break;
          case sigtekx::ExecutorConfig::ExecutionMode::STREAMING:
            mode_str = "STREAMING";
            break;
        }
        return "<ExecutorConfig mode=" + mode_str +
               ", nfft=" + std::to_string(c.nfft) +
               ", channels=" + std::to_string(c.channels) + ">";
      });

  py::class_<sigtekx::StageConfig>(m, "StageConfig")
      .def(py::init<>())
      .def_readwrite("nfft", &sigtekx::StageConfig::nfft)
      .def_readwrite("window_type", &sigtekx::StageConfig::window_type)
      // ... Bind other StageConfig members
      .def("__repr__", [](const sigtekx::StageConfig& c) {
        return "<StageConfig nfft=" + std::to_string(c.nfft) + ">";
      });

  // --- Bind Statistics and Info Structs ---
  py::class_<sigtekx::ProcessingStats>(m, "ProcessingStats")
      .def_readonly("latency_us", &sigtekx::ProcessingStats::latency_us)
      .def_readonly("throughput_gbps",
                    &sigtekx::ProcessingStats::throughput_gbps)
      .def_readonly("frames_processed",
                    &sigtekx::ProcessingStats::frames_processed);

  // --- Bind Executor Classes ---
  py::class_<sigtekx::PyBatchExecutor>(
      m, "BatchExecutor",
      "High-throughput batch executor for processing complete batches")
      .def(py::init<>())
      .def("initialize", &sigtekx::PyBatchExecutor::initialize,
           py::arg("config"), "Initializes the executor with configuration.")
      .def("process", &sigtekx::PyBatchExecutor::process,
           py::return_value_policy::reference_internal,
           py::arg("input"),
           "Processes input and returns zero-copy view into internal buffer.\n\n"
           "IMPORTANT: Returned array is valid while executor exists.\n"
           "Up to 4 outputs can be safely stored before buffer reuse.\n"
           "For independent copy: result.copy()")
      .def("reset", &sigtekx::PyBatchExecutor::reset,
           "Resets the executor to uninitialized state.")
      .def("synchronize", &sigtekx::PyBatchExecutor::synchronize,
           "Synchronizes all CUDA streams.")
      .def("get_stats", &sigtekx::PyBatchExecutor::get_stats,
           "Gets performance statistics from last operation.")
      .def_property_readonly("is_initialized",
                             &sigtekx::PyBatchExecutor::is_initialized,
                             "Check if executor is initialized.");

  py::class_<sigtekx::PyStreamingExecutor>(
      m, "StreamingExecutor", "Low-latency streaming executor (stub in v0.9.3)")
      .def(py::init<>())
      .def("initialize", &sigtekx::PyStreamingExecutor::initialize,
           py::arg("config"), "Initializes the executor with configuration.")
      .def("process", &sigtekx::PyStreamingExecutor::process,
           py::return_value_policy::reference_internal,
           py::arg("input"),
           "Processes input and returns zero-copy view into internal buffer.\n\n"
           "IMPORTANT: Returned array is valid while executor exists.\n"
           "Up to 4 outputs can be safely stored before buffer reuse.\n"
           "For independent copy: result.copy()")
      .def("reset", &sigtekx::PyStreamingExecutor::reset,
           "Resets the executor to uninitialized state.")
      .def("synchronize", &sigtekx::PyStreamingExecutor::synchronize,
           "Synchronizes all CUDA streams.")
      .def("get_stats", &sigtekx::PyStreamingExecutor::get_stats,
           "Gets performance statistics from last operation.")
      .def_property_readonly("is_initialized",
                             &sigtekx::PyStreamingExecutor::is_initialized,
                             "Check if executor is initialized.");

  // --- Bind Utility Functions ---
  m.def("get_available_devices", &sigtekx::signal_utils::get_available_devices,
        "Gets a list of available CUDA devices.");
  m.def("select_best_device", &sigtekx::signal_utils::select_best_device,
        "Selects the best available CUDA device.");

  m.def("estimate_cufft_workspace_bytes",
        &sigtekx::signal_utils::estimate_cufft_workspace_bytes,
        py::arg("nfft"),
        py::arg("channels"),
        py::arg("is_real_input") = true,
        py::arg("use_fallback_on_error") = true,
        R"pbdoc(
            Query precise cuFFT workspace memory requirement.

            Uses lightweight cufftEstimate1d() API for accurate pre-flight memory
            estimation without requiring CUDA context or plan creation. Results may
            be 5-10% conservative compared to actual runtime requirements.

            Args:
                nfft: FFT size (must be > 0)
                channels: Number of parallel FFT batches (must be > 0)
                is_real_input: True for real-to-complex (R2C), False for complex-to-complex (C2C)
                use_fallback_on_error: If True, returns heuristic estimate on API failure

            Returns:
                Workspace size in bytes (integer)

            Raises:
                RuntimeError: If cuFFT API fails and use_fallback_on_error=False

            Examples:
                >>> from sigtekx.core import _native
                >>> workspace_bytes = _native.estimate_cufft_workspace_bytes(
                ...     nfft=4096, channels=8
                ... )
                >>> print(f"Workspace: {workspace_bytes / 1024**2:.2f} MB")
                Workspace: 2.05 MB

            Note:
                cuFFT may return 0 for smaller transforms that don't require workspace,
                or may auto-allocate workspace internally. In such cases, the function
                falls back to a conservative heuristic estimate when use_fallback_on_error=True.
        )pbdoc");

  m.attr("__version__") = "0.9.4";
  m.attr("__architecture_version__") = "cpp-abs (pipeline/executor split)";
}
