"""
Unit tests for the ACME Manager module.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import pytest

# Mock the acme and cryptography imports before importing our module
import sys
sys.modules['acme'] = MagicMock()
sys.modules['acme.client'] = MagicMock()
sys.modules['acme.messages'] = MagicMock()
sys.modules['acme.challenges'] = MagicMock()
sys.modules['acme.errors'] = MagicMock()
sys.modules['josepy'] = MagicMock()

from acme_manager import (
    ACMEManager,
    ACMEManagerError,
    LETSENCRYPT_PRODUCTION,
    LETSENCRYPT_STAGING,
)


class TestACMEManagerInit:
    """Tests for ACMEManager initialization."""

    def test_init_default_production(self):
        """Test initialization with production server."""
        onecom_api = Mock()

        manager = ACMEManager(
            email="test@example.com",
            onecom_api=onecom_api,
            staging=False,
        )

        assert manager.email == "test@example.com"
        assert manager.staging is False
        assert manager.directory_url == LETSENCRYPT_PRODUCTION

    def test_init_staging_server(self):
        """Test initialization with staging server."""
        onecom_api = Mock()

        manager = ACMEManager(
            email="test@example.com",
            onecom_api=onecom_api,
            staging=True,
        )

        assert manager.staging is True
        assert manager.directory_url == LETSENCRYPT_STAGING

    def test_init_custom_paths(self):
        """Test initialization with custom paths."""
        onecom_api = Mock()

        manager = ACMEManager(
            email="test@example.com",
            onecom_api=onecom_api,
            account_key_path="/custom/account.key",
            cert_path="/custom/cert.pem",
            key_path="/custom/key.pem",
        )

        assert manager.account_key_path == "/custom/account.key"
        assert manager.cert_path == "/custom/cert.pem"
        assert manager.key_path == "/custom/key.pem"


class TestACMEManagerDirectories:
    """Tests for directory management."""

    def test_ensure_directories_creates_paths(self):
        """Test that directories are created."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            onecom_api = Mock()

            manager = ACMEManager(
                email="test@example.com",
                onecom_api=onecom_api,
                account_key_path=f"{tmpdir}/acme/account.key",
                cert_path=f"{tmpdir}/ssl/cert.pem",
                key_path=f"{tmpdir}/ssl/key.pem",
            )

            manager._ensure_directories()

            assert os.path.exists(f"{tmpdir}/acme")
            assert os.path.exists(f"{tmpdir}/ssl")


class TestACMEManagerKeyGeneration:
    """Tests for key generation."""

    def test_generate_private_key(self):
        """Test private key generation."""
        onecom_api = Mock()

        manager = ACMEManager(
            email="test@example.com",
            onecom_api=onecom_api,
        )

        # This will use the mocked cryptography
        key = manager._generate_private_key(2048)
        assert key is not None


class TestACMEManagerCertificateExpiry:
    """Tests for certificate expiry checking."""

    def test_get_certificate_expiry_no_cert(self):
        """Test expiry check when no certificate exists."""
        onecom_api = Mock()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            manager = ACMEManager(
                email="test@example.com",
                onecom_api=onecom_api,
                cert_path=f"{tmpdir}/nonexistent.pem",
            )

            expiry = manager.get_certificate_expiry()
            assert expiry is None

    def test_needs_renewal_no_cert(self):
        """Test renewal check when no certificate exists."""
        onecom_api = Mock()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            manager = ACMEManager(
                email="test@example.com",
                onecom_api=onecom_api,
                cert_path=f"{tmpdir}/nonexistent.pem",
            )

            assert manager.needs_renewal() is True


class TestACMEManagerCertificateSaving:
    """Tests for certificate saving."""

    def test_save_certificate(self):
        """Test saving certificate and key."""
        onecom_api = Mock()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            cert_path = f"{tmpdir}/cert.pem"
            key_path = f"{tmpdir}/key.pem"
            account_key_path = f"{tmpdir}/account.key"

            manager = ACMEManager(
                email="test@example.com",
                onecom_api=onecom_api,
                cert_path=cert_path,
                key_path=key_path,
                account_key_path=account_key_path,
            )

            cert_pem = "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
            key_pem = "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"

            manager.save_certificate(cert_pem, key_pem)

            assert os.path.exists(cert_path)
            assert os.path.exists(key_path)

            with open(cert_path) as f:
                assert f.read() == cert_pem

            with open(key_path) as f:
                assert f.read() == key_pem


class TestACMEManagerTimezoneHandling:
    """Tests for timezone-aware certificate expiry comparison."""

    def test_needs_renewal_with_timezone_aware_expiry(self):
        """Test needs_renewal handles timezone-aware expiry from cryptography."""
        from datetime import datetime, timedelta, timezone

        onecom_api = Mock()
        manager = ACMEManager(
            email="test@example.com",
            onecom_api=onecom_api,
        )

        # Simulate a timezone-aware expiry (as returned by cryptography's not_valid_after_utc)
        future_expiry = datetime.now(timezone.utc) + timedelta(days=60)
        with patch.object(manager, 'get_certificate_expiry', return_value=future_expiry):
            assert manager.needs_renewal(days_before_expiry=30) is False

    def test_needs_renewal_with_timezone_aware_expiry_soon(self):
        """Test needs_renewal correctly detects expiring timezone-aware cert."""
        from datetime import datetime, timedelta, timezone

        onecom_api = Mock()
        manager = ACMEManager(
            email="test@example.com",
            onecom_api=onecom_api,
        )

        # Simulate a certificate expiring in 10 days (UTC-aware)
        soon_expiry = datetime.now(timezone.utc) + timedelta(days=10)
        with patch.object(manager, 'get_certificate_expiry', return_value=soon_expiry):
            assert manager.needs_renewal(days_before_expiry=30) is True

    def test_needs_renewal_with_timezone_naive_expiry(self):
        """Test needs_renewal still works with timezone-naive expiry (fallback)."""
        from datetime import datetime, timedelta

        onecom_api = Mock()
        manager = ACMEManager(
            email="test@example.com",
            onecom_api=onecom_api,
        )

        # Simulate a timezone-naive expiry (as returned by older cryptography versions)
        future_expiry = datetime.now() + timedelta(days=60)
        with patch.object(manager, 'get_certificate_expiry', return_value=future_expiry):
            assert manager.needs_renewal(days_before_expiry=30) is False


class TestACMEManagerValidation:
    """Tests for input validation."""

    def test_obtain_certificate_no_domains(self):
        """Test that empty domain list raises error."""
        onecom_api = Mock()

        manager = ACMEManager(
            email="test@example.com",
            onecom_api=onecom_api,
        )

        with pytest.raises(ACMEManagerError, match="No domains specified"):
            manager.obtain_certificate([])


class TestACMEManagerStopEvent:
    """Tests for ACMEManager stop event and graceful shutdown."""

    def test_default_stop_event_created(self):
        """Test that a private stop_event is created when none provided."""
        import threading

        manager = ACMEManager(
            email="test@example.com",
            onecom_api=Mock(),
        )

        assert isinstance(manager._stop_event, threading.Event)
        assert not manager._stop_event.is_set()

    def test_external_stop_event_used(self):
        """Test that an externally provided stop_event is used."""
        import threading

        ext_event = threading.Event()
        manager = ACMEManager(
            email="test@example.com",
            onecom_api=Mock(),
            stop_event=ext_event,
        )

        assert manager._stop_event is ext_event

    def test_stop_sets_event(self):
        """Test that stop() sets the event."""
        manager = ACMEManager(
            email="test@example.com",
            onecom_api=Mock(),
        )

        assert not manager._stop_event.is_set()
        manager.stop()
        assert manager._stop_event.is_set()

    def test_shared_stop_event_propagates(self):
        """Test that setting a shared event is visible in ACMEManager."""
        import threading

        shared = threading.Event()
        manager = ACMEManager(
            email="test@example.com",
            onecom_api=Mock(),
            stop_event=shared,
        )

        assert not manager._stop_event.is_set()
        shared.set()
        assert manager._stop_event.is_set()


class TestACMEManagerError:
    """Tests for ACMEManagerError exception."""

    def test_exception_message(self):
        """Test exception stores message correctly."""
        error = ACMEManagerError("Test error message")
        assert str(error) == "Test error message"

    def test_exception_inheritance(self):
        """Test exception inherits from Exception."""
        error = ACMEManagerError("Test")
        assert isinstance(error, Exception)
