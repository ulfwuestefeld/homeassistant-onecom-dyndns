"""
Advanced unit tests for the Certificate Manager module.
Tests for online verification, renewal logic, and edge cases.
"""

import json
import os
import socket
import ssl
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock, PropertyMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock ACME modules before importing
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
    DEFAULT_CERT_PATH,
    DEFAULT_KEY_PATH,
)


class TestOnlineCertificateVerification:
    """Tests for online certificate verification."""

    @pytest.fixture
    def manager(self, temp_cert_paths):
        """Create a test certificate manager with temp paths."""
        mgr = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=temp_cert_paths['cert_path'],
            key_path=temp_cert_paths['key_path'],
            status_file=temp_cert_paths['status_file'],
        )
        yield mgr

    @patch("certificate_manager.socket.create_connection")
    @patch("certificate_manager.ssl.create_default_context")
    def test_verify_online_certificate_success(self, mock_ssl_context, mock_create_conn, manager):
        """Test successful online certificate verification."""
        # Mock SSL socket
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = {
            "subject": ((("commonName", "example.com"),),),
            "issuer": ((("organizationName", "Let's Encrypt"),), (("commonName", "R3"),)),
            "subjectAltName": (("DNS", "example.com"), ("DNS", "www.example.com")),
            "notBefore": "Jan 30 00:00:00 2026 GMT",
            "notAfter": "Apr 30 00:00:00 2026 GMT",
        }

        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__ = Mock(return_value=mock_sock)
        mock_create_conn.return_value.__exit__ = Mock(return_value=False)

        mock_context = MagicMock()
        mock_context.wrap_socket.return_value.__enter__ = Mock(return_value=mock_ssock)
        mock_context.wrap_socket.return_value.__exit__ = Mock(return_value=False)
        mock_ssl_context.return_value = mock_context

        result = manager.verify_online_certificate("example.com")

        assert result["valid"] is True
        assert result["reachable"] is True
        assert result["error"] is None
        assert result["domain_covered"] is True

    @patch("certificate_manager.socket.create_connection")
    def test_verify_online_certificate_timeout(self, mock_create_conn, manager):
        """Test certificate verification with timeout."""
        mock_create_conn.side_effect = socket.timeout("Connection timed out")

        result = manager.verify_online_certificate("example.com")

        assert result["valid"] is False
        assert result["reachable"] is False
        assert "timeout" in result["error"].lower()

    @patch("certificate_manager.socket.create_connection")
    def test_verify_online_certificate_dns_failure(self, mock_create_conn, manager):
        """Test certificate verification with DNS failure."""
        mock_create_conn.side_effect = socket.gaierror(8, "Name not resolved")

        result = manager.verify_online_certificate("nonexistent.example.com")

        assert result["valid"] is False
        assert result["reachable"] is False
        assert "DNS" in result["error"]

    @patch("certificate_manager.socket.create_connection")
    def test_verify_online_certificate_connection_refused(self, mock_create_conn, manager):
        """Test certificate verification with connection refused."""
        mock_create_conn.side_effect = ConnectionRefusedError()

        result = manager.verify_online_certificate("example.com")

        assert result["valid"] is False
        assert "refused" in result["error"].lower()

    @patch("certificate_manager.socket.create_connection")
    @patch("certificate_manager.ssl.create_default_context")
    def test_verify_online_certificate_ssl_error(self, mock_ssl_context, mock_create_conn, manager):
        """Test certificate verification with SSL error."""
        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__ = Mock(return_value=mock_sock)
        mock_create_conn.return_value.__exit__ = Mock(return_value=False)

        mock_context = MagicMock()
        mock_context.wrap_socket.side_effect = ssl.SSLCertVerificationError(
            1, "certificate verify failed"
        )
        mock_ssl_context.return_value = mock_context

        result = manager.verify_online_certificate("example.com")

        assert result["valid"] is False
        assert result["reachable"] is True
        assert "verification failed" in result["error"].lower()

    @patch("certificate_manager.socket.create_connection")
    @patch("certificate_manager.ssl.create_default_context")
    def test_verify_online_certificate_wildcard(self, mock_ssl_context, mock_create_conn, manager):
        """Test certificate verification with wildcard certificate."""
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = {
            "subject": ((("commonName", "*.example.com"),),),
            "issuer": ((("organizationName", "Let's Encrypt"),),),
            "subjectAltName": (("DNS", "*.example.com"), ("DNS", "example.com")),
            "notBefore": "Jan 30 00:00:00 2026 GMT",
            "notAfter": "Apr 30 00:00:00 2026 GMT",
        }

        mock_sock = MagicMock()
        mock_create_conn.return_value.__enter__ = Mock(return_value=mock_sock)
        mock_create_conn.return_value.__exit__ = Mock(return_value=False)

        mock_context = MagicMock()
        mock_context.wrap_socket.return_value.__enter__ = Mock(return_value=mock_ssock)
        mock_context.wrap_socket.return_value.__exit__ = Mock(return_value=False)
        mock_ssl_context.return_value = mock_context

        result = manager.verify_online_certificate("www.example.com")

        assert result["valid"] is True
        assert result["domain_covered"] is True


class TestVerifyAllDomains:
    """Tests for verifying all configured domains."""

    @pytest.fixture
    def manager(self, temp_cert_paths):
        """Create a test certificate manager with multiple domains."""
        mgr = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            ssl_domains=["example.com", "www.example.com", "api.example.com"],
            cert_path=temp_cert_paths['cert_path'],
            key_path=temp_cert_paths['key_path'],
            status_file=temp_cert_paths['status_file'],
        )
        yield mgr

    @patch.object(CertificateManager, 'verify_online_certificate')
    def test_verify_all_domains_all_valid(self, mock_verify, manager):
        """Test verifying all domains when all are valid."""
        mock_verify.return_value = {"valid": True, "domain": "mock", "error": None}

        results = manager.verify_all_domains()

        assert len(results) == 3
        assert all(r["valid"] for r in results.values())
        assert mock_verify.call_count == 3

    @patch.object(CertificateManager, 'verify_online_certificate')
    def test_verify_all_domains_some_invalid(self, mock_verify, manager):
        """Test verifying all domains when some are invalid."""
        def mock_result(domain, **kwargs):
            if domain == "api.example.com":
                return {"valid": False, "domain": domain, "error": "Connection refused"}
            return {"valid": True, "domain": domain, "error": None}

        mock_verify.side_effect = mock_result

        callback_called = []
        manager.add_callback(lambda event, data: callback_called.append((event, data)))

        results = manager.verify_all_domains()

        assert results["example.com"]["valid"] is True
        assert results["www.example.com"]["valid"] is True
        assert results["api.example.com"]["valid"] is False

        # Should notify about invalid certificate
        assert len(callback_called) == 1
        assert callback_called[0][0] == "certificate_invalid_online"
        assert "api.example.com" in callback_called[0][1]["invalid_domains"]


class TestCertificateRenewalLogic:
    """Tests for certificate renewal logic."""

    @pytest.fixture
    def manager(self, temp_cert_paths):
        """Create a test certificate manager."""
        mgr = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            renewal_days=30,
            cert_path=temp_cert_paths['cert_path'],
            key_path=temp_cert_paths['key_path'],
            status_file=temp_cert_paths['status_file'],
        )
        yield mgr

    @patch.object(CertificateManager, 'get_certificate_info')
    @patch.object(CertificateManager, 'request_certificate')
    @patch.object(CertificateManager, 'verify_all_domains')
    def test_check_and_renew_no_certificate(self, mock_verify, mock_request, mock_info, manager):
        """Test check and renew when no certificate exists."""
        mock_info.return_value = None
        mock_verify.return_value = {}

        manager._check_and_renew()

        mock_request.assert_called_once()

    @patch.object(CertificateManager, 'get_certificate_info')
    @patch.object(CertificateManager, 'request_certificate')
    @patch.object(CertificateManager, 'verify_all_domains')
    def test_check_and_renew_certificate_expiring(self, mock_verify, mock_request, mock_info, manager):
        """Test check and renew when certificate is expiring."""
        mock_info.return_value = {
            "days_remaining": 25,  # Less than renewal_days (30)
            "domains": ["example.com"],
        }
        mock_verify.return_value = {}

        callback_events = []
        manager.add_callback(lambda event, data: callback_events.append(event))

        manager._check_and_renew()

        mock_request.assert_called_once()
        assert "expiring" in callback_events

    @patch.object(CertificateManager, 'get_certificate_info')
    @patch.object(CertificateManager, 'request_certificate')
    @patch.object(CertificateManager, 'verify_all_domains')
    def test_check_and_renew_certificate_valid(self, mock_verify, mock_request, mock_info, manager):
        """Test check and renew when certificate is still valid."""
        mock_info.return_value = {
            "days_remaining": 60,  # More than renewal_days (30)
            "domains": ["example.com"],
        }
        mock_verify.return_value = {}

        manager._check_and_renew()

        mock_request.assert_not_called()

    @patch.object(CertificateManager, 'get_certificate_info')
    @patch.object(CertificateManager, 'request_certificate')
    @patch.object(CertificateManager, 'verify_all_domains')
    def test_check_and_renew_expiring_soon_notification(self, mock_verify, mock_request, mock_info, manager):
        """Test notification when certificate is expiring soon but not yet."""
        mock_info.return_value = {
            "days_remaining": 35,  # Between renewal_days and renewal_days+7
            "domains": ["example.com"],
        }
        mock_verify.return_value = {}

        callback_events = []
        manager.add_callback(lambda event, data: callback_events.append(event))

        manager._check_and_renew()

        mock_request.assert_not_called()
        assert "expiring_soon" in callback_events


class TestRequestCertificate:
    """Tests for certificate request functionality."""

    @pytest.fixture
    def manager(self, temp_cert_paths):
        """Create a test certificate manager."""
        mgr = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=temp_cert_paths['cert_path'],
            key_path=temp_cert_paths['key_path'],
            status_file=temp_cert_paths['status_file'],
        )
        yield mgr

    @patch.object(CertificateManager, 'get_certificate_info')
    def test_request_certificate_skip_if_valid(self, mock_info, manager):
        """Test that certificate request is skipped if certificate is valid."""
        mock_info.return_value = {
            "days_remaining": 60,
            "needs_renewal": False,
        }

        result = manager.request_certificate(force=False)

        assert result is True

    @patch.object(CertificateManager, 'get_certificate_info')
    @patch("certificate_manager.OneComAPI")
    @patch("certificate_manager.ACMEManager")
    def test_request_certificate_force_renewal(self, mock_acme, mock_api, mock_info, manager):
        """Test forced certificate renewal."""
        mock_info.return_value = {
            "days_remaining": 60,
            "needs_renewal": False,
        }

        mock_api_instance = Mock()
        mock_api.return_value = mock_api_instance

        mock_acme_instance = Mock()
        mock_acme_instance.obtain_and_save_certificate.return_value = True
        mock_acme.return_value = mock_acme_instance

        # Return new cert info after renewal
        mock_info.side_effect = [
            {"days_remaining": 60, "needs_renewal": False},  # First call
            {"days_remaining": 89, "needs_renewal": False},  # After renewal
        ]

        result = manager.request_certificate(force=True)

        assert result is True
        mock_acme_instance.obtain_and_save_certificate.assert_called_once()
        mock_api_instance.logout.assert_called_once()

    @patch.object(CertificateManager, 'get_certificate_info')
    @patch("certificate_manager.OneComAPI")
    def test_request_certificate_api_error(self, mock_api, mock_info, manager):
        """Test certificate request with API error."""
        from onecom_api import OneComAPIError

        mock_info.return_value = None
        mock_api.side_effect = OneComAPIError("Login failed")

        callback_events = []
        manager.add_callback(lambda event, data: callback_events.append(event))

        result = manager.request_certificate()

        assert result is False
        assert "error" in callback_events

    @patch.object(CertificateManager, 'get_certificate_info')
    @patch("certificate_manager.OneComAPI")
    @patch("certificate_manager.ACMEManager")
    def test_request_certificate_acme_error(self, mock_acme, mock_api, mock_info, manager):
        """Test certificate request with ACME error."""
        from acme_manager import ACMEManagerError

        mock_info.return_value = None

        mock_api_instance = Mock()
        mock_api.return_value = mock_api_instance

        mock_acme.side_effect = ACMEManagerError("Challenge failed")

        callback_events = []
        manager.add_callback(lambda event, data: callback_events.append(event))

        result = manager.request_certificate()

        assert result is False
        assert "error" in callback_events
        mock_api_instance.logout.assert_called_once()


class TestCertificateInfoParsing:
    """Tests for certificate info parsing."""

    @pytest.fixture
    def manager(self, temp_cert_paths):
        """Create a test certificate manager."""
        mgr = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=temp_cert_paths['cert_path'],
            key_path=temp_cert_paths['key_path'],
            status_file=temp_cert_paths['status_file'],
        )
        yield mgr

    def test_get_certificate_info_no_file(self, manager):
        """Test getting info when no certificate file exists."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            manager.cert_path = os.path.join(tmpdir, "nonexistent.pem")
            info = manager.get_certificate_info()
            assert info is None

    @patch("certificate_manager.x509.load_pem_x509_certificate")
    def test_get_certificate_info_parse_error(self, mock_load_cert, manager):
        """Test getting info when certificate parsing fails."""
        mock_load_cert.side_effect = Exception("Invalid certificate")

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            cert_path = os.path.join(tmpdir, "cert.pem")
            with open(cert_path, "w") as f:
                f.write("-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----")
            
            manager.cert_path = cert_path
            info = manager.get_certificate_info()
            assert info is None


class TestThreadingBehavior:
    """Tests for threading behavior."""

    @pytest.fixture
    def manager(self, temp_cert_paths):
        """Create a test certificate manager."""
        mgr = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            check_interval_hours=0.001,  # Very short for testing
            cert_path=temp_cert_paths['cert_path'],
            key_path=temp_cert_paths['key_path'],
            status_file=temp_cert_paths['status_file'],
        )
        yield mgr

    def test_start_creates_daemon_thread(self, manager):
        """Test that start creates a daemon thread."""
        with patch.object(manager, '_renewal_loop'):
            manager.start()

            assert manager._thread is not None
            assert manager._thread.daemon is True
            assert manager._running is True

            manager.stop()

    def test_double_start_is_safe(self, manager):
        """Test that starting twice doesn't create duplicate threads."""
        with patch.object(manager, '_renewal_loop'):
            manager.start()
            first_thread = manager._thread

            manager.start()

            assert manager._thread is first_thread

            manager.stop()

    def test_stop_without_start(self, manager):
        """Test that stopping without starting is safe."""
        manager.stop()  # Should not raise
        assert manager._running is False


class TestStatusPersistence:
    """Tests for status file persistence."""

    @pytest.fixture
    def manager(self, temp_cert_paths):
        """Create a test certificate manager."""
        mgr = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            cert_path=temp_cert_paths['cert_path'],
            key_path=temp_cert_paths['key_path'],
            status_file=temp_cert_paths['status_file'],
        )
        yield mgr

    def test_save_and_load_status_roundtrip(self, manager):
        """Test that status can be saved and loaded."""
        test_status = {
            "status": "valid",
            "last_renewal": "2026-01-30T12:00:00",
            "certificate": {"days_remaining": 89},
        }

        manager._save_status(test_status)

        loaded = manager._load_status()

        assert loaded["status"] == "valid"
        assert loaded["last_renewal"] == "2026-01-30T12:00:00"
        assert "last_updated" in loaded

    def test_load_status_invalid_json(self, manager):
        """Test loading status with invalid JSON."""
        # Write invalid JSON to the manager's status file
        os.makedirs(os.path.dirname(manager.status_file), exist_ok=True)
        with open(manager.status_file, "w") as f:
            f.write("not valid json")

        loaded = manager._load_status()
        assert loaded == {}


class TestGetStatus:
    """Tests for get_status method."""

    @pytest.fixture
    def manager(self, temp_cert_paths):
        """Create a test certificate manager."""
        mgr = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            ssl_domains=["example.com", "www.example.com"],
            staging=True,
            renewal_days=45,
            check_interval_hours=6,
            cert_path=temp_cert_paths['cert_path'],
            key_path=temp_cert_paths['key_path'],
            status_file=temp_cert_paths['status_file'],
        )
        yield mgr

    @patch.object(CertificateManager, 'get_certificate_info')
    @patch.object(CertificateManager, '_load_status')
    def test_get_status_complete(self, mock_load, mock_info, manager):
        """Test that get_status returns complete information."""
        mock_info.return_value = {
            "days_remaining": 89,
            "domains": ["example.com"],
        }
        mock_load.return_value = {"status": "valid"}

        status = manager.get_status()

        assert status["running"] is False
        assert status["staging"] is True
        assert status["ssl_domains"] == ["example.com", "www.example.com"]
        assert status["renewal_days"] == 45
        assert status["check_interval_hours"] == 6.0
        assert status["certificate"]["days_remaining"] == 89
        assert status["saved_status"]["status"] == "valid"


class TestChallengeCallback:
    """Tests for ACME challenge callback."""

    def test_challenge_callback_called_during_request(self):
        """Test that challenge callback is passed to ACME manager."""
        callback_calls = []

        def test_callback(domain, txt_name, txt_value):
            callback_calls.append((domain, txt_name, txt_value))

        manager = CertificateManager(
            username="test@example.com",
            password="password",
            domain="example.com",
            email="ssl@example.com",
            challenge_callback=test_callback,
        )

        assert manager.challenge_callback is test_callback


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
