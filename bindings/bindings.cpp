/**
 * @file bindings.cpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief pybind11 wrappers to expose the C++ ResearchEngine to Python.
 *
 * This file creates the Python module `_engine` and provides bindings for the
 * core C++ classes and functions. It includes a Python-friendly wrapper class,
 * `PyResearchEngine`, to handle conversions between NumPy arrays and C++ pointers,
 * enabling efficient, zero-copy data exchange where possible.
 */

#include "ionosense/research_engine.hpp"
#include "ionosense/processing_stage.hpp"
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <sstream>

namespace py = pybind11;
namespace ionosense {

/**
 * @class PyResearchEngine
 * @brief A Python-facing wrapper for the C++ ResearchEngine.
 *
 * This class adapts the C++ engine's pointer-based API to a more Pythonic,
 * NumPy-based interface. It manages input/output buffers and validates array
 * shapes and sizes to provide a safe and convenient API for Python users.
 */
class PyResearchEngine {
public:
    /**
     * @brief Constructs the Python wrapper and the underlying C++ engine.
     */
    PyResearchEngine() : engine_(std::make_unique<ResearchEngine>()) {}
    
    /**
     * @brief Initializes the engine and pre-allocates Python-side buffers.
     * @param config The engine configuration.
     */
    void initialize(const EngineConfig& config) {
        engine_->initialize(config);
        config_ = config;
        output_buffer_.resize(config.num_output_bins() * config.batch);
    }
    
    /**
     * @brief Processes a NumPy array.
     * @param input A 1D or 2D NumPy array of floats.
     * @return A 2D NumPy array containing the magnitude spectra.
     * @throws std::runtime_error if input dimensions or size are incorrect.
     */
    py::array_t<float> process(py::array_t<float, py::array::c_style | py::array::forcecast> input) {
        if (input.ndim() != 1) {
            throw std::runtime_error("Input must be a 1D NumPy array.");
        }
        
        size_t expected_size = static_cast<size_t>(config_.nfft) * config_.batch;
        if (static_cast<size_t>(input.size()) != expected_size) {
            std::ostringstream oss;
            oss << "Input size mismatch. Expected " << expected_size 
                << " samples, but got " << input.size() << ".";
            throw std::runtime_error(oss.str());
        }
        
        engine_->process(input.data(), output_buffer_.data(), expected_size);
        
        // Return a copy of the output buffer, reshaped for Python.
        return py::array(py::buffer_info(
            output_buffer_.data(),
            sizeof(float),
            py::format_descriptor<float>::format(),
            2,
            { static_cast<py::ssize_t>(config_.batch),
              static_cast<py::ssize_t>(config_.num_output_bins()) },
            { sizeof(float) * config_.num_output_bins(), sizeof(float) }
        ));
    }
    
    /** @brief Resets the engine to an uninitialized state. */
    void reset() { engine_->reset(); }
    
    /** @brief Synchronizes all CUDA streams in the engine. */
    void synchronize() { engine_->synchronize(); }
    
    /** @brief Gets the latest processing statistics. */
    ProcessingStats get_stats() const { return engine_->get_stats(); }
    
    /** @brief Gets runtime information about the CUDA environment. */
    RuntimeInfo get_runtime_info() const { return engine_->get_runtime_info(); }
    
    /** @brief Checks if the engine has been initialized. */
    bool is_initialized() const { return engine_->is_initialized(); }
    
    /** @brief Enables or disables internal profiling. */
    void set_profiling_enabled(bool enabled) { engine_->set_profiling_enabled(enabled); }
    
    /** @brief Gets the current engine configuration. */
    EngineConfig get_config() const { return config_; }
    
    /** @brief Gets the current stage configuration. */
    StageConfig get_stage_config() const { return engine_->get_stage_config(); }

    /** @brief Sets a new stage configuration. Note: requires re-initialization. */
    void set_stage_config(const StageConfig& config) { engine_->set_stage_config(config); }

private:
    std::unique_ptr<ResearchEngine> engine_;
    EngineConfig config_;
    std::vector<float> output_buffer_;
};

}  // namespace ionosense

/**
 * @brief The pybind11 module definition.
 *
 * This macro defines the `_engine` Python module and binds all the C++
 * classes, methods, and enumerations to make them accessible from Python.
 */
PYBIND11_MODULE(_engine, m) {
    m.doc() = "Ionosense HPC CUDA FFT Engine - C++ Core Module";
    
    // --- Bind Enums for StageConfig ---
    py::enum_<ionosense::StageConfig::WindowType>(m, "WindowType")
        .value("HANN", ionosense::StageConfig::WindowType::HANN)
        .export_values();
    
    py::enum_<ionosense::StageConfig::ScalePolicy>(m, "ScalePolicy")
        .value("NONE", ionosense::StageConfig::ScalePolicy::NONE)
        .value("ONE_OVER_N", ionosense::StageConfig::ScalePolicy::ONE_OVER_N)
        .value("ONE_OVER_SQRT_N", ionosense::StageConfig::ScalePolicy::ONE_OVER_SQRT_N)
        .export_values();

    // --- Bind Configuration Structs ---
    py::class_<ionosense::EngineConfig>(m, "EngineConfig")
        .def(py::init<>())
        .def_readwrite("nfft", &ionosense::EngineConfig::nfft)
        .def_readwrite("batch", &ionosense::EngineConfig::batch)
        // ... Bind other EngineConfig members
        .def("num_output_bins", &ionosense::EngineConfig::num_output_bins)
        .def("__repr__", [](const ionosense::EngineConfig& c) {
            return "<EngineConfig nfft=" + std::to_string(c.nfft) + ", batch=" + std::to_string(c.batch) + ">";
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
        .def_readonly("throughput_gbps", &ionosense::ProcessingStats::throughput_gbps)
        .def_readonly("frames_processed", &ionosense::ProcessingStats::frames_processed);

    py::class_<ionosense::RuntimeInfo>(m, "RuntimeInfo")
        .def_readonly("device_name", &ionosense::RuntimeInfo::device_name)
        .def_readonly("cuda_version", &ionosense::RuntimeInfo::cuda_version);

    // --- Bind the Main Engine Wrapper Class ---
    py::class_<ionosense::PyResearchEngine>(m, "ResearchEngine")
        .def(py::init<>())
        .def("initialize", &ionosense::PyResearchEngine::initialize, py::arg("config"), "Initializes the engine.")
        .def("process", &ionosense::PyResearchEngine::process, py::arg("input"), "Processes a batch of data.")
        .def("reset", &ionosense::PyResearchEngine::reset, "Resets the engine.")
        .def("synchronize", &ionosense::PyResearchEngine::synchronize, "Synchronizes all CUDA streams.")
        .def("get_stats", &ionosense::PyResearchEngine::get_stats, "Gets performance statistics.")
        .def("get_runtime_info", &ionosense::PyResearchEngine::get_runtime_info, "Gets CUDA runtime info.")
        .def_property_readonly("is_initialized", &ionosense::PyResearchEngine::is_initialized);
    
    // --- Bind Utility Functions ---
    m.def("get_available_devices", &ionosense::engine_utils::get_available_devices, "Gets a list of available CUDA devices.");
    m.def("select_best_device", &ionosense::engine_utils::select_best_device, "Selects the best available CUDA device.");
    
    m.attr("__version__") = "1.0.0";
}
