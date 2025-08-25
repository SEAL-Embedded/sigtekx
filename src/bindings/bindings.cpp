#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <stdexcept>
#include <string>
#include <sstream>

#include "cuda_fft.h"

namespace py = pybind11;

// Helper to verify CUDA is available. Throws a standard C++ exception on failure.
void verify_cuda_available() {
    int device_count = 0;
    cudaError_t err = cudaGetDeviceCount(&device_count);
    if (err != cudaSuccess) {
        throw std::runtime_error(std::string("CUDA initialization failed: ") + cudaGetErrorString(err));
    }
    if (device_count == 0) {
        throw std::runtime_error("No CUDA-enabled devices were found on your system.");
    }
}

PYBIND11_MODULE(cuda_lib, m) {
    m.doc() = "High-performance, multi-stream CUDA FFT engine";
    m.attr("__version__") = "1.0.0";

    py::class_<CudaFftEngineCpp>(m, "CudaFftEngine")
        .def(py::init([](int nfft, int batch, bool use_graphs, bool verbose) {
        verify_cuda_available();
        if (nfft <= 0 || (nfft & (nfft - 1)) != 0) {
            throw py::value_error("nfft must be a positive power of 2.");
        }
        if (batch <= 0) {
            throw py::value_error("batch size must be positive.");
        }
        return std::make_unique<CudaFftEngineCpp>(nfft, batch, use_graphs, verbose);
            }),
            py::arg("nfft"), py::arg("batch"), py::arg("use_graphs") = true, py::arg("verbose") = true
        )
        .def("prepare_for_execution", &CudaFftEngineCpp::prepare_for_execution)
        .def("execute_async", &CudaFftEngineCpp::execute_async, py::arg("idx"))
        .def("sync_stream", &CudaFftEngineCpp::sync_stream, py::arg("idx"))
        .def("synchronize_all_streams", &CudaFftEngineCpp::synchronize_all_streams)
        .def("set_use_graphs", &CudaFftEngineCpp::set_use_graphs, py::arg("enable"),
            "Enable or disable CUDA Graph usage at runtime.")
        .def("get_use_graphs", &CudaFftEngineCpp::get_use_graphs,
            "Check if graphs are currently enabled.")
        .def("graphs_ready", &CudaFftEngineCpp::graphs_ready,
            "Check if graphs have been successfully captured.")
        .def("get_last_exec_time_ms", &CudaFftEngineCpp::get_last_exec_time_ms, py::arg("idx"),
            "Get performance metrics for the last execution in ms (if profiling is enabled).")
        .def("set_window", [](CudaFftEngineCpp& self, py::array_t<float, py::array::c_style | py::array::forcecast> window) {
        if (window.ndim() != 1 || window.shape(0) != self.get_fft_size()) {
            throw std::runtime_error("Window array must be 1D with length equal to nfft");
        }
        self.set_window(window.data());
            }, py::arg("window"), "Sets the windowing function from a NumPy array.")

        .def("pinned_input", [](CudaFftEngineCpp& self, int idx) {
        py::ssize_t size = static_cast<py::ssize_t>(self.get_fft_size()) * self.get_batch_size();
        return py::array_t<float>({ size }, self.pinned_input(idx), py::cast(&self));
            }, py::arg("idx"), py::return_value_policy::reference_internal)
        .def("pinned_output", [](CudaFftEngineCpp& self, int idx) {
        py::ssize_t bins = static_cast<py::ssize_t>(self.get_fft_size() / 2 + 1);
        py::ssize_t size = bins * self.get_batch_size();
        return py::array_t<float>({ size }, self.pinned_output(idx), py::cast(&self));
            }, py::arg("idx"), py::return_value_policy::reference_internal)
        .def_property_readonly("fft_size", &CudaFftEngineCpp::get_fft_size)
        .def_property_readonly("batch_size", &CudaFftEngineCpp::get_batch_size)
        .def_property_readonly("num_streams", &CudaFftEngineCpp::get_num_streams);
}
