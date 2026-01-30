# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.9] - 2026-01-30

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
