"""
Pytest configuration and fixtures for One.com DynDNS tests.
"""

import pytest
import sys
import os

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
