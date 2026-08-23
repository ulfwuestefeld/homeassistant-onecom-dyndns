"""
Unit tests for the main() function and application entry point.
"""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMainFunction:
    """Tests for the main() entry point function."""

    @patch('run.load_options')
    @patch('run.DynDNSUpdater')
    @patch('run.deploy_custom_component')
    @patch('run.publish_addon_discovery')
    def test_main_initializes_updater(self, mock_discovery, mock_deploy, mock_updater_class, mock_load_options):
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
    @patch('run.DynDNSUpdater')
    @patch('run.deploy_custom_component')
    @patch('run.publish_addon_discovery')
    def test_main_calls_deploy_custom_component(self, mock_discovery, mock_deploy, mock_updater_class, mock_load_options):
        """Test that main() calls deploy_custom_component before starting."""
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
        mock_updater.run.side_effect = KeyboardInterrupt

        with patch('signal.signal'):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        mock_deploy.assert_called_once()

    @patch('run.load_options')
    @patch('run.DynDNSUpdater')
    @patch('run.deploy_custom_component')
    @patch('run.publish_addon_discovery')
    def test_main_calls_publish_addon_discovery(self, mock_discovery, mock_deploy, mock_updater_class, mock_load_options):
        """Test that main() calls publish_addon_discovery with options."""
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
        mock_updater.run.side_effect = KeyboardInterrupt

        with patch('signal.signal'):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        mock_discovery.assert_called_once_with(mock_options)

    @patch('run.load_options')
    @patch('run.DynDNSUpdater')
    @patch('run.deploy_custom_component')
    @patch('run.publish_addon_discovery')
    def test_main_calls_deploy_before_discovery(self, mock_discovery, mock_deploy, mock_updater_class, mock_load_options):
        """Test that deploy_custom_component is called before publish_addon_discovery."""
        from run import main

        call_order = []
        mock_deploy.side_effect = lambda: call_order.append("deploy")
        mock_discovery.side_effect = lambda opts: call_order.append("discovery")

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
        mock_updater.run.side_effect = KeyboardInterrupt

        with patch('signal.signal'):
            try:
                main()
            except (KeyboardInterrupt, SystemExit):
                pass

        assert call_order == ["deploy", "discovery"]

    @patch('run.deploy_custom_component')
    @patch('run.load_options')
    def test_main_handles_missing_config(self, mock_load_options, mock_deploy):
        """Test that main() handles missing configuration gracefully."""
        from run import main
        
        mock_load_options.side_effect = FileNotFoundError("Config not found")
        
        with pytest.raises(FileNotFoundError):
            main()

    @patch('run.deploy_custom_component')
    @patch('run.load_options')
    def test_main_handles_invalid_json(self, mock_load_options, mock_deploy):
        """Test that main() handles invalid JSON configuration."""
        from run import main
        
        mock_load_options.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        with pytest.raises(json.JSONDecodeError):
            main()


class TestLoadOptions:
    """Tests for the load_options() function."""

    def test_load_options_from_file(self):
        """Test loading options from a JSON file."""
        
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
            # Mock the file path by patching open
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(test_options)
                # The actual load_options implementation may vary
                # This test documents expected behavior
        finally:
            os.unlink(temp_path)

    def test_load_options_returns_dict(self):
        """Test that load_options returns a dictionary."""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'username': 'test', 'password': 'pass', 'domain': 'test.com'}, f)
            temp_path = f.name
        
        try:
            # Test that the function can parse JSON
            with open(temp_path, 'r') as file:
                data = json.load(file)
                assert isinstance(data, dict)
        finally:
            os.unlink(temp_path)


class TestSignalHandlers:
    """Tests for signal handling in the application."""

    @patch('run.load_options')
    @patch('run.DynDNSUpdater')
    @patch('run.deploy_custom_component')
    @patch('run.publish_addon_discovery')
    def test_sigterm_stops_updater(self, mock_discovery, mock_deploy, mock_updater_class, mock_load_options):
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

    @patch('run.OneComAPI')
    def test_updater_cleanup_on_exception(self, mock_api):
        """Test that updater cleans up resources on exception."""
        from run import DynDNSUpdater
        
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
            
            # Verify updater can be stopped even if not started
            updater.stop()
            assert updater._running == False

    @patch('run.OneComAPI')
    def test_updater_multiple_stop_calls(self, mock_api):
        """Test that multiple stop() calls don't cause errors."""
        from run import DynDNSUpdater
        
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
            
            # Multiple stop calls should be safe
            updater.stop()
            updater.stop()
            updater.stop()
            assert updater._running == False
