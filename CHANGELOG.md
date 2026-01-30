# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-01-30

### Added

- **Automatic SSL certificate generation via Let's Encrypt**
- DNS-01 challenge support using One.com DNS API
- TXT record creation/deletion for ACME challenges
- Automatic certificate renewal (configurable days before expiry)
- Staging mode for testing without hitting rate limits
- Certificate status monitoring and callbacks
- DNS propagation waiting with Google DNS verification
- New configuration options:
  - `ssl_enabled`: Enable/disable SSL feature
  - `ssl_email`: Email for Let's Encrypt account
  - `ssl_domains`: Custom domain list for certificate
  - `ssl_staging`: Use staging server for testing
  - `ssl_renewal_days`: Days before expiry to renew
  - `ssl_check_interval`: Hours between renewal checks

- **Home Assistant Custom Integration with Config Flow**
- Step-by-step setup wizard with credential validation
- Automatic domain detection from One.com account
- Automatic subdomain detection from existing DNS records
- Options flow for runtime configuration changes
- Sensor entities:
  - Current IP address
  - Last update timestamp
  - Certificate expiry date
- Binary sensor entities:
  - DNS status (connectivity)
  - Certificate validity
- Services:
  - `onecom_dyndns.update_dns`: Force DNS update
  - `onecom_dyndns.renew_certificate`: Force certificate renewal
  - `onecom_dyndns.check_ip`: Check current IP
- German and English UI translations

### Changed

- Updated version to 1.1.0
- Added `ssl:rw` mapping for certificate storage
- Extended One.com API with TXT record management

### Dependencies

- Added `acme` library for ACME protocol
- Added `josepy` for JSON Object Signing
- Added `cryptography` for certificate handling

## [1.0.0] - 2026-01-28

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
