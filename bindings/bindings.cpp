/**
 * @file bindings.cpp
 * @brief Pybind11 bindings for the ionosense FFT engine
 */
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include "ionosense/fft_engine.hpp"

namespace py = pybind11;

// Helper for zero-copy numpy views over pinned buffers
static inline py::buffer_info make_buf(float* ptr, int rows, int cols) {
    return py::buffer_info(
        ptr,                                  // ptr
        sizeof(float),                        // itemsize
        py::format_descriptor<float>::format(), // format
        2,                                    // ndim
        { rows, cols },                       // shape
        { sizeof(float) * cols, sizeof(float) } // strides
    );
}

PYBIND11_MODULE(_engine, m) {
    m.doc() = "High-performance CUDA FFT engine for Ionosense";

    // ---------------------------
    // Config
    // ---------------------------
    py::class_<ionosense::RtFftConfig>(m, "RtFftConfig")
        // default ctor (kept)
        .def(py::init<>())

        // keyword-friendly ctor expected by tests:
        // RtFftConfig(nfft=1024, batch=4, use_graphs=True, verbose=False)
        .def(py::init([](int nfft,
                         int batch,
                         bool use_graphs,
                         bool verbose) {
                ionosense::RtFftConfig cfg;
                cfg.nfft = nfft;
                cfg.batch = batch;
                cfg.use_graphs = use_graphs;
                cfg.verbose = verbose;
                return cfg; // struct is trivially copyable
            }),
            py::arg("nfft"),
            py::arg("batch"),
            py::arg("use_graphs") = true,
            py::arg("verbose") = false
        )

        // fields
        .def_readwrite("nfft", &ionosense::RtFftConfig::nfft)
        .def_readwrite("batch", &ionosense::RtFftConfig::batch)
        .def_readwrite("use_graphs", &ionosense::RtFftConfig::use_graphs)
        .def_readwrite("verbose", &ionosense::RtFftConfig::verbose)
    ;

    // ---------------------------
    // Engine
    // ---------------------------
    py::class_<ionosense::RtFftEngine>(m, "RtFftEngine")
        // canonical ctor taking a config
        .def(py::init<const ionosense::RtFftConfig&>())

        // convenience overload for benches:
        // RtFftEngine(nfft, batch, use_graphs=True, verbose=False)
        .def(py::init([](int nfft,
                         int batch,
                         bool use_graphs,
                         bool verbose) {
                ionosense::RtFftConfig cfg;
                cfg.nfft = nfft;
                cfg.batch = batch;
                cfg.use_graphs = use_graphs;
                cfg.verbose = verbose;
                // return unique_ptr to avoid needing a copy/move ctor
                return std::make_unique<ionosense::RtFftEngine>(cfg);
            }),
            py::arg("nfft"),
            py::arg("batch"),
            py::arg("use_graphs") = true,
            py::arg("verbose") = false
        )

        // lifecycle / control
        .def("prepare_for_execution", &ionosense::RtFftEngine::prepare_for_execution)
        .def("execute_async", &ionosense::RtFftEngine::execute_async)
        .def("sync_stream", &ionosense::RtFftEngine::sync_stream)
        .def("synchronize_all_streams", &ionosense::RtFftEngine::synchronize_all_streams)

        // window setter (size must match nfft)
        .def("set_window", [](ionosense::RtFftEngine &self,
                              py::array_t<float, py::array::c_style | py::array::forcecast> arr) {
            if (arr.size() != self.get_fft_size()) {
                throw std::runtime_error("Window size must match FFT size.");
            }
            self.set_window(arr.data(0));
        })

        // exposed pinned buffers (zero-copy views)
        .def("pinned_input", [](ionosense::RtFftEngine &self, int stream_idx) {
            float* ptr = self.pinned_input(stream_idx);
            return py::array_t<float>(make_buf(ptr, self.get_batch_size(), self.get_fft_size()));
        }, py::arg("stream_idx") = 0)

        .def("pinned_output", [](ionosense::RtFftEngine &self, int stream_idx) {
            float* ptr = self.pinned_output(stream_idx);
            int bins = self.get_fft_size() / 2 + 1;
            return py::array_t<float>(make_buf(ptr, self.get_batch_size(), bins));
        }, py::arg("stream_idx") = 0)

        // properties
        .def_property("use_graphs",
            &ionosense::RtFftEngine::get_use_graphs,
            &ionosense::RtFftEngine::set_use_graphs)
        .def_property_readonly("fft_size", &ionosense::RtFftEngine::get_fft_size)
        .def_property_readonly("batch_size", &ionosense::RtFftEngine::get_batch_size)
        .def_property_readonly("num_streams", &ionosense::RtFftEngine::get_num_streams)
        .def_property_readonly("graphs_ready", &ionosense::RtFftEngine::graphs_ready)
    ;

    // Back-compat so old code importing CudaFft* keeps working
    m.attr("CudaFftEngine") = m.attr("RtFftEngine");
    m.attr("CudaFftConfig") = m.attr("RtFftConfig");
}
