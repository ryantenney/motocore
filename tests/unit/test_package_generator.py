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

"""Tests for package generator scripts."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).parent.parent.parent / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_service_package import (
    format_size,
    get_botocore_root,
    get_module_name,
    get_service_data_path,
    get_service_size,
    list_available_services,
    normalize_service_name,
    generate_init_py,
    generate_pyproject_toml,
    generate_readme,
    generate_service_package,
    HANDLER_MODULE_MAPPING,
)


class TestFormatSize:
    """Tests for format_size function."""

    def test_format_bytes(self):
        assert format_size(500) == "500 B"

    def test_format_kilobytes(self):
        assert format_size(1024) == "1.0 KB"
        assert format_size(2048) == "2.0 KB"

    def test_format_megabytes(self):
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(5 * 1024 * 1024) == "5.0 MB"


class TestNormalization:
    """Tests for name normalization functions."""

    def test_normalize_service_name(self):
        assert normalize_service_name('dynamodb') == 'dynamodb'
        assert normalize_service_name('DynamoDB') == 'dynamodb'
        assert normalize_service_name('api_gateway') == 'api-gateway'

    def test_get_module_name(self):
        assert get_module_name('dynamodb') == 'motocore_dynamodb'
        assert get_module_name('s3') == 'motocore_s3'
        assert get_module_name('api-gateway') == 'motocore_api_gateway'
        assert get_module_name('iot.data') == 'motocore_iot_data'


class TestServiceDiscovery:
    """Tests for service discovery functions."""

    def test_get_botocore_root(self):
        root = get_botocore_root()
        assert root.exists()
        assert (root / 'botocore').exists()

    def test_get_service_data_path(self):
        root = get_botocore_root()
        data_path = get_service_data_path(root)
        assert data_path.exists()
        assert (data_path / 'dynamodb').exists()

    def test_list_available_services(self):
        root = get_botocore_root()
        services = list_available_services(root)
        assert isinstance(services, list)
        assert len(services) > 100  # Should have many services
        assert 'dynamodb' in services
        assert 's3' in services
        assert 'ec2' in services

    def test_get_service_size(self):
        root = get_botocore_root()
        size = get_service_size(root, 'dynamodb')
        assert size > 0
        assert size > 100 * 1024  # DynamoDB is over 100 KB

    def test_get_service_size_nonexistent(self):
        root = get_botocore_root()
        size = get_service_size(root, 'nonexistent-service-xyz')
        assert size == 0


class TestHandlerModuleMapping:
    """Tests for handler module mapping."""

    def test_s3_handler_mapping(self):
        assert HANDLER_MODULE_MAPPING['s3'] == '_s3'
        assert HANDLER_MODULE_MAPPING['s3control'] == '_s3'

    def test_rds_handler_mapping(self):
        assert HANDLER_MODULE_MAPPING['rds'] == '_rds'
        assert HANDLER_MODULE_MAPPING['neptune'] == '_rds'
        assert HANDLER_MODULE_MAPPING['docdb'] == '_rds'

    def test_ec2_handler_mapping(self):
        assert HANDLER_MODULE_MAPPING['ec2'] == '_ec2'


class TestInitPyGeneration:
    """Tests for __init__.py generation."""

    def test_generate_init_py(self):
        content = generate_init_py('dynamodb', 'motocore_dynamodb')

        # Check required elements
        assert 'AWS DYNAMODB' in content
        assert "boto3.client('dynamodb')" in content
        assert 'from botocore.dataprovider import PackageDataProvider' in content
        assert "__service__ = 'dynamodb'" in content
        assert "services=['dynamodb']" in content
        assert 'def get_data_provider()' in content
        assert 'def register()' in content

    def test_generate_init_py_with_hyphen(self):
        content = generate_init_py('api-gateway', 'motocore_api_gateway')

        assert "boto3.client('api-gateway')" in content
        assert "__service__ = 'api-gateway'" in content


class TestPyprojectTomlGeneration:
    """Tests for pyproject.toml generation."""

    def test_generate_pyproject_toml(self):
        content = generate_pyproject_toml('dynamodb', 'motocore_dynamodb')

        # Check required elements
        assert 'name = "motocore-dynamodb"' in content
        assert 'version = "1.0.0"' in content
        assert '"motocore-core>=1.0.0"' in content
        assert '[project.entry-points."botocore.services"]' in content
        assert 'dynamodb = "motocore_dynamodb:register"' in content

    def test_generate_pyproject_toml_custom_version(self):
        content = generate_pyproject_toml(
            'dynamodb', 'motocore_dynamodb', version='2.0.0'
        )
        assert 'version = "2.0.0"' in content

    def test_generate_pyproject_toml_custom_motocore_version(self):
        content = generate_pyproject_toml(
            'dynamodb', 'motocore_dynamodb', motocore_version='>=2.0.0'
        )
        assert '"motocore-core>=2.0.0"' in content


class TestReadmeGeneration:
    """Tests for README.md generation."""

    def test_generate_readme(self):
        content = generate_readme('dynamodb', '600.8 KB')

        # Check required elements
        assert '# motocore-dynamodb' in content
        assert 'AWS DYNAMODB' in content
        assert 'Package size: 600.8 KB' in content
        assert 'pip install motocore-core motocore-dynamodb' in content
        assert "client = boto3.client('dynamodb'" in content


class TestPackageGeneration:
    """Tests for full package generation."""

    def test_generate_service_package(self):
        root = get_botocore_root()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            package_dir = generate_service_package(
                'dynamodb', output_dir, root
            )

            # Check package was created
            assert package_dir.exists()
            assert package_dir.name == 'motocore-dynamodb'

            # Check expected files
            assert (package_dir / 'pyproject.toml').exists()
            assert (package_dir / 'README.md').exists()

            module_dir = package_dir / 'motocore_dynamodb'
            assert module_dir.exists()
            assert (module_dir / '__init__.py').exists()
            assert (module_dir / 'data' / 'dynamodb').exists()

    def test_generate_service_package_with_handlers(self):
        root = get_botocore_root()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            package_dir = generate_service_package(
                's3', output_dir, root, include_handlers=True
            )

            # Check handlers were included
            handlers_dir = package_dir / 'motocore_s3' / 'handlers'
            assert handlers_dir.exists()
            assert (handlers_dir / '_s3.py').exists()
            assert (handlers_dir / '__init__.py').exists()

    def test_generate_service_package_overwrites_existing(self):
        root = get_botocore_root()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Generate first time
            package_dir1 = generate_service_package(
                'dynamodb', output_dir, root
            )

            # Add a marker file
            marker = package_dir1 / 'marker.txt'
            marker.write_text('marker')

            # Generate second time
            package_dir2 = generate_service_package(
                'dynamodb', output_dir, root
            )

            # Marker should be gone (package was recreated)
            assert not marker.exists()
            assert package_dir1 == package_dir2


# Test bundle generator if available
try:
    from generate_bundle_package import (
        load_bundle_config,
        get_bundle_services,
        get_bundle_description,
        normalize_bundle_name,
        get_bundle_module_name,
        calculate_bundle_size,
        get_required_handlers,
        generate_bundle_init_py,
        generate_bundle_pyproject_toml,
        generate_bundle_readme,
        generate_bundle_package,
    )

    class TestBundleConfig:
        """Tests for bundle configuration loading."""

        def test_load_bundle_config(self):
            config = load_bundle_config()

            assert 'bundles' in config
            assert 'serverless' in config['bundles']
            assert 'lambda-dynamodb' in config['bundles']

        def test_get_bundle_services(self):
            config = load_bundle_config()
            services = get_bundle_services('lambda-dynamodb', config)

            assert isinstance(services, list)
            assert 'dynamodb' in services
            assert 'sts' in services
            assert 'logs' in services

        def test_get_bundle_services_unknown(self):
            config = load_bundle_config()

            with pytest.raises(ValueError):
                get_bundle_services('unknown-bundle', config)

        def test_get_bundle_description(self):
            config = load_bundle_config()
            desc = get_bundle_description('lambda-dynamodb', config)

            assert 'Lambda' in desc or 'DynamoDB' in desc

    class TestBundleNormalization:
        """Tests for bundle name normalization."""

        def test_normalize_bundle_name(self):
            assert normalize_bundle_name('lambda-dynamodb') == 'lambda-dynamodb'
            assert normalize_bundle_name('Lambda_DynamoDB') == 'lambda-dynamodb'

        def test_get_bundle_module_name(self):
            assert get_bundle_module_name('lambda-dynamodb') == 'motocore_bundle_lambda_dynamodb'

    class TestBundleSize:
        """Tests for bundle size calculation."""

        def test_calculate_bundle_size(self):
            root = get_botocore_root()
            services = ['dynamodb', 'sts', 'logs']
            size = calculate_bundle_size(root, services)

            assert size > 0
            # Should be sum of individual services
            individual_sum = sum(
                get_service_size(root, s) for s in services
            )
            assert size == individual_sum

        def test_calculate_bundle_size_deduplicates(self):
            root = get_botocore_root()
            # Same service listed twice
            services = ['dynamodb', 'dynamodb']
            size = calculate_bundle_size(root, services)

            single_size = get_service_size(root, 'dynamodb')
            assert size == single_size

    class TestBundleHandlers:
        """Tests for bundle handler detection."""

        def test_get_required_handlers(self):
            services = ['s3', 'dynamodb', 'ec2']
            handlers = get_required_handlers(services)

            assert '_s3' in handlers
            assert '_ec2' in handlers
            # DynamoDB doesn't have special handlers
            assert len(handlers) == 2

        def test_get_required_handlers_shared_module(self):
            services = ['rds', 'neptune', 'docdb']
            handlers = get_required_handlers(services)

            # All three use the same handler module
            assert '_rds' in handlers
            assert len(handlers) == 1

    class TestBundleGeneration:
        """Tests for bundle package generation."""

        def test_generate_bundle_package(self):
            root = get_botocore_root()

            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_bundle_package(
                    'minimal-lambda', output_dir, root
                )

                # Check package was created
                assert package_dir.exists()
                assert package_dir.name == 'motocore-bundle-minimal-lambda'

                # Check expected files
                assert (package_dir / 'pyproject.toml').exists()
                assert (package_dir / 'README.md').exists()

                module_dir = package_dir / 'motocore_bundle_minimal_lambda'
                assert module_dir.exists()
                assert (module_dir / '__init__.py').exists()

                # Check all services are included
                data_dir = module_dir / 'data'
                assert (data_dir / 'sts').exists()
                assert (data_dir / 'logs').exists()

        def test_generate_bundle_init_py(self):
            content = generate_bundle_init_py(
                'test-bundle',
                ['dynamodb', 'sts'],
                'motocore_bundle_test_bundle',
                'Test bundle description'
            )

            assert '__bundle__' in content
            assert "__services__ = ['dynamodb', 'sts']" in content
            assert 'def get_data_provider()' in content
            assert 'def register()' in content

        def test_generate_bundle_pyproject_toml(self):
            content = generate_bundle_pyproject_toml(
                'test-bundle',
                ['dynamodb', 'sts', 'logs'],
                'motocore_bundle_test_bundle',
                'Test bundle'
            )

            assert 'name = "motocore-bundle-test-bundle"' in content
            assert 'dynamodb = "motocore_bundle_test_bundle:register"' in content
            assert 'sts = "motocore_bundle_test_bundle:register"' in content
            assert 'logs = "motocore_bundle_test_bundle:register"' in content

except ImportError:
    # Bundle generator not available
    pass
