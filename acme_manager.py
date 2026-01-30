"""
ACME Manager Module

This module handles Let's Encrypt certificate management using the ACME protocol
with DNS-01 challenge validation through One.com.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, List, Callable

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import josepy as jose
from acme import client, messages, challenges, errors as acme_errors

from onecom_api import OneComAPI, OneComAPIError

_LOGGER = logging.getLogger(__name__)

# Let's Encrypt directory URLs
LETSENCRYPT_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
LETSENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"

# Default paths
DEFAULT_ACCOUNT_KEY_PATH = "/data/acme/account.key"
DEFAULT_CERT_PATH = "/ssl/fullchain.pem"
DEFAULT_KEY_PATH = "/ssl/privkey.pem"


class ACMEManagerError(Exception):
    """Exception raised for ACME Manager errors."""
    pass


class ACMEManager:
    """Manages Let's Encrypt certificates using ACME with DNS-01 challenge."""

    def __init__(
        self,
        email: str,
        onecom_api: OneComAPI,
        staging: bool = False,
        account_key_path: str = DEFAULT_ACCOUNT_KEY_PATH,
        cert_path: str = DEFAULT_CERT_PATH,
        key_path: str = DEFAULT_KEY_PATH,
        challenge_callback: Optional[Callable[[str, str, str], None]] = None,
    ):
        """Initialize the ACME Manager.

        Args:
            email: Email address for Let's Encrypt account
            onecom_api: Configured OneComAPI instance
            staging: Use staging server for testing
            account_key_path: Path to store/load account key
            cert_path: Path to store certificate
            key_path: Path to store private key
            challenge_callback: Optional callback function(domain, txt_name, txt_value)
                               called when an ACME challenge is created
        """
        self.email = email
        self.onecom_api = onecom_api
        self.staging = staging
        self.account_key_path = account_key_path
        self.cert_path = cert_path
        self.key_path = key_path
        self.challenge_callback = challenge_callback

        self.directory_url = LETSENCRYPT_STAGING if staging else LETSENCRYPT_PRODUCTION
        self._account_key: Optional[jose.JWKRSA] = None
        self._client: Optional[client.ClientV2] = None

        _LOGGER.info(f"ACME Manager initialized (staging={staging})")

    def _ensure_directories(self):
        """Ensure all necessary directories exist."""
        for path in [self.account_key_path, self.cert_path, self.key_path]:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)

    def _generate_private_key(self, key_size: int = 2048) -> rsa.RSAPrivateKey:
        """Generate a new RSA private key.

        Args:
            key_size: Key size in bits

        Returns:
            RSA private key object.
        """
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )

    def _load_or_create_account_key(self) -> jose.JWKRSA:
        """Load existing account key or create a new one.

        Returns:
            JOSE RSA key for ACME account.
        """
        self._ensure_directories()

        if os.path.exists(self.account_key_path):
            _LOGGER.debug("Loading existing account key")
            with open(self.account_key_path, "rb") as f:
                key_data = f.read()
                private_key = serialization.load_pem_private_key(
                    key_data,
                    password=None,
                    backend=default_backend()
                )
                return jose.JWKRSA(key=private_key)

        _LOGGER.info("Generating new account key")
        private_key = self._generate_private_key(4096)

        # Save the key
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        with open(self.account_key_path, "wb") as f:
            f.write(key_pem)

        # Set restrictive permissions
        os.chmod(self.account_key_path, 0o600)

        return jose.JWKRSA(key=private_key)

    def _get_client(self) -> client.ClientV2:
        """Get or create ACME client.

        Returns:
            Configured ACME client.
        """
        if self._client:
            return self._client

        self._account_key = self._load_or_create_account_key()

        # Create network client
        net = client.ClientNetwork(self._account_key, user_agent="OneComDynDNS/1.0")

        # Get directory
        directory = messages.Directory.from_json(
            net.get(self.directory_url).json()
        )

        self._client = client.ClientV2(directory, net)
        return self._client

    def register_account(self) -> messages.RegistrationResource:
        """Register or retrieve existing ACME account.

        Returns:
            Registration resource.

        Raises:
            ACMEManagerError: If registration fails.
        """
        acme_client = self._get_client()

        _LOGGER.info(f"Registering ACME account for {self.email}")

        try:
            # Try to create new registration
            new_reg = messages.NewRegistration.from_data(
                email=self.email,
                terms_of_service_agreed=True
            )
            regr = acme_client.new_account(new_reg)
            _LOGGER.info("New ACME account registered")
            return regr

        except acme_errors.ConflictError:
            # Account already exists, retrieve it
            _LOGGER.info("ACME account already exists, retrieving...")
            try:
                existing_reg = messages.NewRegistration.from_data(
                    email=self.email,
                    terms_of_service_agreed=True
                )
                regr = acme_client.new_account(existing_reg)
                _LOGGER.debug("Account retrieved successfully")
                return regr
            except Exception as e2:
                raise ACMEManagerError(f"Failed to retrieve existing ACME account: {e2}")

        except Exception as e:
            raise ACMEManagerError(f"Failed to register ACME account: {e}")

    def _perform_dns_challenge(
        self,
        domain: str,
        challenge: challenges.DNS01,
        authz: messages.AuthorizationResource
    ) -> bool:
        """Perform DNS-01 challenge for a domain.

        Args:
            domain: The domain being validated
            challenge: The DNS-01 challenge object
            authz: Authorization resource

        Returns:
            True if challenge was successful.
        """
        acme_client = self._get_client()

        # Get the validation token
        response, validation = challenge.response_and_validation(self._account_key)

        # Determine the ACME challenge subdomain
        # For subdomains like "homeassistant.wuesti.eu", the TXT record prefix
        # must be "_acme-challenge.homeassistant" (relative to the base domain)
        if domain.startswith("*."):
            # Wildcard certificate
            base_domain = domain[2:]
            challenge_subdomain = "_acme-challenge"
        else:
            # Check if domain is a subdomain of the configured base domain
            base_domain = self.onecom_api.domain
            if domain == base_domain:
                # Root domain - just use _acme-challenge
                challenge_subdomain = "_acme-challenge"
            elif domain.endswith(f".{base_domain}"):
                # Subdomain - prepend subdomain to _acme-challenge
                subdomain_part = domain[:-len(f".{base_domain}")]
                challenge_subdomain = f"_acme-challenge.{subdomain_part}"
            else:
                # Domain doesn't match base domain - use just _acme-challenge
                challenge_subdomain = "_acme-challenge"

        # Build the full DNS name for the TXT record
        full_txt_name = f"{challenge_subdomain}.{self.onecom_api.domain}"
        
        _LOGGER.info(f"Setting up DNS-01 challenge for {domain}")
        _LOGGER.info(f"=== ACME DNS-01 Challenge ===")
        _LOGGER.info(f"TXT Record Name: {full_txt_name}")
        _LOGGER.info(f"TXT Record Value: {validation}")
        _LOGGER.info(f"=============================")
        _LOGGER.debug(f"Challenge subdomain (prefix): {challenge_subdomain}")
        
        # Notify via callback (e.g., Home Assistant notification)
        if self.challenge_callback:
            try:
                self.challenge_callback(domain, full_txt_name, validation)
            except Exception as e:
                _LOGGER.warning(f"Challenge callback failed: {e}")

        record_id = None
        try:
            # Create TXT record
            _LOGGER.info(f"Creating TXT record at One.com...")
            record_id = self.onecom_api.create_txt_record(
                subdomain=challenge_subdomain,
                content=validation,
                ttl=60
            )

            # Wait for DNS propagation
            if not self.onecom_api.wait_for_dns_propagation(
                subdomain=challenge_subdomain,
                expected_content=validation,
                timeout=180,
                interval=10
            ):
                _LOGGER.warning("DNS propagation timeout, attempting validation anyway...")

            # Additional wait for safety
            time.sleep(5)

            # Answer the challenge
            acme_client.answer_challenge(challenge, response)

            # Poll for authorization status
            deadline = datetime.now() + timedelta(minutes=5)
            while datetime.now() < deadline:
                authz_response = acme_client.poll(authz)
                authz = authz_response

                status = authz.body.status.name
                _LOGGER.debug(f"Authorization status: {status}")

                if status == "valid":
                    _LOGGER.info(f"Challenge successful for {domain}")
                    return True
                elif status == "invalid":
                    _LOGGER.error(f"Challenge failed for {domain}")
                    return False

                time.sleep(5)

            _LOGGER.error(f"Challenge timeout for {domain}")
            return False

        except OneComAPIError as e:
            _LOGGER.error(f"DNS operation failed: {e}")
            _LOGGER.error(f"If automatic creation fails, you can manually create the TXT record:")
            _LOGGER.error(f"  Name: {full_txt_name}")
            _LOGGER.error(f"  Type: TXT")
            _LOGGER.error(f"  Value: {validation}")
            return False

        except Exception as e:
            _LOGGER.error(f"Challenge failed: {e}")
            return False

        finally:
            # Cleanup: remove the challenge record
            if record_id:
                try:
                    self.onecom_api.delete_txt_record(record_id)
                except OneComAPIError as e:
                    _LOGGER.warning(f"Failed to cleanup challenge record: {e}")

    def obtain_certificate(self, domains: List[str]) -> Tuple[str, str]:
        """Obtain a certificate for the specified domains.

        Args:
            domains: List of domains (first one is the primary domain)

        Returns:
            Tuple of (certificate_pem, private_key_pem).

        Raises:
            ACMEManagerError: If certificate issuance fails.
        """
        if not domains:
            raise ACMEManagerError("No domains specified")

        _LOGGER.debug("Getting ACME client...")
        acme_client = self._get_client()

        # Ensure account is registered
        _LOGGER.debug("Registering/retrieving ACME account...")
        self.register_account()
        _LOGGER.debug("ACME account ready")

        _LOGGER.info(f"Requesting certificate for: {', '.join(domains)}")

        try:
            # Generate CSR private key
            csr_key = self._generate_private_key(2048)

            # Create CSR
            csr_builder = x509.CertificateSigningRequestBuilder()
            csr_builder = csr_builder.subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, domains[0])
            ]))

            # Add all domains as SANs
            san_list = [x509.DNSName(d.lstrip("*.") if d.startswith("*.") else d) for d in domains]
            # Add wildcard separately if present
            for d in domains:
                if d.startswith("*."):
                    san_list.append(x509.DNSName(d))

            csr_builder = csr_builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False
            )

            csr = csr_builder.sign(csr_key, hashes.SHA256(), default_backend())

            # Request new order
            order = acme_client.new_order(csr.public_bytes(serialization.Encoding.PEM))

            # Process each authorization
            for authz in order.authorizations:
                domain = authz.body.identifier.value
                _LOGGER.info(f"Processing authorization for {domain}")

                # Find DNS-01 challenge
                dns_challenge = None
                for challenge in authz.body.challenges:
                    if isinstance(challenge.chall, challenges.DNS01):
                        dns_challenge = challenge
                        break

                if not dns_challenge:
                    raise ACMEManagerError(f"No DNS-01 challenge available for {domain}")

                # Perform the challenge
                if not self._perform_dns_challenge(domain, dns_challenge.chall, authz):
                    raise ACMEManagerError(f"DNS-01 challenge failed for {domain}")

            # Finalize the order
            _LOGGER.info("Finalizing certificate order...")
            order = acme_client.poll_and_finalize(order)

            # Get the certificate
            cert_pem = order.fullchain_pem

            # Get the private key
            key_pem = csr_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode("utf-8")

            _LOGGER.info("Certificate obtained successfully")
            return cert_pem, key_pem

        except acme_errors.Error as e:
            raise ACMEManagerError(f"ACME error: {e}")
        except Exception as e:
            raise ACMEManagerError(f"Failed to obtain certificate: {e}")

    def save_certificate(self, cert_pem: str, key_pem: str):
        """Save certificate and key to files.

        Args:
            cert_pem: Certificate chain in PEM format
            key_pem: Private key in PEM format
        """
        self._ensure_directories()

        _LOGGER.info(f"Saving certificate to {self.cert_path}")
        _LOGGER.info(f"Saving private key to {self.key_path}")

        # Save certificate
        try:
            with open(self.cert_path, "w") as f:
                f.write(cert_pem)
            os.chmod(self.cert_path, 0o644)
            
            # Verify file was written
            cert_size = os.path.getsize(self.cert_path)
            cert_mtime = os.path.getmtime(self.cert_path)
            _LOGGER.info(f"Certificate saved: {cert_size} bytes, modified: {cert_mtime}")
        except Exception as e:
            _LOGGER.error(f"Failed to save certificate: {e}")
            raise

        # Save private key
        try:
            with open(self.key_path, "w") as f:
                f.write(key_pem)
            os.chmod(self.key_path, 0o600)
            
            # Verify file was written
            key_size = os.path.getsize(self.key_path)
            key_mtime = os.path.getmtime(self.key_path)
            _LOGGER.info(f"Private key saved: {key_size} bytes, modified: {key_mtime}")
        except Exception as e:
            _LOGGER.error(f"Failed to save private key: {e}")
            raise
        
        _LOGGER.info("="*50)
        _LOGGER.info("CERTIFICATE UPDATE COMPLETE")
        _LOGGER.info(f"Certificate: {self.cert_path}")
        _LOGGER.info(f"Private Key: {self.key_path}")
        _LOGGER.info("NOTE: Restart NGINX or Home Assistant to use new certificate!")
        _LOGGER.info("="*50)

    def get_certificate_expiry(self) -> Optional[datetime]:
        """Get the expiry date of the current certificate.

        Returns:
            Expiry datetime or None if no certificate exists.
        """
        if not os.path.exists(self.cert_path):
            return None

        try:
            with open(self.cert_path, "rb") as f:
                cert_data = f.read()

            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            # Use UTC-aware method to avoid deprecation warning
            try:
                return cert.not_valid_after_utc
            except AttributeError:
                return cert.not_valid_after

        except Exception as e:
            _LOGGER.warning(f"Failed to read certificate expiry: {e}")
            return None

    def needs_renewal(self, days_before_expiry: int = 30) -> bool:
        """Check if the certificate needs renewal.

        Args:
            days_before_expiry: Renew if expiring within this many days

        Returns:
            True if renewal is needed.
        """
        expiry = self.get_certificate_expiry()

        if expiry is None:
            _LOGGER.info("No certificate found, renewal needed")
            return True

        days_remaining = (expiry - datetime.now()).days
        _LOGGER.info(f"Certificate expires in {days_remaining} days")

        if days_remaining <= days_before_expiry:
            _LOGGER.info(f"Certificate will expire soon, renewal needed")
            return True

        return False

    def obtain_and_save_certificate(self, domains: List[str]) -> bool:
        """Obtain and save a new certificate.

        Args:
            domains: List of domains for the certificate

        Returns:
            True if successful.
        """
        try:
            cert_pem, key_pem = self.obtain_certificate(domains)
            self.save_certificate(cert_pem, key_pem)
            return True
        except ACMEManagerError as e:
            _LOGGER.error(f"Failed to obtain certificate: {e}")
            return False

    def renew_if_needed(self, domains: List[str], days_before_expiry: int = 30) -> bool:
        """Renew the certificate if it's expiring soon.

        Args:
            domains: List of domains for the certificate
            days_before_expiry: Renew if expiring within this many days

        Returns:
            True if renewal was successful or not needed.
        """
        if not self.needs_renewal(days_before_expiry):
            _LOGGER.info("Certificate is still valid, no renewal needed")
            return True

        _LOGGER.info("Starting certificate renewal...")
        return self.obtain_and_save_certificate(domains)
