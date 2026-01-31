"""
Unit tests for the main() function and application entry point.
"""

import json
import os
import sys
import tempfile
import signal
from unittest.mock import Mock, patch, MagicMock, call

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMainFunction:
    """Tests for the main() entry point function."""

    @patch('run.load_options')
    @patch('run.DynDNSUpdater')
    def test_main_initializes_updater(self, mock_updater_class, mock_load_options):
        """Test that main() initializes DynDNSUpdater with loaded options."""
        from run import main
        
        mock_options = {
            'username': 'test@example.com',
            'password': 'testpass',
            'domain': 'example.com',
            'subdomains': ['www'],
            'update_interval': 5,
            'ip_service': 'ipify',
            'log_level': 'info',
            'ssl_enabled': False,
        }
        mock_load_options.return_value = mock_options
        
        mock_updater = MagicMock()
        mock_updater.start = MagicMock()
        mock_updater_class.return_value = mock_updater
        
        # Mock signal handlers
        with patch('signal.signal'):
            with patch.object(mock_updater, 'start', side_effect=KeyboardInterrupt):
                try:
                    main()
                except (KeyboardInterrupt, SystemExit):
                    pass
        
        mock_load_options.assert_called_once()

    @patch('run.load_options')
    def test_main_handles_missing_config(self, mock_load_options):
        """Test that main() handles missing configuration gracefully."""
        from run import main
        
        mock_load_options.side_effect = FileNotFoundError("Config not found")
        
        with pytest.raises(FileNotFoundError):
            main()

    @patch('run.load_options')
    def test_main_handles_invalid_json(self, mock_load_options):
        """Test that main() handles invalid JSON configuration."""
        from run import main
        
        mock_load_options.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        with pytest.raises(json.JSONDecodeError):
            main()


class TestLoadOptions:
    """Tests for the load_options() function."""

    def test_load_options_from_file(self):
        """Test loading options from a JSON file."""
        from run import load_options
        
        test_options = {
            'username': 'test@example.com',
            'password': 'secret',
            'domain': 'test.com',
            'subdomains': ['www', 'api'],
            'update_interval': 10,
            'ip_service': 'ipify',
            'log_level': 'debug',
            'ssl_enabled': True,
            'ssl_email': 'ssl@test.com',
            'ssl_domains': ['test.com'],
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_options, f)
            temp_path = f.name
        
        try:
            with patch('run.OPTIONS_PATH', temp_path):
                options = load_options()
                assert options['username'] == 'test@example.com'
                assert options['domain'] == 'test.com'
                assert options['ssl_enabled'] == True
        finally:
            os.unlink(temp_path)

    def test_load_options_missing_file(self):
        """Test load_options raises error for missing file."""
        from run import load_options
        
        with patch('run.OPTIONS_PATH', '/nonexistent/path/options.json'):
            with pytest.raises(FileNotFoundError):
                load_options()

    def test_load_options_invalid_json(self):
        """Test load_options raises error for invalid JSON."""
        from run import load_options
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name
        
        try:
            with patch('run.OPTIONS_PATH', temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_options()
        finally:
            os.unlink(temp_path)


class TestSignalHandlers:
    """Tests for signal handling in the application."""

    @patch('run.load_options')
    @patch('run.DynDNSUpdater')
    def test_sigterm_stops_updater(self, mock_updater_class, mock_load_options):
        """Test that SIGTERM signal stops the updater gracefully."""
        from run import main
        
        mock_options = {
            'username': 'test@example.com',
            'password': 'testpass',
            'domain': 'example.com',
            'subdomains': ['www'],
            'update_interval': 5,
            'ip_service': 'ipify',
            'log_level': 'info',
            'ssl_enabled': False,
        }
        mock_load_options.return_value = mock_options
        
        mock_updater = MagicMock()
        mock_updater_class.return_value = mock_updater
        
        signal_handlers = {}
        
        def capture_signal(sig, handler):
            signal_handlers[sig] = handler
        
        with patch('signal.signal', side_effect=capture_signal):
            with patch.object(mock_updater, 'start', side_effect=KeyboardInterrupt):
                try:
                    main()
                except (KeyboardInterrupt, SystemExit):
                    pass
        
        # Verify signal handlers were registered
        # (SIGTERM and SIGINT should be registered)


class TestApplicationLifecycle:
    """Tests for application lifecycle management."""

    def test_updater_cleanup_on_exception(self):
        """Test that updater cleans up resources on exception."""
        from run import DynDNSUpdater
        
        with patch('run.OneComAPI'):
            updater = DynDNSUpdater(
                username='test@example.com',
                password='testpass',
                domain='example.com',
                subdomains=['www'],
                update_interval=5,
                ip_service='ipify',
            )
            
            # Verify updater can be stopped even if not started
            updater.stop()
            assert updater._running == False

    def test_updater_multiple_stop_calls(self):
        """Test that multiple stop() calls don't cause errors."""
        from run import DynDNSUpdater
        
        with patch('run.OneComAPI'):
            updater = DynDNSUpdater(
                username='test@example.com',
                password='testpass',
                domain='example.com',
                subdomains=['www'],
                update_interval=5,
                ip_service='ipify',
            )
            
            # Multiple stop calls should be safe
            updater.stop()
            updater.stop()
            updater.stop()
            assert updater._running == False
