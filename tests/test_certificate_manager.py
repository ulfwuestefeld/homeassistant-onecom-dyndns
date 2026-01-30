"""
Unit tests for the Certificate Manager module.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import threading
import time

import pytest

# Mock the dependencies before importing
import sys
sys.modules['acme'] = MagicMock()
sys.modules['acme.client'] = MagicMock()
sys.modules['acme.messages'] = MagicMock()
sys.modules['acme.challenges'] = MagicMock()
sys.modules['acme.errors'] = MagicMock()
sys.modules['josepy'] = MagicMock()

from certificate_manager import (
    CertificateManager,
    CertificateManagerError,
    CERT_STATUS_FILE,
)


class TestCertificateManagerInit:
    """Tests for CertificateManager initialization."""

    def test_init_basic(self):
        """Test basic initialization."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        assert manager.username == "user@example.com"
        assert manager.password == "password"
        assert manager.domain == "example.com"
        assert manager.email == "ssl@example.com"
        assert manager.ssl_domains == ["example.com"]
        assert manager.staging is False
        assert manager.renewal_days == 30

    def test_init_with_ssl_domains(self):
        """Test initialization with custom SSL domains."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            ssl_domains=["example.com", "www.example.com", "*.example.com"],
        )

        assert manager.ssl_domains == ["example.com", "www.example.com", "*.example.com"]

    def test_init_staging_mode(self):
        """Test initialization with staging mode."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            staging=True,
        )

        assert manager.staging is True

    def test_init_custom_renewal_days(self):
        """Test initialization with custom renewal days."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            renewal_days=45,
        )

        assert manager.renewal_days == 45


class TestCertificateManagerCallbacks:
    """Tests for callback functionality."""

    def test_add_callback(self):
        """Test adding a callback."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        callback = Mock()
        manager.add_callback(callback)

        assert callback in manager._callbacks

    def test_notify_calls_callbacks(self):
        """Test that notify calls all registered callbacks."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        callback1 = Mock()
        callback2 = Mock()
        manager.add_callback(callback1)
        manager.add_callback(callback2)

        manager._notify("test_event", {"key": "value"})

        callback1.assert_called_once_with("test_event", {"key": "value"})
        callback2.assert_called_once_with("test_event", {"key": "value"})

    def test_notify_handles_callback_errors(self):
        """Test that callback errors don't crash notification."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        failing_callback = Mock(side_effect=Exception("Callback error"))
        success_callback = Mock()

        manager.add_callback(failing_callback)
        manager.add_callback(success_callback)

        # Should not raise
        manager._notify("test_event", {})

        # Second callback should still be called
        success_callback.assert_called_once()


class TestCertificateManagerStatus:
    """Tests for status management."""

    def test_save_and_load_status(self):
        """Test saving and loading status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            status_file = f"{tmpdir}/status.json"

            with patch('certificate_manager.CERT_STATUS_FILE', status_file):
                manager = CertificateManager(
                    username="user@example.com",
                    password="password",
                    domain="example.com",
                    email="ssl@example.com",
                )

                test_status = {"status": "valid", "test_key": "test_value"}
                manager._save_status(test_status)

                loaded_status = manager._load_status()

                assert loaded_status["status"] == "valid"
                assert loaded_status["test_key"] == "test_value"
                assert "last_updated" in loaded_status

    def test_load_status_no_file(self):
        """Test loading status when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            status_file = f"{tmpdir}/nonexistent.json"

            with patch('certificate_manager.CERT_STATUS_FILE', status_file):
                manager = CertificateManager(
                    username="user@example.com",
                    password="password",
                    domain="example.com",
                    email="ssl@example.com",
                )

                status = manager._load_status()
                assert status == {}


class TestCertificateManagerCertInfo:
    """Tests for certificate info retrieval."""

    def test_get_certificate_info_no_cert(self):
        """Test getting info when no certificate exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CertificateManager(
                username="user@example.com",
                password="password",
                domain="example.com",
                email="ssl@example.com",
                cert_path=f"{tmpdir}/nonexistent.pem",
            )

            info = manager.get_certificate_info()
            assert info is None


class TestCertificateManagerStartStop:
    """Tests for start/stop functionality."""

    def test_start_creates_thread(self):
        """Test that start creates a background thread."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        # Mock the renewal loop to exit immediately
        with patch.object(manager, '_renewal_loop'):
            manager.start()

            assert manager._running is True
            assert manager._thread is not None

            manager.stop()

    def test_stop_sets_running_false(self):
        """Test that stop sets running to False."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        manager._running = True
        manager._thread = Mock()
        manager._thread.join = Mock()

        manager.stop()

        assert manager._running is False

    def test_start_when_already_running(self):
        """Test that start does nothing when already running."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
        )

        manager._running = True
        original_thread = manager._thread

        manager.start()

        # Thread should not change
        assert manager._thread == original_thread


class TestCertificateManagerGetStatus:
    """Tests for get_status method."""

    def test_get_status_basic(self):
        """Test getting basic status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CertificateManager(
                username="user@example.com",
                password="password",
                domain="example.com",
                email="ssl@example.com",
                cert_path=f"{tmpdir}/cert.pem",
                key_path=f"{tmpdir}/key.pem",
                staging=True,
                renewal_days=45,
                check_interval_hours=6,
            )

            status = manager.get_status()

            assert status["running"] is False
            assert status["staging"] is True
            assert status["ssl_domains"] == ["example.com"]
            assert status["renewal_days"] == 45
            assert status["check_interval_hours"] == 6.0
            assert status["certificate"] is None


class TestCertificateManagerError:
    """Tests for CertificateManagerError exception."""

    def test_exception_message(self):
        """Test exception stores message correctly."""
        error = CertificateManagerError("Test error message")
        assert str(error) == "Test error message"

    def test_exception_inheritance(self):
        """Test exception inherits from Exception."""
        error = CertificateManagerError("Test")
        assert isinstance(error, Exception)
