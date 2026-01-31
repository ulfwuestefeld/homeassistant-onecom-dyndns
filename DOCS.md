# One.com DynDNS Updater

This Home Assistant add-on automatically updates DNS A records at One.com when your public IP address changes. It also supports automatic SSL certificate generation using Let's Encrypt.

## Features

- Automatic IP change detection
- Support for multiple subdomains
- Configurable update interval
- Multiple IP detection services
- Detailed logging
- **Automatic SSL certificates via Let's Encrypt**
- DNS-01 challenge for certificate validation
- Automatic certificate renewal
- Online certificate verification
- Force renewal option for adding new domains
- ACME challenge notifications in Home Assistant

## Requirements

- A One.com account with at least one domain
- DNS A records must already exist (this add-on cannot create new records)
- Two-Factor Authentication must be disabled on your One.com account

## Configuration

### Required Settings

| Option | Description |
|--------|-------------|
| `username` | Your One.com account email address |
| `password` | Your One.com account password |
| `domain` | The domain to update (e.g., `example.com`) |

### Optional Settings

| Option | Default | Description |
|--------|---------|-------------|
| `subdomains` | `[""]` | List of subdomains to update. Use an empty string `""` for the root domain. |
| `update_interval` | `5` | How often to check for IP changes (in minutes, 1-60) |
| `ip_service` | `ipify` | Service for detecting public IP (`ipify`, `ifconfig`, `icanhazip`) |
| `log_level` | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`) |

### SSL Settings (Optional)

| Option | Default | Description |
|--------|---------|-------------|
| `ssl_enabled` | `false` | Enable automatic SSL certificate generation via Let's Encrypt |
| `ssl_email` | `""` | Email address for Let's Encrypt account (required when SSL is enabled) |
| `ssl_domains` | `[]` | Domains to include in certificate. Empty = main domain + subdomains |
| `ssl_staging` | `false` | Use Let's Encrypt staging server for testing |
| `ssl_renewal_days` | `30` | Renew certificate this many days before expiration |
| `ssl_check_interval` | `12` | How often to check for renewal (in hours) |
| `ssl_force_renewal` | `false` | Force certificate renewal on next startup (use when adding new domains) |

### Example Configuration (DynDNS only)

```yaml
username: "your.email@example.com"
password: "your-secure-password"
domain: "example.com"
subdomains:
  - ""           # Root domain (example.com)
  - "www"        # www.example.com
  - "home"       # home.example.com
update_interval: 5
ip_service: "ipify"
log_level: "info"
```

### Example Configuration (DynDNS + SSL)

```yaml
username: "your.email@example.com"
password: "your-secure-password"
domain: "example.com"
subdomains:
  - ""           # Root domain (example.com)
  - "www"        # www.example.com
  - "home"       # home.example.com
update_interval: 5
ip_service: "ipify"
log_level: "info"
ssl_enabled: true
ssl_email: "ssl@example.com"
ssl_domains:
  - "example.com"
  - "www.example.com"
  - "home.example.com"
ssl_staging: false
ssl_renewal_days: 30
ssl_check_interval: 12
ssl_force_renewal: false
```

### Force Certificate Renewal

If you need to renew your certificate immediately (e.g., after adding new domains), set `ssl_force_renewal: true` and restart the add-on:

```yaml
ssl_force_renewal: true  # Set to true, restart, then set back to false
```

This will request a new certificate with all configured domains, even if the current certificate is still valid.

## Setup Instructions

### 1. Prepare DNS Records at One.com

Before using this add-on, you need to create the DNS A records at One.com:

1. Log into your One.com Control Panel
2. Go to **DNS Settings**
3. Create A records for each subdomain you want to update
4. Set them to any IP address (it will be updated by the add-on)

### 2. Disable Two-Factor Authentication

This add-on does not support Two-Factor Authentication. If enabled:

1. Go to your One.com account settings
2. Disable Two-Factor Authentication
3. Consider using a strong, unique password

### 3. Install and Configure the Add-on

1. Add this repository to your Home Assistant Add-on Store
2. Install the "One.com DynDNS Updater" add-on
3. Configure the add-on with your One.com credentials
4. Start the add-on

## How It Works

### DynDNS

1. The add-on periodically checks your public IP address
2. If the IP has changed since the last check:
   - Logs into your One.com account
   - Updates all configured DNS A records
   - Saves the new IP for future comparisons
3. DNS changes typically propagate within minutes

### SSL Certificates (when enabled)

1. On startup, the add-on checks if a valid certificate exists
2. If no certificate or expiring soon (within `ssl_renewal_days`):
   - Registers/retrieves a Let's Encrypt account
   - For each domain, creates a DNS-01 challenge:
     - Creates a TXT record at `_acme-challenge.yourdomain.com`
     - Waits for DNS propagation
     - Let's Encrypt validates the challenge
     - TXT record is automatically cleaned up
   - Certificate is issued and saved to `/ssl/`
3. The add-on checks for renewal every `ssl_check_interval` hours
4. Certificates are stored at:
   - Certificate: `/ssl/fullchain.pem`
   - Private Key: `/ssl/privkey.pem`

### Online Certificate Verification

The add-on periodically verifies that your certificates are actually active on your servers:

- Connects to each configured domain on port 443
- Validates the SSL certificate is trusted and not expired
- Checks that the certificate covers the domain (including wildcard support)
- Logs warnings if any domain has an invalid or missing certificate

This helps detect issues like:
- Certificate not deployed to web server
- Hostname mismatch (domain not in certificate)
- Expired certificates
- Server unreachable

## Troubleshooting

### Login Failed

- Verify your One.com credentials are correct
- Ensure Two-Factor Authentication is disabled
- Check if One.com is accessible from your network

### DNS Record Not Found

- The DNS record must exist before it can be updated
- Create the A record manually in the One.com Control Panel
- Use the exact subdomain name in the configuration

### IP Detection Failed

- Try a different `ip_service` option
- Check your internet connection
- Verify outbound HTTPS connections are allowed

### Updates Not Working

- Set `log_level` to `debug` for detailed logs
- Check the add-on logs for error messages
- Verify DNS record permissions in One.com

### SSL Certificate Issues

- **Challenge Failed**: DNS propagation may take time. The add-on waits up to 3 minutes.
- **Rate Limited**: Let's Encrypt has rate limits. Use `ssl_staging: true` for testing.
- **Certificate Not Trusted**: If using staging mode, certificates won't be trusted by browsers. Set `ssl_staging: false` for production certificates.
- **Renewal Failed**: Check if One.com credentials are still valid.
- **Hostname Mismatch**: Your certificate doesn't cover all domains. Set `ssl_force_renewal: true` to request a new certificate with all configured domains.
- **Online Verification Failed**: The certificate exists locally but isn't active on the server. Check your web server configuration.
- **ERR_SSL_PROTOCOL_ERROR**: Check your router port forwarding! Port 443 must forward to internal port 443 (NGINX), NOT to port 8123 (Home Assistant HTTP). See Router Configuration section above.

### Manual DNS Challenge

When the add-on creates an ACME challenge, it sends a **Home Assistant notification** with the TXT record details. You can also find the challenge information in:

- **Home Assistant Notifications**: Look for "ACME DNS Challenge" notification
- **File**: `/data/acme_challenge.json` in the add-on data directory
- **Sensor**: `sensor.onecom_dyndns_acme_challenge`

If automatic TXT record creation fails, you can manually create the record at One.com with the provided name and value.

## Home Assistant Sensors

The add-on creates the following sensors in Home Assistant:

| Sensor | Description |
|--------|-------------|
| `sensor.onecom_dyndns_ip` | Current public IP address with domain/subdomain info |
| `sensor.onecom_dyndns_dns_status` | DNS update status (ok/error) |
| `sensor.onecom_dyndns_certificate` | SSL certificate expiry date with days remaining |
| `sensor.onecom_dyndns_acme_challenge` | Current ACME challenge TXT record value |

These sensors can be used in automations, dashboards, or alerts. For example:

```yaml
# Alert when certificate is expiring soon
automation:
  - alias: "SSL Certificate Expiry Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.onecom_dyndns_certificate
        attribute: days_remaining
        below: 14
    action:
      - service: notify.notify
        data:
          message: "SSL certificate expires in {{ state_attr('sensor.onecom_dyndns_certificate', 'days_remaining') }} days"
```

## Security Considerations

- Your One.com password is stored in the add-on configuration
- Consider using a dedicated One.com sub-account if available
- Regularly rotate your One.com password
- Monitor the add-on logs for unauthorized access attempts

## Home Assistant Integration (Alternative to Add-on)

Instead of using the add-on, you can install this as a custom integration with a guided setup wizard.

### Installation

1. Copy the `custom_components/onecom_dyndns` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration**
4. Search for "One.com DynDNS" and follow the setup wizard

### Setup Wizard Steps

1. **Login**: Enter your One.com credentials (validated in real-time)
2. **Domain Selection**: Choose from your detected domains or enter manually
3. **Subdomain Selection**: Pick which DNS records to update
4. **Options**: Set update interval, IP service, and enable SSL
5. **SSL Configuration** (optional): Configure Let's Encrypt settings

### Entities

The integration creates the following entities:

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.current_ip` | Sensor | Current public IP address |
| `sensor.last_update` | Sensor | Timestamp of last DNS update |
| `sensor.certificate_expiry` | Sensor | SSL certificate expiry date |
| `binary_sensor.dns_status` | Binary Sensor | DNS connectivity status |
| `binary_sensor.certificate_valid` | Binary Sensor | Certificate validity status |

### Services

| Service | Description |
|---------|-------------|
| `onecom_dyndns.update_dns` | Force immediate DNS update |
| `onecom_dyndns.renew_certificate` | Force certificate renewal |
| `onecom_dyndns.check_ip` | Refresh IP address check |

## Using with NGINX SSL Proxy

To enable both HTTP (Port 80) and HTTPS (Port 443) access to Home Assistant, you can use the official **NGINX Home Assistant SSL proxy** add-on together with certificates generated by this add-on.

### Step 1: Install NGINX SSL Proxy Add-on

1. Go to **Settings → Add-ons → Add-on Store**
2. Search for **"NGINX Home Assistant SSL proxy"**
3. Click **Install**

### Step 2: Configure NGINX

In the NGINX add-on configuration:

```yaml
domain: your-domain.com
certfile: fullchain.pem
keyfile: privkey.pem
hsts: "max-age=31536000; includeSubDomains"
cloudflare: false
customize:
  active: false
```

### Step 3: Configure Home Assistant

Add the following to your `configuration.yaml`:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.30.33.0/24
```

### Step 4: Restart and Test

1. Restart Home Assistant
2. Start the NGINX add-on

You will now have:
- **Port 80** (HTTP) → Redirects to HTTPS
- **Port 443** (HTTPS) → Secured with your Let's Encrypt certificate
- **Port 8123** → Direct internal access

### Router Configuration

Make sure your router forwards:
- Port 80 → Home Assistant IP, **Port 80**
- Port 443 → Home Assistant IP, **Port 443**

⚠️ **WICHTIG / IMPORTANT**: Die Portweiterleitung muss auf die korrekten internen Ports zeigen!

| Extern | Intern | Beschreibung |
|--------|--------|--------------|
| 443 | **443** | ✅ Korrekt - NGINX SSL Proxy |
| 443 | 8123 | ❌ FALSCH - Home Assistant HTTP |
| 80 | **80** | ✅ Korrekt - NGINX HTTP Redirect |
| 80 | 8123 | ❌ FALSCH - Home Assistant HTTP |

Port 443 muss auf Port **443** (NGINX) zeigen, NICHT auf Port 8123 (Home Assistant HTTP). NGINX macht die SSL-Terminierung und leitet dann intern an Home Assistant weiter.

## Limitations

- One.com does not provide an official API
- This add-on uses web scraping, which may break if One.com changes their interface
- Two-Factor Authentication is not supported
- Only IPv4 A records are supported (no IPv6/AAAA)

## Support

If you encounter issues:

1. Check the add-on logs
2. Search existing issues on GitHub
3. Open a new issue with:
   - Your configuration (without password)
   - Relevant log entries
   - Steps to reproduce the problem

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.

## License

MIT License - See LICENSE file for details.
