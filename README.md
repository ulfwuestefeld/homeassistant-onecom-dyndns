# One.com DynDNS Updater for Home Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant add-on that automatically updates DNS A records at One.com when your public IP address changes. It also supports **automatic SSL certificate generation** using Let's Encrypt.

## Features

### DynDNS
- Automatic public IP detection
- Periodic IP change monitoring
- Support for multiple subdomains
- Configurable update interval
- Multiple IP detection services

### SSL Certificates (Optional)
- **Automatic SSL certificates via Let's Encrypt**
- DNS-01 challenge for certificate validation
- Automatic certificate renewal
- Online certificate verification
- Force renewal option for adding new domains
- Staging mode for testing

### General
- Full Home Assistant UI configuration
- German and English translations
- Also available as **Custom Integration** with Config Flow

## Installation

### Add Repository to Home Assistant

1. Open Home Assistant
2. Go to **Settings** → **Add-ons** → **Add-on Store**
3. Click the three dots in the top right → **Repositories**
4. Add this repository URL: `https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns`
5. Click **Add** → **Close**

### Install the Add-on

1. Find "One.com DynDNS Updater" in the add-on store
2. Click **Install**
3. Configure the add-on (see below)
4. Start the add-on

## Configuration

Configure the add-on through the Home Assistant UI:

### Required Settings

| Option | Description |
|--------|-------------|
| `username` | One.com account email |
| `password` | One.com account password |
| `domain` | Domain to update (e.g., `example.com`) |

### Optional Settings

| Option | Default | Description |
|--------|---------|-------------|
| `subdomains` | `[""]` | Subdomains to update (empty for root) |
| `update_interval` | `5` | Check interval in minutes (1-60) |
| `ip_service` | `ipify` | IP detection service |
| `log_level` | `info` | Logging verbosity |

### SSL Settings (Optional)

| Option | Default | Description |
|--------|---------|-------------|
| `ssl_enabled` | `false` | Enable Let's Encrypt certificates |
| `ssl_email` | `""` | Email for Let's Encrypt account |
| `ssl_domains` | `[]` | Domains for certificate |
| `ssl_staging` | `false` | Use staging server for testing |
| `ssl_renewal_days` | `30` | Days before expiry to renew |
| `ssl_check_interval` | `12` | Hours between renewal checks |
| `ssl_force_renewal` | `false` | Force renewal on next startup |

### Example (DynDNS + SSL)

```yaml
username: your.email@one.com
password: your-password
domain: example.com
subdomains:
  - ""       # Root domain
  - "www"    # www.example.com
  - "home"   # home.example.com
update_interval: 5
ip_service: ipify
log_level: info
ssl_enabled: true
ssl_email: ssl@example.com
ssl_domains:
  - "example.com"
  - "www.example.com"
  - "home.example.com"
```

## Prerequisites

1. **Create DNS records first**: The add-on can only update existing A records. Create them manually in the One.com Control Panel.

2. **Disable 2FA**: Two-Factor Authentication is not supported. Disable it in your One.com account settings.

## How It Works

### DynDNS Flow

```
┌─────────────────┐
│  Start Add-on   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Get Public IP  │◄─────────────┐
│   (ipify.org)   │              │
└────────┬────────┘              │
         │                       │
         ▼                       │
┌─────────────────┐              │
│  IP Changed?    │──No──────────┤
└────────┬────────┘              │
         │ Yes                   │
         ▼                       │
┌─────────────────┐              │
│ Login to One.com│              │
└────────┬────────┘              │
         │                       │
         ▼                       │
┌─────────────────┐              │
│ Update DNS      │              │
│ A Records       │              │
└────────┬────────┘              │
         │                       │
         ▼                       │
┌─────────────────┐              │
│  Save New IP    │              │
└────────┬────────┘              │
         │                       │
         ▼                       │
┌─────────────────┐              │
│ Wait Interval   │──────────────┘
└─────────────────┘
```

### SSL Certificate Flow (when enabled)

1. Checks if certificate exists and is valid
2. If renewal needed: Creates DNS-01 challenge TXT records
3. Let's Encrypt validates domain ownership
4. Certificate saved to `/ssl/fullchain.pem` and `/ssl/privkey.pem`
5. Periodic online verification of deployed certificates

## Development

### Run Tests

```bash
pip install pytest requests
pytest tests/ -v
```

### Local Testing

```bash
export ONECOM_USERNAME="your@email.com"
export ONECOM_PASSWORD="your-password"
export ONECOM_DOMAIN="example.com"
export ONECOM_SUBDOMAINS="www,"
python run.py
```

## Custom Integration (Alternative)

Instead of the add-on, you can install this as a **Custom Integration** with a guided setup wizard:

1. Copy `custom_components/onecom_dyndns` to your HA config directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for "One.com DynDNS"

The integration provides sensors, binary sensors, and services. See [DOCS.md](DOCS.md) for details.

## Troubleshooting

See [DOCS.md](DOCS.md) for detailed troubleshooting information.

## License

MIT License - see [LICENSE](LICENSE) file.

## Disclaimer

This add-on uses web scraping to interact with One.com since they don't provide an official API. This means:

- It may break if One.com changes their website
- Use at your own risk
- No guarantee of functionality

## Contributing

Contributions are welcome! Please open an issue first to discuss proposed changes.
