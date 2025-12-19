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

"""Generate standalone packages for individual AWS services.

This script creates minimal, self-contained Python packages for individual
AWS services that can be installed alongside motocore-core. This allows
Lambda functions and other size-constrained environments to install only
the services they need.

Usage:
    python generate_service_package.py dynamodb ./dist
    python generate_service_package.py s3 ./dist --include-handlers
    python generate_service_package.py --list-services
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Set


# Handlers that are shared between services
SHARED_HANDLER_SERVICES = {
    'rds': ['rds', 'neptune', 'docdb'],
    's3': ['s3', 's3control', 's3-control'],
}

# Services that share handler modules
HANDLER_MODULE_MAPPING = {
    's3': '_s3',
    's3control': '_s3',
    's3-control': '_s3',
    'ec2': '_ec2',
    'rds': '_rds',
    'neptune': '_rds',
    'docdb': '_rds',
    'glacier': '_glacier',
    'route53': '_route53',
    'iam': '_iam',
    'sts': '_sts',
    'cognito-identity': '_sts',
    'cloudformation': '_cloudformation',
    'machinelearning': '_machinelearning',
    'iot-data': '_iot',
    'cloudsearchdomain': '_cloudsearch',
    'mturk': '_mturk',
    'sqs': '_sqs',
    'lex-runtime-v2': '_lex',
    'qbusiness': '_qbusiness',
    'bedrock-runtime': '_bedrock',
    'bedrock-agentcore': '_bedrock',
    'polly': '_polly',
    'autoscaling': '_autoscaling',
    'apigateway': '_apigateway',
    'lambda': '_lambda',
    'dsql': '_dsql',
    'socialmessaging': '_socialmessaging',
}


def get_botocore_root() -> Path:
    """Get the root directory of the botocore source."""
    # This script is in scripts/, so go up one level
    return Path(__file__).parent.parent


def get_service_data_path(botocore_root: Path) -> Path:
    """Get the path to service data files."""
    return botocore_root / 'botocore' / 'data'


def list_available_services(botocore_root: Path) -> List[str]:
    """List all available services in botocore."""
    data_path = get_service_data_path(botocore_root)
    services = []

    for item in data_path.iterdir():
        if item.is_dir() and not item.name.startswith('_'):
            # Check if it has service-2.json in any version folder
            for version_dir in item.iterdir():
                if version_dir.is_dir():
                    service_file = version_dir / 'service-2.json'
                    if service_file.exists():
                        services.append(item.name)
                        break

    return sorted(services)


def get_service_size(botocore_root: Path, service_name: str) -> int:
    """Get the total size of a service's data files in bytes."""
    service_path = get_service_data_path(botocore_root) / service_name
    if not service_path.exists():
        return 0

    total_size = 0
    for root, dirs, files in os.walk(service_path):
        for file in files:
            file_path = Path(root) / file
            total_size += file_path.stat().st_size

    return total_size


def format_size(size_bytes: int) -> str:
    """Format size in bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def normalize_service_name(service_name: str) -> str:
    """Normalize service name for use in package names."""
    return service_name.replace('_', '-').lower()


def get_module_name(service_name: str) -> str:
    """Get Python module name from service name."""
    return f"motocore_{service_name.replace('-', '_').replace('.', '_')}"


def generate_init_py(service_name: str, module_name: str) -> str:
    """Generate __init__.py content for a service package."""
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
AWS {service_name.upper()} service definitions for motocore.

This package provides service model data for the {service_name} service.
It should be installed alongside motocore-core to enable {service_name} support.

Usage:
    import boto3
    client = boto3.client('{service_name}')
"""

import os
from pathlib import Path

from botocore.dataprovider import PackageDataProvider

__version__ = '1.0.0'
__service__ = '{service_name}'

# Path to the service data files
DATA_PATH = Path(__file__).parent / 'data'


def get_data_provider():
    """Return a data provider for this service package.

    This function is called by botocore via entry points to discover
    and register this service package.

    Returns:
        A PackageDataProvider instance for this service.
    """
    return PackageDataProvider(
        str(DATA_PATH),
        services=['{service_name}']
    )


# For backwards compatibility and direct imports
def register():
    """Register this service package with botocore.

    This is an alias for get_data_provider() for compatibility
    with different entry point configurations.
    """
    return get_data_provider()
'''


def generate_pyproject_toml(
    service_name: str,
    module_name: str,
    version: str = '1.0.0',
    motocore_version: str = '>=1.0.0',
) -> str:
    """Generate pyproject.toml content for a service package."""
    package_name = f"motocore-{normalize_service_name(service_name)}"

    return f'''[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "{version}"
description = "AWS {service_name.upper()} service definitions for motocore"
readme = "README.md"
license = {{text = "Apache License 2.0"}}
requires-python = ">=3.9"
keywords = ["aws", "botocore", "{service_name}"]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "motocore-core{motocore_version}",
]

[project.entry-points."botocore.services"]
{service_name} = "{module_name}:register"

[tool.setuptools]
packages = ["{module_name}"]

[tool.setuptools.package-data]
"{module_name}" = ["data/**/*.json", "data/**/*.json.gz"]
'''


def generate_readme(service_name: str, size_info: str) -> str:
    """Generate README.md content for a service package."""
    package_name = f"motocore-{normalize_service_name(service_name)}"

    return f'''# {package_name}

AWS {service_name.upper()} service definitions for motocore.

## Overview

This package provides the service model data needed to use AWS {service_name.upper()}
with botocore/boto3. It is designed for use in size-constrained environments
like AWS Lambda where the full botocore package (111 MB) is too large.

**Package size: {size_info}**

## Installation

```bash
pip install motocore-core {package_name}
```

## Usage

```python
import boto3

# Create a {service_name} client
client = boto3.client('{service_name}', region_name='us-east-1')

# Use the client as normal
# response = client.some_operation(...)
```

## Requirements

- Python >= 3.9
- motocore-core >= 1.0.0

## License

Apache License 2.0
'''


def copy_service_data(
    botocore_root: Path,
    service_name: str,
    dest_path: Path,
) -> None:
    """Copy service data files to the destination package."""
    source_path = get_service_data_path(botocore_root) / service_name
    dest_data_path = dest_path / 'data' / service_name

    if not source_path.exists():
        raise ValueError(f"Service data not found: {service_name}")

    # Copy the entire service directory
    shutil.copytree(source_path, dest_data_path)


def generate_service_package(
    service_name: str,
    output_dir: Path,
    botocore_root: Optional[Path] = None,
    version: str = '1.0.0',
    include_handlers: bool = False,
) -> Path:
    """Generate a standalone package for a single AWS service.

    Args:
        service_name: The name of the AWS service (e.g., 'dynamodb', 's3')
        output_dir: Directory where the package will be created
        botocore_root: Root directory of botocore source (auto-detected if None)
        version: Package version string
        include_handlers: Whether to include service-specific handlers

    Returns:
        Path to the generated package directory
    """
    if botocore_root is None:
        botocore_root = get_botocore_root()

    # Normalize names
    service_name = normalize_service_name(service_name)
    package_name = f"motocore-{service_name}"
    module_name = get_module_name(service_name)

    # Create package directory
    package_dir = output_dir / package_name
    module_dir = package_dir / module_name

    # Clean up existing package
    if package_dir.exists():
        shutil.rmtree(package_dir)

    module_dir.mkdir(parents=True)

    # Copy service data
    copy_service_data(botocore_root, service_name, module_dir)

    # Get size info
    size = get_service_size(botocore_root, service_name)
    size_info = format_size(size)

    # Generate package files
    (module_dir / '__init__.py').write_text(
        generate_init_py(service_name, module_name)
    )

    (package_dir / 'pyproject.toml').write_text(
        generate_pyproject_toml(service_name, module_name, version)
    )

    (package_dir / 'README.md').write_text(
        generate_readme(service_name, size_info)
    )

    # Optionally copy handlers
    if include_handlers and service_name in HANDLER_MODULE_MAPPING:
        handler_module = HANDLER_MODULE_MAPPING[service_name]
        copy_service_handlers(botocore_root, handler_module, module_dir)

    print(f"Generated package: {package_name} ({size_info})")
    return package_dir


def copy_service_handlers(
    botocore_root: Path,
    handler_module: str,
    dest_path: Path,
) -> None:
    """Copy service-specific handler module to the package."""
    handlers_dir = botocore_root / 'botocore' / 'handlers'
    source_file = handlers_dir / f'{handler_module}.py'

    if source_file.exists():
        dest_handlers = dest_path / 'handlers'
        dest_handlers.mkdir(exist_ok=True)

        # Copy the handler module
        shutil.copy(source_file, dest_handlers / f'{handler_module}.py')

        # Create __init__.py for handlers
        (dest_handlers / '__init__.py').write_text(
            '# Service-specific handlers\n'
        )


def generate_all_packages(
    output_dir: Path,
    botocore_root: Optional[Path] = None,
    version: str = '1.0.0',
    services: Optional[List[str]] = None,
) -> List[Path]:
    """Generate packages for all (or specified) services.

    Args:
        output_dir: Directory where packages will be created
        botocore_root: Root directory of botocore source
        version: Package version string
        services: List of services to generate (all if None)

    Returns:
        List of paths to generated package directories
    """
    if botocore_root is None:
        botocore_root = get_botocore_root()

    if services is None:
        services = list_available_services(botocore_root)

    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for service in services:
        try:
            package_dir = generate_service_package(
                service, output_dir, botocore_root, version
            )
            generated.append(package_dir)
        except Exception as e:
            print(f"Error generating {service}: {e}", file=sys.stderr)

    return generated


def main():
    parser = argparse.ArgumentParser(
        description='Generate standalone packages for AWS services'
    )
    parser.add_argument(
        'service',
        nargs='?',
        help='Service name to generate package for (e.g., dynamodb, s3)'
    )
    parser.add_argument(
        'output_dir',
        nargs='?',
        default='./dist/packages',
        help='Output directory for generated packages'
    )
    parser.add_argument(
        '--list-services',
        action='store_true',
        help='List all available services and exit'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Generate packages for all services'
    )
    parser.add_argument(
        '--version',
        default='1.0.0',
        help='Package version (default: 1.0.0)'
    )
    parser.add_argument(
        '--include-handlers',
        action='store_true',
        help='Include service-specific handlers in package'
    )
    parser.add_argument(
        '--show-sizes',
        action='store_true',
        help='Show service data sizes'
    )

    args = parser.parse_args()
    botocore_root = get_botocore_root()

    if args.list_services or args.show_sizes:
        services = list_available_services(botocore_root)

        if args.show_sizes:
            print(f"{'Service':<30} {'Size':>10}")
            print('-' * 42)

            # Sort by size
            sizes = [
                (s, get_service_size(botocore_root, s))
                for s in services
            ]
            sizes.sort(key=lambda x: x[1], reverse=True)

            for service, size in sizes:
                print(f"{service:<30} {format_size(size):>10}")

            total = sum(s for _, s in sizes)
            print('-' * 42)
            print(f"{'Total':<30} {format_size(total):>10}")
        else:
            print(f"Available services ({len(services)}):")
            for service in services:
                print(f"  {service}")
        return

    if args.all:
        output_dir = Path(args.output_dir)
        packages = generate_all_packages(
            output_dir, botocore_root, args.version
        )
        print(f"\nGenerated {len(packages)} packages in {output_dir}")
        return

    if not args.service:
        parser.error('Service name required (or use --list-services or --all)')

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generate_service_package(
        args.service,
        output_dir,
        botocore_root,
        args.version,
        args.include_handlers,
    )


if __name__ == '__main__':
    main()
