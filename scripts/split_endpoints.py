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

"""Split endpoints.json into per-service endpoint files.

This script extracts service-specific endpoint data from the monolithic
endpoints.json file and creates individual endpoint files for each service.
This allows service packages to include only their endpoint data.

Usage:
    python split_endpoints.py              # Split all services
    python split_endpoints.py dynamodb s3  # Split specific services
    python split_endpoints.py --list       # List services with endpoint data
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set


def get_botocore_root() -> Path:
    """Get the root directory of the botocore source."""
    return Path(__file__).parent.parent


def load_endpoints_data(botocore_root: Path) -> Dict:
    """Load the monolithic endpoints.json file."""
    endpoints_path = botocore_root / 'botocore' / 'data' / 'endpoints.json'
    with open(endpoints_path) as f:
        return json.load(f)


def get_all_services(endpoints_data: Dict) -> Set[str]:
    """Get all services that have endpoint data."""
    services = set()
    for partition in endpoints_data.get('partitions', []):
        services.update(partition.get('services', {}).keys())
    return services


def extract_service_endpoints(
    endpoints_data: Dict,
    service_name: str,
) -> Dict:
    """Extract endpoint data for a specific service.

    Creates a minimal endpoints structure containing only the specified
    service's endpoint data across all partitions.

    Args:
        endpoints_data: The full endpoints.json data
        service_name: Name of the service to extract

    Returns:
        A dict with the same structure as endpoints.json but containing
        only the specified service.
    """
    result = {
        'version': endpoints_data.get('version', '3'),
        'partitions': []
    }

    for partition in endpoints_data.get('partitions', []):
        services = partition.get('services', {})
        if service_name in services:
            # Create a minimal partition with just this service
            partition_copy = {
                'defaults': partition.get('defaults', {}),
                'dnsSuffix': partition.get('dnsSuffix', ''),
                'partition': partition.get('partition', ''),
                'partitionName': partition.get('partitionName', ''),
                'regionRegex': partition.get('regionRegex', ''),
                'regions': partition.get('regions', {}),
                'services': {service_name: services[service_name]}
            }
            result['partitions'].append(partition_copy)

    return result


def extract_partition_structure(endpoints_data: Dict) -> Dict:
    """Extract just the partition structure without services.

    Creates a minimal partition data file that can be used for partition
    lookup without loading any service-specific endpoint data.

    Args:
        endpoints_data: The full endpoints.json data

    Returns:
        A dict with partition structure but no services.
    """
    result = {
        'version': endpoints_data.get('version', '3'),
        'partitions': []
    }

    for partition in endpoints_data.get('partitions', []):
        partition_copy = {
            'defaults': partition.get('defaults', {}),
            'dnsSuffix': partition.get('dnsSuffix', ''),
            'partition': partition.get('partition', ''),
            'partitionName': partition.get('partitionName', ''),
            'regionRegex': partition.get('regionRegex', ''),
            'regions': partition.get('regions', {}),
            # Empty services - will be filled from per-service files
            'services': {}
        }
        result['partitions'].append(partition_copy)

    return result


def get_service_data_path(botocore_root: Path, service_name: str) -> Optional[Path]:
    """Get the data path for a service's latest version."""
    service_dir = botocore_root / 'botocore' / 'data' / service_name
    if not service_dir.exists():
        return None

    # Find the latest version directory
    versions = sorted(
        [d for d in service_dir.iterdir() if d.is_dir()],
        reverse=True
    )
    if not versions:
        return None

    return versions[0]


def write_service_endpoints(
    botocore_root: Path,
    service_name: str,
    endpoints_data: Dict,
) -> Optional[Path]:
    """Write service-specific endpoint data to the service's data directory.

    Args:
        botocore_root: Root directory of botocore
        service_name: Name of the service
        endpoints_data: Service-specific endpoint data

    Returns:
        Path to the written file, or None if service directory not found.
    """
    service_data_path = get_service_data_path(botocore_root, service_name)
    if service_data_path is None:
        return None

    output_path = service_data_path / 'endpoints.json'
    with open(output_path, 'w') as f:
        json.dump(endpoints_data, f, indent=2)

    return output_path


def calculate_size(data: Dict) -> int:
    """Calculate the JSON size of data."""
    return len(json.dumps(data, indent=2))


def split_all_endpoints(
    botocore_root: Path,
    services: Optional[List[str]] = None,
) -> Dict[str, int]:
    """Split endpoint data for all (or specified) services.

    Args:
        botocore_root: Root directory of botocore
        services: List of services to split (all if None)

    Returns:
        Dict mapping service name to file size in bytes.
    """
    endpoints_data = load_endpoints_data(botocore_root)
    all_services = get_all_services(endpoints_data)

    if services is None:
        services_to_split = all_services
    else:
        services_to_split = set(services) & all_services

    results = {}
    for service_name in sorted(services_to_split):
        service_endpoints = extract_service_endpoints(endpoints_data, service_name)

        # Only write if there's actual data
        if service_endpoints['partitions']:
            output_path = write_service_endpoints(
                botocore_root, service_name, service_endpoints
            )
            if output_path:
                size = calculate_size(service_endpoints)
                results[service_name] = size
                print(f"  {service_name}: {size / 1024:.1f} KB")
            else:
                print(f"  {service_name}: SKIPPED (no data directory)")

    return results


def write_partition_structure(botocore_root: Path, endpoints_data: Dict) -> Path:
    """Write the partition structure file.

    Args:
        botocore_root: Root directory of botocore
        endpoints_data: The full endpoints.json data

    Returns:
        Path to the written file.
    """
    partition_data = extract_partition_structure(endpoints_data)
    output_path = botocore_root / 'botocore' / 'data' / '_endpoints_partitions.json'

    with open(output_path, 'w') as f:
        json.dump(partition_data, f, indent=2)

    size = calculate_size(partition_data)
    print(f"Partition structure: {size / 1024:.1f} KB")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Split endpoints.json into per-service files'
    )
    parser.add_argument(
        'services',
        nargs='*',
        help='Services to split (all if not specified)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all services with endpoint data'
    )
    parser.add_argument(
        '--partition-only',
        action='store_true',
        help='Only generate partition structure file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without writing files'
    )

    args = parser.parse_args()
    botocore_root = get_botocore_root()
    endpoints_data = load_endpoints_data(botocore_root)

    if args.list:
        services = get_all_services(endpoints_data)
        print(f"Services with endpoint data ({len(services)}):")
        for service in sorted(services):
            print(f"  {service}")
        return

    if args.dry_run:
        services = get_all_services(endpoints_data)
        if args.services:
            services = set(args.services) & services

        print("Would generate:")
        total_size = 0
        for service in sorted(services):
            service_endpoints = extract_service_endpoints(endpoints_data, service)
            size = calculate_size(service_endpoints)
            total_size += size
            print(f"  {service}: {size / 1024:.1f} KB")

        partition_data = extract_partition_structure(endpoints_data)
        partition_size = calculate_size(partition_data)
        print(f"\nPartition structure: {partition_size / 1024:.1f} KB")
        print(f"\nTotal: {(total_size + partition_size) / 1024:.1f} KB")
        print(f"Original endpoints.json: {calculate_size(endpoints_data) / 1024:.1f} KB")
        return

    print("Generating partition structure...")
    write_partition_structure(botocore_root, endpoints_data)

    if not args.partition_only:
        print("\nSplitting endpoint data for services...")
        services = args.services if args.services else None
        results = split_all_endpoints(botocore_root, services)
        print(f"\nGenerated {len(results)} service endpoint files")


if __name__ == '__main__':
    main()
