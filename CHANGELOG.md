# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
