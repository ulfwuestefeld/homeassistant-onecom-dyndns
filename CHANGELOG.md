# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.3] - 2026-02-06

### Changed

- **Add-on↔Integration Architecture**: Custom component now reads state from the
  add-on via a shared state file (`/config/.onecom_dyndns_state.json`) instead of
  independently polling IP services and updating DNS records.  This eliminates
  redundant network calls and ensures the entities always display the same data the
  add-on produces.
  - Add-on writes state file after every check cycle and SSL events
  - Add-on checks for command file every 5 seconds (button presses / service calls)
  - Coordinator in add-on mode polls the state file every 30 seconds
  - Standalone mode (without add-on) retains the original direct-polling behaviour
- Button presses (Update DNS, Check IP, Renew Certificate) now write a command file
  (`/config/.onecom_dyndns_commands.json`) that the add-on picks up and executes,
  instead of the integration performing the action itself

### Added

- **Integration Icon**: `icon.png` added to custom component directory so the
  integration displays the same icon as the add-on in the HA Integrations page
- `"after_dependencies": ["hassio"]` in `manifest.json` ensures the Supervisor
  creates the add-on device before the integration attaches entities to it
- `ADDON_STATE_FILE` and `ADDON_COMMAND_FILE` constants in `const.py`
- `DynDNSUpdater._write_state_file()` – writes current add-on state as JSON
- `DynDNSUpdater._check_commands()` – reads and executes commands from integration
- `OneComDynDNSCoordinator._async_read_addon_state()` – reads shared state file
- `OneComDynDNSCoordinator._write_command_sync()` – writes command for add-on
- `OneComDynDNSCoordinator._async_poll_directly()` – standalone-mode fallback
- **Extended Test Suite** (422 → 445 tests)
  - Tests for `_write_state_file()` (5 cases: JSON validity, FQDN subdomains,
    certificate info, write error handling, ip_changed flag)
  - Tests for `_check_commands()` (6 cases: no file, update_dns, check_ip,
    invalid JSON, unknown command, renew_certificate)
  - Tests for coordinator add-on mode (5 cases: mode detection, standalone fallback,
    reads state file, default on missing file, default on invalid JSON)
  - Tests for command file writing (3 cases: update_dns, renew_certificate,
    standalone no-write)
  - Tests for state/command file constants (2 cases)
  - Tests for update interval (2 cases: 30s add-on vs config standalone)

## [1.3.2] - 2026-02-06

### Added

- **Extended Test Suite** (378 → 422 tests)
  - Tests for `deploy_custom_component()` (10 cases: source missing, manifest missing,
    unreadable JSON, IOError, same version skip, fresh deploy, version upgrade,
    corrupted target manifest, copy failure, parent directory creation)
  - Tests for `publish_addon_discovery()` (8 cases: no token, success, API error,
    exception, data structure, correct URL, bearer auth, default values)
  - Tests for `get_device_info()` (4 cases: with addon_slug, without, default, empty)
  - Tests for config flow `async_step_hassio()` and `async_step_hassio_confirm()`
    (8 cases: valid domain, stores slug, empty domain abort, missing domain abort,
    creates entry, shows form, sets unique ID, extracts config)
  - Tests for `OneComDynDNSButton.async_press()` (3 cases: update_dns, check_ip,
    renew_certificate each call the correct coordinator method)
  - Tests for `ADDON_SLUG` and `CONF_ADDON_SLUG` constants
  - Tests for `main()` calling `deploy_custom_component` and `publish_addon_discovery`
    (4 cases incl. correct call order)
  - Tests for conditional `async_setup_entry` entity filtering (6 cases: sensor,
    binary_sensor, button platforms each with SSL enabled/disabled)

### Changed

- Updated existing `main()` tests with required mocks for `deploy_custom_component`
  and `publish_addon_discovery`

## [1.3.1] - 2026-02-06

### Added

- **New Entity Types**
  - `acme_challenge` sensor entity – Displays current ACME DNS-01 challenge TXT value
    (entity_category: DIAGNOSTIC, disabled by default)
  - `button.update_dns` – Button to trigger DNS update from UI
  - `button.check_ip` – Button to trigger IP check from UI
  - `button.renew_certificate` – Button to trigger certificate renewal (SSL-only)
  - All buttons are entity_category: CONFIG and appear on the device page

- **Entity Metadata**
  - `entity_category=DIAGNOSTIC` for `last_update` and `acme_challenge` sensors
  - `entity_category=CONFIG` for all button entities
  - `entity_registry_enabled_default=False` for `acme_challenge` (rarely needed)
  - `button` platform added to PLATFORMS constant

- **Coordinator Enhancements**
  - `set_acme_challenge()` / `clear_acme_challenge()` methods for ACME challenge lifecycle
  - `acme_challenge` data included in coordinator update cycle

- **Extended Test Suite** (346 → 378 tests)
  - Tests for `acme_challenge` sensor (native_value, attributes, null handling)
  - Tests for entity_category on diagnostic and primary sensors
  - Tests for binary sensors (dns_status, certificate_valid)
  - Tests for button entity types, methods, and SSL-conditional creation
  - Tests for coordinator ACME challenge set/clear
  - Tests for PLATFORMS and ATTR_ACME_CHALLENGE constants

- **Auto-Deployment of Custom Component**
  - Add-on automatically deploys `custom_components/onecom_dyndns/` to `/config/custom_components/`
    at startup – no manual file copying required
  - Version-aware: only overwrites when the bundled version differs from the installed version
  - Dockerfile now bundles the custom component into the Docker image

- **Supervisor Discovery & Auto-Configuration**
  - Add-on publishes discovery via Supervisor API (`POST /discovery`) at startup
  - New `async_step_hassio()` in config flow handles automatic integration setup
  - Confirmation dialog ("Add-on detected – create entities?") in English and German
  - Add-on slug stored in config entry for device attachment

- **Supervisor Device Attachment**
  - Integration entities now attach to the existing Supervisor add-on device
    (`identifiers={("hassio", "homeassistant-onecom-dyndns")}`)
  - Sensors, binary sensors and buttons appear directly on the "One.com DynDNS Updater" device
  - Shared `get_device_info()` helper in `const.py`; falls back to standalone device
    when the integration is used without the add-on

### Changed

- **Custom component (1.2.0 → 1.3.3)**
  - SENSOR_TYPES extended from 5 to 6 (+ acme_challenge)
  - ssl_only_sensors set now includes acme_challenge
  - Updated English, German translations and strings.json for new entities
  - `DeviceInfo` import removed from sensor.py, binary_sensor.py, button.py (now via `get_device_info`)

## [1.3.0] - 2026-02-06

### Added

- **New Sensors**
  - `sensor.onecom_dyndns_last_ip_update` – Timestamp of last IP change / DNS update
  - `sensor.onecom_dyndns_last_certificate_renewal` – Timestamp of last certificate renewal
  - Custom component: `last_ip_update` and `last_certificate_renewal` sensor entities
  - All new sensors include extra state attributes (domain, current_ip, certificate_expiry, etc.)
  - SSL-related sensors are only created when SSL is enabled

- **Sensor Test Suite** (`test_sensors.py`)
  - 45 tests covering all 5 sensor types (custom component + add-on)
  - Tests for native_value, extra_state_attributes, SSL-conditional creation
  - Tests for add-on sensor update methods and event-driven flows

### Changed

- **Performance: Reduced CPU usage and memory footprint**
  - Replaced `time.sleep(1)` polling loop with `threading.Event.wait()` in main loop
    (300 syscalls/cycle → 1 syscall; instant graceful shutdown)
  - Replaced `time.sleep(60)` polling loop with `threading.Event.wait()` in certificate renewal loop
    (720 syscalls/12h-cycle → 1 syscall)
  - DNS records fetched once per `update_all_subdomains` call instead of N times (1 API call vs N)
  - SSL context created once and reused across all domain verifications
  - Debug-level log messages converted to lazy `%s` formatting (no string allocation when disabled)

- **Import cleanup**
  - Removed unused `from pathlib import Path` (certificate_manager.py, acme_manager.py)
  - Removed redundant `from datetime import timezone` inside method body
  - Moved `import traceback` from function-level to module-level (acme_manager.py)

- **Custom component (1.1.0 → 1.2.0)**
  - Coordinator now correctly populates `last_update` timestamp (was broken / always None)
  - Coordinator tracks `last_ip_update` and `last_certificate_renewal` timestamps
  - New constants `ATTR_LAST_IP_UPDATE`, `ATTR_LAST_CERTIFICATE_RENEWAL`
  - Updated English and German translations for new sensor entities

### Fixed

- `last_update` sensor in custom component coordinator was never populated (always None)

## [1.2.21] - 2026-01-30

### Added

- **Extended Test Suite**
  - `test_main_function.py` - Tests for main() entry point and signal handlers
  - `test_retry_decorator.py` - Tests for retry_with_backoff decorator
  - `test_dns_operations.py` - Tests for DNS record operations
  - `test_ip_services.py` - Tests for IP detection services
  - `test_ssl_certificates.py` - Tests for SSL certificate operations

## [1.2.19] - 2026-01-30

### Added

- **GitHub Actions CI/CD Pipeline**
  - Automated testing on every push and pull request
  - Code coverage reporting with Codecov integration
  - Linting with flake8 for code quality checks
  - Test artifacts (coverage reports) uploaded for 30 days

## [1.2.18] - 2026-01-30

### Added

- **Comprehensive Test Suite**
  - Unit tests for all modules (OneComAPI, ACMEManager, CertificateManager, run.py)
  - End-to-End (E2E) tests for complete workflows
  - Integration tests for component interactions
  - Security tests for credential handling
  - Edge case tests for boundary conditions
  - Error handling tests for recovery scenarios
  - ~200+ tests across 13 test files

- **Software Bill of Materials (SBOM)**
  - `sbom.json` in CycloneDX 1.5 format
  - `SBOM.md` human-readable version
  - Complete dependency inventory

- **Test Documentation**
  - `Test.md` with bilingual instructions (English/German)
  - Installation guide for test prerequisites
  - Test execution commands and examples

### Changed

- Updated `.cursorrules` with correct project information (Python, not C#)
- Enhanced router configuration documentation with port forwarding warning
- Added troubleshooting for `ERR_SSL_PROTOCOL_ERROR` (port 443→8123 issue)

## [1.2.17] - 2026-01-30

### Fixed

- Fixed ACME poll error: `'tuple' object has no attribute 'body'`
- `client.poll()` returns `(authz, response)` tuple in acme 2.x
- Added compatibility handling for both old and new return types

## [1.2.16] - 2026-01-30

### Fixed

- Fixed ACME challenge error: `'DNS01' object has no attribute 'uri'`
- Now passing full `ChallengeBody` to `answer_challenge()` instead of just `.chall`
- Compatible with modern acme library versions

## [1.2.15] - 2026-01-30

### Fixed

- Fixed ACME record cleanup: Now finds all records starting with `_acme-challenge`
  (including `_acme-challenge.homeassistant` for subdomains)
- Added handling for "record already exists" conflict error from One.com API
- Improved TXT record creation: If record exists with same content, treat as success
- If record exists with different content, automatically delete and recreate

## [1.2.14] - 2026-01-30

### Fixed

- Fixed explicit ttl=60 in acme_manager.py that overrode the default
- TTL now correctly set to 600 seconds for ACME challenge TXT records

## [1.2.13] - 2026-01-30

### Fixed

- Fixed DNS TXT record TTL: One.com requires minimum 600 seconds
- Changed default TTL from 60 to 600 seconds
- Updated TTL in all onecom_api.py copies

## [1.2.11] - 2026-01-30

### Fixed

- Fixed "No Key ID in JWS header" error completely
- All ACME operations now use `self._client` with registered account
- Removed redundant `_get_client()` calls that created unregistered clients

## [1.2.10] - 2026-01-30

### Fixed

- Fixed "No Key ID in JWS header" error
- Registration is now correctly set on existing client via `net.account`
- Avoid recreating client after registration to preserve Key ID

## [1.2.9] - 2026-01-30

### Fixed

- Fixed ACME ClientV2 initialization for acme library 2.x
- Registration is now passed via ClientNetwork's `account` parameter

## [1.2.8] - 2026-01-30

### Added

- **Intelligent retry mechanism with exponential backoff**
  - Automatically retries on network timeouts and connection errors
  - Up to 5 retries with exponential backoff (2s, 4s, 8s, 16s, 32s)
  - Random jitter to prevent thundering herd
  - Clear logging of retry attempts

## [1.2.6] - 2026-01-30

### Fixed

- Fixed ConflictError handling for existing ACME accounts
- Properly extract account URI from ConflictError exception
- Account registration now works correctly for both new and existing accounts

## [1.2.4] - 2026-01-30

### Fixed

- Fixed "No Key ID in JWS header" error by properly updating ACME client with registration
- Client now uses account URI (Key ID) for authenticated requests after registration
- Simplified account registration flow

## [1.2.3] - 2026-01-30

### Fixed

- Fixed ACME account retrieval when account already exists
- Added fallback for `only_return_existing` flag in account registration
- Improved error handling for existing Let's Encrypt accounts

## [1.2.2] - 2026-01-30

### Added

- Home Assistant notification when SSL certificate is renewed
- Reminder to restart NGINX after certificate update

### Fixed

- Improved SUPERVISOR_TOKEN detection with multiple fallback methods
- Added token file detection for s6 container environments
- Enhanced debug logging to show available environment variables and token files
- Added detailed logging for certificate file saving (size, timestamp)

## [1.2.1] - 2026-01-30

### Added

- **Documentation: NGINX SSL Proxy Integration**
  - Step-by-step guide for using certificates with NGINX Home Assistant SSL proxy
  - Enables HTTP (Port 80) and HTTPS (Port 443) simultaneously
  - Includes Home Assistant configuration and router setup instructions

## [1.2.0] - 2026-01-30

### Added

- **Home Assistant Sensors**
  - `sensor.onecom_dyndns_ip` - Current public IP address
  - `sensor.onecom_dyndns_dns_status` - DNS update status
  - `sensor.onecom_dyndns_certificate` - SSL certificate expiry date
  - `sensor.onecom_dyndns_acme_challenge` - Current ACME challenge value

### Fixed

- Improved SUPERVISOR_TOKEN detection (now checks both SUPERVISOR_TOKEN and HASSIO_TOKEN)
- Added debug logging for environment variables when token is not found

## [1.1.0] - 2026-01-30

### Added

- **Automatic SSL certificate generation via Let's Encrypt**
  - DNS-01 challenge support using One.com DNS API
  - TXT record creation/deletion for ACME challenges
  - Automatic certificate renewal (configurable days before expiry)
  - Staging mode for testing without hitting rate limits
  - DNS propagation waiting with Google DNS verification
  - New configuration options: `ssl_enabled`, `ssl_email`, `ssl_domains`, `ssl_staging`, `ssl_renewal_days`, `ssl_check_interval`

- **Online certificate verification**
  - Periodic validation that certificates are active on configured domains
  - Checks server reachability, certificate validity, and domain coverage
  - Automatic notifications when online certificates are invalid
  - Support for wildcard certificate detection

- **Force certificate renewal option**
  - New `ssl_force_renewal` configuration option
  - Forces renewal even if current certificate is still valid
  - Useful when adding new domains to an existing certificate

- **ACME Challenge Notification**
  - Displays TXT record name and value in Home Assistant notifications
  - Saves challenge info to `/data/acme_challenge.json`
  - Helps with manual DNS configuration if automatic creation fails

- **Home Assistant Sensors**
  - `sensor.onecom_dyndns_ip` - Current public IP address
  - `sensor.onecom_dyndns_dns_status` - DNS update status
  - `sensor.onecom_dyndns_certificate` - SSL certificate expiry date
  - `sensor.onecom_dyndns_acme_challenge` - Current ACME challenge value

- **Home Assistant Custom Integration with Config Flow**
  - Step-by-step setup wizard with credential validation
  - Automatic domain and subdomain detection from One.com account
  - Options flow for runtime configuration changes
  - Sensor entities: Current IP, Last update, Certificate expiry
  - Binary sensor entities: DNS status, Certificate validity
  - Services: `update_dns`, `renew_certificate`, `check_ip`
  - German and English UI translations

### Fixed

- Login compatibility with One.com's Keycloak authentication
  - HTML entity decoding for OAuth URLs (`&amp;` → `&`)
  - Browser-like headers for Keycloak compatibility
  - Improved error messages for login failures
- Support for both `dns_service_records` and `dns_custom_records` types
- ACME challenge TXT record creation for subdomains (e.g., `_acme-challenge.homeassistant`)
- TXT record creation using correct `dns_custom_records` type
- Cryptography deprecation warnings (UTC-aware datetime)
- Enhanced debug logging for troubleshooting

### Changed

- Added `ssl:rw` mapping for certificate storage
- Extended One.com API with TXT record management

### Dependencies

- Added `acme`, `josepy`, `cryptography` for SSL support

## [0.0.1] - 2026-01-28

### Added

- Initial release
- One.com DNS A record updating
- Support for multiple subdomains
- Automatic IP change detection
- Configurable update interval (1-60 minutes)
- Multiple IP detection services (ipify, ifconfig, icanhazip)
- German and English translations
- Detailed logging with configurable log levels
- Graceful shutdown handling

### Security

- Password field uses secure input type
- Session-based authentication with One.com
