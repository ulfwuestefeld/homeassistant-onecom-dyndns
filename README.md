# One.com DynDNS Updater for Home Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant add-on that automatically updates DNS A records at One.com when your public IP address changes.

## Features

- Automatic public IP detection
- Periodic IP change monitoring
- Support for multiple subdomains
- Configurable update interval
- Multiple IP detection services
- Full Home Assistant UI configuration
- German and English translations

## Installation

### Add Repository to Home Assistant

1. Open Home Assistant
2. Go to **Settings** → **Add-ons** → **Add-on Store**
3. Click the three dots in the top right → **Repositories**
4. Add this repository URL: `https://github.com/your-username/homeassistant-onecom-dyndns`
5. Click **Add** → **Close**

### Install the Add-on

1. Find "One.com DynDNS Updater" in the add-on store
2. Click **Install**
3. Configure the add-on (see below)
4. Start the add-on

## Configuration

Configure the add-on through the Home Assistant UI:

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `username` | Yes | - | One.com account email |
| `password` | Yes | - | One.com account password |
| `domain` | Yes | - | Domain to update (e.g., `example.com`) |
| `subdomains` | No | `[""]` | Subdomains to update (empty for root) |
| `update_interval` | No | `5` | Check interval in minutes (1-60) |
| `ip_service` | No | `ipify` | IP detection service |
| `log_level` | No | `info` | Logging verbosity |

### Example

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
```

## Prerequisites

1. **Create DNS records first**: The add-on can only update existing A records. Create them manually in the One.com Control Panel.

2. **Disable 2FA**: Two-Factor Authentication is not supported. Disable it in your One.com account settings.

## How It Works

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
