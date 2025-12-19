#!/usr/bin/env python
# Copyright 2012-2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

"""Generate the motocore-core package.

This script creates the core motocore package that contains all the
essential functionality needed by service packages. It excludes service-
specific data files and handlers, keeping only what's required for the
SDK to function.

Usage:
    python generate_core_package.py ./dist
    python generate_core_package.py ./dist --version 1.0.0
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Set

from generate_service_package import format_size, get_botocore_root


# Core Python modules that must be included
CORE_MODULES = [
    '__init__.py',
    'args.py',
    'auth.py',
    'awsrequest.py',
    'cacert.pem',
    'client.py',
    'compat.py',
    'compress.py',
    'config.py',
    'configloader.py',
    'configprovider.py',
    'context.py',
    'credentials.py',
    'dataprovider.py',
    'discovery.py',
    'endpoint.py',
    'endpoint_provider.py',
    'errorfactory.py',
    'eventstream.py',
    'exceptions.py',
    'handlers.py',
    'history.py',
    'hooks.py',
    'httpchecksum.py',
    'httpsession.py',
    'loaders.py',
    'model.py',
    'modelcache.py',
    'monitoring.py',
    'paginate.py',
    'parsers.py',
    'plugin.py',
    'regions.py',
    'response.py',
    'retryhandler.py',
    'serialize.py',
    'session.py',
    'signers.py',
    'stub.py',
    'tokens.py',
    'translate.py',
    'useragent.py',
    'utils.py',
    'validate.py',
    'waiter.py',
]

# Subdirectories that must be included in full
CORE_SUBDIRECTORIES = [
    'crt',
    'docs',
    'retries',
    'vendored',
]

# Core data files needed for operation (not service-specific)
CORE_DATA_FILES = [
    '_retry.json',
    'endpoints.json',
    'partitions.json',
    'sdk-default-configuration.json',
]

# Handler files to include (core handlers only)
CORE_HANDLER_FILES = [
    '__init__.py',
    '_core.py',
    '_registry.py',
]


def calculate_directory_size(path: Path) -> int:
    """Calculate total size of a directory."""
    total = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            file_path = Path(root) / file
            total += file_path.stat().st_size
    return total


def copy_core_modules(
    botocore_root: Path,
    dest_botocore: Path,
) -> None:
    """Copy core Python modules to destination."""
    src_botocore = botocore_root / 'botocore'

    for module in CORE_MODULES:
        src_path = src_botocore / module
        if src_path.exists():
            shutil.copy2(src_path, dest_botocore / module)
        else:
            print(f"Warning: Module not found: {module}", file=sys.stderr)


def copy_core_subdirectories(
    botocore_root: Path,
    dest_botocore: Path,
) -> None:
    """Copy core subdirectories to destination."""
    src_botocore = botocore_root / 'botocore'

    for subdir in CORE_SUBDIRECTORIES:
        src_path = src_botocore / subdir
        if src_path.exists():
            dest_path = dest_botocore / subdir
            shutil.copytree(
                src_path,
                dest_path,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc')
            )
        else:
            print(f"Warning: Subdirectory not found: {subdir}", file=sys.stderr)


def generate_core_handlers_init() -> str:
    """Generate a core-only handlers/__init__.py."""
    return '''# Copyright 2012-2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

"""Builtin event handlers - Core package version.

This is a minimal version of the handlers module that only includes
core handlers. Service-specific handlers are loaded dynamically via
the handler registry when a service client is created.
"""

# Re-export core components
from botocore.handlers._core import (
    REGISTER_FIRST,
    REGISTER_LAST,
    _resolve_sigv4a_region,
    _set_auth_scheme_preference_signer,
    _should_prefer_bearer_auth,
    add_expect_header,
    add_recursion_detection_header,
    add_retry_headers,
    disable_signing,
    generate_idempotent_uuid,
    get_bearer_auth_supported_services,
    handle_service_name_alias,
    inject_api_version_header_if_needed,
    set_operation_specific_signer,
)

from botocore.handlers._registry import (
    SERVICE_HANDLER_MODULES,
    get_service_handlers,
    register_lazy_handlers,
)

# BUILTIN_HANDLERS contains only core handlers in the core package.
# Service-specific handlers are registered dynamically via the registry.
from botocore.handlers._core import CORE_HANDLERS


def _build_builtin_handlers():
    """Build the BUILTIN_HANDLERS list from core handlers."""
    handlers = []

    for item in CORE_HANDLERS:
        if len(item) == 2:
            handlers.append((item[0], item[1]))
        else:
            handlers.append((item[0], item[1], item[2]))

    return handlers


BUILTIN_HANDLERS = _build_builtin_handlers()
'''


def copy_core_handlers(
    botocore_root: Path,
    dest_botocore: Path,
) -> None:
    """Copy core handler files to destination."""
    src_handlers = botocore_root / 'botocore' / 'handlers'
    dest_handlers = dest_botocore / 'handlers'
    dest_handlers.mkdir(exist_ok=True)

    # Copy _core.py and _registry.py
    for handler_file in ['_core.py', '_registry.py']:
        src_path = src_handlers / handler_file
        if src_path.exists():
            shutil.copy2(src_path, dest_handlers / handler_file)
        else:
            print(f"Warning: Handler file not found: {handler_file}", file=sys.stderr)

    # Generate a core-only __init__.py
    (dest_handlers / '__init__.py').write_text(generate_core_handlers_init())


def copy_core_data(
    botocore_root: Path,
    dest_botocore: Path,
) -> None:
    """Copy core data files to destination."""
    src_data = botocore_root / 'botocore' / 'data'
    dest_data = dest_botocore / 'data'
    dest_data.mkdir(exist_ok=True)

    for data_file in CORE_DATA_FILES:
        src_path = src_data / data_file
        if src_path.exists():
            shutil.copy2(src_path, dest_data / data_file)
        else:
            print(f"Warning: Data file not found: {data_file}", file=sys.stderr)


def generate_core_init_py(version: str) -> str:
    """Generate modified __init__.py for core package."""
    return f'''# Copyright 2012-2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

"""
Motocore - Core AWS SDK functionality.

This is the core package that provides essential AWS SDK functionality.
Install service packages (e.g., motocore-dynamodb) to add specific service support.
"""

import logging
import os
import re

__version__ = '{version}'

# Public API imports
from botocore.session import Session
from botocore.exceptions import BotoCoreError, ClientError


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


# Configure default logging
log = logging.getLogger('botocore')
log.addHandler(NullHandler())


def xform_name(name, sep='_', _xform_cache={{}}):
    """Convert camelCase to snake_case."""
    if name in _xform_cache:
        return _xform_cache[name]

    s1 = re.sub('(.)([A-Z][a-z]+)', r'\\1' + sep + r'\\2', name)
    transformed = re.sub('([a-z0-9])([A-Z])', r'\\1' + sep + r'\\2', s1).lower()
    _xform_cache[name] = transformed
    return transformed


# Singleton for unsigned requests
class _UNSIGNED:
    def __repr__(self):
        return 'UNSIGNED'

UNSIGNED = _UNSIGNED()


class ScalarTypes:
    SCALAR_TYPES = ('string', 'integer', 'boolean', 'timestamp', 'float', 'double')


# Re-export for backwards compatibility
def get_session(env_vars=None):
    """Get a default session."""
    return Session(env_vars)
'''


def generate_pyproject_toml(version: str) -> str:
    """Generate pyproject.toml for core package."""
    return f'''[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "motocore-core"
version = "{version}"
description = "Core AWS SDK functionality for Python (modular botocore)"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.9"
keywords = ["aws", "botocore", "sdk"]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet",
]
dependencies = [
    "jmespath>=0.7.1,<2.0.0",
    "python-dateutil>=2.1,<3.0.0",
    "urllib3>=1.25.4,<3",
]

[project.optional-dependencies]
crt = ["awscrt>=0.22.0"]

[project.urls]
Homepage = "https://github.com/boto/botocore"
Documentation = "https://botocore.amazonaws.com/v1/documentation/api/latest/index.html"

[tool.setuptools.packages.find]
where = ["."]
include = ["botocore*"]

[tool.setuptools.package-data]
botocore = ["cacert.pem", "data/*.json"]
'''


def generate_readme() -> str:
    """Generate README.md for core package."""
    return '''# motocore-core

Core AWS SDK functionality for Python (modular botocore).

## Overview

This package provides the core functionality needed to interact with AWS services.
It is designed for size-constrained environments like AWS Lambda where the full
botocore package (111 MB) is too large.

Install this package along with individual service packages (e.g., `motocore-dynamodb`)
to use specific AWS services.

## Installation

```bash
# Install core + DynamoDB support
pip install motocore-core motocore-dynamodb

# Install core + S3 support
pip install motocore-core motocore-s3

# Install core + serverless bundle
pip install motocore-core motocore-bundle-serverless
```

## Usage

```python
import boto3

# Create a DynamoDB client (requires motocore-dynamodb)
dynamodb = boto3.client('dynamodb', region_name='us-east-1')

# Use the client as normal
response = dynamodb.list_tables()
```

## Package Structure

- **motocore-core**: Core SDK functionality (this package)
- **motocore-{service}**: Individual service packages (e.g., motocore-dynamodb)
- **motocore-bundle-{name}**: Service bundles for common use cases

## Requirements

- Python >= 3.9
- jmespath >= 0.7.1
- python-dateutil >= 2.1
- urllib3 >= 1.25.4

## Optional Dependencies

- awscrt >= 0.22.0 (for CRT-based features)

## License

Apache License 2.0
'''


def generate_meta_package_pyproject(
    package_name: str,
    description: str,
    dependencies: List[str],
    version: str = '1.0.0',
) -> str:
    """Generate pyproject.toml for a meta-package."""
    deps = ',\n    '.join(f'"{d}"' for d in dependencies)

    return f'''[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "{version}"
description = "{description}"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.9"
keywords = ["aws", "botocore", "sdk"]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
]
dependencies = [
    {deps}
]
'''


def generate_core_package(
    output_dir: Path,
    botocore_root: Optional[Path] = None,
    version: str = '1.0.0',
) -> Path:
    """Generate the motocore-core package.

    Args:
        output_dir: Directory where the package will be created
        botocore_root: Root directory of botocore source (auto-detected if None)
        version: Package version string

    Returns:
        Path to the generated package directory
    """
    if botocore_root is None:
        botocore_root = get_botocore_root()

    # Create package directory structure
    package_dir = output_dir / 'motocore-core'
    dest_botocore = package_dir / 'botocore'

    # Clean up existing package
    if package_dir.exists():
        shutil.rmtree(package_dir)

    dest_botocore.mkdir(parents=True)

    # Copy core components
    copy_core_modules(botocore_root, dest_botocore)
    copy_core_subdirectories(botocore_root, dest_botocore)
    copy_core_handlers(botocore_root, dest_botocore)
    copy_core_data(botocore_root, dest_botocore)

    # Generate package files
    (package_dir / 'pyproject.toml').write_text(generate_pyproject_toml(version))
    (package_dir / 'README.md').write_text(generate_readme())

    # Calculate size
    size = calculate_directory_size(package_dir)
    print(f"Generated motocore-core ({format_size(size)})")

    return package_dir


def generate_full_meta_package(
    output_dir: Path,
    botocore_root: Optional[Path] = None,
    version: str = '1.0.0',
) -> Path:
    """Generate motocore-full meta-package that includes all services.

    Args:
        output_dir: Directory where the package will be created
        botocore_root: Root directory of botocore source
        version: Package version string

    Returns:
        Path to the generated package directory
    """
    if botocore_root is None:
        botocore_root = get_botocore_root()

    from generate_service_package import list_available_services

    # Get all available services
    services = list_available_services(botocore_root)

    # Create dependency list
    dependencies = ['motocore-core>=' + version]
    dependencies.extend(f'motocore-{s}>={version}' for s in services)

    # Create package directory
    package_dir = output_dir / 'motocore-full'
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    # Generate pyproject.toml
    pyproject = generate_meta_package_pyproject(
        'motocore-full',
        'Full AWS SDK for Python (all services) - modular botocore',
        dependencies,
        version,
    )
    (package_dir / 'pyproject.toml').write_text(pyproject)

    # Generate README
    readme = f'''# motocore-full

Full AWS SDK for Python with all {len(services)} services.

This is a meta-package that installs motocore-core and all service packages.
For size-constrained environments, install only the services you need instead.

## Installation

```bash
pip install motocore-full
```

This is equivalent to installing motocore-core plus all individual service packages.

## License

Apache License 2.0
'''
    (package_dir / 'README.md').write_text(readme)

    print(f"Generated motocore-full ({len(services)} services)")
    return package_dir


def generate_motocore_meta_package(
    output_dir: Path,
    version: str = '1.0.0',
) -> Path:
    """Generate motocore meta-package (points to motocore-full for backwards compat).

    Args:
        output_dir: Directory where the package will be created
        version: Package version string

    Returns:
        Path to the generated package directory
    """
    # Create package directory
    package_dir = output_dir / 'motocore'
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    # Generate pyproject.toml
    pyproject = generate_meta_package_pyproject(
        'motocore',
        'AWS SDK for Python - modular botocore (backwards compatible)',
        [f'motocore-full>={version}'],
        version,
    )
    (package_dir / 'pyproject.toml').write_text(pyproject)

    # Generate README
    readme = '''# motocore

AWS SDK for Python - modular botocore.

This is a backwards-compatible meta-package that installs the full motocore
package with all services.

## For Size-Constrained Environments

If you're deploying to AWS Lambda or another size-constrained environment,
install only what you need:

```bash
# Install core + specific services
pip install motocore-core motocore-dynamodb motocore-s3

# Or install a bundle
pip install motocore-core motocore-bundle-serverless
```

## Full Installation

```bash
pip install motocore
```

This installs all services (equivalent to the original botocore).

## License

Apache License 2.0
'''
    (package_dir / 'README.md').write_text(readme)

    print("Generated motocore (meta-package)")
    return package_dir


def main():
    parser = argparse.ArgumentParser(
        description='Generate the motocore-core package and meta-packages'
    )
    parser.add_argument(
        'output_dir',
        nargs='?',
        default='./dist/packages',
        help='Output directory for generated packages'
    )
    parser.add_argument(
        '--version',
        default='1.0.0',
        help='Package version (default: 1.0.0)'
    )
    parser.add_argument(
        '--core-only',
        action='store_true',
        help='Generate only motocore-core (skip meta-packages)'
    )
    parser.add_argument(
        '--with-meta',
        action='store_true',
        help='Also generate motocore and motocore-full meta-packages'
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    botocore_root = get_botocore_root()

    # Generate core package
    generate_core_package(output_dir, botocore_root, args.version)

    # Generate meta-packages if requested
    if args.with_meta:
        generate_full_meta_package(output_dir, botocore_root, args.version)
        generate_motocore_meta_package(output_dir, args.version)


if __name__ == '__main__':
    main()
