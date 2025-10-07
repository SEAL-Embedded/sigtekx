/**
 * @file research_engine.cpp
 * @version 1.0
 * @date 2025-09-01
 * @author [Kevin Rahsaz]
 *
 * @brief Implementation of the ResearchEngine for HPC signal processing.
 *
 * This file contains the core logic for the ResearchEngine class, which
 * orchestrates the entire asynchronous signal processing pipeline. It utilizes
 * the Pimpl idiom to hide CUDA-specific implementation details, managing
 * streams, events, and device memory to ensure high-throughput, low-latency
 * FFT processing.
 */

#include "ionosense/research_engine.hpp"

#include <algorithm>
#include <chrono>
#include <iomanip>
#include <numeric>
#include <sstream>
#include <stdexcept>

#include "ionosense/cuda_wrappers.hpp"
#include "ionosense/processing_stage.hpp"
#include "ionosense/profiling_macros.hpp"  // Profiling second

namespace ionosense {

// ============================================================================
//  ResearchEngine::Impl (Private Implementation)
// ============================================================================

/**
 * @class ResearchEngine::Impl
 * @brief Private implementation of the ResearchEngine using the Pimpl idiom.
 *
 * This class encapsulates all CUDA-specific resources and logic, including
 * streams, events, device buffers, and the processing pipeline stages. This
 * ensures the public `ResearchEngine` header remains clean of CUDA
 * dependencies.
 */
class ResearchEngine::Impl {
 public:
  /**
   * @brief Constructor for the implementation.
   *
   * Selects the best available CUDA device and queries its properties.
   * @throws std::runtime_error if no CUDA devices are found.
   */
  Impl() {
    int device_count = 0;
    IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    if (device_count == 0) {
      throw std::runtime_error("No CUDA-capable devices found.");
    }

    device_id_ = engine_utils::select_best_device();
    IONO_CUDA_CHECK(cudaSetDevice(device_id_));
    IONO_CUDA_CHECK(cudaGetDeviceProperties(&device_props_, device_id_));
  }

  /**
   * @brief Destructor. Ensures all resources are released via reset().
   */
  ~Impl() { reset(); }

  /**
   * @brief Initializes all engine resources based on the provided
   * configuration.
   *
   * This function is the main setup routine. It creates CUDA streams and
   * events, allocates device and pinned host memory, and initializes the
   * processing stages.
   *
   * @param config The configuration for the engine.
   */
  void initialize(const EngineConfig& config) {
    IONO_NVTX_RANGE("ResearchEngine::Initialize", profiling::colors::DARK_GRAY);
    if (initialized_) {
      reset();  // Ensure clean state if re-initializing.
    }
    config_ = config;

    // --- Resource Allocation ---
    {
      IONO_NVTX_RANGE("Create CUDA Streams", profiling::colors::DARK_GRAY);
      streams_.clear();
      for (int i = 0; i < config.stream_count; ++i) {
        streams_.emplace_back();
      }
    }

    {
      IONO_NVTX_RANGE("Create CUDA Events", profiling::colors::DARK_GRAY);
      events_.clear();
      for (int i = 0; i < config.pinned_buffer_count * 2; ++i) {
        events_.emplace_back(cudaEventDisableTiming);
      }
    }

    // --- Stage Configuration ---
    stage_config_.nfft = config.nfft;
    stage_config_.batch = config.batch;
    stage_config_.overlap = config.overlap;
    stage_config_.sample_rate_hz = config.sample_rate_hz;
    stage_config_.warmup_iters = config.warmup_iters;

    // --- Pipeline Construction ---
    {
      IONO_NVTX_RANGE("Initialize Pipeline Stages", profiling::colors::MAGENTA);
      if (stages_.empty()) {
        stages_ = StageFactory::create_default_pipeline();
      }
      for (auto& stage : stages_) {
        {
          IONO_NVTX_RANGE("Init Stage", profiling::colors::DARK_GRAY);
          stage->initialize(stage_config_, streams_[0].get());
        }
      }
    }

    // --- Buffer Allocation ---
    const size_t buffer_size = static_cast<size_t>(config.nfft) * config.batch;
    const size_t output_buffer_size =
        static_cast<size_t>(config.num_output_bins()) * config.batch;
    const size_t complex_buffer_size = output_buffer_size;

    {
      const size_t total_bytes =
          (buffer_size + output_buffer_size + complex_buffer_size * 2) *
          static_cast<size_t>(config.pinned_buffer_count) * sizeof(float);
      const std::string alloc_msg = profiling::format_memory_range(
          "Allocate Device Buffers", total_bytes);
      IONO_NVTX_RANGE(alloc_msg.c_str(), profiling::colors::CYAN);

      d_input_buffers_.clear();
      d_output_buffers_.clear();
      d_intermediate_buffers_.clear();

      for (int i = 0; i < config.pinned_buffer_count; ++i) {
        d_input_buffers_.emplace_back(buffer_size);
        d_input_buffers_.back().memset(0);

        d_output_buffers_.emplace_back(output_buffer_size);
        d_output_buffers_.back().memset(0);

        d_intermediate_buffers_.emplace_back(complex_buffer_size * 2);
        d_intermediate_buffers_.back().memset(0);
      }

      h_input_staging_.resize(buffer_size);
      h_output_staging_.resize(output_buffer_size);
    }

    initialized_ = true;

    // --- Warmup ---
    if (config_.warmup_iters > 0) {
      run_warmup();
    }

    stats_ = ProcessingStats{};  // Reset stats after warmup.
    stats_.is_warmup = false;
    IONO_NVTX_MARK("Initialization Complete", profiling::colors::CYAN);
  }

  /**
   * @brief Processes a single batch of data synchronously.
   *
   * This method orchestrates the full pipeline: H2D copy, processing, D2H copy,
   * and final synchronization. It serves as the core processing loop.
   *
   * @param input Pointer to the host input data.
   * @param output Pointer to the host output buffer.
   * @param num_samples The total number of float samples in the input.
   */
  void process(const float* input, float* output, size_t num_samples) {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);
    if (!initialized_) {
      throw std::runtime_error(
          "ResearchEngine is not initialized. Call initialize() first.");
    }

    const auto start_time = std::chrono::high_resolution_clock::now();

    // --- Resource Selection (Round-robin) ---
    const int buffer_idx =
        static_cast<int>(frame_counter_ % config_.pinned_buffer_count);
    auto& d_input = d_input_buffers_[buffer_idx];
    auto& d_output = d_output_buffers_[buffer_idx];
    auto& d_intermediate = d_intermediate_buffers_[buffer_idx];

    const int h2d_stream_idx = 0;
    const int compute_stream_idx = (streams_.size() > 1) ? 1 : 0;
    const int d2h_stream_idx = (streams_.size() > 2) ? 2 : compute_stream_idx;

    auto& e_h2d_done = events_[buffer_idx * 2 + 0];
    auto& e_compute_done = events_[buffer_idx * 2 + 1];

    // Ensure this buffer is free from previous frame using same buffer slot
    // Critical for correctness with round-robin buffer reuse
    if (frame_counter_ >= static_cast<size_t>(config_.pinned_buffer_count)) {
      IONO_NVTX_RANGE("Wait for Buffer Availability", profiling::colors::YELLOW);
      IONO_CUDA_CHECK(cudaStreamSynchronize(streams_[compute_stream_idx].get()));
    }

    // --- Asynchronous Pipeline Execution ---
    // 1. Host-to-Device Transfer
    {
      const size_t bytes = num_samples * sizeof(float);
      const std::string h2d_msg =
          profiling::format_memory_range("H2D Transfer", bytes);
      IONO_NVTX_RANGE(h2d_msg.c_str(), profiling::colors::GREEN);
      d_input.copy_from_host(input, num_samples,
                             streams_[h2d_stream_idx].get());
      e_h2d_done.record(streams_[h2d_stream_idx].get());
    }

    // 2. Processing Pipeline (on compute stream)
    IONO_CUDA_CHECK(cudaStreamWaitEvent(streams_[compute_stream_idx].get(),
                                        e_h2d_done.get(), 0));

    {
      IONO_NVTX_RANGE("Compute Pipeline", profiling::colors::PURPLE);
      stages_[0]->process(d_input.get(), d_input.get(), num_samples,
                          streams_[compute_stream_idx].get());
      stages_[1]->process(d_input.get(), d_intermediate.get(), num_samples,
                          streams_[compute_stream_idx].get());
      const size_t complex_elements =
          static_cast<size_t>(config_.num_output_bins()) * config_.batch;
      stages_[2]->process(d_intermediate.get(), d_output.get(),
                          complex_elements, streams_[compute_stream_idx].get());
      e_compute_done.record(streams_[compute_stream_idx].get());
    }

    // 3. Device-to-Host Transfer
    {
      const size_t complex_elements =
          static_cast<size_t>(config_.num_output_bins()) * config_.batch;
      const size_t bytes = complex_elements * sizeof(float);
      const std::string d2h_msg =
          profiling::format_memory_range("D2H Transfer", bytes);
      IONO_NVTX_RANGE(d2h_msg.c_str(), profiling::colors::ORANGE);
      IONO_CUDA_CHECK(cudaStreamWaitEvent(streams_[d2h_stream_idx].get(),
                                          e_compute_done.get(), 0));
      d_output.copy_to_host(output, complex_elements,
                            streams_[d2h_stream_idx].get());
    }

    // 4. Final Synchronization for this batch
    {
      IONO_NVTX_RANGE("Stream Sync", profiling::colors::YELLOW);
      IONO_CUDA_CHECK(cudaStreamSynchronize(streams_[d2h_stream_idx].get()));
    }

    // --- Statistics Update ---
    const auto end_time = std::chrono::high_resolution_clock::now();
    const auto duration =
        std::chrono::duration<float, std::micro>(end_time - start_time);
    stats_.latency_us = duration.count();
    stats_.frames_processed++;
    stats_.throughput_gbps =
        calculate_throughput(num_samples, stats_.latency_us);

    frame_counter_++;
  }

  /**
   * @brief Asynchronously processes data and invokes a callback upon
   * completion.
   */
  void process_async(const float* input, size_t num_samples,
                     ResultCallback callback) {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::NVIDIA_BLUE);
    if (!initialized_) {
      throw std::runtime_error("Engine not initialized");
    }
    std::vector<float> output(config_.num_output_bins() * config_.batch);
    process(input, output.data(), num_samples);
    if (callback) {
      IONO_NVTX_RANGE("Result Callback", profiling::colors::CYAN);
      callback(output.data(), config_.num_output_bins(), config_.batch, stats_);
    }
  }

  /**
   * @brief Blocks until all streams in the engine have completed all pending
   * work.
   */
  void synchronize() {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::YELLOW);
    for (auto& s : streams_) {
      s.synchronize();
    }
  }

  /**
   * @brief Resets the engine, releasing all CUDA resources.
   */
  void reset() {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::RED);
    if (!initialized_) return;
    {
      IONO_NVTX_RANGE("Synchronize All Streams", profiling::colors::YELLOW);
      synchronize();
    }
    {
      IONO_NVTX_RANGE("Release Resources", profiling::colors::RED);
      stages_.clear();
      streams_.clear();
      events_.clear();
      d_input_buffers_.clear();
      d_intermediate_buffers_.clear();
      d_output_buffers_.clear();
      h_input_staging_ = PinnedHostBuffer<float>();
      h_output_staging_ = PinnedHostBuffer<float>();
    }
    frame_counter_ = 0;
    initialized_ = false;
    IONO_NVTX_MARK("Reset Complete", profiling::colors::RED);
  }

  ProcessingStats get_stats() const { return stats_; }

  RuntimeInfo get_runtime_info() const {
    IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
    RuntimeInfo info;
    int cuda_runtime_version = 0, cuda_driver_version = 0;
    IONO_CUDA_CHECK(cudaRuntimeGetVersion(&cuda_runtime_version));
    IONO_CUDA_CHECK(cudaDriverGetVersion(&cuda_driver_version));
    info.cuda_runtime_version = cuda_runtime_version;
    info.cuda_driver_version = cuda_driver_version;

    std::ostringstream v;
    v << (cuda_runtime_version / 1000) << "."
      << (cuda_runtime_version % 1000) / 10;
    info.cuda_version = v.str();
    info.cufft_version =
        info.cuda_version;  // cuFFT version often tracks CUDA version

    info.device_name = device_props_.name;
    info.device_compute_capability_major = device_props_.major;
    info.device_compute_capability_minor = device_props_.minor;
    info.device_memory_total_mb = device_props_.totalGlobalMem / (1024 * 1024);

    size_t free_mem = 0, total_mem = 0;
    IONO_CUDA_CHECK(cudaMemGetInfo(&free_mem, &total_mem));
    info.device_memory_free_mb = free_mem / (1024 * 1024);
    return info;
  }

  bool is_initialized() const { return initialized_; }
  void set_profiling_enabled(bool enabled) {
    profiling_enabled_ = enabled;
#ifdef IONOSENSE_ENABLE_PROFILING
    profiling::set_profiling_enabled(enabled);
#endif
  }
  void add_stage(std::unique_ptr<IProcessingStage> stage) {
    stages_.push_back(std::move(stage));
  }
  void clear_stages() { stages_.clear(); }
  size_t num_stages() const { return stages_.size(); }
  void set_stage_config(const StageConfig& cfg) { stage_config_ = cfg; }
  StageConfig get_stage_config() const { return stage_config_; }

 private:
  void run_warmup() {
    std::vector<float> dummy_input(
        static_cast<size_t>(config_.nfft) * config_.batch, 0.0f);
    std::vector<float> dummy_output(
        static_cast<size_t>(config_.num_output_bins()) * config_.batch);

    stats_.is_warmup = true;
    for (int i = 0; i < config_.warmup_iters; ++i) {
      process(dummy_input.data(), dummy_output.data(), dummy_input.size());
    }
    stats_.is_warmup = false;
  }

  float calculate_throughput(size_t num_samples, float latency_us) const {
    const size_t bytes = num_samples * sizeof(float) * 2;  // Input + Output
    const float secs = latency_us * 1e-6f;
    if (secs < 1e-9f) return 0.0f;
    return (static_cast<float>(bytes) / (1024.0f * 1024.0f * 1024.0f)) / secs;
  }

  // --- Member Variables ---
  EngineConfig config_{};
  StageConfig stage_config_{};
  int device_id_ = 0;
  cudaDeviceProp device_props_{};
  std::vector<std::unique_ptr<IProcessingStage>> stages_;
  std::vector<CudaStream> streams_;
  std::vector<CudaEvent> events_;
  std::vector<DeviceBuffer<float>> d_input_buffers_;
  std::vector<DeviceBuffer<float>> d_intermediate_buffers_;
  std::vector<DeviceBuffer<float>> d_output_buffers_;
  PinnedHostBuffer<float> h_input_staging_;
  PinnedHostBuffer<float> h_output_staging_;
  bool initialized_ = false;
  bool profiling_enabled_ = false;
  uint64_t frame_counter_ = 0;
  ProcessingStats stats_{};
};

// ============================================================================
//  ResearchEngine Public Interface (forwarding to Pimpl)
// ============================================================================
ResearchEngine::ResearchEngine() : pImpl(std::make_unique<Impl>()) {}
ResearchEngine::~ResearchEngine() = default;
ResearchEngine::ResearchEngine(ResearchEngine&&) noexcept = default;
ResearchEngine& ResearchEngine::operator=(ResearchEngine&&) noexcept = default;

void ResearchEngine::initialize(const EngineConfig& config) {
  pImpl->initialize(config);
}
void ResearchEngine::process(const float* in, float* out, size_t n) {
  pImpl->process(in, out, n);
}
void ResearchEngine::process_async(const float* in, size_t n,
                                   ResultCallback cb) {
  pImpl->process_async(in, n, cb);
}
void ResearchEngine::synchronize() { pImpl->synchronize(); }
void ResearchEngine::reset() { pImpl->reset(); }
ProcessingStats ResearchEngine::get_stats() const { return pImpl->get_stats(); }
RuntimeInfo ResearchEngine::get_runtime_info() const {
  return pImpl->get_runtime_info();
}
bool ResearchEngine::is_initialized() const { return pImpl->is_initialized(); }
void ResearchEngine::set_profiling_enabled(bool enabled) {
  pImpl->set_profiling_enabled(enabled);
}
void ResearchEngine::dump_profiling_data(
    const std::string&) { /* NVTX integration placeholder */ }
void ResearchEngine::add_stage(std::unique_ptr<IProcessingStage> s) {
  pImpl->add_stage(std::move(s));
}
void ResearchEngine::clear_stages() { pImpl->clear_stages(); }
size_t ResearchEngine::num_stages() const { return pImpl->num_stages(); }
void ResearchEngine::set_stage_config(const StageConfig& c) {
  pImpl->set_stage_config(c);
}
StageConfig ResearchEngine::get_stage_config() const {
  return pImpl->get_stage_config();
}

// ============================================================================
//  Factory and Utility Functions
// ============================================================================

std::unique_ptr<IPipelineEngine> create_engine(const std::string& engine_type) {
  IONO_NVTX_RANGE("Create Engine", profiling::colors::DARK_GRAY);
  if (engine_type == "research") {
    return std::make_unique<ResearchEngine>();
  } else if (engine_type == "ife" || engine_type == "obe") {
    // These are known but not implemented, so a runtime error is appropriate.
    throw std::runtime_error("Engine type '" + engine_type +
                             "' not implemented in v1.0");
  } else {
    // This is an unknown/invalid engine type.
    throw std::invalid_argument("Unknown engine type: " + engine_type);
  }
}

namespace engine_utils {
std::vector<std::string> get_available_devices() {
  IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
  std::vector<std::string> devices;
  int device_count = 0;
  if (cudaGetDeviceCount(&device_count) == cudaSuccess) {
    for (int i = 0; i < device_count; ++i) {
      cudaDeviceProp prop{};
      if (cudaGetDeviceProperties(&prop, i) == cudaSuccess) {
        std::ostringstream oss;
        oss << "[" << i << "] " << prop.name << " (CC " << prop.major << "."
            << prop.minor << ")";
        devices.push_back(oss.str());
      }
    }
  }
  return devices;
}

int select_best_device() {
  IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
  int device_count = 0;
  IONO_CUDA_CHECK(cudaGetDeviceCount(&device_count));
  if (device_count == 0) {
    throw std::runtime_error("No CUDA devices found for selection.");
  }

  int best_device = 0;
  int best_sm_count = -1;
  for (int i = 0; i < device_count; ++i) {
    cudaDeviceProp prop{};
    IONO_CUDA_CHECK(cudaGetDeviceProperties(&prop, i));
    if (prop.multiProcessorCount > best_sm_count) {
      best_sm_count = prop.multiProcessorCount;
      best_device = i;
    }
  }
  return best_device;
}

bool validate_config(const EngineConfig& cfg, std::string& error_msg) {
  IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
  if (cfg.nfft <= 0 || (cfg.nfft & (cfg.nfft - 1)) != 0) {
    error_msg = "nfft must be a positive power of 2.";
    return false;
  }
  if (cfg.batch <= 0) {
    error_msg = "batch must be positive.";
    return false;
  }
  if (cfg.overlap < 0.0f || cfg.overlap >= 1.0f) {
    error_msg = "overlap must be in the range [0.0, 1.0).";
    return false;
  }
  if (cfg.sample_rate_hz <= 0) {
    error_msg = "sample_rate_hz must be positive.";
    return false;
  }
  if (cfg.stream_count <= 0) {
    error_msg = "stream_count must be positive.";
    return false;
  }
  if (cfg.pinned_buffer_count < 2) {
    error_msg = "pinned_buffer_count must be at least 2 for double buffering.";
    return false;
  }
  error_msg.clear();
  return true;
}

size_t estimate_memory_usage(const EngineConfig& cfg) {
  IONO_NVTX_RANGE_FUNCTION(profiling::colors::CYAN);
  size_t total = 0;
  const size_t input_bytes =
      static_cast<size_t>(cfg.nfft) * cfg.batch * sizeof(float);
  const size_t output_bytes =
      static_cast<size_t>(cfg.num_output_bins()) * cfg.batch * sizeof(float);
  const size_t complex_bytes = output_bytes * 2;

  total +=
      cfg.pinned_buffer_count * (input_bytes + output_bytes + complex_bytes);
  total += static_cast<size_t>(cfg.nfft) * sizeof(float);  // window

  // A rough estimate for cuFFT workspace.
  total += static_cast<size_t>(cfg.nfft) * cfg.batch * sizeof(float) * 2;

  return total;
}
}  // namespace engine_utils
}  // namespace ionosense
