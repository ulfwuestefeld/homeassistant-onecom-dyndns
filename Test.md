# Test Documentation / Test-Dokumentation

[English](#english) | [Deutsch](#deutsch)

---

<a name="english"></a>
## 🇬🇧 English

### Prerequisites

Before running the tests, you need to install the following:

1. **Python 3.12+**
   - Download: https://www.python.org/downloads/
   - Verify installation: `python --version`

2. **pip** (Python Package Manager)
   - Usually included with Python
   - Verify: `pip --version`

3. **Test Dependencies**
   Install via pip:
   ```bash
   pip install pytest pytest-cov responses pytest-asyncio
   ```

   Or install all dependencies from requirements.txt:
   ```bash
   pip install -r requirements.txt
   ```

4. **Home Assistant Integration Tests** (optional)
   To run config flow and setup/unload tests:
   ```bash
   pip install pytest-homeassistant-custom-component
   ```

### Optional Tools

- **pytest-xdist** - Run tests in parallel (faster)
  ```bash
  pip install pytest-xdist
  ```

- **pytest-html** - Generate HTML test reports
  ```bash
  pip install pytest-html
  ```

### Running Tests

#### Run All Tests
```bash
pytest tests/ -v
```

#### Run with Coverage Report
```bash
pytest tests/ -v --cov=. --cov-report=term --cov-report=html
```
Coverage report will be generated in `htmlcov/index.html`

#### Run Specific Test Categories

| Command | Description |
|---------|-------------|
| `pytest tests/test_onecom_api.py -v` | One.com API tests |
| `pytest tests/test_acme_manager.py -v` | ACME Manager tests |
| `pytest tests/test_certificate_manager.py -v` | Certificate Manager tests |
| `pytest tests/test_run.py -v` | Main entry point tests |
| `pytest tests/test_e2e.py -v` | End-to-End tests |
| `pytest tests/test_integration.py -v` | Integration tests |
| `pytest tests/test_security.py -v` | Security tests |
| `pytest tests/test_edge_cases.py -v` | Edge case tests |
| `pytest tests/test_error_handling.py -v` | Error handling tests |
| `pytest tests/test_sensors.py -v` | Sensor entity tests |
| `pytest tests/test_config_flow.py -v` | Config flow tests (requires HA) |
| `pytest tests/test_init.py -v` | Setup/unload/services tests (requires HA) |

#### Run Tests in Parallel (Faster)
```bash
pytest tests/ -v -n auto
```
Requires: `pip install pytest-xdist`

#### Run Tests with HTML Report
```bash
pytest tests/ -v --html=report.html --self-contained-html
```
Requires: `pip install pytest-html`

#### Run Only Fast Tests (Skip E2E)
```bash
pytest tests/ -v -m "not e2e"
```

### Test Structure

```
tests/
├── conftest.py                      # Shared fixtures
├── test_onecom_api.py               # One.com API unit tests
├── test_onecom_api_advanced.py      # Advanced API tests (conflicts, retry)
├── test_acme_manager.py             # ACME Manager unit tests
├── test_certificate_manager.py      # Certificate Manager unit tests
├── test_certificate_manager_advanced.py  # Advanced cert tests
├── test_run.py                      # Main module unit tests
├── test_main_function.py            # Entry point and signal handler tests
├── test_retry_decorator.py          # Retry decorator tests
├── test_dns_operations.py           # DNS record operation tests
├── test_ip_services.py              # IP detection service tests
├── test_ssl_certificates.py         # SSL certificate tests
├── test_e2e.py                      # End-to-End workflow tests
├── test_integration.py              # Component integration tests
├── test_security.py                 # Security-related tests
├── test_edge_cases.py               # Boundary and edge case tests
├── test_error_handling.py           # Error handling tests
├── test_sensors.py                  # Sensor entity tests (component + add-on)
├── test_config_flow.py             # HA config flow tests (requires HA framework)
└── test_init.py                    # HA setup/unload/services tests (requires HA framework)
```

### Test Categories Explained

| Category | Purpose |
|----------|---------|
| **Unit Tests** | Test individual functions and classes in isolation |
| **Integration Tests** | Test multiple components working together |
| **E2E Tests** | Test complete workflows from start to finish |
| **Security Tests** | Verify secure handling of credentials and data |
| **Edge Case Tests** | Test boundary conditions and unusual inputs |
| **Error Handling Tests** | Verify proper error handling and recovery |
| **HA Config Flow Tests** | Test Home Assistant configuration wizard steps |
| **HA Init Tests** | Test integration setup, teardown, and service registration |

### Continuous Integration (CI)

Tests are automatically run on every push and pull request via **GitHub Actions**.

- **Workflow file:** `.github/workflows/test.yml`
- **Branches:** `main`, `master`, `develop`
- **Status badge:** [![Tests](https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns/actions/workflows/test.yml/badge.svg)](https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns/actions/workflows/test.yml)

The CI pipeline:
1. Runs all tests with coverage reporting
2. Uploads coverage reports as artifacts
3. Optionally uploads to Codecov
4. Runs flake8 linting for code quality

### Troubleshooting

**ImportError: No module named 'pytest'**
```bash
pip install pytest
```

**Tests fail with "ModuleNotFoundError"**
Make sure you're in the project root directory:
```bash
cd /path/to/onecomdyndns
pytest tests/ -v
```

**Coverage report not generated**
```bash
pip install pytest-cov
```

---

<a name="deutsch"></a>
## 🇩🇪 Deutsch

### Voraussetzungen

Bevor Sie die Tests ausführen können, müssen Sie folgendes installieren:

1. **Python 3.12+**
   - Download: https://www.python.org/downloads/
   - Installation prüfen: `python --version`

2. **pip** (Python-Paketmanager)
   - Normalerweise mit Python installiert
   - Prüfen: `pip --version`

3. **Test-Abhängigkeiten**
   Installation über pip:
   ```bash
   pip install pytest pytest-cov responses pytest-asyncio
   ```

   Oder alle Abhängigkeiten aus requirements.txt installieren:
   ```bash
   pip install -r requirements.txt
   ```

4. **Home Assistant Integrationstests** (optional)
   Zum Ausführen der Config-Flow- und Setup-Tests:
   ```bash
   pip install pytest-homeassistant-custom-component
   ```

### Optionale Werkzeuge

- **pytest-xdist** - Tests parallel ausführen (schneller)
  ```bash
  pip install pytest-xdist
  ```

- **pytest-html** - HTML-Testberichte erstellen
  ```bash
  pip install pytest-html
  ```

### Tests ausführen

#### Alle Tests ausführen
```bash
pytest tests/ -v
```

#### Mit Coverage-Bericht ausführen
```bash
pytest tests/ -v --cov=. --cov-report=term --cov-report=html
```
Der Coverage-Bericht wird in `htmlcov/index.html` erstellt.

#### Spezifische Test-Kategorien ausführen

| Befehl | Beschreibung |
|--------|--------------|
| `pytest tests/test_onecom_api.py -v` | One.com API Tests |
| `pytest tests/test_acme_manager.py -v` | ACME Manager Tests |
| `pytest tests/test_certificate_manager.py -v` | Certificate Manager Tests |
| `pytest tests/test_run.py -v` | Hauptmodul Tests |
| `pytest tests/test_e2e.py -v` | End-to-End Tests |
| `pytest tests/test_integration.py -v` | Integrationstests |
| `pytest tests/test_security.py -v` | Sicherheitstests |
| `pytest tests/test_edge_cases.py -v` | Grenzfall-Tests |
| `pytest tests/test_error_handling.py -v` | Fehlerbehandlungs-Tests |
| `pytest tests/test_sensors.py -v` | Sensor-Entity-Tests |
| `pytest tests/test_config_flow.py -v` | Config-Flow-Tests (benötigt HA) |
| `pytest tests/test_init.py -v` | Setup/Unload/Service-Tests (benötigt HA) |

#### Tests parallel ausführen (schneller)
```bash
pytest tests/ -v -n auto
```
Benötigt: `pip install pytest-xdist`

#### Tests mit HTML-Bericht ausführen
```bash
pytest tests/ -v --html=report.html --self-contained-html
```
Benötigt: `pip install pytest-html`

#### Nur schnelle Tests ausführen (E2E überspringen)
```bash
pytest tests/ -v -m "not e2e"
```

### Test-Struktur

```
tests/
├── conftest.py                      # Gemeinsame Fixtures
├── test_onecom_api.py               # One.com API Unit-Tests
├── test_onecom_api_advanced.py      # Erweiterte API-Tests (Konflikte, Retry)
├── test_acme_manager.py             # ACME Manager Unit-Tests
├── test_certificate_manager.py      # Certificate Manager Unit-Tests
├── test_certificate_manager_advanced.py  # Erweiterte Zertifikat-Tests
├── test_run.py                      # Hauptmodul Unit-Tests
├── test_main_function.py            # Einstiegspunkt- und Signal-Handler-Tests
├── test_retry_decorator.py          # Retry-Decorator-Tests
├── test_dns_operations.py           # DNS-Record-Operations-Tests
├── test_ip_services.py              # IP-Erkennungsdienst-Tests
├── test_ssl_certificates.py         # SSL-Zertifikat-Tests
├── test_e2e.py                      # End-to-End Workflow-Tests
├── test_integration.py              # Komponenten-Integrationstests
├── test_security.py                 # Sicherheitsbezogene Tests
├── test_edge_cases.py               # Grenzfall- und Edge-Case-Tests
├── test_error_handling.py           # Fehlerbehandlungs-Tests
├── test_sensors.py                  # Sensor-Entity-Tests (Komponente + Add-on)
├── test_config_flow.py             # HA Config-Flow-Tests (benötigt HA-Framework)
└── test_init.py                    # HA Setup/Unload/Service-Tests (benötigt HA-Framework)
```

### Test-Kategorien erklärt

| Kategorie | Zweck |
|-----------|-------|
| **Unit Tests** | Testen einzelne Funktionen und Klassen isoliert |
| **Integrationstests** | Testen mehrere Komponenten im Zusammenspiel |
| **E2E Tests** | Testen komplette Workflows von Anfang bis Ende |
| **Sicherheitstests** | Überprüfen sichere Handhabung von Zugangsdaten |
| **Grenzfall-Tests** | Testen Randbedingungen und ungewöhnliche Eingaben |
| **Fehlerbehandlungs-Tests** | Überprüfen korrekte Fehlerbehandlung und Wiederherstellung |
| **HA Config-Flow-Tests** | Testen die Home Assistant Konfigurationsschritte |
| **HA Init-Tests** | Testen Setup, Teardown und Service-Registrierung |

### Continuous Integration (CI)

Tests werden bei jedem Push und Pull Request automatisch über **GitHub Actions** ausgeführt.

- **Workflow-Datei:** `.github/workflows/test.yml`
- **Branches:** `main`, `master`, `develop`
- **Status-Badge:** [![Tests](https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns/actions/workflows/test.yml/badge.svg)](https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns/actions/workflows/test.yml)

Die CI-Pipeline:
1. Führt alle Tests mit Coverage-Reporting aus
2. Lädt Coverage-Berichte als Artefakte hoch
3. Lädt optional zu Codecov hoch
4. Führt flake8-Linting für Code-Qualität aus

### Fehlerbehebung

**ImportError: No module named 'pytest'**
```bash
pip install pytest
```

**Tests schlagen fehl mit "ModuleNotFoundError"**
Stellen Sie sicher, dass Sie im Projekt-Stammverzeichnis sind:
```bash
cd /pfad/zu/onecomdyndns
pytest tests/ -v
```

**Coverage-Bericht wird nicht erstellt**
```bash
pip install pytest-cov
```

---

## Quick Reference / Kurzreferenz

### Installation (All Platforms)

```bash
# Clone repository / Repository klonen
git clone https://github.com/ulfwuestefeld/homeassistant-onecom-dyndns.git
cd homeassistant-onecom-dyndns

# Create virtual environment (recommended) / Virtuelle Umgebung erstellen (empfohlen)
python -m venv venv

# Activate virtual environment / Virtuelle Umgebung aktivieren
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies / Abhängigkeiten installieren
pip install -r requirements.txt
pip install pytest pytest-cov responses

# Run tests / Tests ausführen
pytest tests/ -v
```

### Useful Links / Nützliche Links

| Resource | Link |
|----------|------|
| Python Download | https://www.python.org/downloads/ |
| pytest Documentation | https://docs.pytest.org/ |
| pytest-cov Documentation | https://pytest-cov.readthedocs.io/ |
| pytest-xdist (Parallel) | https://pytest-xdist.readthedocs.io/ |
| pytest-html (Reports) | https://pytest-html.readthedocs.io/ |

---

## Test Statistics / Test-Statistiken

| Metric | Value |
|--------|-------|
| Test Files / Test-Dateien | 19 (+conftest.py) |
| Estimated Tests / Geschätzte Tests | ~497 |
| Test Categories / Test-Kategorien | 10 |
| Coverage Target / Coverage-Ziel | >80% |

---

*Last updated / Zuletzt aktualisiert: 2026-02-08*
