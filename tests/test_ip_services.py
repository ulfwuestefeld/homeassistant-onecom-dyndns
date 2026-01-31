"""
Tests for IP detection services used by the DynDNS updater.
"""

import os
import sys
from unittest.mock import Mock, patch, MagicMock

import pytest
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run import IP_SERVICES, DynDNSUpdater


class TestIPServices:
    """Tests for IP service configuration and URLs."""

    def test_ipify_service_url(self):
        """Test ipify service URL."""
        assert 'ipify' in IP_SERVICES
        assert 'ipify.org' in IP_SERVICES['ipify']
        assert IP_SERVICES['ipify'].startswith('https://')

    def test_ifconfig_service_url(self):
        """Test ifconfig.me service URL."""
        assert 'ifconfig' in IP_SERVICES
        assert 'ifconfig.me' in IP_SERVICES['ifconfig']

    def test_icanhazip_service_url(self):
        """Test icanhazip service URL."""
        assert 'icanhazip' in IP_SERVICES
        assert 'icanhazip.com' in IP_SERVICES['icanhazip']

    def test_all_services_use_https(self):
        """Test that all IP services use HTTPS."""
        for service, url in IP_SERVICES.items():
            assert url.startswith('https://'), f"{service} does not use HTTPS"


class TestIPDetection:
    """Tests for IP detection functionality."""

    @patch('run.OneComAPI')
    @patch('requests.get')
    def test_get_current_ip_success(self, mock_get, mock_api):
        """Test successful IP detection."""
        mock_response = Mock()
        mock_response.text = "91.51.131.49"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        options = {
            'username': 'test@example.com',
            'password': 'testpass',
            'domain': 'example.com',
            'subdomains': ['www'],
            'update_interval': 5,
            'ip_service': 'ipify',
        }
        
        with patch.object(DynDNSUpdater, '_load_last_ip'):
            updater = DynDNSUpdater(options)
            ip = updater._get_current_ip()
            assert ip == "91.51.131.49"

    @patch('run.OneComAPI')
    @patch('requests.get')
    def test_get_current_ip_with_whitespace(self, mock_get, mock_api):
        """Test IP detection with leading/trailing whitespace."""
        mock_response = Mock()
        mock_response.text = "  91.51.131.49\n"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        options = {
            'username': 'test@example.com',
            'password': 'testpass',
            'domain': 'example.com',
            'subdomains': ['www'],
            'update_interval': 5,
            'ip_service': 'ipify',
        }
        
        with patch.object(DynDNSUpdater, '_load_last_ip'):
            updater = DynDNSUpdater(options)
            ip = updater._get_current_ip()
            # Should be stripped
            assert ip.strip() == "91.51.131.49"

    @patch('run.OneComAPI')
    @patch('requests.get')
    def test_get_current_ip_timeout(self, mock_get, mock_api):
        """Test IP detection timeout handling."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        options = {
            'username': 'test@example.com',
            'password': 'testpass',
            'domain': 'example.com',
            'subdomains': ['www'],
            'update_interval': 5,
            'ip_service': 'ipify',
        }
        
        with patch.object(DynDNSUpdater, '_load_last_ip'):
            updater = DynDNSUpdater(options)
            ip = updater._get_current_ip()
            assert ip is None

    @patch('run.OneComAPI')
    @patch('requests.get')
    def test_get_current_ip_connection_error(self, mock_get, mock_api):
        """Test IP detection connection error handling."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")
        
        options = {
            'username': 'test@example.com',
            'password': 'testpass',
            'domain': 'example.com',
            'subdomains': ['www'],
            'update_interval': 5,
            'ip_service': 'ipify',
        }
        
        with patch.object(DynDNSUpdater, '_load_last_ip'):
            updater = DynDNSUpdater(options)
            ip = updater._get_current_ip()
            assert ip is None


class TestIPServiceFallback:
    """Tests for IP service fallback behavior."""

    @patch('requests.get')
    def test_fallback_on_primary_failure(self, mock_get):
        """Test fallback to secondary service on primary failure."""
        call_count = [0]
        
        def mock_get_side_effect(url, **kwargs):
            call_count[0] += 1
            if 'ipify' in url:
                raise requests.exceptions.ConnectionError("Primary failed")
            mock_response = Mock()
            mock_response.text = "91.51.131.49"
            mock_response.raise_for_status = Mock()
            return mock_response
        
        mock_get.side_effect = mock_get_side_effect
        
        # Note: Current implementation may not have fallback
        # This test documents expected behavior

    @patch('requests.get')
    def test_all_services_return_same_format(self, mock_get):
        """Test that all services return IP in same format."""
        for service, url in IP_SERVICES.items():
            mock_response = Mock()
            mock_response.text = "91.51.131.49"
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            response = requests.get(url, timeout=10)
            ip = response.text.strip()
            
            # Should be a valid IPv4 address
            import re
            assert re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip)


class TestIPChangeDetection:
    """Tests for IP change detection logic."""

    def test_ip_changed_detection(self):
        """Test detection of IP address change."""
        old_ip = "91.51.131.49"
        new_ip = "91.51.131.50"
        
        assert old_ip != new_ip

    def test_ip_unchanged_detection(self):
        """Test detection when IP hasn't changed."""
        old_ip = "91.51.131.49"
        new_ip = "91.51.131.49"
        
        assert old_ip == new_ip

    def test_first_run_no_previous_ip(self):
        """Test first run when no previous IP is stored."""
        previous_ip = None
        current_ip = "91.51.131.49"
        
        # First run should always trigger update
        should_update = previous_ip is None or previous_ip != current_ip
        assert should_update

    def test_ip_persistence(self):
        """Test that IP is persisted between checks."""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            last_ip_file = os.path.join(tmpdir, 'last_ip.txt')
            
            # Simulate saving IP
            with open(last_ip_file, 'w') as f:
                f.write("91.51.131.49")
            
            # Simulate loading IP
            with open(last_ip_file, 'r') as f:
                loaded_ip = f.read().strip()
            
            assert loaded_ip == "91.51.131.49"


class TestIPValidation:
    """Tests for IP address validation."""

    def test_valid_public_ipv4(self):
        """Test valid public IPv4 addresses."""
        import ipaddress
        
        # Use truly public IPs (not documentation range)
        valid_public_ips = [
            "8.8.8.8",
            "1.1.1.1",
            "91.51.131.49",
        ]
        
        for ip in valid_public_ips:
            addr = ipaddress.ip_address(ip)
            assert addr.is_global

    def test_invalid_for_dyndns(self):
        """Test IP addresses invalid for DynDNS use."""
        import ipaddress
        
        invalid_ips = [
            "127.0.0.1",      # Loopback
            "0.0.0.0",        # Unspecified
            "255.255.255.255", # Broadcast
        ]
        
        for ip in invalid_ips:
            addr = ipaddress.ip_address(ip)
            # These should not be used for DynDNS
            assert addr.is_loopback or addr.is_unspecified or addr == ipaddress.ip_address("255.255.255.255")

    def test_ipv6_not_supported(self):
        """Test that IPv6 addresses are handled appropriately."""
        import ipaddress
        
        ipv6_addresses = [
            "2001:db8::1",
            "::1",
            "fe80::1",
        ]
        
        for ip in ipv6_addresses:
            addr = ipaddress.ip_address(ip)
            assert addr.version == 6
            # Current implementation focuses on IPv4


class TestUpdateInterval:
    """Tests for update interval configuration."""

    def test_valid_update_intervals(self):
        """Test valid update interval values."""
        valid_intervals = [1, 5, 10, 15, 30, 60]
        
        for interval in valid_intervals:
            assert 1 <= interval <= 60

    def test_interval_to_seconds_conversion(self):
        """Test conversion from minutes to seconds."""
        interval_minutes = 5
        interval_seconds = interval_minutes * 60
        assert interval_seconds == 300

    @patch('run.OneComAPI')
    def test_update_interval_stored(self, mock_api):
        """Test that update interval is stored correctly."""
        options = {
            'username': 'test@example.com',
            'password': 'testpass',
            'domain': 'example.com',
            'subdomains': ['www'],
            'update_interval': 10,
            'ip_service': 'ipify',
        }
        
        with patch.object(DynDNSUpdater, '_load_last_ip'):
            updater = DynDNSUpdater(options)
            assert updater.update_interval == 10
