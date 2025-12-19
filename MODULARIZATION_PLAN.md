# Botocore Modularization Plan

## Executive Summary

This document outlines a comprehensive strategy to modularize botocore, reducing the package size from **111 MB** to as little as **2-3 MB** for single-service use cases (e.g., Lambda functions using only DynamoDB). The plan maintains **100% backwards compatibility** with boto3 and preserves all existing tests.

### Current State

| Component | Size | Notes |
|-----------|------|-------|
| Service definitions (`data/`) | 104 MB | 415 AWS services |
| Core Python modules | ~1.2 MB | 42 modules |
| Endpoints configuration | 1.2 MB | Single `endpoints.json` |
| SSL certs, vendored libs | ~0.5 MB | Required |
| **Total** | **~111 MB** | |

### Target State (Single Service Package)

| Component | Size | Notes |
|-----------|------|-------|
| Core modules | ~1.2 MB | Required |
| Single service (e.g., DynamoDB) | ~616 KB | Just what you need |
| Minimal endpoints | ~50 KB | Service-specific only |
| SSL certs, vendored libs | ~0.5 MB | Required |
| **Total** | **~2.5 MB** | **97.7% reduction** |

---

## Architectural Overview

### Design Principles

1. **Backwards Compatibility First**: All existing boto3/botocore APIs must continue to work unchanged
2. **Opt-in Modularization**: Default installation includes everything (no breaking changes)
3. **Lazy Loading**: Load service data only when a client is created
4. **Pluggable Service Packs**: Allow installing only needed services
5. **Test Preservation**: All 37,000+ lines of tests must pass

### Key Interfaces That Must Remain Stable

```python
# Session API (boto3 depends on this)
botocore.session.get_session()
botocore.session.Session
Session.create_client(service_name, region_name=None, ...)

# Client API
client.get_paginator(operation_name)
client.can_paginate(operation_name)
client.get_waiter(waiter_name)
client.exceptions.*
client.meta.service_model
client.meta.events

# Configuration
botocore.config.Config

# Exceptions
botocore.exceptions.ClientError
botocore.exceptions.BotoCoreError

# Testing utilities
botocore.stub.Stubber
botocore.stub.ANY
```

---

## Phase 1: Service Data Extraction Architecture

**Goal**: Create infrastructure to load service definitions from separate packages while maintaining backwards compatibility.

### 1.1 Create Service Data Provider Interface

Create an abstraction layer that allows service definitions to come from multiple sources.

**New file**: `botocore/dataprovider.py`

```python
class ServiceDataProvider(ABC):
    """Abstract base class for service data providers."""

    @abstractmethod
    def has_service(self, service_name: str) -> bool:
        """Check if this provider can serve the given service."""
        pass

    @abstractmethod
    def load_service_data(self, service_name: str, type_name: str,
                          api_version: str = None) -> dict:
        """Load service definition data."""
        pass

    @abstractmethod
    def list_available_services(self, type_name: str) -> List[str]:
        """List all services this provider can serve."""
        pass

class FileSystemDataProvider(ServiceDataProvider):
    """Loads service data from filesystem (current behavior)."""
    pass

class PackageDataProvider(ServiceDataProvider):
    """Loads service data from installed Python packages."""
    pass

class CompositeDataProvider(ServiceDataProvider):
    """Combines multiple providers, checking in order."""
    pass
```

### 1.2 Modify Loader to Use Data Providers

Update `botocore/loaders.py` to support pluggable data sources:

```python
class Loader:
    def __init__(self, ..., data_providers=None):
        if data_providers is None:
            # Default: filesystem provider with builtin data
            data_providers = [
                FileSystemDataProvider(self.BUILTIN_DATA_PATH),
                FileSystemDataProvider(self.CUSTOMER_DATA_PATH),
            ]
        self._data_providers = CompositeDataProvider(data_providers)
```

### 1.3 Service Package Structure

Each service can be packaged separately:

```
motocore-dynamodb/
├── motocore_dynamodb/
│   ├── __init__.py           # Registers with botocore
│   └── data/
│       └── dynamodb/
│           └── 2012-08-10/
│               ├── service-2.json
│               ├── paginators-1.json
│               ├── waiters-2.json
│               └── endpoint-rule-set-1.json
├── pyproject.toml
└── README.md
```

### 1.4 Service Discovery via Entry Points

Services register themselves using Python entry points:

```toml
# pyproject.toml for motocore-dynamodb
[project.entry-points."motocore.services"]
dynamodb = "motocore_dynamodb:register"
```

```python
# motocore_dynamodb/__init__.py
import os
from botocore.dataprovider import PackageDataProvider

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data')

def register():
    """Return a data provider for this service package."""
    return PackageDataProvider(DATA_PATH, services=['dynamodb'])
```

### 1.5 Backwards Compatibility

The main `motocore` package continues to include all services:

```toml
# pyproject.toml for motocore (full package)
[project]
name = "motocore"
dependencies = []  # No dependencies by default

[project.optional-dependencies]
# Full installation includes all services
full = ["motocore-ec2", "motocore-s3", "motocore-dynamodb", ...]

# Service bundles
compute = ["motocore-ec2", "motocore-lambda", "motocore-ecs", ...]
database = ["motocore-dynamodb", "motocore-rds", ...]
storage = ["motocore-s3", "motocore-glacier", ...]
```

**For Lambda users**:
```bash
pip install motocore motocore-dynamodb
```

---

## Phase 2: Handler Modularization Strategy

**Goal**: Extract service-specific handlers from the monolithic `handlers.py` into lazy-loaded modules.

### 2.1 Current Handler Analysis

The `BUILTIN_HANDLERS` list (handlers.py:1451-1727) contains 150+ handlers for:

| Service | Handler Count | Purpose |
|---------|---------------|---------|
| S3 | 40+ | SSE, presigned URLs, bucket validation |
| EC2 | 10+ | Base64 encoding, presigned URLs |
| RDS/Neptune/DocDB | 15+ | Presigned URLs for cross-region |
| Glacier | 8+ | Checksums, account ID injection |
| Cognito | 4+ | Signature disabling |
| STS | 2+ | Signature disabling |
| Route53 | 2+ | ID fixing |
| IAM | 1+ | Policy JSON decoding |
| Others | ~20 | Various service-specific handlers |
| **Core** | ~10 | Retry, recursion detection, signing |

### 2.2 Handler Module Structure

Create a `handlers/` package with service-specific modules:

```
botocore/handlers/
├── __init__.py           # Core handlers + lazy loading
├── _core.py              # Always-loaded handlers (retry, signing, recursion)
├── _registry.py          # Handler registration infrastructure
├── s3.py                 # S3-specific handlers
├── ec2.py                # EC2-specific handlers
├── rds.py                # RDS/Neptune/DocDB handlers
├── glacier.py            # Glacier handlers
├── cognito.py            # Cognito handlers
├── sts.py                # STS handlers
├── route53.py            # Route53 handlers
├── iam.py                # IAM handlers
└── ...
```

### 2.3 Lazy Handler Loading

Implement lazy handler registration that only loads handlers when a service client is created:

```python
# botocore/handlers/_registry.py

# Map of service name to handler module
SERVICE_HANDLER_MODULES = {
    's3': 'botocore.handlers.s3',
    's3control': 'botocore.handlers.s3',
    'ec2': 'botocore.handlers.ec2',
    'rds': 'botocore.handlers.rds',
    'neptune': 'botocore.handlers.rds',
    'docdb': 'botocore.handlers.rds',
    'glacier': 'botocore.handlers.glacier',
    'cognito-identity': 'botocore.handlers.cognito',
    'sts': 'botocore.handlers.sts',
    'route53': 'botocore.handlers.route53',
    'iam': 'botocore.handlers.iam',
    # ... etc
}

_loaded_handlers = set()

def register_service_handlers(events, service_name):
    """Lazily load and register handlers for a specific service."""
    if service_name in _loaded_handlers:
        return

    module_name = SERVICE_HANDLER_MODULES.get(service_name)
    if module_name:
        module = importlib.import_module(module_name)
        module.register_handlers(events, service_name)
        _loaded_handlers.add(service_name)
```

### 2.4 Handler Module Template

Each service handler module follows this pattern:

```python
# botocore/handlers/s3.py
"""S3-specific event handlers."""

from botocore.handlers._core import (
    REGISTER_FIRST, REGISTER_LAST,
    convert_body_to_file_like_object,
    # ... other shared utilities
)

def validate_bucket_name(params, **kwargs):
    """Validate S3 bucket name format."""
    # ... implementation
    pass

def add_expect_header(params, **kwargs):
    """Add Expect: 100-continue header for large uploads."""
    # ... implementation
    pass

# Service-specific handlers list
S3_HANDLERS = [
    ('before-parameter-build.s3.UploadPart', convert_body_to_file_like_object, REGISTER_LAST),
    ('before-parameter-build.s3.PutObject', convert_body_to_file_like_object, REGISTER_LAST),
    ('before-parameter-build.s3', validate_bucket_name),
    ('before-call.s3', add_expect_header),
    # ... all S3 handlers
]

def register_handlers(events, service_name):
    """Register all S3 handlers with the event system."""
    for handler_args in S3_HANDLERS:
        events.register(*handler_args)
```

### 2.5 Integration with Client Creation

Modify `Session.create_client()` to trigger lazy handler loading:

```python
# botocore/session.py

def create_client(self, service_name, ...):
    # ... existing code ...

    # Lazy load service-specific handlers
    from botocore.handlers._registry import register_service_handlers
    register_service_handlers(self._events, service_name)

    # ... continue with client creation ...
```

### 2.6 Backwards Compatibility for Handlers

The monolithic `handlers.py` continues to work but delegates to modules:

```python
# botocore/handlers.py (modified)

# Import core handlers that are always needed
from botocore.handlers._core import (
    handle_service_name_alias,
    add_recursion_detection_header,
    set_operation_specific_signer,
    # ... other core handlers
)

# For backwards compatibility, BUILTIN_HANDLERS still exists
# but now only contains core handlers
BUILTIN_HANDLERS = [
    ('choose-service-name', handle_service_name_alias),
    ('before-call', add_recursion_detection_header),
    ('choose-signer', set_operation_specific_signer),
    # ... only core handlers that apply to ALL services
]
```

---

## Phase 3: Lazy Loading Infrastructure

**Goal**: Defer loading of service models, endpoint data, and handlers until actually needed.

### 3.1 Enhanced Lazy Component Loading

Expand the existing `ComponentLocator` pattern:

```python
# botocore/session.py

class Session:
    def _register_components(self):
        # Current components (already lazy)
        self._components.lazy_register_component(
            'data_loader',
            lambda: create_loader(self._get_data_path())
        )

        # New: Lazy service model cache
        self._components.lazy_register_component(
            'service_model_cache',
            lambda: ServiceModelCache(self._get_component('data_loader'))
        )

        # New: Lazy endpoint data (per-service)
        self._components.lazy_register_component(
            'endpoint_data_provider',
            lambda: LazyEndpointDataProvider(self._get_component('data_loader'))
        )
```

### 3.2 Service Model Cache

Implement a cache that loads models on-demand:

```python
# botocore/modelcache.py

class ServiceModelCache:
    """Caches service models, loading them lazily on first access."""

    def __init__(self, loader):
        self._loader = loader
        self._cache = {}
        self._service_list = None

    def get_service_model(self, service_name, api_version=None):
        cache_key = (service_name, api_version)
        if cache_key not in self._cache:
            model_data = self._loader.load_service_model(
                service_name, 'service-2', api_version
            )
            self._cache[cache_key] = ServiceModel(model_data, service_name)
        return self._cache[cache_key]

    def list_services(self):
        """List available services without loading any models."""
        if self._service_list is None:
            self._service_list = self._loader.list_available_services('service-2')
        return self._service_list
```

### 3.3 Lazy Endpoint Resolution

Split endpoint data loading per-service:

```python
# botocore/regions.py (modified)

class LazyEndpointResolver:
    """Resolves endpoints, loading service-specific data lazily."""

    def __init__(self, loader):
        self._loader = loader
        self._partition_data = None
        self._service_endpoints = {}

    def _load_partition_data(self):
        """Load only partition definitions (minimal)."""
        if self._partition_data is None:
            self._partition_data = self._loader.load_data('partitions')
        return self._partition_data

    def _get_service_endpoints(self, service_name):
        """Load endpoint data for a specific service."""
        if service_name not in self._service_endpoints:
            # Try to load from service-specific endpoint file
            try:
                data = self._loader.load_service_model(
                    service_name, 'endpoint-rule-set-1'
                )
            except DataNotFoundError:
                data = None
            self._service_endpoints[service_name] = data
        return self._service_endpoints[service_name]
```

### 3.4 Deferred Import Strategy

Use deferred imports for heavyweight modules:

```python
# botocore/session.py

# Instead of:
# import botocore.credentials

# Use:
def _get_credentials_module():
    import botocore.credentials
    return botocore.credentials

class Session:
    def get_credentials(self):
        credentials_module = _get_credentials_module()
        return credentials_module.get_credentials(self)
```

---

## Phase 4: Build Tooling for Service-Specific Packages

**Goal**: Create tooling to generate and maintain individual service packages.

### 4.1 Package Generator Script

Create a script to generate service packages:

```
scripts/
├── generate_service_package.py    # Generate a single service package
├── generate_all_packages.py       # Generate all 415 service packages
├── service_package_template/      # Template for service packages
│   ├── pyproject.toml.template
│   ├── README.md.template
│   └── __init__.py.template
└── service_groups.json            # Service groupings for bundles
```

### 4.2 Package Generator Implementation

```python
# scripts/generate_service_package.py

import os
import shutil
import json
from pathlib import Path

def generate_service_package(service_name, output_dir, botocore_root):
    """Generate a standalone package for a single AWS service."""

    # Create package directory
    package_name = f"motocore-{service_name}"
    package_dir = Path(output_dir) / package_name
    package_dir.mkdir(parents=True, exist_ok=True)

    # Copy service data
    service_data_src = Path(botocore_root) / 'botocore' / 'data' / service_name
    service_data_dst = package_dir / f'motocore_{service_name.replace("-", "_")}' / 'data' / service_name
    shutil.copytree(service_data_src, service_data_dst)

    # Generate __init__.py with registration
    generate_init_py(package_dir, service_name)

    # Generate pyproject.toml
    generate_pyproject_toml(package_dir, service_name)

    # Generate README
    generate_readme(package_dir, service_name)

def generate_pyproject_toml(package_dir, service_name):
    """Generate pyproject.toml for service package."""
    package_name = f"motocore-{service_name}"
    module_name = f"motocore_{service_name.replace('-', '_')}"

    content = f'''
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "1.0.0"
description = "AWS {service_name.upper()} service definitions for motocore"
requires-python = ">=3.9"
dependencies = ["motocore-core>=1.0.0"]

[project.entry-points."motocore.services"]
{service_name} = "{module_name}:register"

[tool.setuptools.package-data]
"*" = ["data/**/*.json", "data/**/*.json.gz"]
'''

    (package_dir / 'pyproject.toml').write_text(content.strip())
```

### 4.3 Service Bundle Definitions

```json
// scripts/service_groups.json
{
    "bundles": {
        "compute": ["ec2", "lambda", "ecs", "eks", "batch", "lightsail"],
        "database": ["dynamodb", "rds", "redshift", "elasticache", "neptune", "docdb"],
        "storage": ["s3", "s3control", "glacier", "efs", "fsx"],
        "serverless": ["lambda", "dynamodb", "apigateway", "sqs", "sns", "stepfunctions"],
        "ml": ["sagemaker", "bedrock", "rekognition", "comprehend", "translate"],
        "security": ["iam", "kms", "secretsmanager", "sts", "cognito-idp"]
    },
    "shared_handlers": {
        "dynamodb": [],
        "s3": ["s3", "s3control"],
        "rds": ["rds", "neptune", "docdb"]
    }
}
```

### 4.4 CI/CD Integration

Add GitHub Actions workflow for package generation:

```yaml
# .github/workflows/generate-packages.yml
name: Generate Service Packages

on:
  push:
    paths:
      - 'botocore/data/**'
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Generate all service packages
        run: python scripts/generate_all_packages.py --output dist/packages

      - name: Upload packages
        uses: actions/upload-artifact@v4
        with:
          name: service-packages
          path: dist/packages/
```

---

## Phase 5: Core Package Definition

**Goal**: Define the minimal core package that all service packages depend on.

### 5.1 Core Package Contents

```
motocore-core/
├── motocore/
│   ├── __init__.py
│   ├── session.py
│   ├── client.py
│   ├── config.py
│   ├── credentials.py
│   ├── auth.py
│   ├── endpoint.py
│   ├── hooks.py
│   ├── loaders.py
│   ├── model.py
│   ├── parsers.py
│   ├── serialize.py
│   ├── paginate.py
│   ├── waiter.py
│   ├── stub.py
│   ├── exceptions.py
│   ├── compat.py
│   ├── utils.py
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── _core.py
│   │   └── _registry.py
│   ├── dataprovider.py      # New: data provider abstraction
│   ├── retries/             # Retry infrastructure
│   ├── crt/                 # CRT auth support
│   ├── docs/                # Documentation generation
│   ├── vendored/            # Vendored dependencies
│   └── cacert.pem           # SSL certificates
├── pyproject.toml
└── README.md
```

### 5.2 Core Package pyproject.toml

```toml
[project]
name = "motocore-core"
version = "1.0.0"
description = "Core botocore functionality for AWS SDK"
requires-python = ">=3.9"
dependencies = [
    "jmespath>=0.7.1,<2.0.0",
    "python-dateutil>=2.1,<3.0.0",
    "urllib3>=1.25.4,<3"
]

[project.optional-dependencies]
crt = ["awscrt==0.22.0"]
```

---

## Phase 6: Endpoint Data Optimization

**Goal**: Reduce the 1.2 MB `endpoints.json` to service-specific chunks.

### 6.1 Endpoint Data Split Strategy

Split the monolithic `endpoints.json` into:

1. **Partition definitions** (~10 KB): AWS partition structure
2. **Per-service endpoint rules** (~2-5 KB each): Service-specific routing

```
botocore/data/
├── _partitions.json              # Partition structure only
├── dynamodb/
│   └── 2012-08-10/
│       ├── service-2.json
│       ├── endpoint-rule-set-1.json   # Already exists per-service
│       └── endpoints.json              # NEW: Service-specific endpoints
```

### 6.2 Endpoint Loader Modification

```python
# botocore/regions.py

class ModularEndpointResolver:
    def __init__(self, loader):
        self._loader = loader
        self._partitions = None
        self._service_endpoints_cache = {}

    def resolve(self, service_name, region_name):
        # Load partitions (small, ~10KB)
        if self._partitions is None:
            self._partitions = self._loader.load_data('_partitions')

        # Load service-specific endpoint data
        service_endpoints = self._get_service_endpoints(service_name)

        # Resolve using partition + service data
        return self._do_resolve(service_endpoints, region_name)
```

---

## Implementation Roadmap

### Milestone 1: Foundation (Weeks 1-2)

**Tasks**:
- [ ] Create `botocore/dataprovider.py` with abstract base class
- [ ] Implement `FileSystemDataProvider` wrapping current behavior
- [ ] Implement `CompositeDataProvider` for chaining
- [ ] Update `Loader` to use data providers
- [ ] Add entry point discovery for service packages
- [ ] Write unit tests for new data provider infrastructure

**Test Verification**:
```bash
python scripts/ci/run-tests unit/test_loaders.py
python scripts/ci/run-tests functional/test_loaders.py
```

### Milestone 2: Handler Modularization (Weeks 3-4)

**Tasks**:
- [ ] Create `botocore/handlers/` package structure
- [ ] Extract core handlers to `_core.py`
- [ ] Create handler registry in `_registry.py`
- [ ] Extract S3 handlers to `s3.py`
- [ ] Extract EC2 handlers to `ec2.py`
- [ ] Extract RDS/Neptune/DocDB handlers to `rds.py`
- [ ] Extract remaining service handlers
- [ ] Implement lazy handler loading in `Session.create_client()`
- [ ] Update `handlers.py` for backwards compatibility

**Test Verification**:
```bash
python scripts/ci/run-tests unit/test_handlers.py
python scripts/ci/run-tests functional/test_s3.py
python scripts/ci/run-tests functional/test_client.py
```

### Milestone 3: Package Generator (Weeks 5-6)

**Tasks**:
- [ ] Create package generator script
- [ ] Create package templates
- [ ] Generate test service package (DynamoDB)
- [ ] Test installation and usage
- [ ] Create bundle definitions
- [ ] Add CI/CD workflow for package generation

**Test Verification**:
```bash
# Generate DynamoDB package
python scripts/generate_service_package.py dynamodb ./dist

# Install and test
pip install ./dist/motocore-dynamodb
python -c "import boto3; ddb = boto3.client('dynamodb')"
```

### Milestone 4: Core Package Split (Weeks 7-8)

**Tasks**:
- [ ] Define core package contents
- [ ] Create motocore-core package structure
- [ ] Update dependencies between packages
- [ ] Test core + single service installation
- [ ] Verify boto3 compatibility

**Test Verification**:
```bash
# Fresh environment test
pip install motocore-core motocore-dynamodb boto3
python -c "
import boto3
ddb = boto3.resource('dynamodb')
print('Success!')
"
```

### Milestone 5: Endpoint Optimization (Week 9)

**Tasks**:
- [ ] Create partition extraction script
- [ ] Generate per-service endpoint files
- [ ] Implement `ModularEndpointResolver`
- [ ] Update loaders to use split endpoints
- [ ] Benchmark endpoint resolution

**Test Verification**:
```bash
python scripts/ci/run-tests unit/test_regions.py
python scripts/ci/run-tests unit/test_endpoint_provider.py
```

### Milestone 6: Full Integration (Week 10)

**Tasks**:
- [ ] Generate all 415 service packages
- [ ] Run full test suite
- [ ] Performance benchmarking
- [ ] Documentation updates
- [ ] Migration guide for users

**Test Verification**:
```bash
# Full test suite
python scripts/ci/run-tests --with-cov unit/ functional/

# Lambda cold start benchmark
python scripts/benchmark_cold_start.py
```

---

## Test Strategy

### Test Categories and Coverage

| Category | File Count | Lines | Strategy |
|----------|------------|-------|----------|
| Unit tests | 46 | ~37,400 | Run after each phase |
| Functional | 100 | ~16,200 | Run after each phase |
| Integration | 20 | ~2,000 | Run at milestones |
| Acceptance | 5 | ~1,000 | Run at milestones |

### Critical Test Files (Must Pass at All Times)

1. `tests/unit/test_client.py` - Client creation
2. `tests/unit/test_session.py` - Session initialization
3. `tests/unit/test_credentials.py` - Credential chain
4. `tests/unit/test_handlers.py` - Event handlers
5. `tests/unit/test_loaders.py` - Model loading
6. `tests/unit/test_parsers.py` - Response parsing
7. `tests/functional/test_client.py` - End-to-end client
8. `tests/functional/test_credentials.py` - Credential flows
9. `tests/functional/test_s3.py` - S3 operations

### New Tests Required

```python
# tests/unit/test_dataprovider.py
class TestServiceDataProvider:
    def test_filesystem_provider_loads_service(self): ...
    def test_package_provider_loads_service(self): ...
    def test_composite_provider_chains_correctly(self): ...
    def test_entry_point_discovery(self): ...

# tests/unit/test_lazy_handlers.py
class TestLazyHandlerLoading:
    def test_handlers_loaded_on_client_creation(self): ...
    def test_handlers_not_loaded_until_needed(self): ...
    def test_handler_isolation_between_services(self): ...

# tests/functional/test_modular_install.py
class TestModularInstallation:
    def test_core_only_fails_for_unknown_service(self): ...
    def test_core_plus_service_works(self): ...
    def test_service_package_registers_correctly(self): ...
```

### Test Execution Commands

```bash
# Quick validation (run frequently during development)
python scripts/ci/run-tests unit/test_loaders.py unit/test_handlers.py

# Full unit test suite
python scripts/ci/run-tests unit/

# Full test suite with coverage
python scripts/ci/run-tests --with-cov unit/ functional/

# Parallel execution for speed
python scripts/ci/run-tests --with-xdist unit/ functional/
```

---

## Backwards Compatibility Guarantees

### Guaranteed Stable (MUST NOT CHANGE)

1. **Public Functions**
   - `botocore.session.get_session()`
   - `botocore.session.Session.create_client()`
   - All parameters and return types

2. **Public Classes**
   - `botocore.session.Session`
   - `botocore.config.Config`
   - `botocore.exceptions.ClientError`
   - `botocore.stub.Stubber`

3. **Client Interface**
   - `client.<operation>()`
   - `client.get_paginator()`
   - `client.get_waiter()`
   - `client.can_paginate()`
   - `client.exceptions.*`
   - `client.meta.*`

4. **Module Exports**
   - `botocore.UNSIGNED`
   - `botocore.xform_name()`
   - `botocore.__version__`

### Compatibility Testing

```python
# tests/test_backwards_compat.py

def test_session_api_unchanged():
    """Verify Session API matches expected signature."""
    import inspect
    from botocore.session import Session

    sig = inspect.signature(Session.create_client)
    params = list(sig.parameters.keys())

    assert 'service_name' in params
    assert 'region_name' in params
    assert 'api_version' in params
    assert 'endpoint_url' in params
    # ... verify all expected parameters

def test_client_meta_interface():
    """Verify client.meta has expected attributes."""
    session = Session()
    client = session.create_client('dynamodb', region_name='us-east-1')

    assert hasattr(client.meta, 'service_model')
    assert hasattr(client.meta, 'region_name')
    assert hasattr(client.meta, 'endpoint_url')
    assert hasattr(client.meta, 'config')
    assert hasattr(client.meta, 'events')
```

---

## Performance Benchmarks

### Target Metrics

| Metric | Current | Target | Notes |
|--------|---------|--------|-------|
| Package size (full) | 111 MB | 111 MB | No change for full install |
| Package size (DynamoDB only) | 111 MB | ~2.5 MB | 97.7% reduction |
| Import time (full) | ~500ms | ~500ms | No change for full |
| Import time (DynamoDB only) | ~500ms | ~50ms | 90% reduction |
| Lambda cold start | ~2-3s | ~300ms | Significant improvement |
| First client creation | ~100ms | ~80ms | Slight improvement |

### Benchmark Script

```python
# scripts/benchmark_cold_start.py

import subprocess
import time
import statistics

def benchmark_import(package_config):
    """Benchmark import time for a package configuration."""
    code = '''
import time
start = time.perf_counter()
import boto3
client = boto3.client('dynamodb', region_name='us-east-1')
end = time.perf_counter()
print(f"{end - start:.4f}")
'''

    times = []
    for _ in range(10):
        result = subprocess.run(
            ['python', '-c', code],
            capture_output=True,
            text=True,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        )
        times.append(float(result.stdout.strip()))

    return {
        'mean': statistics.mean(times),
        'median': statistics.median(times),
        'stdev': statistics.stdev(times),
        'min': min(times),
        'max': max(times)
    }
```

---

## Risk Mitigation

### Risk 1: Breaking boto3 Compatibility

**Mitigation**:
- Comprehensive compatibility test suite
- Run boto3 test suite against modular botocore
- Staged rollout with feature flags

### Risk 2: Performance Regression

**Mitigation**:
- Benchmark at each milestone
- Profile critical paths
- Maintain performance test suite

### Risk 3: Handler Registration Order Changes

**Mitigation**:
- Document handler execution order
- Test handler interaction scenarios
- Maintain explicit registration order in modular handlers

### Risk 4: Service Package Version Drift

**Mitigation**:
- Automated package generation from source
- Version pinning between core and service packages
- CI/CD validation of package combinations

---

## Appendix A: Service Handler Mapping

| Service | Handler Module | Handler Count |
|---------|---------------|---------------|
| s3, s3control | `handlers/s3.py` | 40+ |
| ec2 | `handlers/ec2.py` | 10+ |
| rds, neptune, docdb | `handlers/rds.py` | 15+ |
| glacier | `handlers/glacier.py` | 8+ |
| cognito-identity | `handlers/cognito.py` | 4+ |
| sts | `handlers/sts.py` | 2+ |
| route53 | `handlers/route53.py` | 2+ |
| iam | `handlers/iam.py` | 1+ |
| cloudformation | `handlers/cloudformation.py` | 1+ |
| lambda | `handlers/lambda_.py` | 1+ |
| apigateway | `handlers/apigateway.py` | 1+ |
| polly | `handlers/polly.py` | 1+ |
| machinelearning | `handlers/machinelearning.py` | 1+ |
| cloudsearchdomain | `handlers/cloudsearchdomain.py` | 1+ |
| mturk | `handlers/mturk.py` | 1+ |
| lex-runtime-v2 | `handlers/lex.py` | 1+ |
| bedrock-runtime | `handlers/bedrock.py` | 1+ |
| dsql | `handlers/dsql.py` | 1+ |
| autoscaling | `handlers/autoscaling.py` | 1+ |

## Appendix B: Top 30 Services by Size

| Rank | Service | Size | Potential Savings |
|------|---------|------|-------------------|
| 1 | ec2 | 9.2 MB | High |
| 2 | cloudfront | 4.6 MB | High |
| 3 | sagemaker | 2.3 MB | High |
| 4 | s3 | 2.2 MB | High |
| 5 | quicksight | 1.7 MB | High |
| 6 | rds | 1.6 MB | High |
| 7 | connect | 1.5 MB | High |
| 8 | securityhub | 1.2 MB | Medium |
| 9 | medialive | 1.2 MB | Medium |
| 10 | glue | 1.2 MB | Medium |
| ... | ... | ... | ... |
| 27 | dynamodb | 616 KB | **Target for Lambda** |

## Appendix C: Package Naming Convention

```
motocore              # Meta-package, depends on motocore-full
motocore-core         # Core functionality, no service data
motocore-full         # All services (backwards compat)
motocore-{service}    # Individual service (e.g., motocore-dynamodb)
motocore-{bundle}     # Service bundles (e.g., motocore-serverless)
```

---

## Conclusion

This modularization plan provides a path to reduce botocore's footprint from 111 MB to ~2.5 MB for single-service use cases while maintaining complete backwards compatibility with boto3 and all existing tests. The phased approach allows for incremental validation and reduces risk.

The key innovations are:
1. **Data Provider Abstraction**: Pluggable sources for service definitions
2. **Lazy Handler Loading**: Service-specific handlers loaded on demand
3. **Entry Point Discovery**: Service packages self-register via Python entry points
4. **Endpoint Splitting**: Per-service endpoint data instead of monolithic file

This will dramatically improve Lambda cold start times and reduce deployment package sizes for serverless applications.
