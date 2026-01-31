"""
Pytest configuration and fixtures for One.com DynDNS tests.
"""

import pytest
import sys
import os
import tempfile
from unittest.mock import Mock, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_options():
    """Provide standard test options."""
    return {
        "username": "test@example.com",
        "password": "testpassword",
        "domain": "example.com",
        "subdomains": ["www", "api", ""],
        "update_interval": 5,
        "ip_service": "ipify",
        "log_level": "error"
    }


@pytest.fixture
def mock_ssl_options():
    """Provide SSL-enabled test options."""
    return {
        "username": "test@example.com",
        "password": "testpassword",
        "domain": "example.com",
        "subdomains": ["www", ""],
        "update_interval": 5,
        "ip_service": "ipify",
        "log_level": "error",
        "ssl_enabled": True,
        "ssl_email": "ssl@example.com",
        "ssl_domains": ["example.com", "www.example.com"],
        "ssl_staging": True,
        "ssl_renewal_days": 30,
        "ssl_check_interval": 12,
        "ssl_force_renewal": False,
    }


@pytest.fixture
def mock_dns_records():
    """Provide mock DNS records response."""
    return {
        "result": {
            "data": [
                {
                    "type": "dns_service_records",
                    "id": "www123",
                    "attributes": {
                        "prefix": "www",
                        "type": "A",
                        "content": "1.1.1.1",
                        "ttl": 3600
                    }
                },
                {
                    "type": "dns_service_records",
                    "id": "api456",
                    "attributes": {
                        "prefix": "api",
                        "type": "A",
                        "content": "1.1.1.1",
                        "ttl": 3600
                    }
                },
                {
                    "type": "dns_service_records",
                    "id": "root789",
                    "attributes": {
                        "prefix": "@",
                        "type": "A",
                        "content": "1.1.1.1",
                        "ttl": 3600
                    }
                }
            ]
        }
    }


@pytest.fixture
def mock_txt_records():
    """Provide mock TXT records response for ACME challenges."""
    return {
        "result": {
            "data": [
                {
                    "type": "dns_custom_records",
                    "id": "acme1",
                    "attributes": {
                        "prefix": "_acme-challenge",
                        "type": "TXT",
                        "content": "token123",
                        "ttl": 600
                    }
                },
                {
                    "type": "dns_custom_records",
                    "id": "acme2",
                    "attributes": {
                        "prefix": "_acme-challenge.www",
                        "type": "TXT",
                        "content": "token456",
                        "ttl": 600
                    }
                }
            ]
        }
    }


@pytest.fixture
def temp_directory():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_certificate_info():
    """Provide mock certificate info."""
    return {
        "not_valid_after": "2026-04-30T00:00:00+00:00",
        "not_valid_before": "2026-01-30T00:00:00+00:00",
        "days_remaining": 89,
        "domains": ["example.com", "www.example.com"],
        "issuer": "Let's Encrypt",
        "needs_renewal": False,
    }


@pytest.fixture
def mock_session():
    """Provide a mock requests session."""
    session = Mock()
    session.headers = {}
    return session


@pytest.fixture
def mock_successful_response():
    """Provide a mock successful HTTP response."""
    response = Mock()
    response.status_code = 200
    response.raise_for_status = Mock()
    return response


@pytest.fixture
def mock_failed_response():
    """Provide a mock failed HTTP response."""
    response = Mock()
    response.status_code = 500
    response.raise_for_status.side_effect = Exception("500 Server Error")
    return response


# Configure pytest to show more details
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
