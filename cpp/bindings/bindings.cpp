/**
 * @file bindings.cpp
 * @version 0.9.4
 * @date 2025-10-23
 * @author [Kevin Rahsaz]
 *
 * @brief pybind11 wrappers to expose C++ executors to Python.
 *
 * This file creates the Python module `_engine` and provides bindings for
 * the pipeline executor architecture. It includes Python-friendly wrapper
 * classes to handle conversions between NumPy arrays and C++ pointers,
 * enabling efficient, zero-copy data exchange where possible.
 */

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <sstream>

#include "ionosense/core/executor_config.hpp"
#include "ionosense/core/pipeline_executor.hpp"
#include "ionosense/core/processing_stage.hpp"
#include "ionosense/executors/batch_executor.hpp"
#include "ionosense/executors/streaming_executor.hpp"

namespace py = pybind11;
namespace ionosense {

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
    output_buffer_.resize(config.num_output_bins() * config.channels);
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

    executor_->submit(input.data(), output_buffer_.data(), expected_size);

    // Return a copy of the output buffer, reshaped for Python.
    return py::array(py::buffer_info(
        output_buffer_.data(), sizeof(float),
        py::format_descriptor<float>::format(), 2,
        {static_cast<py::ssize_t>(config_.channels),
         static_cast<py::ssize_t>(config_.num_output_bins())},
        {sizeof(float) * config_.num_output_bins(), sizeof(float)}));
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
  std::vector<float> output_buffer_;
};

// Type aliases for Python bindings
using PyBatchExecutor = PyExecutor<BatchExecutor>;
using PyStreamingExecutor = PyExecutor<StreamingExecutor>;

}  // namespace ionosense

/**
 * @brief The pybind11 module definition.
 *
 * This macro defines the `_engine` Python module and binds all the C++
 * classes, methods, and enumerations to make them accessible from Python.
 */
PYBIND11_MODULE(_engine, m) {
  m.doc() = R"pbdoc(
        Ionosense HPC CUDA FFT Engine - C++ Core Module (v0.9.3)

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
            >>> import _engine
            >>> config = _engine.ExecutorConfig()
            >>> config.nfft = 1024
            >>> config.channels = 4
            >>> config.mode = _engine.ExecutionMode.channels
            >>> executor = _engine.BatchExecutor()
            >>> executor.initialize(config)
            >>> output = executor.process(input_data)
    )pbdoc";

  // --- Bind Enums for StageConfig ---
  py::enum_<ionosense::StageConfig::WindowType>(m, "WindowType")
      .value("RECTANGULAR", ionosense::StageConfig::WindowType::RECTANGULAR)
      .value("HANN", ionosense::StageConfig::WindowType::HANN)
      .value("BLACKMAN", ionosense::StageConfig::WindowType::BLACKMAN)
      .export_values();

  py::enum_<ionosense::StageConfig::WindowSymmetry>(
      m, "WindowSymmetry",
      "Window symmetry mode (PERIODIC for FFT, SYMMETRIC for time-domain)")
      .value("PERIODIC", ionosense::StageConfig::WindowSymmetry::PERIODIC,
             "Periodic window (FFT processing, denominator N)")
      .value("SYMMETRIC", ionosense::StageConfig::WindowSymmetry::SYMMETRIC,
             "Symmetric window (time-domain, denominator N-1)")
      .export_values();

  py::enum_<ionosense::StageConfig::WindowNorm>(m, "WindowNorm",
                                                "Window normalization scheme")
      .value("UNITY", ionosense::StageConfig::WindowNorm::UNITY,
             "Unity power/energy gain normalization")
      .value("SQRT", ionosense::StageConfig::WindowNorm::SQRT,
             "Square root normalization")
      .export_values();

  py::enum_<ionosense::StageConfig::ScalePolicy>(m, "ScalePolicy")
      .value("NONE", ionosense::StageConfig::ScalePolicy::NONE)
      .value("ONE_OVER_N", ionosense::StageConfig::ScalePolicy::ONE_OVER_N)
      .value("ONE_OVER_SQRT_N",
             ionosense::StageConfig::ScalePolicy::ONE_OVER_SQRT_N)
      .export_values();

  py::enum_<ionosense::StageConfig::OutputMode>(m, "OutputMode",
                                                "Pipeline output format")
      .value("MAGNITUDE", ionosense::StageConfig::OutputMode::MAGNITUDE,
             "Real magnitude spectrum")
      .value("COMPLEX_PASSTHROUGH",
             ionosense::StageConfig::OutputMode::COMPLEX_PASSTHROUGH,
             "Complex FFT output")
      .export_values();

  // --- Bind ExecutorConfig Enums (v0.9.3 architecture) ---
  py::enum_<ionosense::ExecutorConfig::ExecutionMode>(m, "ExecutionMode",
                                                      "Execution strategy for "
                                                      "pipeline executors")
      .value("channels", ionosense::ExecutorConfig::ExecutionMode::BATCH,
             "Process complete batches with maximum throughput")
      .value("STREAMING", ionosense::ExecutorConfig::ExecutionMode::STREAMING,
             "Continuous processing with low-latency via ring buffer (v0.9.4+)")
      .export_values();

  // --- Bind Configuration Structs ---
  py::class_<ionosense::EngineConfig>(m, "EngineConfig")
      .def(py::init<>())
      .def_readwrite("nfft", &ionosense::EngineConfig::nfft)
      .def_readwrite("channels", &ionosense::EngineConfig::channels)
      .def_readwrite("overlap", &ionosense::EngineConfig::overlap)
      .def_readwrite("sample_rate_hz", &ionosense::EngineConfig::sample_rate_hz)
      .def_readwrite("window_type", &ionosense::EngineConfig::window_type)
      .def_readwrite("window_symmetry",
                     &ionosense::EngineConfig::window_symmetry)
      .def_readwrite("window_norm", &ionosense::EngineConfig::window_norm)
      .def_readwrite("scale_policy", &ionosense::EngineConfig::scale_policy)
      .def_readwrite("output_mode", &ionosense::EngineConfig::output_mode)
      .def_readwrite("stream_count", &ionosense::EngineConfig::stream_count)
      .def_readwrite("pinned_buffer_count",
                     &ionosense::EngineConfig::pinned_buffer_count)
      .def_readwrite("warmup_iters", &ionosense::EngineConfig::warmup_iters)
      .def("num_output_bins", &ionosense::EngineConfig::num_output_bins)
      .def("__repr__", [](const ionosense::EngineConfig& c) {
        return "<EngineConfig nfft=" + std::to_string(c.nfft) +
               ", channels=" + std::to_string(c.channels) + ">";
      });

  // --- Bind ExecutorConfig (v0.9.3 architecture) ---
  py::class_<ionosense::ExecutorConfig, ionosense::EngineConfig>(
      m, "ExecutorConfig",
      "Configuration for pipeline executors (extends EngineConfig)")
      .def(py::init<>())
      .def_readwrite("mode", &ionosense::ExecutorConfig::mode,
                     "Execution strategy (BATCH/STREAMING)")
      .def_readwrite("max_inflight_batches",
                     &ionosense::ExecutorConfig::max_inflight_batches,
                     "Maximum concurrent batches (streaming mode, v0.9.4+)")
      .def_readwrite("device_id", &ionosense::ExecutorConfig::device_id,
                     "CUDA device ID (-1 for auto-select)")
      .def("__repr__", [](const ionosense::ExecutorConfig& c) {
        std::string mode_str;
        switch (c.mode) {
          case ionosense::ExecutorConfig::ExecutionMode::BATCH:
            mode_str = "channels";
            break;
          case ionosense::ExecutorConfig::ExecutionMode::STREAMING:
            mode_str = "STREAMING";
            break;
        }
        return "<ExecutorConfig mode=" + mode_str +
               ", nfft=" + std::to_string(c.nfft) +
               ", channels=" + std::to_string(c.channels) + ">";
      });

  py::class_<ionosense::StageConfig>(m, "StageConfig")
      .def(py::init<>())
      .def_readwrite("nfft", &ionosense::StageConfig::nfft)
      .def_readwrite("window_type", &ionosense::StageConfig::window_type)
      // ... Bind other StageConfig members
      .def("__repr__", [](const ionosense::StageConfig& c) {
        return "<StageConfig nfft=" + std::to_string(c.nfft) + ">";
      });

  // --- Bind Statistics and Info Structs ---
  py::class_<ionosense::ProcessingStats>(m, "ProcessingStats")
      .def_readonly("latency_us", &ionosense::ProcessingStats::latency_us)
      .def_readonly("throughput_gbps",
                    &ionosense::ProcessingStats::throughput_gbps)
      .def_readonly("frames_processed",
                    &ionosense::ProcessingStats::frames_processed);

  // --- Bind Executor Classes ---
  py::class_<ionosense::PyBatchExecutor>(
      m, "BatchExecutor",
      "High-throughput batch executor for processing complete batches")
      .def(py::init<>())
      .def("initialize", &ionosense::PyBatchExecutor::initialize,
           py::arg("config"), "Initializes the executor with configuration.")
      .def("process", &ionosense::PyBatchExecutor::process, py::arg("input"),
           "Processes a batch of input data.")
      .def("reset", &ionosense::PyBatchExecutor::reset,
           "Resets the executor to uninitialized state.")
      .def("synchronize", &ionosense::PyBatchExecutor::synchronize,
           "Synchronizes all CUDA streams.")
      .def("get_stats", &ionosense::PyBatchExecutor::get_stats,
           "Gets performance statistics from last operation.")
      .def_property_readonly("is_initialized",
                             &ionosense::PyBatchExecutor::is_initialized,
                             "Check if executor is initialized.");

  py::class_<ionosense::PyStreamingExecutor>(
      m, "StreamingExecutor", "Low-latency streaming executor (stub in v0.9.3)")
      .def(py::init<>())
      .def("initialize", &ionosense::PyStreamingExecutor::initialize,
           py::arg("config"), "Initializes the executor with configuration.")
      .def("process", &ionosense::PyStreamingExecutor::process,
           py::arg("input"), "Processes a batch of input data.")
      .def("reset", &ionosense::PyStreamingExecutor::reset,
           "Resets the executor to uninitialized state.")
      .def("synchronize", &ionosense::PyStreamingExecutor::synchronize,
           "Synchronizes all CUDA streams.")
      .def("get_stats", &ionosense::PyStreamingExecutor::get_stats,
           "Gets performance statistics from last operation.")
      .def_property_readonly("is_initialized",
                             &ionosense::PyStreamingExecutor::is_initialized,
                             "Check if executor is initialized.");

  // --- Bind Utility Functions ---
  m.def("get_available_devices",
        &ionosense::engine_utils::get_available_devices,
        "Gets a list of available CUDA devices.");
  m.def("select_best_device", &ionosense::engine_utils::select_best_device,
        "Selects the best available CUDA device.");

  m.attr("__version__") = "0.9.4";
  m.attr("__architecture_version__") = "cpp-abs (pipeline/executor split)";
}
