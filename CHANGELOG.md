# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.3] - 2026-06-03

### Fixed

- **Discovery info**: fixed deprecated discovery_info.get by discovery_info.config

## [1.4.2] - 2026-06-03

### Fixed

- **Deprecated architectures**: Removed deprecated 32-bit architecture support
  (`armhf`, `armv7`, `i386`) from `build.yaml`. Only actively supported
  architectures (`aarch64` and `amd64`) are now built.
- **F821 undefined name 'DeviceInfo'**: Added `TYPE_CHECKING` import guard
  in `const.py` to fix flake8 F821 error. The `DeviceInfo` type is now
  properly guarded for type checking without causing runtime import errors.

### Changed

- **GitHub Actions**: Removed `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` environment
  variable. GitHub Actions will naturally handle the Node.js 20 → 24 migration
  without explicit forcing. Latest patches of v4/v5 actions support Node.js 24.

## [1.4.1] - 2026-02-08

### Added

- **Reauth flow**: When One.com credentials expire or become invalid, the
  integration now raises `ConfigEntryAuthFailed` and shows a re-authentication
  dialog instead of silently failing.
- **Reconfigure flow**: Users can change domain and subdomain settings without
  deleting and recreating the config entry.
- **Diagnostics support**: New `diagnostics.py` enables the "Download
  diagnostics" button in the HA UI. Sensitive data (passwords, keys, tokens)
  is automatically redacted.
- **`data_description` for Options flow**: Help text is now shown below each
  field in the Options flow for both English and German.
- **`no_domain` abort reason**: Supervisor discovery now shows a proper message
  instead of a raw key when the add-on provides no domain.
- **`reauth_successful` / `reconfigure_successful` abort reasons** with
  `[%key:...]` references to HA common strings.
- **New test files**: `test_config_flow.py` (13 tests covering user/domain/
  options/hassio/reauth flows) and `test_init.py` (8 tests covering setup,
  unload, services, options reload).

### Fixed

- **P0 -- Options flow bug**: The coordinator now reads configurable values
  (`update_interval`, `ip_service`, `ssl_enabled`, etc.) from `entry.options`
  with fallback to `entry.data`. Previously, changes made through the Options
  flow were silently ignored.
- **P0 -- Missing API methods**: `update_all_subdomains()`,
  `_update_dns_record_with_cache()`, `find_txt_records()`,
  `cleanup_acme_records()`, and `wait_for_dns_propagation()` were present in
  the root `onecom_api.py` but missing from the custom component copy.
  Standalone DNS batch updates crashed with `AttributeError`.
- **P0 -- No HTTP timeouts**: The custom component API client had no timeouts
  on any HTTP request. Added `REQUEST_TIMEOUT = 30` on all `session.get/post/
  patch/delete` calls.
- **P1 -- `asyncio.get_event_loop()`**: Replaced with
  `asyncio.get_running_loop()` in `async_validate_credentials()` for Python
  3.14 compatibility.
- **P1 -- `datetime.fromisoformat()` crash**: Added `try/except ValueError`
  around all datetime parsing in `sensor.py` via `_safe_parse_datetime()`.
- **P1 -- False-positive certificate problem**: `binary_sensor.py` now returns
  `None` (unknown) instead of `True` (problem) when no certificate info is
  available at startup.
- **P1 -- Wrong TXT record type**: `create_txt_record()` now uses
  `dns_custom_records` (matching the root version) instead of
  `dns_service_records`.
- **P1 -- Supervisor device metadata overwrite**: `get_device_info()` in
  add-on mode now only sets `identifiers` and no longer overwrites the
  Supervisor's own `name`/`manufacturer`/`model`.
- **Weak test assertion**: `test_run.py` `test_returns_empty_when_no_token`
  now asserts `token == ""` instead of the always-true
  `token == "" or isinstance(token, str)`.
- **CI -- `PermissionError` on ACMEManager init**: `_ensure_directories()` was
  called eagerly in `ACMEManager.__init__`, trying to create `/data/acme/` even
  in test environments. Directory creation is now lazy (deferred to first file
  operation) with a `_directories_created` guard flag, preventing
  `PermissionError` on CI runners and restricted environments.

### Changed

- **`const.py` modernised**: `CONF_USERNAME`, `CONF_PASSWORD`, `CONF_DOMAIN`
  are now re-exported from `homeassistant.const`. `PLATFORMS` uses
  `Platform.SENSOR` etc. instead of string literals. Dead constant
  `UPDATE_INTERVAL_SECONDS` removed.
- **`config_flow.py` modernised**: `FlowResult` replaced by
  `ConfigFlowResult`. Added `MINOR_VERSION = 1`. Removed redundant
  `OptionsFlowHandler.__init__`. Options flow now shows current values from
  merged `data | options`.
- **`manifest.json` cleaned up**: Core dependencies `requests` and
  `cryptography` removed (always available in HA). Versions pinned
  (`acme==2.9.0`, `josepy==1.14.0`). Added `homeassistant` minimum version
  `2024.12.0`.
- **`__init__.py` improved**: Added `config_entry=entry` kwarg to coordinator.
  Temp file path uses `pathlib` instead of string concatenation. Unused loop
  variables replaced with `_`.
- **Entity cleanup**: Removed unused `self._entry` attribute, redundant
  `_handle_coordinator_update` overrides, and unused imports across
  `sensor.py`, `binary_sensor.py`, `button.py`. Hardcoded `"ssl_enabled"`
  replaced with `CONF_SSL_ENABLED` constant. Type hints added to coordinator
  parameters.
- **`strings.json`**: Standard error/abort strings now use `[%key:...]`
  references. Added `reauth_confirm`, `reconfigure`, and `no_domain` entries.
- **`de.json` typo fixed**: "Zertifikat Ablauf" → "Zertifikatsablauf".
- **`en.json` synchronised** with `strings.json` changes.
- **`button.py` error handling**: `async_press()` now checks for method
  existence and logs/re-raises exceptions.
- **`onecom_api.py` HTML decoding**: Manual `&amp;`/`&lt;`/`&gt;` replacement
  replaced with `html.unescape()`.
- **Test stubs updated**: HA stubs in `test_sensors.py` extended with
  `ConfigFlowResult`, `ConfigEntryAuthFailed`, standard HA constants, and
  `entry.options = {}` on all mock entries.

## [1.3.8] - 2026-02-07

### Changed

- **Performance: Persistent HTTP session** for IP detection and HA API calls.
  `DynDNSUpdater` now creates a `requests.Session` (`_http_session`) at init and
  reuses it across all `get_public_ip()` calls, eliminating redundant TCP + TLS
  handshakes on every check cycle. Session is properly closed on `stop()`.
- **Performance: DNS propagation uses session** – `wait_for_dns_propagation()`
  in `onecom_api.py` now uses `self.session` (the already-authenticated session)
  for DNS-over-HTTPS checks instead of creating bare `requests.get()` calls.
- **Performance: Certificate info caching** – `CertificateManager.get_certificate_info()`
  caches the parsed certificate data in memory (`_cached_cert_info`) and only
  re-reads from disk when a new certificate is issued, avoiding repeated x509
  decoding on every state file write.
- **Performance: ACME account key caching** – `ACMEManager._get_client()` now
  caches the RSA account key in `_account_key` after first load, avoiding
  redundant disk reads on subsequent certificate requests.
- **Performance: State file mtime caching** – `OneComDynDNSCoordinator._read_state_file_sync()`
  only rereads and JSON-parses the state file when its `st_mtime` has changed,
  reducing unnecessary I/O and CPU on every coordinator update cycle.
- **Performance: ACME challenge in-memory caching** – `DynDNSUpdater` caches
  the current ACME challenge in `_current_acme_challenge` and reads from memory
  in `_write_state_file()` instead of re-reading the challenge file from disk.
- **Performance: Standalone mode batch DNS update** – `_async_update_dns()` in
  the custom component now uses `api.update_all_subdomains()` (single API call)
  instead of per-subdomain `update_dns_record()` calls.
- **Performance: Lazy single `_ensure_directories()` call** – `CertificateManager`
  and `ACMEManager` now use a `_directories_created` flag so filesystem
  `mkdir -p` operations run only once (on first use) instead of on every
  status save. Directories are created lazily on the first file operation,
  not at construction time.

### Fixed

- **Stability: Request timeouts** – Added `REQUEST_TIMEOUT = 30` constant to
  `OneComAPI` and applied `timeout=30` to every `session.get`, `.post`, `.patch`,
  and `.delete` call. Previously, requests could hang indefinitely if the
  One.com server was unresponsive.
- **Stability: Session leak in `update_dns()`** – Wrapped `api.login()` and
  `api.update_all_subdomains()` in a `try/finally` block to guarantee
  `api.logout()` is called even when exceptions occur (both in `run.py` and
  `custom_components/__init__.py`).
- **Stability: Interruptible retry backoff** – `retry_with_backoff` decorator
  in `acme_manager.py` now uses `_stop_event.wait()` instead of `time.sleep()`
  for delays, so retries abort immediately on graceful shutdown.
- **Stability: `CertificateManager` restartable** – `start()` now clears the
  `_stop_event`, allowing the manager to be stopped and restarted without
  creating a new instance.
- **Tests: Mock targets updated** – All tests that mocked `run.requests.get` or
  `onecom_api.requests.get` now mock the correct session-based `.get()` methods
  (`updater._http_session.get`, `api.session.get`), ensuring tests exercise the
  real code paths. Fixed 475 tests across 17 test files.

## [1.3.7] - 2026-02-07

### Changed

- **CI: Python version updated** from 3.11 to **3.12 + 3.13** in the test matrix,
  matching the current Home Assistant Core requirement (Python 3.13 since HA 2024.12).
  Lint job also updated from Python 3.11 to 3.13.
  Coverage artifacts now include the Python version in their name for matrix uniqueness.

### Fixed

- **Add-on device naming**: `get_device_info()` now provides `name`, `manufacturer`,
  `model`, and `configuration_url` even in add-on mode. Previously only `identifiers`
  were set, causing an "Unnamed Device" in the HA UI when the Supervisor device was
  not yet created.
- **Orphaned standalone device cleanup**: New `_async_remove_standalone_device()` in
  `__init__.py` automatically removes the old standalone device
  (`identifiers={(DOMAIN, entry_id)}`) when the integration switches to add-on mode,
  preventing duplicate devices in the UI.

## [1.3.6] - 2026-02-07

### Added

- **`discovery` field in `config.yaml`**: Declares `onecom_dyndns` as a discovered
  integration, aligning with Home Assistant add-on best practices
- **GitHub Templates**: Bug report, feature request, and pull request templates
  in `.github/` for better contributor guidance
- **Architecture section in README.md**: Documents the state/command file mechanism,
  discovery retry logic, and add-on ↔ integration communication flow
- **Entity list in README.md features**: Sensors, binary sensors, and buttons now
  listed in the Features section
- **DOCS.md: Add-on Mode vs. Standalone Mode**: Clear comparison of both modes with
  data source, button behaviour, device attachment, and configuration differences
- **DOCS.md: State File Format**: Full JSON structure documentation for
  `/config/.onecom_dyndns_state.json`
- **DOCS.md: Command File Format**: JSON structure and supported commands for
  `/config/.onecom_dyndns_commands.json`
- **DOCS.md: Button Behaviour table**: Shows how each button works in add-on vs.
  standalone mode

### Fixed

- **ACMEManager graceful shutdown**: Added `stop_event` parameter to `ACMEManager.__init__`
  and a `stop()` method. `CertificateManager` now shares its `_stop_event` with
  `ACMEManager`, so `CertificateManager.stop()` interrupts in-progress DNS propagation
  waits and challenge polling loops immediately. Previously the event was never set,
  so `wait()` calls always timed out instead of allowing graceful interruption.
  Also replaced the non-interruptible `time.sleep(5)` safety wait with
  `self._stop_event.wait(timeout=5)`.

### Changed

- **Cursor Rules** extended with 2 new rule files and updates to 4 existing ones:
  - `python-standards.mdc`: Error handling patterns (specific exceptions, traceback
    logging, `@retry_with_backoff`, credential safety)
  - `quality-checklist.mdc`: Detailed version bump process listing all 5 files to update
  - `ha-integration.mdc`: Workflows for adding sensors, buttons, services; translation
    management (two systems documented)
  - `project-overview.mdc`: Build & deployment conventions (Docker, architectures, CI)
  - New `file-structure.mdc`: Directory layout and naming conventions
  - New `security.mdc`: Credential handling, API security, file permissions, network security

## [1.3.5] - 2026-02-07

### Changed

- **Lazy Log Formatting**: Converted all 111 f-string logging calls across 5 source
  files (`run.py`, `acme_manager.py`, `certificate_manager.py`, `onecom_api.py`,
  `custom_components/.../onecom_api.py`) to lazy `%s`-formatting. Arguments are only
  interpolated when the log level is active, reducing unnecessary string allocations.
- **Interruptible Polling Loops**: Replaced `time.sleep()` with `threading.Event.wait()`
  in the ACME authorization polling loop (`acme_manager.py`) and DNS propagation
  polling loop (`onecom_api.py`), enabling graceful shutdown during long waits.
- **`typing.Final` for Constants**: Added `Final` annotation to `SENSOR_TYPES`,
  `BINARY_SENSOR_TYPES`, and `BUTTON_TYPES` in the custom component entity modules.
- **`from __future__ import annotations`**: Added to `custom_components/.../onecom_api.py`
  for consistency with all other component files.
- **Consistent Config Flow Entry Titles**: Manual setup via `async_step_options()` and
  `async_step_ssl()` now produces entry titles "One.com DynDNS Updater - {domain}"
  matching the auto-discovery path.
- **Cursor Rules Migration**: Replaced monolithic `.cursorrules` with 5 focused
  `.cursor/rules/*.mdc` files (project-overview, python-standards, testing,
  ha-integration, quality-checklist) following Cursor best practices.
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

### Removed

- **Direct Supervisor API sensor updates** (`update_ha_sensor()` calls) removed from
  `check_and_update()`, `_ssl_event_callback()`, `_start_ssl_manager()`,
  `save_acme_challenge_info()` and `_check_commands()`.  These created orphaned entities
  not linked to the add-on device and caused `502 Bad Gateway` errors during startup
  when HA Core was not yet ready.  The state file replaces this mechanism entirely.
  The legacy `_update_*_sensor()` methods are kept (marked deprecated) for compatibility.

### Added

- **Integration Icon**: `icon.png` added to custom component directory so the
  integration displays the same icon as the add-on in the HA Integrations page
- **Auto-Discovery**: `async_step_hassio()` now auto-creates the config entry
  immediately when the add-on publishes discovery, eliminating the manual
  confirmation step. Entities appear on the add-on device without user interaction.
- **Automatic Add-on Detection**: `_async_detect_addon()` in `__init__.py` checks
  for the state file at startup. If a manually created config entry finds the
  state file, it switches to add-on mode automatically, attaching entities to the
  add-on device and reading state instead of polling independently.
- **Discovery Retry Logic**: `publish_addon_discovery()` now retries up to 5 times
  with increasing delays when HA Core is not yet ready (e.g. during first boot).
  Failure messages are logged at WARNING level for better visibility.
- `"after_dependencies": ["hassio"]` in `manifest.json` ensures the Supervisor
  creates the add-on device before the integration attaches entities to it
- `ADDON_STATE_FILE` and `ADDON_COMMAND_FILE` constants in `const.py`
- `DynDNSUpdater._write_state_file()` – writes current add-on state as JSON
- `DynDNSUpdater._check_commands()` – reads and executes commands from integration
- `OneComDynDNSCoordinator._async_read_addon_state()` – reads shared state file
- `OneComDynDNSCoordinator._write_command_sync()` – writes command for add-on
- `OneComDynDNSCoordinator._async_poll_directly()` – standalone-mode fallback
- **Extended Test Suite** (422 → 452 tests)
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
  - Tests for `_async_detect_addon()` (3 cases: detected via state file, no file,
    error handling)
  - Tests for `_build_discovery_config()` (2 cases: full config, empty defaults)
  - Tests for discovery retry logic (2 cases: succeeds after retries, exhausted)

### Fixed

- **Integration Name**: Renamed from "One.com DynDNS" to **"One.com DynDNS Updater"**
  across `manifest.json`, config flow entry titles, standalone device name, and all
  translations (`strings.json`, `en.json`, `de.json`)
- **Discovery Payload**: Removed the `addon` key from the Supervisor
  `POST /discovery` request body. The Supervisor infers the calling add-on from the
  bearer token; sending it explicitly caused `400 Bad Request` errors.
- **Metadata**: `manifest.json` codeowners, documentation URL, and issue tracker
  URL now point to `@ulfwuestefeld` / GitHub repository
- **Device Info**: Standalone device shows `manufacturer: ulfwuestefeld` and
  `configuration_url` pointing to the GitHub repository instead of one.com admin
- **Repository Name**: `repository.yaml` `name` field changed to `ulfwuestefeld`
  so the add-on device shows the correct "von" (by) attribution in the HA UI
- **Config Flow URL**: `docs_url` placeholder in `async_step_user()` updated to
  the correct GitHub repository URL

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

- **Custom component (1.2.0 → 1.3.7)**
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
