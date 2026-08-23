"""
Unit tests for the Certificate Manager module.
"""

# Mock the dependencies before importing
import sys
import tempfile
from unittest.mock import MagicMock, Mock, patch

sys.modules['acme'] = MagicMock()
sys.modules['acme.client'] = MagicMock()
sys.modules['acme.messages'] = MagicMock()
sys.modules['acme.challenges'] = MagicMock()
sys.modules['acme.errors'] = MagicMock()
sys.modules['josepy'] = MagicMock()

from certificate_manager import (
    CertificateManager,
    CertificateManagerError,
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
            cert_path = f"{tmpdir}/cert.pem"
            key_path = f"{tmpdir}/key.pem"

            manager = CertificateManager(
                username="user@example.com",
                password="password",
                domain="example.com",
                email="ssl@example.com",
                cert_path=cert_path,
                key_path=key_path,
                status_file=status_file,
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

            manager = CertificateManager(
                username="user@example.com",
                password="password",
                domain="example.com",
                email="ssl@example.com",
                status_file=status_file,
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


class TestCertificateInfoCaching:
    """Tests for certificate info caching in CertificateManager."""

    def test_cached_cert_info_returned_on_second_call(self, tmp_path):
        """Second call to get_certificate_info returns cached data."""
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        status_file = tmp_path / "status.json"

        # Create a dummy cert file so the existence check passes
        cert_path.write_bytes(b"placeholder")

        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=str(cert_path),
            key_path=str(key_path),
            status_file=str(status_file),
        )

        # Manually set cache (simulating a previous successful parse)
        fake_info = {"days_remaining": 60, "needs_renewal": False}
        manager._cached_cert_info = fake_info

        # Call returns cached value without re-parsing the file
        assert manager.get_certificate_info() is fake_info

    def test_cache_invalidated_when_cert_file_deleted(self, tmp_path):
        """Cache is cleared and None returned when the cert file is deleted."""
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        status_file = tmp_path / "status.json"

        # Create a dummy cert file
        cert_path.write_bytes(b"placeholder")

        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=str(cert_path),
            key_path=str(key_path),
            status_file=str(status_file),
        )

        # Simulate cached cert info from a previous call
        manager._cached_cert_info = {"days_remaining": 60, "needs_renewal": False}

        # Delete the certificate file (external cleanup)
        cert_path.unlink()

        # Should detect the missing file, clear cache, and return None
        result = manager.get_certificate_info()
        assert result is None
        assert manager._cached_cert_info is None

    def test_cache_invalidated_after_request_certificate(self, tmp_path):
        """Cache should be None after successful certificate request."""
        cert_path = tmp_path / "cert.pem"
        key_path = tmp_path / "key.pem"
        status_file = tmp_path / "status.json"

        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=str(cert_path),
            key_path=str(key_path),
            status_file=str(status_file),
        )

        # Set fake cache
        manager._cached_cert_info = {"days_remaining": 60}

        # Mock the certificate request flow
        with patch("certificate_manager.OneComAPI") as mock_api, \
             patch("certificate_manager.ACMEManager") as mock_acme:
            mock_api_instance = Mock()
            mock_api.return_value = mock_api_instance

            mock_acme_instance = Mock()
            mock_acme_instance.obtain_and_save_certificate.return_value = True
            mock_acme.return_value = mock_acme_instance

            manager.request_certificate(force=True)

        # Cache should have been invalidated
        assert manager._cached_cert_info is None


class TestStartClearsStopEvent:
    """Tests for CertificateManager.start() clearing _stop_event."""

    def test_start_clears_stop_event(self, tmp_path):
        """start() should clear _stop_event so renewal loop doesn't exit."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=str(tmp_path / "cert.pem"),
            key_path=str(tmp_path / "key.pem"),
            status_file=str(tmp_path / "status.json"),
        )

        # Simulate stop() was called previously
        manager._stop_event.set()
        assert manager._stop_event.is_set()

        # Now start() should clear the event
        with patch.object(manager, '_renewal_loop'):
            manager.start()

        assert not manager._stop_event.is_set()
        manager.stop()

    def test_restart_after_stop_works(self, tmp_path):
        """Manager can be started after being stopped."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=str(tmp_path / "cert.pem"),
            key_path=str(tmp_path / "key.pem"),
            status_file=str(tmp_path / "status.json"),
        )

        with patch.object(manager, '_renewal_loop'):
            manager.start()
            assert manager._running is True
            manager.stop()
            assert manager._running is False
            assert manager._stop_event.is_set()

            # Second start
            manager.start()
            assert manager._running is True
            assert not manager._stop_event.is_set()
            manager.stop()


class TestEnsureDirectoriesOnce:
    """Tests that _ensure_directories only runs once."""

    def test_directories_flag(self, tmp_path):
        """_ensure_directories sets the _directories_created flag."""
        manager = CertificateManager(
            username="user@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=str(tmp_path / "ssl" / "cert.pem"),
            key_path=str(tmp_path / "ssl" / "key.pem"),
            status_file=str(tmp_path / "data" / "status.json"),
        )

        # Flag should already be set because _ensure_directories is NOT
        # called in CertificateManager.__init__; it's called lazily.
        # Let's call it explicitly.
        manager._directories_created = False
        manager._ensure_directories()
        assert manager._directories_created is True

        # Subsequent calls are no-ops (directories exist)
        with patch("os.makedirs") as mock_mkdirs:
            manager._ensure_directories()
            mock_mkdirs.assert_not_called()
