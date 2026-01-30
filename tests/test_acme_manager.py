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
        with tempfile.TemporaryDirectory() as tmpdir:
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

        with tempfile.TemporaryDirectory() as tmpdir:
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

        with tempfile.TemporaryDirectory() as tmpdir:
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

        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = f"{tmpdir}/cert.pem"
            key_path = f"{tmpdir}/key.pem"

            manager = ACMEManager(
                email="test@example.com",
                onecom_api=onecom_api,
                cert_path=cert_path,
                key_path=key_path,
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
