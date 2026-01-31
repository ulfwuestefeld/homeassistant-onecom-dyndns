"""
Unit tests for the retry_with_backoff decorator in acme_manager.py
"""

import os
import sys
import time
from unittest.mock import Mock, patch, MagicMock, call

import pytest
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acme_manager import retry_with_backoff, ACMEManager, ACMEManagerError


class TestRetryWithBackoffDecorator:
    """Tests for the retry_with_backoff decorator."""

    def test_successful_call_no_retry(self):
        """Test that successful calls don't trigger retries."""
        call_count = 0
        
        @retry_with_backoff
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_function()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_connection_error(self):
        """Test retry on ConnectionError."""
        call_count = 0
        
        @retry_with_backoff
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.exceptions.ConnectionError("Connection failed")
            return "success"
        
        with patch('time.sleep'):  # Skip actual sleep
            result = failing_then_success()
        
        assert result == "success"
        assert call_count == 3

    def test_retry_on_timeout(self):
        """Test retry on Timeout error."""
        call_count = 0
        
        @retry_with_backoff
        def timeout_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise requests.exceptions.Timeout("Request timed out")
            return "success"
        
        with patch('time.sleep'):
            result = timeout_then_success()
        
        assert result == "success"
        assert call_count == 2

    def test_retry_on_request_exception(self):
        """Test retry on generic RequestException."""
        call_count = 0
        
        @retry_with_backoff
        def request_error_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise requests.exceptions.RequestException("Request failed")
            return "success"
        
        with patch('time.sleep'):
            result = request_error_then_success()
        
        assert result == "success"
        assert call_count == 2

    def test_max_retries_exceeded(self):
        """Test that exception is raised after max retries."""
        call_count = 0
        
        @retry_with_backoff
        def always_failing():
            nonlocal call_count
            call_count += 1
            raise requests.exceptions.ConnectionError("Always fails")
        
        with patch('time.sleep'):
            with pytest.raises(requests.exceptions.ConnectionError):
                always_failing()
        
        # Default max_retries is 3, so it should be called 4 times (initial + 3 retries)
        assert call_count == 4

    def test_non_retryable_exception_not_retried(self):
        """Test that non-network exceptions are not retried."""
        call_count = 0
        
        @retry_with_backoff
        def value_error_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a network error")
        
        with pytest.raises(ValueError):
            value_error_function()
        
        assert call_count == 1  # Should only be called once

    def test_exponential_backoff_timing(self):
        """Test that exponential backoff is applied correctly."""
        sleep_times = []
        
        @retry_with_backoff
        def always_failing():
            raise requests.exceptions.ConnectionError("Always fails")
        
        def mock_sleep(seconds):
            sleep_times.append(seconds)
        
        with patch('time.sleep', side_effect=mock_sleep):
            with pytest.raises(requests.exceptions.ConnectionError):
                always_failing()
        
        # Verify exponential backoff pattern (2^0, 2^1, 2^2 = 1, 2, 4)
        # With jitter, values should be around these numbers
        assert len(sleep_times) == 3
        # First retry should be around 1 second (plus jitter)
        assert 0.5 <= sleep_times[0] <= 2.0
        # Second retry should be around 2 seconds (plus jitter)
        assert 1.0 <= sleep_times[1] <= 4.0
        # Third retry should be around 4 seconds (plus jitter)
        assert 2.0 <= sleep_times[2] <= 8.0


class TestRetryWithBackoffWithMethods:
    """Tests for retry_with_backoff used on class methods."""

    def test_retry_preserves_self(self):
        """Test that retry decorator preserves self reference in methods."""
        
        class TestClass:
            def __init__(self):
                self.call_count = 0
            
            @retry_with_backoff
            def method_with_retry(self):
                self.call_count += 1
                if self.call_count < 2:
                    raise requests.exceptions.ConnectionError("Retry needed")
                return f"success after {self.call_count} calls"
        
        obj = TestClass()
        with patch('time.sleep'):
            result = obj.method_with_retry()
        
        assert result == "success after 2 calls"
        assert obj.call_count == 2

    def test_retry_preserves_arguments(self):
        """Test that retry decorator preserves method arguments."""
        
        class TestClass:
            def __init__(self):
                self.call_count = 0
            
            @retry_with_backoff
            def method_with_args(self, arg1, arg2, kwarg1=None):
                self.call_count += 1
                if self.call_count < 2:
                    raise requests.exceptions.ConnectionError("Retry needed")
                return f"{arg1}-{arg2}-{kwarg1}"
        
        obj = TestClass()
        with patch('time.sleep'):
            result = obj.method_with_args("a", "b", kwarg1="c")
        
        assert result == "a-b-c"


class TestRetryWithBackoffEdgeCases:
    """Edge case tests for retry_with_backoff."""

    def test_retry_with_ssl_error(self):
        """Test retry on SSL errors."""
        call_count = 0
        
        @retry_with_backoff
        def ssl_error_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise requests.exceptions.SSLError("SSL handshake failed")
            return "success"
        
        with patch('time.sleep'):
            result = ssl_error_then_success()
        
        assert result == "success"
        assert call_count == 2

    def test_retry_with_chunked_encoding_error(self):
        """Test retry on ChunkedEncodingError."""
        call_count = 0
        
        @retry_with_backoff
        def chunked_error_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise requests.exceptions.ChunkedEncodingError("Chunked encoding error")
            return "success"
        
        with patch('time.sleep'):
            result = chunked_error_then_success()
        
        assert result == "success"
        assert call_count == 2

    def test_function_metadata_preserved(self):
        """Test that function metadata is preserved by decorator."""
        
        @retry_with_backoff
        def documented_function():
            """This is the docstring."""
            return "result"
        
        assert documented_function.__name__ == "documented_function"
        assert "docstring" in documented_function.__doc__

    def test_retry_returns_correct_type(self):
        """Test that retry returns the same type as the original function."""
        
        @retry_with_backoff
        def returns_dict():
            return {"key": "value"}
        
        @retry_with_backoff
        def returns_list():
            return [1, 2, 3]
        
        @retry_with_backoff
        def returns_none():
            return None
        
        assert isinstance(returns_dict(), dict)
        assert isinstance(returns_list(), list)
        assert returns_none() is None
