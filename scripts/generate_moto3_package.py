#!/usr/bin/env python3
"""
Generate moto3 wrapper packages.

moto3 is a thin wrapper around boto3 that depends on motocore packages
instead of the full botocore, providing a clean single-install experience
for size-constrained environments like AWS Lambda.

Package types:
- moto3: Base package wrapping boto3, depends on motocore-core
- moto3-{service}: Service package, depends on moto3 + motocore-{service}
- moto3-bundle-{name}: Bundle package, depends on moto3 + motocore-bundle-{name}
- moto3-full: Full package with all services (for compatibility testing)

Usage:
    # Generate base moto3 package
    python scripts/generate_moto3_package.py --base

    # Generate service package
    python scripts/generate_moto3_package.py --service dynamodb

    # Generate bundle package
    python scripts/generate_moto3_package.py --bundle serverless

    # Generate all packages
    python scripts/generate_moto3_package.py --all

    # List available services and bundles
    python scripts/generate_moto3_package.py --list
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

from botocore.loaders import Loader

# moto3 version - should track boto3 version compatibility
MOTO3_VERSION = "1.0.0"
BOTO3_VERSION = ">=1.35.0,<2.0.0"
MOTOCORE_VERSION = ">=1.0.0"


def get_available_services() -> list[str]:
    """Get list of available AWS services from botocore data."""
    loader = Loader()
    return sorted(loader.list_available_services('service-2'))


def load_bundles() -> dict:
    """Load bundle configurations from service_groups.json."""
    groups_file = SCRIPT_DIR / 'service_groups.json'
    if groups_file.exists():
        with open(groups_file) as f:
            data = json.load(f)
            return data.get('bundles', {})
    return {}


def generate_base_package(output_dir: Path) -> Path:
    """
    Generate the base moto3 package.

    This package:
    - Wraps boto3's public API
    - Depends on boto3 and motocore-core
    - Provides the foundation for service packages
    """
    package_dir = output_dir / 'moto3'
    package_dir.mkdir(parents=True, exist_ok=True)

    # Create moto3/__init__.py - re-exports boto3's API
    init_content = '''"""
moto3 - Lightweight boto3 wrapper using modular motocore.

This package provides the same API as boto3 but depends on motocore-core
instead of the full botocore package, reducing deployment size significantly.

Usage:
    import moto3 as boto3

    # Or use directly
    from moto3 import client, resource, Session

    dynamodb = moto3.client('dynamodb')
    s3 = moto3.resource('s3')
"""

# Re-export boto3's public API
from boto3 import (
    # Core functions
    client,
    resource,

    # Session management
    Session,
    setup_default_session,
    set_stream_logger,

    # NullHandler for logging
    NullHandler,

    # Version info
    __version__ as boto3_version,
)

# Also expose commonly used exceptions via botocore
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    PartialCredentialsError,
    NoRegionError,
    EndpointConnectionError,
)

__version__ = "''' + MOTO3_VERSION + '''"
__all__ = [
    'client',
    'resource',
    'Session',
    'setup_default_session',
    'set_stream_logger',
    'NullHandler',
    'boto3_version',
    '__version__',
    # Exceptions
    'BotoCoreError',
    'ClientError',
    'NoCredentialsError',
    'PartialCredentialsError',
    'NoRegionError',
    'EndpointConnectionError',
]
'''

    (package_dir / 'moto3' / '__init__.py').parent.mkdir(parents=True, exist_ok=True)
    with open(package_dir / 'moto3' / '__init__.py', 'w') as f:
        f.write(init_content)

    # Create pyproject.toml
    pyproject_content = f'''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "moto3"
version = "{MOTO3_VERSION}"
description = "Lightweight boto3 wrapper using modular motocore for reduced package size"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.8"
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "boto3{BOTO3_VERSION}",
    "motocore-core{MOTOCORE_VERSION}",
]

[project.urls]
Homepage = "https://github.com/ryantenney/motocore"
Repository = "https://github.com/ryantenney/motocore"

[tool.setuptools.packages.find]
include = ["moto3*"]
'''

    with open(package_dir / 'pyproject.toml', 'w') as f:
        f.write(pyproject_content)

    # Create README.md
    readme_content = '''# moto3

Lightweight boto3 wrapper using modular motocore for reduced package size.

## Installation

```bash
pip install moto3
```

For specific services, install the service package:

```bash
pip install moto3-dynamodb
```

## Usage

Use moto3 as a drop-in replacement for boto3:

```python
import moto3 as boto3

dynamodb = boto3.client('dynamodb')
response = dynamodb.list_tables()
```

Or import directly:

```python
from moto3 import client, resource, Session

dynamodb = client('dynamodb')
s3 = resource('s3')
```

## Package Size

| Package | Size |
|---------|------|
| boto3 + botocore | ~113 MB |
| moto3 + moto3-dynamodb | ~4 MB |

## Available Packages

- `moto3` - Base package (requires motocore-core)
- `moto3-{service}` - Individual service packages
- `moto3-bundle-{name}` - Pre-configured bundles for common use cases

See [motocore](https://github.com/ryantenney/motocore) for the full list.
'''

    with open(package_dir / 'README.md', 'w') as f:
        f.write(readme_content)

    return package_dir


def generate_service_package(service_name: str, output_dir: Path) -> Path:
    """
    Generate a moto3 service package.

    These packages provide a convenient single install that includes
    moto3 base + the corresponding motocore service package.
    """
    package_name = f'moto3-{service_name}'
    package_dir = output_dir / package_name
    package_dir.mkdir(parents=True, exist_ok=True)

    # Create minimal __init__.py (just version info)
    pkg_module_name = package_name.replace('-', '_')
    module_dir = package_dir / pkg_module_name
    module_dir.mkdir(parents=True, exist_ok=True)

    init_content = f'''"""
moto3-{service_name} - moto3 with {service_name} service support.

This is a convenience package that installs:
- moto3 (boto3 wrapper)
- motocore-{service_name} (service data)

Usage:
    import moto3 as boto3
    client = boto3.client('{service_name}')
"""

__version__ = "{MOTO3_VERSION}"
__service__ = "{service_name}"
'''

    with open(module_dir / '__init__.py', 'w') as f:
        f.write(init_content)

    # Create pyproject.toml
    pyproject_content = f'''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "{MOTO3_VERSION}"
description = "moto3 with {service_name} service support"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.8"
dependencies = [
    "moto3>={MOTO3_VERSION}",
    "motocore-{service_name}{MOTOCORE_VERSION}",
]

[project.urls]
Homepage = "https://github.com/ryantenney/motocore"

[tool.setuptools.packages.find]
include = ["{pkg_module_name}*"]
'''

    with open(package_dir / 'pyproject.toml', 'w') as f:
        f.write(pyproject_content)

    # Create README.md
    readme_content = f'''# {package_name}

moto3 with {service_name} service support.

## Installation

```bash
pip install {package_name}
```

## Usage

```python
import moto3 as boto3

client = boto3.client('{service_name}')
```

This package installs:
- `moto3` - boto3 wrapper
- `motocore-{service_name}` - {service_name} service data

## Size

This package is significantly smaller than installing boto3 + botocore.
'''

    with open(package_dir / 'README.md', 'w') as f:
        f.write(readme_content)

    return package_dir


def generate_bundle_package(bundle_name: str, services: list[str], output_dir: Path,
                           description: str = None) -> Path:
    """
    Generate a moto3 bundle package.

    Bundles provide multiple related services in a single install.
    """
    package_name = f'moto3-bundle-{bundle_name}'
    package_dir = output_dir / package_name
    package_dir.mkdir(parents=True, exist_ok=True)

    # Create minimal __init__.py
    pkg_module_name = package_name.replace('-', '_')
    module_dir = package_dir / pkg_module_name
    module_dir.mkdir(parents=True, exist_ok=True)

    services_list = ', '.join(f'"{s}"' for s in services)
    init_content = f'''"""
moto3-bundle-{bundle_name} - moto3 with {bundle_name} services bundle.

Included services: {', '.join(services)}

Usage:
    import moto3 as boto3

    # Use any of the bundled services
    dynamodb = boto3.client('dynamodb')
    s3 = boto3.client('s3')
"""

__version__ = "{MOTO3_VERSION}"
__bundle__ = "{bundle_name}"
__services__ = [{services_list}]
'''

    with open(module_dir / '__init__.py', 'w') as f:
        f.write(init_content)

    # Build dependencies list
    deps = [f'    "moto3>={MOTO3_VERSION}"']
    deps.append(f'    "motocore-bundle-{bundle_name}{MOTOCORE_VERSION}"')
    deps_str = ',\n'.join(deps)

    desc = description or f"moto3 with {bundle_name} services bundle"

    # Create pyproject.toml
    pyproject_content = f'''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "{MOTO3_VERSION}"
description = "{desc}"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.8"
dependencies = [
{deps_str},
]

[project.urls]
Homepage = "https://github.com/ryantenney/motocore"

[tool.setuptools.packages.find]
include = ["{pkg_module_name}*"]
'''

    with open(package_dir / 'pyproject.toml', 'w') as f:
        f.write(pyproject_content)

    # Create README.md
    services_md = '\n'.join(f'- {s}' for s in services)
    readme_content = f'''# {package_name}

{desc}

## Installation

```bash
pip install {package_name}
```

## Included Services

{services_md}

## Usage

```python
import moto3 as boto3

# Use any of the bundled services
dynamodb = boto3.client('dynamodb')
lambda_client = boto3.client('lambda')
```

## Size

This bundle is significantly smaller than installing boto3 + botocore.
'''

    with open(package_dir / 'README.md', 'w') as f:
        f.write(readme_content)

    return package_dir


def generate_full_package(output_dir: Path) -> Path:
    """
    Generate moto3-full package with all services.

    This is useful for compatibility testing or when you need all services
    but want to use the moto3 API.
    """
    package_name = 'moto3-full'
    package_dir = output_dir / package_name
    package_dir.mkdir(parents=True, exist_ok=True)

    # Create minimal __init__.py
    module_dir = package_dir / 'moto3_full'
    module_dir.mkdir(parents=True, exist_ok=True)

    init_content = f'''"""
moto3-full - moto3 with all AWS services.

This package includes all available AWS services. For size-constrained
environments, consider using service-specific packages instead.

Usage:
    import moto3 as boto3
    client = boto3.client('any-service')
"""

__version__ = "{MOTO3_VERSION}"
'''

    with open(module_dir / '__init__.py', 'w') as f:
        f.write(init_content)

    # Create pyproject.toml - depends on motocore-full
    pyproject_content = f'''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "{MOTO3_VERSION}"
description = "moto3 with all AWS services"
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.8"
dependencies = [
    "moto3>={MOTO3_VERSION}",
    "motocore-full{MOTOCORE_VERSION}",
]

[project.urls]
Homepage = "https://github.com/ryantenney/motocore"

[tool.setuptools.packages.find]
include = ["moto3_full*"]
'''

    with open(package_dir / 'pyproject.toml', 'w') as f:
        f.write(pyproject_content)

    # Create README.md
    readme_content = '''# moto3-full

moto3 with all AWS services included.

## Installation

```bash
pip install moto3-full
```

## Usage

```python
import moto3 as boto3

# Any AWS service is available
client = boto3.client('any-service')
```

## Note

This package includes all AWS services and is similar in size to boto3 + botocore.
For size-constrained environments like AWS Lambda, consider using service-specific
packages like `moto3-dynamodb` or bundles like `moto3-bundle-serverless`.
'''

    with open(package_dir / 'README.md', 'w') as f:
        f.write(readme_content)

    return package_dir


def main():
    parser = argparse.ArgumentParser(
        description='Generate moto3 wrapper packages for modular motocore'
    )
    parser.add_argument(
        '--base',
        action='store_true',
        help='Generate base moto3 package'
    )
    parser.add_argument(
        '--service',
        type=str,
        help='Generate package for a specific service (e.g., dynamodb)'
    )
    parser.add_argument(
        '--bundle',
        type=str,
        help='Generate a bundle package (e.g., serverless)'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Generate moto3-full package with all services'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Generate all packages (base, all services, all bundles, full)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available services and bundles'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='dist/moto3',
        help='Output directory for generated packages'
    )

    args = parser.parse_args()

    services = get_available_services()
    bundles = load_bundles()

    if args.list:
        print("Available services:")
        for s in services:
            print(f"  - {s}")
        print(f"\nTotal: {len(services)} services")
        print("\nAvailable bundles:")
        for name, config in bundles.items():
            svcs = ', '.join(config.get('services', [])[:5])
            if len(config.get('services', [])) > 5:
                svcs += ', ...'
            print(f"  - {name}: {svcs}")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []

    if args.base or args.all:
        pkg_dir = generate_base_package(output_dir)
        print(f"Generated: moto3 -> {pkg_dir}")
        generated.append('moto3')

    if args.service:
        if args.service not in services:
            print(f"Error: Unknown service '{args.service}'")
            print(f"Use --list to see available services")
            sys.exit(1)
        pkg_dir = generate_service_package(args.service, output_dir)
        print(f"Generated: moto3-{args.service} -> {pkg_dir}")
        generated.append(f'moto3-{args.service}')

    if args.bundle:
        if args.bundle not in bundles:
            print(f"Error: Unknown bundle '{args.bundle}'")
            print(f"Use --list to see available bundles")
            sys.exit(1)
        config = bundles[args.bundle]
        pkg_dir = generate_bundle_package(
            args.bundle,
            config.get('services', []),
            output_dir,
            config.get('description')
        )
        print(f"Generated: moto3-bundle-{args.bundle} -> {pkg_dir}")
        generated.append(f'moto3-bundle-{args.bundle}')

    if args.full or args.all:
        pkg_dir = generate_full_package(output_dir)
        print(f"Generated: moto3-full -> {pkg_dir}")
        generated.append('moto3-full')

    if args.all:
        # Generate all service packages
        print(f"\nGenerating {len(services)} service packages...")
        for service in services:
            pkg_dir = generate_service_package(service, output_dir)
            generated.append(f'moto3-{service}')
        print(f"Generated {len(services)} service packages")

        # Generate all bundle packages
        print(f"\nGenerating {len(bundles)} bundle packages...")
        for name, config in bundles.items():
            pkg_dir = generate_bundle_package(
                name,
                config.get('services', []),
                output_dir,
                config.get('description')
            )
            generated.append(f'moto3-bundle-{name}')
        print(f"Generated {len(bundles)} bundle packages")

    if generated:
        print(f"\n✓ Generated {len(generated)} package(s) in {output_dir}")
    else:
        print("No packages generated. Use --base, --service, --bundle, --full, or --all")
        parser.print_help()


if __name__ == '__main__':
    main()
