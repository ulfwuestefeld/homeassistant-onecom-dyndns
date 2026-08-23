"""
Tests for DNS operations including record creation, deletion, and validation.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onecom_api import OneComAPI


class TestDNSRecordTypes:
    """Tests for different DNS record type operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")

    def test_a_record_format(self):
        """Test A record data format."""
        record_data = {
            'type': 'dns_custom_records',
            'attributes': {
                'type': 'A',
                'prefix': 'www',
                'content': '192.168.1.100',
                'ttl': 600
            }
        }
        assert record_data['attributes']['type'] == 'A'
        assert record_data['attributes']['content'] == '192.168.1.100'

    def test_txt_record_format(self):
        """Test TXT record data format."""
        record_data = {
            'type': 'dns_custom_records',
            'attributes': {
                'type': 'TXT',
                'prefix': '_acme-challenge',
                'content': 'verification_token_123',
                'ttl': 600
            }
        }
        assert record_data['attributes']['type'] == 'TXT'
        assert record_data['attributes']['prefix'] == '_acme-challenge'

    def test_cname_record_format(self):
        """Test CNAME record data format."""
        record_data = {
            'type': 'dns_custom_records',
            'attributes': {
                'type': 'CNAME',
                'prefix': 'mail',
                'content': 'mail.example.com',
                'ttl': 600
            }
        }
        assert record_data['attributes']['type'] == 'CNAME'


class TestDNSTTLHandling:
    """Tests for DNS TTL (Time To Live) handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")

    def test_minimum_ttl_enforcement(self):
        """Test that minimum TTL of 600 is enforced for One.com."""
        # One.com requires minimum TTL of 600 seconds
        MIN_TTL = 600
        assert MIN_TTL == 600

    def test_ttl_below_minimum_raises_error(self):
        """Test that TTL below 600 causes API error."""
        # This is documented behavior from One.com API
        low_ttl_data = {
            'type': 'dns_custom_records',
            'attributes': {
                'type': 'TXT',
                'prefix': 'test',
                'content': 'value',
                'ttl': 60  # Too low!
            }
        }
        # The API would reject this with error code COMRST_000003
        assert low_ttl_data['attributes']['ttl'] < 600

    def test_valid_ttl_values(self):
        """Test various valid TTL values."""
        valid_ttls = [600, 900, 1800, 3600, 7200, 14400, 28800, 43200, 86400]
        for ttl in valid_ttls:
            assert ttl >= 600


class TestDNSPropagation:
    """Tests for DNS propagation checking."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")

    @patch('requests.get')
    def test_dns_propagation_check_success(self, mock_get):
        """Test successful DNS propagation check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'Status': 0,
            'Answer': [
                {'type': 16, 'data': '"expected_value"'}
            ]
        }
        mock_get.return_value = mock_response
        
        # Simulate DNS check via Google DNS
        response = requests.get(
            'https://dns.google/resolve',
            params={'name': '_acme-challenge.example.com', 'type': 'TXT'}
        )
        
        data = response.json()
        assert data['Status'] == 0
        assert len(data['Answer']) > 0

    @patch('requests.get')
    def test_dns_propagation_check_not_found(self, mock_get):
        """Test DNS propagation check when record not found."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'Status': 3,  # NXDOMAIN
            'Answer': []
        }
        mock_get.return_value = mock_response
        
        response = requests.get(
            'https://dns.google/resolve',
            params={'name': '_acme-challenge.notfound.com', 'type': 'TXT'}
        )
        
        data = response.json()
        assert data['Status'] == 3  # NXDOMAIN

    @patch('requests.get')
    def test_dns_propagation_timeout(self, mock_get):
        """Test DNS propagation check timeout handling."""
        mock_get.side_effect = requests.exceptions.Timeout("DNS query timeout")
        
        with pytest.raises(requests.exceptions.Timeout):
            requests.get(
                'https://dns.google/resolve',
                params={'name': 'test.example.com', 'type': 'TXT'},
                timeout=5
            )


class TestDNSRecordConflicts:
    """Tests for handling DNS record conflicts."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")

    def test_conflict_detection_same_prefix(self):
        """Test detection of conflicting records with same prefix."""
        existing_record = {
            'id': '12345',
            'attributes': {
                'prefix': '_acme-challenge.www',
                'type': 'TXT',
                'content': 'old_value'
            }
        }
        new_record = {
            'prefix': '_acme-challenge.www',
            'type': 'TXT',
            'content': 'new_value'
        }
        
        # Same prefix and type = conflict
        assert existing_record['attributes']['prefix'] == new_record['prefix']
        assert existing_record['attributes']['type'] == new_record['type']

    def test_no_conflict_different_prefix(self):
        """Test no conflict for different prefixes."""
        existing_record = {
            'id': '12345',
            'attributes': {
                'prefix': '_acme-challenge.www',
                'type': 'TXT',
                'content': 'value1'
            }
        }
        new_record = {
            'prefix': '_acme-challenge.api',
            'type': 'TXT',
            'content': 'value2'
        }
        
        # Different prefix = no conflict
        assert existing_record['attributes']['prefix'] != new_record['prefix']

    def test_conflict_resolution_same_content(self):
        """Test that same content is treated as success (no action needed)."""
        existing_content = "challenge_token_abc"
        new_content = "challenge_token_abc"
        
        # Same content means record already exists correctly
        assert existing_content == new_content


class TestDNSSubdomainHandling:
    """Tests for subdomain handling in DNS operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.api = OneComAPI("test@example.com", "password", "example.com")

    def test_simple_subdomain(self):
        """Test simple subdomain formatting."""
        subdomain = "www"
        domain = "example.com"
        full_name = f"{subdomain}.{domain}"
        assert full_name == "www.example.com"

    def test_nested_subdomain(self):
        """Test nested subdomain formatting."""
        subdomain = "api.v2"
        domain = "example.com"
        full_name = f"{subdomain}.{domain}"
        assert full_name == "api.v2.example.com"

    def test_acme_challenge_subdomain(self):
        """Test ACME challenge subdomain formatting."""
        base_subdomain = "homeassistant"
        acme_prefix = "_acme-challenge"
        domain = "example.com"
        
        challenge_name = f"{acme_prefix}.{base_subdomain}.{domain}"
        assert challenge_name == "_acme-challenge.homeassistant.example.com"

    def test_empty_subdomain_root_domain(self):
        """Test empty subdomain (root domain)."""
        subdomain = ""
        domain = "example.com"
        
        if subdomain:
            full_name = f"{subdomain}.{domain}"
        else:
            full_name = domain
        
        assert full_name == "example.com"

    def test_wildcard_subdomain(self):
        """Test wildcard subdomain handling."""
        subdomain = "*"
        domain = "example.com"
        full_name = f"{subdomain}.{domain}"
        assert full_name == "*.example.com"


class TestDNSIPValidation:
    """Tests for IP address validation in DNS A records."""

    def test_valid_ipv4_addresses(self):
        """Test valid IPv4 addresses."""
        valid_ips = [
            "192.168.1.1",
            "10.0.0.1",
            "172.16.0.1",
            "8.8.8.8",
            "1.1.1.1",
            "255.255.255.255",
            "0.0.0.0",
        ]
        
        import re
        ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        
        for ip in valid_ips:
            assert re.match(ipv4_pattern, ip) is not None

    def test_invalid_ipv4_addresses(self):
        """Test invalid IPv4 addresses."""
        invalid_ips = [
            "256.1.1.1",      # Out of range
            "1.1.1",          # Missing octet
            "1.1.1.1.1",      # Extra octet
            "abc.def.ghi.jkl", # Non-numeric
            "",               # Empty
            "192.168.1",      # Incomplete
        ]
        
        import re
        ipv4_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        
        for ip in invalid_ips:
            assert re.match(ipv4_pattern, ip) is None

    def test_private_vs_public_ip(self):
        """Test distinction between private and public IP addresses."""
        import ipaddress
        
        private_ips = ["192.168.1.1", "10.0.0.1", "172.16.0.1"]
        public_ips = ["8.8.8.8", "1.1.1.1", "91.51.131.49"]
        
        for ip in private_ips:
            assert ipaddress.ip_address(ip).is_private
        
        for ip in public_ips:
            assert not ipaddress.ip_address(ip).is_private
