# python/tests/test_buffers.py
"""
Unit tests for the buffer management system.
"""
import numpy as np
import pytest
from numpy.testing import assert_array_equal

from ionosense_hpc.core.buffers import ManagedBuffer, BufferPool

# Mark all tests in this file as belonging to the 'buffers' suite
pytestmark = pytest.mark.buffers


def test_managed_buffer_creation_and_properties():
    """Tests the basic properties of a ManagedBuffer."""
    view = np.zeros((16, 1024), dtype=np.float32)
    buf = ManagedBuffer(view=view, stream_id=0, name="test_buf")
    
    assert buf.stream_id == 0
    assert buf.shape == (16, 1024)
    assert buf.dtype == np.float32
    assert buf.nbytes == 16 * 1024 * 4


def test_managed_buffer_use_context():
    """Tests that the context manager provides access and allows modification."""
    view = np.zeros((2, 4), dtype=np.float32)
    buf = ManagedBuffer(view=view, stream_id=0, name="test_context")
    
    data_to_write = np.arange(8, dtype=np.float32).reshape(2, 4)
    
    with buf.use() as buffer_view:
        assert buffer_view.shape == (2, 4)
        np.copyto(buffer_view, data_to_write)
    
    # Verify that the original view was modified
    assert_array_equal(view, data_to_write)


def test_managed_buffer_lock_prevents_nested_use():
    """
    Tests that the lock correctly prevents acquiring a buffer that is already in use.
    """
    view = np.zeros(1)
    buf = ManagedBuffer(view=view, stream_id=0, name="test_lock")
    
    with buf.use() as outer_view:
        # Trying to acquire the lock again inside the `with` block will fail
        # because a simple Lock is not re-entrant.
        assert not buf._lock.acquire(blocking=False)
        # We can still work with the view we already have
        outer_view[0] = 123
        
    # After the `with` block, the lock should be released
    assert buf._lock.acquire(blocking=False)
    buf._lock.release() # Clean up


def test_buffer_pool_creation():
    """Tests that the BufferPool initializes correctly."""
    pool = BufferPool(num_streams=3)
    assert pool.num_streams == 3


def test_buffer_pool_registration_and_retrieval():
    """Tests registering and getting buffers from the pool."""
    pool = BufferPool(num_streams=2)
    
    in_view_0 = np.zeros((8, 1024), dtype=np.float32)
    out_view_1 = np.ones((8, 513), dtype=np.float32)
    
    pool.register_input_buffer(stream_id=0, view=in_view_0)
    pool.register_output_buffer(stream_id=1, view=out_view_1)
    
    retrieved_in = pool.get_input_buffer(0)
    retrieved_out = pool.get_output_buffer(1)
    
    assert retrieved_in.shape == in_view_0.shape
    assert retrieved_out.stream_id == 1
    
    # Check that the underlying memory is the same
    with retrieved_out.use() as buf:
        assert_array_equal(buf, out_view_1)


def test_buffer_pool_invalid_access():
    """Tests that accessing unregistered or out-of-bounds buffers raises errors."""
    pool = BufferPool(num_streams=3)
    
    # Getting a buffer that hasn't been registered
    with pytest.raises(KeyError):
        pool.get_input_buffer(1)
        
    # Registering with an out-of-bounds stream_id
    with pytest.raises(IndexError):
        pool.register_output_buffer(stream_id=3, view=np.zeros(1))
