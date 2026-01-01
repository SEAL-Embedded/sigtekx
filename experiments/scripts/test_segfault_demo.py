"""Test the ACTUAL segfault scenario from the GitHub issue."""
import numpy as np

from sigtekx.core import _native  # Direct C++ binding

BatchExecutor = _native.BatchExecutor

# Test 1: Direct C++ executor (like GitHub issue example)
print("Test 1: Direct BatchExecutor usage")

# Create C++ config (not Python EngineConfig)
cpp_config = _native.ExecutorConfig()
cpp_config.nfft = 256
cpp_config.channels = 1
cpp_config.overlap = 0.5

executor = BatchExecutor()
executor.initialize(cpp_config)

data = np.ones(256, dtype=np.float32)
output = executor.process(data)

print(f"Before del: output mean = {output.mean():.6f}")
print(f"Before del: output address = {output.__array_interface__['data'][0]:x}")

# The critical test - delete executor while output still referenced
del executor

print("\nAfter del executor:")
try:
    # This SHOULD segfault if output is a dangling pointer
    value = output[0, 0]
    print(f"✅ No crash! value = {value:.6f}")
    print(f"✅ Output still accessible: mean = {output.mean():.6f}")
except Exception as e:
    print(f"❌ Crashed with error: {e}")

print("\n" + "="*60)

# Test 2: Multiple outputs from same executor
print("\nTest 2: Multiple outputs (aliasing check)")

# Create another C++ config
cpp_config2 = _native.ExecutorConfig()
cpp_config2.nfft = 256
cpp_config2.channels = 1
cpp_config2.overlap = 0.5

executor2 = BatchExecutor()
executor2.initialize(cpp_config2)

data1 = np.ones(256, dtype=np.float32) * 1.0
data2 = np.ones(256, dtype=np.float32) * 2.0

output1 = executor2.process(data1)
output2 = executor2.process(data2)

print(f"output1 mean: {output1.mean():.6f}")
print(f"output2 mean: {output2.mean():.6f}")
print(f"output1 address: {output1.__array_interface__['data'][0]:x}")
print(f"output2 address: {output2.__array_interface__['data'][0]:x}")

if output1.__array_interface__['data'][0] == output2.__array_interface__['data'][0]:
    print("❌ Same address - aliasing bug confirmed!")
else:
    print("✅ Different addresses - no aliasing")

# Check if values are identical (would indicate buffer reuse)
if np.allclose(output1, output2):
    print("⚠️  Values are identical - might indicate buffer reuse despite different addresses")
else:
    print("✅ Values are different - outputs are truly independent")
