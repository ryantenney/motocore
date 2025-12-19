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

"""Generate bundle packages for groups of related AWS services.

This script creates packages that bundle multiple related AWS services
together, optimized for common use cases like serverless applications,
Lambda with DynamoDB, etc.

Usage:
    python generate_bundle_package.py serverless ./dist
    python generate_bundle_package.py lambda-dynamodb ./dist
    python generate_bundle_package.py --list-bundles
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from generate_service_package import (
    copy_service_data,
    format_size,
    get_botocore_root,
    get_service_data_path,
    get_service_size,
    HANDLER_MODULE_MAPPING,
)


def load_bundle_config(config_path: Optional[Path] = None) -> Dict:
    """Load bundle configuration from JSON file."""
    if config_path is None:
        config_path = Path(__file__).parent / 'service_groups.json'

    with open(config_path) as f:
        return json.load(f)


def get_bundle_services(bundle_name: str, config: Dict) -> List[str]:
    """Get the list of services in a bundle."""
    bundles = config.get('bundles', {})
    bundle = bundles.get(bundle_name)

    if bundle is None:
        raise ValueError(f"Unknown bundle: {bundle_name}")

    return bundle.get('services', [])


def get_bundle_description(bundle_name: str, config: Dict) -> str:
    """Get the description of a bundle."""
    bundles = config.get('bundles', {})
    bundle = bundles.get(bundle_name)

    if bundle is None:
        return f"Bundle of AWS services for {bundle_name}"

    return bundle.get('description', f"Bundle of AWS services for {bundle_name}")


def normalize_bundle_name(bundle_name: str) -> str:
    """Normalize bundle name for use in package names."""
    return bundle_name.replace('_', '-').lower()


def get_bundle_module_name(bundle_name: str) -> str:
    """Get Python module name from bundle name."""
    return f"motocore_bundle_{bundle_name.replace('-', '_').replace('.', '_')}"


def calculate_bundle_size(
    botocore_root: Path,
    services: List[str],
) -> int:
    """Calculate total size of all services in a bundle."""
    total = 0
    seen_services = set()

    for service in services:
        if service not in seen_services:
            total += get_service_size(botocore_root, service)
            seen_services.add(service)

    return total


def get_required_handlers(services: List[str]) -> Set[str]:
    """Get the set of handler modules required for the services."""
    handlers = set()
    for service in services:
        if service in HANDLER_MODULE_MAPPING:
            handlers.add(HANDLER_MODULE_MAPPING[service])
    return handlers


def generate_bundle_init_py(
    bundle_name: str,
    services: List[str],
    module_name: str,
    description: str,
) -> str:
    """Generate __init__.py content for a bundle package."""
    services_list = ', '.join(f"'{s}'" for s in services)
    services_doc = ', '.join(services)

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
{description}

This bundle package provides service model data for: {services_doc}

It should be installed alongside motocore-core to enable these services.

Usage:
    import boto3
    client = boto3.client('dynamodb')  # or any service in the bundle
"""

import os
from pathlib import Path

from botocore.dataprovider import PackageDataProvider

__version__ = '1.0.0'
__bundle__ = '{bundle_name}'
__services__ = [{services_list}]

# Path to the service data files
DATA_PATH = Path(__file__).parent / 'data'


def get_data_provider():
    """Return a data provider for this bundle package.

    This function is called by botocore via entry points to discover
    and register service packages.

    Returns:
        A PackageDataProvider instance for all services in this bundle.
    """
    return PackageDataProvider(
        str(DATA_PATH),
        services=__services__
    )


# For backwards compatibility and direct imports
def register():
    """Register this bundle package with botocore.

    This is an alias for get_data_provider() for compatibility
    with different entry point configurations.
    """
    return get_data_provider()
'''


def generate_bundle_pyproject_toml(
    bundle_name: str,
    services: List[str],
    module_name: str,
    description: str,
    version: str = '1.0.0',
    motocore_version: str = '>=1.0.0',
) -> str:
    """Generate pyproject.toml content for a bundle package."""
    package_name = f"motocore-bundle-{normalize_bundle_name(bundle_name)}"

    # Generate entry points for each service
    entry_points = '\n'.join(
        f'{service} = "{module_name}:register"'
        for service in services
    )

    return f'''[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "{version}"
description = "{description}"
readme = "README.md"
license = {{text = "Apache License 2.0"}}
requires-python = ">=3.9"
keywords = ["aws", "botocore", "{bundle_name}"]
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
{entry_points}

[tool.setuptools]
packages = ["{module_name}"]

[tool.setuptools.package-data]
"{module_name}" = ["data/**/*.json", "data/**/*.json.gz"]
'''


def generate_bundle_readme(
    bundle_name: str,
    services: List[str],
    description: str,
    size_info: str,
) -> str:
    """Generate README.md content for a bundle package."""
    package_name = f"motocore-bundle-{normalize_bundle_name(bundle_name)}"
    services_list = '\n'.join(f'- {s}' for s in services)

    return f'''# {package_name}

{description}

## Overview

This bundle package provides service model data for multiple AWS services,
optimized for a common use case. It is designed for use in size-constrained
environments like AWS Lambda where the full botocore package (111 MB) is too large.

**Bundle size: {size_info}**

## Included Services

{services_list}

## Installation

```bash
pip install motocore-core {package_name}
```

## Usage

```python
import boto3

# Create clients for any service in the bundle
dynamodb = boto3.client('dynamodb', region_name='us-east-1')
sqs = boto3.client('sqs', region_name='us-east-1')
# etc.
```

## Requirements

- Python >= 3.9
- motocore-core >= 1.0.0

## License

Apache License 2.0
'''


def copy_bundle_handlers(
    botocore_root: Path,
    handler_modules: Set[str],
    dest_path: Path,
) -> None:
    """Copy service-specific handler modules for all services in bundle."""
    if not handler_modules:
        return

    handlers_dir = botocore_root / 'botocore' / 'handlers'
    dest_handlers = dest_path / 'handlers'
    dest_handlers.mkdir(exist_ok=True)

    for handler_module in handler_modules:
        source_file = handlers_dir / f'{handler_module}.py'
        if source_file.exists():
            shutil.copy(source_file, dest_handlers / f'{handler_module}.py')

    # Create __init__.py for handlers
    (dest_handlers / '__init__.py').write_text(
        '# Service-specific handlers for bundle\n'
    )


def generate_bundle_package(
    bundle_name: str,
    output_dir: Path,
    botocore_root: Optional[Path] = None,
    config: Optional[Dict] = None,
    version: str = '1.0.0',
    include_handlers: bool = False,
) -> Path:
    """Generate a bundle package for multiple AWS services.

    Args:
        bundle_name: The name of the bundle (e.g., 'serverless', 'lambda-dynamodb')
        output_dir: Directory where the package will be created
        botocore_root: Root directory of botocore source (auto-detected if None)
        config: Bundle configuration dict (loaded from file if None)
        version: Package version string
        include_handlers: Whether to include service-specific handlers

    Returns:
        Path to the generated package directory
    """
    if botocore_root is None:
        botocore_root = get_botocore_root()

    if config is None:
        config = load_bundle_config()

    # Get bundle info
    services = get_bundle_services(bundle_name, config)
    description = get_bundle_description(bundle_name, config)

    # Normalize names
    bundle_name_normalized = normalize_bundle_name(bundle_name)
    package_name = f"motocore-bundle-{bundle_name_normalized}"
    module_name = get_bundle_module_name(bundle_name)

    # Create package directory
    package_dir = output_dir / package_name
    module_dir = package_dir / module_name

    # Clean up existing package
    if package_dir.exists():
        shutil.rmtree(package_dir)

    module_dir.mkdir(parents=True)

    # Copy service data for all services
    for service in services:
        try:
            copy_service_data(botocore_root, service, module_dir)
        except ValueError as e:
            print(f"Warning: {e}", file=sys.stderr)

    # Calculate total size
    size = calculate_bundle_size(botocore_root, services)
    size_info = format_size(size)

    # Generate package files
    (module_dir / '__init__.py').write_text(
        generate_bundle_init_py(bundle_name, services, module_name, description)
    )

    (package_dir / 'pyproject.toml').write_text(
        generate_bundle_pyproject_toml(
            bundle_name, services, module_name, description, version
        )
    )

    (package_dir / 'README.md').write_text(
        generate_bundle_readme(bundle_name, services, description, size_info)
    )

    # Optionally copy handlers
    if include_handlers:
        handler_modules = get_required_handlers(services)
        copy_bundle_handlers(botocore_root, handler_modules, module_dir)

    print(f"Generated bundle: {package_name} ({size_info}) - {len(services)} services")
    return package_dir


def list_bundles(config: Dict) -> None:
    """Print all available bundles."""
    bundles = config.get('bundles', {})
    botocore_root = get_botocore_root()

    print(f"Available bundles ({len(bundles)}):\n")
    print(f"{'Bundle':<20} {'Services':>8} {'Size':>10}  Description")
    print('-' * 80)

    for name, info in sorted(bundles.items()):
        services = info.get('services', [])
        description = info.get('description', '')[:35]
        size = calculate_bundle_size(botocore_root, services)

        print(f"{name:<20} {len(services):>8} {format_size(size):>10}  {description}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate bundle packages for AWS service groups'
    )
    parser.add_argument(
        'bundle',
        nargs='?',
        help='Bundle name to generate package for (e.g., serverless, lambda-dynamodb)'
    )
    parser.add_argument(
        'output_dir',
        nargs='?',
        default='./dist/packages',
        help='Output directory for generated packages'
    )
    parser.add_argument(
        '--list-bundles',
        action='store_true',
        help='List all available bundles and exit'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Generate packages for all bundles'
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
        '--config',
        type=Path,
        help='Path to bundle configuration file'
    )

    args = parser.parse_args()
    config = load_bundle_config(args.config)

    if args.list_bundles:
        list_bundles(config)
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        bundles = config.get('bundles', {})
        generated = []
        for bundle_name in bundles:
            try:
                package_dir = generate_bundle_package(
                    bundle_name,
                    output_dir,
                    config=config,
                    version=args.version,
                    include_handlers=args.include_handlers,
                )
                generated.append(package_dir)
            except Exception as e:
                print(f"Error generating {bundle_name}: {e}", file=sys.stderr)

        print(f"\nGenerated {len(generated)} bundles in {output_dir}")
        return

    if not args.bundle:
        parser.error('Bundle name required (or use --list-bundles or --all)')

    generate_bundle_package(
        args.bundle,
        output_dir,
        config=config,
        version=args.version,
        include_handlers=args.include_handlers,
    )


if __name__ == '__main__':
    main()
