/**
 * @file bindings.cpp
 * @brief Pybind11 bindings for the ionosense FFT engine.
 */
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include "ionosense/fft_engine.hpp"

#include <memory> // For std::make_unique

namespace py = pybind11;
using namespace ionosense;

// Helper function to create a zero-copy NumPy view over a C++ float pointer.
static inline py::buffer_info make_buf(float* ptr, int rows, int cols) {
    return py::buffer_info(
        ptr,
        sizeof(float),
        py::format_descriptor<float>::format(),
        2,
        { (py::ssize_t)rows, (py::ssize_t)cols },
        { sizeof(float) * cols, sizeof(float) }
    );
}

PYBIND11_MODULE(_engine, m) {
    m.doc() = "High-performance CUDA FFT engine for Ionosense";

    // --- RtFftConfig Binding ---
    py::class_<RtFftConfig>(m, "RtFftConfig")
        .def(py::init<>())
        .def(py::init<int, int, bool, bool>(),
             py::arg("nfft"),
             py::arg("batch"),
             py::arg("use_graphs") = true,
             py::arg("verbose") = false)
        .def_readwrite("nfft", &RtFftConfig::nfft)
        .def_readwrite("batch", &RtFftConfig::batch)
        .def_readwrite("use_graphs", &RtFftConfig::use_graphs)
        .def_readwrite("verbose", &RtFftConfig::verbose);

    // --- RtFftEngine Binding ---
    py::class_<RtFftEngine>(m, "RtFftEngine")
        .def(py::init<const RtFftConfig&>(), py::arg("config"))
        // Convenience constructor using a lambda
        .def(py::init([](int nfft, int batch, bool use_graphs, bool verbose) {
                RtFftConfig cfg{nfft, batch, use_graphs, verbose};
                return std::make_unique<RtFftEngine>(cfg);
            }),
            py::arg("nfft"),
            py::arg("batch"),
            py::arg("use_graphs") = true,
            py::arg("verbose") = false)

        .def("prepare_for_execution", &RtFftEngine::prepare_for_execution, "Warms up and captures CUDA graphs if enabled.")
        .def("execute_async", &RtFftEngine::execute_async, "Execute the FFT pipeline on a stream.", py::arg("stream_idx"))
        .def("sync_stream", &RtFftEngine::sync_stream, "Block until a stream's tasks are complete.", py::arg("stream_idx"))
        .def("synchronize_all_streams", &RtFftEngine::synchronize_all_streams, "Block until all streams are complete.")
        .def("set_window", [](RtFftEngine &self, py::array_t<float, py::array::c_style | py::array::forcecast> arr) {
            if (arr.ndim() != 1 || (size_t)arr.shape(0) != (size_t)self.get_fft_size()) {
                throw std::runtime_error("Window numpy array size must match FFT size.");
            }
            self.set_window(arr.data(0));
        }, "Set the window function from a NumPy array.")
        .def("pinned_input", [](RtFftEngine &self, int stream_idx) {
            float* ptr = self.pinned_input(stream_idx);
            return py::array_t<float>(make_buf(ptr, self.get_batch_size(), self.get_fft_size()));
        }, "Get a zero-copy NumPy view of a pinned input buffer.", py::arg("stream_idx"))
        .def("pinned_output", [](RtFftEngine &self, int stream_idx) {
            float* ptr = self.pinned_output(stream_idx);
            int bins = self.get_fft_size() / 2 + 1;
            return py::array_t<float>(make_buf(ptr, self.get_batch_size(), bins));
        }, "Get a zero-copy NumPy view of a pinned output buffer.", py::arg("stream_idx"))
        .def_property("use_graphs", &RtFftEngine::get_use_graphs, &RtFftEngine::set_use_graphs, "Enable or disable CUDA graph execution at runtime.")
        .def_property_readonly("fft_size", &RtFftEngine::get_fft_size, "Get the FFT size (N).")
        .def_property_readonly("batch_size", &RtFftEngine::get_batch_size, "Get the batch size.")
        .def_property_readonly("num_streams", &RtFftEngine::get_num_streams, "Get the number of CUDA streams.")
        .def_property_readonly("graphs_ready", &RtFftEngine::graphs_ready, "Check if CUDA graphs have been captured.");

    m.attr("CudaFftEngine") = m.attr("RtFftEngine");
    m.attr("CudaFftConfig") = m.attr("RtFftConfig");
}

