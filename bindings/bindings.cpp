/**
 * @file bindings.cpp
 * @brief Pybind11 bindings for the ionosense pipeline engine
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <pybind11/functional.h>

#include "ionosense/pipeline_engine.hpp"
#include "ionosense/processing_stage.hpp"
#include "ionosense/cuda_wrappers.hpp"

#include <memory>
#include <sstream>
#include <vector>

namespace py = pybind11;
using namespace ionosense;

// Helper for creating zero-copy NumPy views
static inline py::buffer_info make_buffer(float* ptr, int rows, int cols) {
    return py::buffer_info(
        ptr,
        sizeof(float),
        py::format_descriptor<float>::format(),
        2,
        { static_cast<py::ssize_t>(rows), static_cast<py::ssize_t>(cols) },
        { sizeof(float) * cols, sizeof(float) }
    );
}

PYBIND11_MODULE(_engine, m) {
    m.doc() = "High-performance CUDA pipeline engine for signal processing";

    // ========================================================================
    // Exception Registration (Corrected with Lambda)
    // ========================================================================
    py::register_exception_translator([](std::exception_ptr p) {
        try {
            if (p) std::rethrow_exception(p);
        } catch (const cuda::IonoException &e) {
            // Catch our custom base exception and map to Python exceptions
            if (dynamic_cast<const cuda::ConfigurationError*>(&e)) {
                PyErr_SetString(PyExc_ValueError, e.what());
            } else { // Catches CudaError, CufftError, StateError
                PyErr_SetString(PyExc_RuntimeError, e.what());
            }
        }
    });

    py::register_exception<cuda::ConfigurationError>(m, "ConfigurationError");

    // ========================================================================
    // Configuration and Statistics Classes
    // ========================================================================
    
    py::class_<ProcessingConfig>(m, "ProcessingConfig")
        .def(py::init<>())
        .def_readwrite("nfft", &ProcessingConfig::nfft)
        .def_readwrite("batch_size", &ProcessingConfig::batch_size)
        .def_readwrite("verbose", &ProcessingConfig::verbose)
        .def("set_param", [](ProcessingConfig& self, const std::string& key, float value) {
            self.params[key] = value;
        })
        .def("get_param", &ProcessingConfig::get_param, py::arg("key"), py::arg("default_val") = 0.0f);
    
    py::class_<PipelineConfig>(m, "PipelineConfig")
        .def(py::init<>())
        .def_readwrite("num_streams", &PipelineConfig::num_streams)
        .def_readwrite("use_graphs", &PipelineConfig::use_graphs)
        .def_readwrite("enable_profiling", &PipelineConfig::enable_profiling)
        .def_readwrite("verbose", &PipelineConfig::verbose)
        .def_readwrite("stage_config", &PipelineConfig::stage_config);

    py::class_<PipelineStats>(m, "PipelineStats")
        .def_readonly("total_executions", &PipelineStats::total_executions)
        .def_readonly("avg_latency_ms", &PipelineStats::avg_latency_ms)
        .def_readonly("min_latency_ms", &PipelineStats::min_latency_ms)
        .def_readonly("max_latency_ms", &PipelineStats::max_latency_ms)
        .def("throughput_per_sec", &PipelineStats::throughput_per_sec)
        .def("__repr__", [](const PipelineStats& stats) {
            std::ostringstream oss;
            oss << "PipelineStats(executions=" << stats.total_executions
                << ", avg_latency_ms=" << stats.avg_latency_ms 
                << ", throughput_per_sec=" << stats.throughput_per_sec() << ")";
            return oss.str();
        });

    // ========================================================================
    // Main Pipeline Engine and Builder
    // ========================================================================
    
    // CRITICAL FIX: Add std::unique_ptr as the holder type
    py::class_<PipelineEngine, std::unique_ptr<PipelineEngine>>(m, "PipelineEngine")
        .def("prepare", &PipelineEngine::prepare)
        .def("execute_async", py::overload_cast<>(&PipelineEngine::execute_async))
        .def("execute_async", py::overload_cast<int>(&PipelineEngine::execute_async), py::arg("stream_idx"))
        .def("sync_stream", &PipelineEngine::sync_stream, py::arg("stream_idx"))
        .def("synchronize_all", &PipelineEngine::synchronize_all)
        .def("get_input_buffer", [](PipelineEngine& self, int stream_idx) {
            auto* stage = dynamic_cast<const FftProcessingStage*>(self.stage());
            if (!stage) throw cuda::StateError("Processing stage is not a valid FFT stage.");
            const auto& stage_config = stage->config();
            return py::array_t<float>(make_buffer(self.get_input_buffer(stream_idx), stage_config.batch_size, stage_config.nfft));
        }, py::arg("stream_idx"), py::return_value_policy::reference_internal)
        .def("get_output_buffer", [](PipelineEngine& self, int stream_idx) {
            auto* stage = dynamic_cast<const FftProcessingStage*>(self.stage());
            if (!stage) throw cuda::StateError("Processing stage is not a valid FFT stage.");
            const auto& stage_config = stage->config();
            int bins = stage_config.nfft / 2 + 1;
            return py::array_t<float>(make_buffer(self.get_output_buffer(stream_idx), stage_config.batch_size, bins));
        }, py::arg("stream_idx"), py::return_value_policy::reference_internal)
        .def_property_readonly("stats", &PipelineEngine::stats)
        .def("reset_stats", &PipelineEngine::reset_stats)
        .def_property_readonly("is_prepared", &PipelineEngine::is_prepared)
        .def_property_readonly("config", &PipelineEngine::config)
        .def_property("use_graphs", [](const PipelineEngine& self) { return self.config().use_graphs; }, &PipelineEngine::set_use_graphs);

    py::class_<PipelineBuilder>(m, "PipelineBuilder")
        .def(py::init<>())
        .def("with_streams", &PipelineBuilder::with_streams, py::arg("num"))
        .def("with_graphs", &PipelineBuilder::with_graphs, py::arg("enable"))
        .def("with_profiling", &PipelineBuilder::with_profiling, py::arg("enable"))
        .def("with_fft", &PipelineBuilder::with_fft, py::arg("size"), py::arg("batch"))
        .def("with_stage", &PipelineBuilder::with_stage, py::arg("type"))
        .def("with_param", &PipelineBuilder::with_param, py::arg("key"), py::arg("value"))
        .def("build", &PipelineBuilder::build);

    // ========================================================================
    // Legacy Compatibility Layer
    // ========================================================================
    
    py::class_<RtFftConfig>(m, "RtFftConfig")
        .def(py::init<>())
        .def(py::init<int, int, bool, bool>(), py::arg("nfft"), py::arg("batch"), py::arg("use_graphs") = true, py::arg("verbose") = false)
        .def_readwrite("nfft", &RtFftConfig::nfft)
        .def_readwrite("batch", &RtFftConfig::batch)
        .def_readwrite("use_graphs", &RtFftConfig::use_graphs)
        .def_readwrite("verbose", &RtFftConfig::verbose);

    py::class_<RtFftEngine>(m, "RtFftEngine")
        .def(py::init<const RtFftConfig&>(), py::arg("config"))
        .def(py::init([](int nfft, int batch, bool use_graphs, bool verbose) {
            return std::make_unique<RtFftEngine>(RtFftConfig{nfft, batch, 1, use_graphs, verbose});
        }), py::arg("nfft"), py::arg("batch"), py::arg("use_graphs") = true, py::arg("verbose") = false)
        .def("prepare_for_execution", &RtFftEngine::prepare_for_execution)
        .def("execute_async", &RtFftEngine::execute_async, py::arg("stream_idx"))
        .def("sync_stream", &RtFftEngine::sync_stream, py::arg("stream_idx"))
        .def("synchronize_all_streams", &RtFftEngine::synchronize_all_streams)
        .def("set_window", [](RtFftEngine &self, py::array_t<float, py::array::c_style | py::array::forcecast> arr) {
            if (arr.ndim() != 1 || (size_t)arr.shape(0) != (size_t)self.get_fft_size()) {
                throw std::runtime_error("Window numpy array size must match FFT size.");
            }
            self.set_window(arr.data(0));
        }, "Set the window function from a NumPy array.")
        .def("pinned_input", [](RtFftEngine &self, int stream_idx) {
            return py::array_t<float>(make_buffer(self.pinned_input(stream_idx), self.get_batch_size(), self.get_fft_size()));
        }, "Get a zero-copy NumPy view of a pinned input buffer.", py::arg("stream_idx"))
        .def("pinned_output", [](RtFftEngine &self, int stream_idx) {
            int bins = self.get_fft_size() / 2 + 1;
            return py::array_t<float>(make_buffer(self.pinned_output(stream_idx), self.get_batch_size(), bins));
        }, "Get a zero-copy NumPy view of a pinned output buffer.", py::arg("stream_idx"))
        .def_property("use_graphs", &RtFftEngine::get_use_graphs, &RtFftEngine::set_use_graphs, "Enable or disable CUDA graph execution at runtime.")
        .def_property_readonly("fft_size", &RtFftEngine::get_fft_size, "Get the FFT size (N).")
        .def_property_readonly("batch_size", &RtFftEngine::get_batch_size, "Get the batch size.")
        .def_property_readonly("num_streams", &RtFftEngine::get_num_streams, "Get the number of CUDA streams.")
        .def_property_readonly("graphs_ready", &RtFftEngine::graphs_ready, "Check if CUDA graphs have been captured.");

    m.attr("CudaFftEngine") = m.attr("RtFftEngine");
    m.attr("CudaFftConfig") = m.attr("RtFftConfig");
}