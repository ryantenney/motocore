#!/usr/bin/env python3
"""
Generate and install motocore/moto3 packages locally for development.

Usage:
    # Install core + dynamodb
    python scripts/install_local.py dynamodb

    # Install core + multiple services
    python scripts/install_local.py dynamodb s3 sqs

    # Install a bundle
    python scripts/install_local.py --bundle serverless

    # Install everything (full)
    python scripts/install_local.py --full

    # Just generate packages (don't install)
    python scripts/install_local.py dynamodb --no-install
"""

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
DIST_DIR = ROOT_DIR / 'dist' / 'local'


def run(cmd, check=True):
    """Run a command and print it."""
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)


def generate_packages(services=None, bundle=None, full=False):
    """Generate the required packages."""
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    packages = []

    # Always generate core
    print("\n=== Generating motocore-core ===")
    run([sys.executable, str(SCRIPT_DIR / 'generate_core_package.py'), str(DIST_DIR)])
    packages.append(DIST_DIR / 'motocore-core')

    if full:
        # Generate all services (this takes a while)
        print("\n=== Generating all service packages ===")
        run([sys.executable, str(SCRIPT_DIR / 'generate_service_package.py'),
             '--all', str(DIST_DIR)])
        # For full, we don't need to track individual packages
        packages.append(DIST_DIR / 'motocore-full')  # Will be created by meta package
    elif bundle:
        # Generate bundle
        print(f"\n=== Generating motocore-bundle-{bundle} ===")
        run([sys.executable, str(SCRIPT_DIR / 'generate_bundle_package.py'),
             bundle, str(DIST_DIR)])
        packages.append(DIST_DIR / f'motocore-bundle-{bundle}')
    elif services:
        # Generate individual services
        for service in services:
            print(f"\n=== Generating motocore-{service} ===")
            run([sys.executable, str(SCRIPT_DIR / 'generate_service_package.py'),
                 service, str(DIST_DIR)])
            packages.append(DIST_DIR / f'motocore-{service}')

    # Generate moto3
    print("\n=== Generating moto3 ===")
    run([sys.executable, str(SCRIPT_DIR / 'generate_moto3_package.py'),
         '--base', '--output-dir', str(DIST_DIR)])
    packages.append(DIST_DIR / 'moto3')

    return packages


def install_packages(packages):
    """Install the generated packages."""
    print("\n=== Installing packages ===")

    # Build the pip install command
    cmd = [sys.executable, '-m', 'pip', 'install']
    cmd.extend(str(p) for p in packages)

    run(cmd)

    print("\n=== Installation complete! ===")
    print("\nTest it:")
    print("  python -c \"import moto3 as boto3; print(boto3.client('dynamodb', region_name='us-east-1'))\"")


def main():
    parser = argparse.ArgumentParser(
        description='Generate and install motocore/moto3 packages locally'
    )
    parser.add_argument(
        'services',
        nargs='*',
        help='Services to install (e.g., dynamodb s3 sqs)'
    )
    parser.add_argument(
        '--bundle',
        type=str,
        help='Install a bundle (e.g., serverless, lambda-dynamodb)'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Install all services'
    )
    parser.add_argument(
        '--no-install',
        action='store_true',
        help='Generate packages but do not install'
    )

    args = parser.parse_args()

    if not args.services and not args.bundle and not args.full:
        print("No services specified. Installing core + moto3 only.")
        print("Hint: Use 'python scripts/install_local.py dynamodb' for DynamoDB support")

    packages = generate_packages(
        services=args.services,
        bundle=args.bundle,
        full=args.full
    )

    if not args.no_install:
        install_packages(packages)
    else:
        print("\n=== Packages generated (not installed) ===")
        for p in packages:
            print(f"  {p}")


if __name__ == '__main__':
    main()
