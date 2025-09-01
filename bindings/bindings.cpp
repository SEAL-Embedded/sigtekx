// bindings/bindings.cpp
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <pybind11/chrono.h>
#include "ionosense/research_engine.hpp"
#include "ionosense/processing_stage.hpp"
#include <sstream>

namespace py = pybind11;

namespace ionosense {

// Helper for zero-copy numpy array creation
template<typename T>
py::array_t<T> make_array(T* data, size_t size) {
    return py::array_t<T>(
        {static_cast<py::ssize_t>(size)},  // shape
        {sizeof(T)},                       // strides
        data,                               // data pointer
        py::capsule(data, [](void* f) {})  // dummy deleter (managed by C++)
    );
}

// Python wrapper for ResearchEngine with numpy support
class PyResearchEngine {
public:
    PyResearchEngine() : engine_(std::make_unique<ResearchEngine>()) {}
    
    void initialize(const EngineConfig& config) {
        engine_->initialize(config);
        config_ = config;
        
        // Pre-allocate output buffer for zero-copy returns
        output_buffer_.resize(config.num_output_bins() * config.batch);
    }
    
    py::array_t<float> process(py::array_t<float, py::array::c_style | py::array::forcecast> input) {
        // Validate input shape
        if (input.ndim() != 1 && input.ndim() != 2) {
            throw std::runtime_error("Input must be 1D or 2D array");
        }
        
        size_t expected_size = config_.nfft * config_.batch;
        size_t actual_size = input.size();
        
        if (actual_size != expected_size) {
            std::ostringstream oss;
            oss << "Input size mismatch. Expected " << expected_size 
                << " samples, got " << actual_size;
            throw std::runtime_error(oss.str());
        }
        
        // Get input data pointer
        const float* input_ptr = static_cast<const float*>(input.data());
        
        // Process through engine
        engine_->process(input_ptr, output_buffer_.data(), actual_size);
        
        // Return view of output buffer (zero-copy)
        return py::array_t<float>(
            {static_cast<py::ssize_t>(config_.num_output_bins()),
             static_cast<py::ssize_t>(config_.batch)},
            output_buffer_.data()
        );
    }
    
    void process_batch(py::array_t<float, py::array::c_style> input_batch,
                      py::array_t<float, py::array::c_style> output_batch) {
        // Validate shapes
        if (input_batch.ndim() != 3) {
            throw std::runtime_error("Input batch must be 3D: [batch, channels, samples]");
        }
        
        if (output_batch.ndim() != 3) {
            throw std::runtime_error("Output batch must be 3D: [batch, channels, bins]");
        }
        
        auto input_shape = input_batch.shape();
        auto output_shape = output_batch.shape();
        
        size_t num_frames = input_shape[0];
        size_t num_channels = input_shape[1];
        size_t num_samples = input_shape[2];
        
        if (num_channels != static_cast<size_t>(config_.batch)) {
            throw std::runtime_error("Channel count mismatch");
        }
        
        if (num_samples != static_cast<size_t>(config_.nfft)) {
            throw std::runtime_error("Sample count mismatch");
        }
        
        if (output_shape[2] != static_cast<size_t>(config_.num_output_bins())) {
            throw std::runtime_error("Output bin count mismatch");
        }
        
        // Process each frame
        const float* input_ptr = static_cast<const float*>(input_batch.data());
        float* output_ptr = static_cast<float*>(output_batch.mutable_data());
        
        size_t input_frame_size = num_channels * num_samples;
        size_t output_frame_size = num_channels * config_.num_output_bins();
        
        for (size_t i = 0; i < num_frames; ++i) {
            engine_->process(input_ptr + i * input_frame_size,
                           output_ptr + i * output_frame_size,
                           input_frame_size);
        }
    }
    
    void reset() {
        engine_->reset();
    }
    
    void synchronize() {
        engine_->synchronize();
    }
    
    ProcessingStats get_stats() const {
        return engine_->get_stats();
    }
    
    RuntimeInfo get_runtime_info() const {
        return engine_->get_runtime_info();
    }
    
    bool is_initialized() const {
        return engine_->is_initialized();
    }
    
    void set_profiling_enabled(bool enabled) {
        engine_->set_profiling_enabled(enabled);
    }
    
    EngineConfig get_config() const {
        return config_;
    }
    
    StageConfig get_stage_config() const {
        return engine_->get_stage_config();
    }
    
    void set_stage_config(const StageConfig& config) {
        engine_->set_stage_config(config);
    }

private:
    std::unique_ptr<ResearchEngine> engine_;
    EngineConfig config_;
    std::vector<float> output_buffer_;
};

}  // namespace ionosense

PYBIND11_MODULE(_engine, m) {
    m.doc() = "Ionosense HPC CUDA FFT Engine";
    
    // EngineConfig
    py::class_<ionosense::EngineConfig>(m, "EngineConfig")
        .def(py::init<>())
        .def_readwrite("nfft", &ionosense::EngineConfig::nfft)
        .def_readwrite("batch", &ionosense::EngineConfig::batch)
        .def_readwrite("overlap", &ionosense::EngineConfig::overlap)
        .def_readwrite("sample_rate_hz", &ionosense::EngineConfig::sample_rate_hz)
        .def_readwrite("stream_count", &ionosense::EngineConfig::stream_count)
        .def_readwrite("pinned_buffer_count", &ionosense::EngineConfig::pinned_buffer_count)
        .def_readwrite("warmup_iters", &ionosense::EngineConfig::warmup_iters)
        .def_readwrite("timeout_ms", &ionosense::EngineConfig::timeout_ms)
        .def_readwrite("use_cuda_graphs", &ionosense::EngineConfig::use_cuda_graphs)
        .def_readwrite("enable_profiling", &ionosense::EngineConfig::enable_profiling)
        .def("hop_size", &ionosense::EngineConfig::hop_size)
        .def("num_output_bins", &ionosense::EngineConfig::num_output_bins)
        .def("__repr__", [](const ionosense::EngineConfig& c) {
            std::ostringstream oss;
            oss << "EngineConfig(nfft=" << c.nfft 
                << ", batch=" << c.batch
                << ", overlap=" << c.overlap
                << ", sample_rate_hz=" << c.sample_rate_hz
                << ", streams=" << c.stream_count << ")";
            return oss.str();
        });
    
    // StageConfig
    py::class_<ionosense::StageConfig>(m, "StageConfig")
        .def(py::init<>())
        .def_readwrite("nfft", &ionosense::StageConfig::nfft)
        .def_readwrite("batch", &ionosense::StageConfig::batch)
        .def_readwrite("overlap", &ionosense::StageConfig::overlap)
        .def_readwrite("sample_rate_hz", &ionosense::StageConfig::sample_rate_hz)
        .def_readwrite("preload_window", &ionosense::StageConfig::preload_window)
        .def_readwrite("inplace", &ionosense::StageConfig::inplace)
        .def_readwrite("warmup_iters", &ionosense::StageConfig::warmup_iters)
        .def("hop_size", &ionosense::StageConfig::hop_size);
    
    // Enums for StageConfig
    py::enum_<ionosense::StageConfig::WindowType>(m, "WindowType")
        .value("HANN", ionosense::StageConfig::WindowType::HANN);
    
    py::enum_<ionosense::StageConfig::WindowNorm>(m, "WindowNorm")
        .value("UNITY", ionosense::StageConfig::WindowNorm::UNITY)
        .value("SQRT", ionosense::StageConfig::WindowNorm::SQRT);
    
    py::enum_<ionosense::StageConfig::ScalePolicy>(m, "ScalePolicy")
        .value("NONE", ionosense::StageConfig::ScalePolicy::NONE)
        .value("ONE_OVER_N", ionosense::StageConfig::ScalePolicy::ONE_OVER_N);
    
    py::enum_<ionosense::StageConfig::OutputMode>(m, "OutputMode")
        .value("MAGNITUDE", ionosense::StageConfig::OutputMode::MAGNITUDE)
        .value("COMPLEX_PASSTHROUGH", ionosense::StageConfig::OutputMode::COMPLEX_PASSTHROUGH);
    
    // ProcessingStats
    py::class_<ionosense::ProcessingStats>(m, "ProcessingStats")
        .def_readonly("latency_us", &ionosense::ProcessingStats::latency_us)
        .def_readonly("throughput_gbps", &ionosense::ProcessingStats::throughput_gbps)
        .def_readonly("frames_processed", &ionosense::ProcessingStats::frames_processed)
        .def_readonly("is_warmup", &ionosense::ProcessingStats::is_warmup)
        .def("__repr__", [](const ionosense::ProcessingStats& s) {
            std::ostringstream oss;
            oss << "ProcessingStats(latency=" << s.latency_us << "μs, "
                << "throughput=" << s.throughput_gbps << "GB/s, "
                << "frames=" << s.frames_processed << ")";
            return oss.str();
        });
    
    // RuntimeInfo
    py::class_<ionosense::RuntimeInfo>(m, "RuntimeInfo")
        .def_readonly("cuda_version", &ionosense::RuntimeInfo::cuda_version)
        .def_readonly("cufft_version", &ionosense::RuntimeInfo::cufft_version)
        .def_readonly("device_name", &ionosense::RuntimeInfo::device_name)
        .def_readonly("device_compute_capability_major", 
                     &ionosense::RuntimeInfo::device_compute_capability_major)
        .def_readonly("device_compute_capability_minor",
                     &ionosense::RuntimeInfo::device_compute_capability_minor)
        .def_readonly("device_memory_total_mb", &ionosense::RuntimeInfo::device_memory_total_mb)
        .def_readonly("device_memory_free_mb", &ionosense::RuntimeInfo::device_memory_free_mb)
        .def_readonly("cuda_driver_version", &ionosense::RuntimeInfo::cuda_driver_version)
        .def_readonly("cuda_runtime_version", &ionosense::RuntimeInfo::cuda_runtime_version)
        .def("__repr__", [](const ionosense::RuntimeInfo& info) {
            std::ostringstream oss;
            oss << "RuntimeInfo(device='" << info.device_name << "', "
                << "cuda=" << info.cuda_version << ", "
                << "memory=" << info.device_memory_free_mb << "/" 
                << info.device_memory_total_mb << "MB)";
            return oss.str();
        });
    
    // PyResearchEngine (main Python interface)
    py::class_<ionosense::PyResearchEngine>(m, "ResearchEngine")
        .def(py::init<>())
        .def("initialize", &ionosense::PyResearchEngine::initialize,
             py::arg("config"),
             "Initialize the engine with the given configuration")
        .def("process", &ionosense::PyResearchEngine::process,
             py::arg("input"),
             "Process input samples and return magnitude spectrum")
        .def("process_batch", &ionosense::PyResearchEngine::process_batch,
             py::arg("input_batch"), py::arg("output_batch"),
             "Process batch of frames in-place")
        .def("reset", &ionosense::PyResearchEngine::reset,
             "Reset the engine state")
        .def("synchronize", &ionosense::PyResearchEngine::synchronize,
             "Synchronize all CUDA streams")
        .def("get_stats", &ionosense::PyResearchEngine::get_stats,
             "Get processing statistics")
        .def("get_runtime_info", &ionosense::PyResearchEngine::get_runtime_info,
             "Get runtime information about CUDA environment")
        .def("is_initialized", &ionosense::PyResearchEngine::is_initialized,
             "Check if engine is initialized")
        .def("set_profiling_enabled", &ionosense::PyResearchEngine::set_profiling_enabled,
             py::arg("enabled"),
             "Enable/disable profiling")
        .def("get_config", &ionosense::PyResearchEngine::get_config,
             "Get current engine configuration")
        .def("get_stage_config", &ionosense::PyResearchEngine::get_stage_config,
             "Get current stage configuration")
        .def("set_stage_config", &ionosense::PyResearchEngine::set_stage_config,
             py::arg("config"),
             "Set stage configuration");
    
    // Utility functions
    m.def("get_available_devices", &ionosense::engine_utils::get_available_devices,
          "Get list of available CUDA devices");
    
    m.def("select_best_device", &ionosense::engine_utils::select_best_device,
          "Select the best CUDA device based on compute capability");
    
    m.def("validate_config", [](const ionosense::EngineConfig& config) {
        std::string error_msg;
        bool valid = ionosense::engine_utils::validate_config(config, error_msg);
        return py::make_tuple(valid, error_msg);
    }, py::arg("config"), "Validate engine configuration");
    
    m.def("estimate_memory_usage", &ionosense::engine_utils::estimate_memory_usage,
          py::arg("config"), "Estimate memory usage for given configuration");
    
    // Version information
    m.attr("__version__") = "1.0.0";
    m.attr("__cuda_support__") = true;
}