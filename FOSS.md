# FOSS Notice

This project and distribution include the following notable Open Source
components and their licenses. See `SBOM.md` and `sbom.json` for the full
machine-readable Software Bill of Materials.

Core components:

- `requests >=2.32.0` — Apache-2.0
- `acme >=3.0.1` (SBOM: 5.6.0) — Apache-2.0
- `josepy >=2.0.0` (SBOM: 2.0.0) — Apache-2.0
- `cryptography >=50.0.0` — Apache-2.0 / BSD-3-Clause
- Home Assistant Base Python / Supervisor API — Apache-2.0
- Python 3.11 — PSF-2.0
- Alpine Linux, musl and libffi — various / MIT

Development & testing:

- `pytest` — MIT
- `ruff` — MIT
- `bandit` — BSD-3-Clause
- `safety` — BSD-3-Clause

The declared runtime dependency versions are also recorded in `sbom.json`.
The checked-in `pip_audit.json` is an environment report and currently records
`cryptography 48.0.0`; regenerate it after installing the declared
`cryptography >=50.0.0` requirement.

License for this project: MIT

If you need a formal third-party license report (for compliance), please open an
issue and I will generate a SPDX-compatible license manifest from the SBOM.
