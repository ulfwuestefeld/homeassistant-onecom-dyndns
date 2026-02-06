# Software Bill of Materials (SBOM)

**Project:** One.com DynDNS Updater  
**Version:** 1.3.2  
**Date:** 2026-02-06  
**License:** MIT  

## Overview

This document provides a complete inventory of all software components used in the One.com DynDNS Updater Home Assistant add-on.

## Application Components

| Component | Version | License | Description |
|-----------|---------|---------|-------------|
| One.com DynDNS Updater | 1.3.2 | MIT | Main application |

### Source Files

| File | Purpose |
|------|---------|
| `run.py` | Main entry point, orchestrates DynDNS and SSL management |
| `onecom_api.py` | One.com API client for DNS management |
| `acme_manager.py` | ACME/Let's Encrypt protocol implementation |
| `certificate_manager.py` | SSL certificate lifecycle management |

## Runtime Dependencies

### Python Packages (Production)

| Package | Min. Version | License | Purpose |
|---------|--------------|---------|---------|
| requests | >=2.28.0 | Apache-2.0 | HTTP client for API calls |
| acme | >=2.0.0 | Apache-2.0 | Let's Encrypt ACME protocol |
| josepy | >=1.13.0 | Apache-2.0 | JOSE/JWK cryptographic operations |
| cryptography | >=41.0.0 | Apache-2.0 / BSD-3-Clause | Cryptographic primitives |

### Python Packages (Development/Testing)

| Package | Min. Version | License | Purpose |
|---------|--------------|---------|---------|
| pytest | >=7.0.0 | MIT | Testing framework |
| pytest-cov | >=4.0.0 | MIT | Code coverage |
| responses | >=0.22.0 | Apache-2.0 | HTTP mocking |

## Container Base Image

| Component | Version | License | Registry |
|-----------|---------|---------|----------|
| Home Assistant Base Python | 3.11-alpine3.18 | Apache-2.0 | ghcr.io/home-assistant |

### Supported Architectures

- `amd64` (x86_64)
- `aarch64` (ARM64)
- `armv7` (ARMv7)
- `armhf` (ARM hard float)
- `i386` (x86 32-bit)

## Operating System Components (Alpine Linux 3.18)

| Package | License | Purpose |
|---------|---------|---------|
| python3 | PSF-2.0 | Python 3.11 runtime |
| py3-pip | MIT | Python package manager |
| py3-requests | Apache-2.0 | Pre-built requests package |
| py3-cryptography | Apache-2.0 / BSD | Pre-built cryptography package |
| py3-openssl | Apache-2.0 | OpenSSL Python bindings |
| openssl | Apache-2.0 | SSL/TLS library |
| libffi | MIT | Foreign function interface |
| gcc | GPL-3.0 | C compiler (build-time) |
| musl | MIT | C standard library |

## External Services

| Service | Purpose | URL |
|---------|---------|-----|
| One.com | DNS management | https://www.one.com |
| Let's Encrypt | SSL certificate issuance | https://letsencrypt.org |
| ipify | Public IP detection | https://api.ipify.org |
| ifconfig.me | Public IP detection (fallback) | https://ifconfig.me |
| icanhazip.com | Public IP detection (fallback) | https://icanhazip.com |
| Google DNS | DNS propagation verification | https://dns.google |

## License Summary

| License | Components |
|---------|------------|
| MIT | Main application, libffi, musl, pytest, pytest-cov |
| Apache-2.0 | requests, acme, josepy, openssl, Home Assistant base |
| BSD-3-Clause | cryptography (dual-licensed) |
| PSF-2.0 | Python |
| GPL-3.0 | gcc (build-time only) |

## Security Considerations

- All dependencies are from trusted sources (PyPI, Alpine packages, Home Assistant registry)
- No known vulnerabilities at time of release
- Credentials are stored in Home Assistant add-on configuration (encrypted)
- HTTPS used for all external communications

## Dependency Graph

```
One.com DynDNS Updater (1.3.2)
├── Python 3.11
│   └── Alpine Linux 3.18
│       ├── openssl
│       ├── libffi
│       └── musl
├── requests (>=2.28.0)
│   ├── urllib3
│   ├── certifi
│   └── charset-normalizer
├── acme (>=2.0.0)
│   ├── josepy (>=1.13.0)
│   ├── cryptography (>=41.0.0)
│   │   └── cffi
│   └── requests
└── Home Assistant Supervisor API
```

## SBOM Format

This SBOM is also available in machine-readable CycloneDX JSON format: `sbom.json`

## Contact

For security issues or dependency updates, please open an issue at:
https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns/issues
