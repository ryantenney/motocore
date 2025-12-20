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


# Test core package generator
try:
    from generate_core_package import (
        CORE_MODULES,
        CORE_SUBDIRECTORIES,
        CORE_DATA_FILES,
        calculate_directory_size,
        generate_core_init_py,
        generate_core_handlers_init,
        generate_pyproject_toml as generate_core_pyproject_toml,
        generate_readme as generate_core_readme,
        generate_core_package,
        generate_full_meta_package,
        generate_motocore_meta_package,
        generate_meta_package_pyproject,
    )

    class TestCoreModuleList:
        """Tests for core module definitions."""

        def test_core_modules_defined(self):
            assert len(CORE_MODULES) > 20
            assert '__init__.py' in CORE_MODULES
            assert 'session.py' in CORE_MODULES
            assert 'client.py' in CORE_MODULES
            assert 'credentials.py' in CORE_MODULES

        def test_core_subdirectories_defined(self):
            assert 'crt' in CORE_SUBDIRECTORIES
            assert 'docs' in CORE_SUBDIRECTORIES
            assert 'retries' in CORE_SUBDIRECTORIES
            assert 'vendored' in CORE_SUBDIRECTORIES

        def test_core_data_files_defined(self):
            assert '_retry.json' in CORE_DATA_FILES
            assert 'endpoints.json' in CORE_DATA_FILES
            assert 'partitions.json' in CORE_DATA_FILES

    class TestCorePackageGeneration:
        """Tests for core package generation."""

        def test_generate_core_init_py(self):
            content = generate_core_init_py('1.0.0')

            assert "__version__ = '1.0.0'" in content
            assert 'from botocore.session import Session' in content
            assert 'from botocore.exceptions import BotoCoreError, ClientError' in content
            assert 'def xform_name' in content
            assert 'UNSIGNED' in content

        def test_generate_core_handlers_init(self):
            content = generate_core_handlers_init()

            assert 'REGISTER_FIRST' in content
            assert 'REGISTER_LAST' in content
            assert 'BUILTIN_HANDLERS' in content
            assert 'from botocore.handlers._core import' in content
            assert 'from botocore.handlers._registry import' in content

        def test_generate_core_pyproject_toml(self):
            content = generate_core_pyproject_toml('1.0.0')

            assert 'name = "motocore-core"' in content
            assert 'version = "1.0.0"' in content
            assert 'jmespath' in content
            assert 'python-dateutil' in content
            assert 'urllib3' in content
            assert '[project.optional-dependencies]' in content
            assert 'crt = ["awscrt' in content

        def test_generate_core_readme(self):
            content = generate_core_readme()

            assert '# motocore-core' in content
            assert 'pip install motocore-core' in content
            assert 'AWS SDK' in content

        def test_generate_core_package(self):
            root = get_botocore_root()

            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_core_package(output_dir, root)

                # Check package was created
                assert package_dir.exists()
                assert package_dir.name == 'motocore-core'

                # Check expected files
                assert (package_dir / 'pyproject.toml').exists()
                assert (package_dir / 'README.md').exists()

                botocore_dir = package_dir / 'botocore'
                assert botocore_dir.exists()
                assert (botocore_dir / '__init__.py').exists()
                assert (botocore_dir / 'session.py').exists()
                assert (botocore_dir / 'client.py').exists()

                # Check handlers
                handlers_dir = botocore_dir / 'handlers'
                assert handlers_dir.exists()
                assert (handlers_dir / '__init__.py').exists()
                assert (handlers_dir / '_core.py').exists()
                assert (handlers_dir / '_registry.py').exists()

                # Check core data
                data_dir = botocore_dir / 'data'
                assert data_dir.exists()
                assert (data_dir / 'endpoints.json').exists()
                assert (data_dir / 'partitions.json').exists()

                # Check subdirectories
                assert (botocore_dir / 'crt').exists()
                assert (botocore_dir / 'retries').exists()
                assert (botocore_dir / 'vendored').exists()

        def test_core_package_size_reasonable(self):
            root = get_botocore_root()

            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_core_package(output_dir, root)

                size = calculate_directory_size(package_dir)
                # Core package should be under 5 MB
                assert size < 5 * 1024 * 1024
                # Core package should be at least 1 MB
                assert size > 1 * 1024 * 1024

    class TestMetaPackageGeneration:
        """Tests for meta-package generation."""

        def test_generate_meta_package_pyproject(self):
            content = generate_meta_package_pyproject(
                'motocore-test',
                'Test package',
                ['motocore-core>=1.0.0', 'motocore-dynamodb>=1.0.0'],
                '1.0.0',
            )

            assert 'name = "motocore-test"' in content
            assert '"motocore-core>=1.0.0"' in content
            assert '"motocore-dynamodb>=1.0.0"' in content

        def test_generate_full_meta_package(self):
            root = get_botocore_root()

            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_full_meta_package(output_dir, root)

                assert package_dir.exists()
                assert package_dir.name == 'motocore-full'
                assert (package_dir / 'pyproject.toml').exists()
                assert (package_dir / 'README.md').exists()

                # Check pyproject has many dependencies
                pyproject = (package_dir / 'pyproject.toml').read_text()
                assert 'motocore-core' in pyproject
                assert 'motocore-dynamodb' in pyproject
                assert 'motocore-s3' in pyproject

        def test_generate_motocore_meta_package(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_motocore_meta_package(output_dir)

                assert package_dir.exists()
                assert package_dir.name == 'motocore'
                assert (package_dir / 'pyproject.toml').exists()
                assert (package_dir / 'README.md').exists()

                # Check it depends on motocore-full
                pyproject = (package_dir / 'pyproject.toml').read_text()
                assert 'motocore-full' in pyproject

except ImportError:
    # Core package generator not available
    pass


# Test moto3 wrapper package generator
try:
    from generate_moto3_package import (
        MOTO3_VERSION,
        BOTO3_VERSION,
        MOTOCORE_VERSION,
        get_available_services,
        load_bundles,
        generate_base_package,
        generate_service_package as generate_moto3_service_package,
        generate_bundle_package as generate_moto3_bundle_package,
        generate_full_package as generate_moto3_full_package,
    )

    class TestMoto3Constants:
        """Tests for moto3 generator constants."""

        def test_moto3_version_defined(self):
            assert MOTO3_VERSION is not None
            assert '.' in MOTO3_VERSION  # Version format like "1.35.0"

        def test_boto3_version_constraint(self):
            assert 'boto3' not in BOTO3_VERSION  # Should just be version constraint
            assert '>=' in BOTO3_VERSION

        def test_motocore_version_constraint(self):
            assert '>=' in MOTOCORE_VERSION

    class TestMoto3ServiceDiscovery:
        """Tests for moto3 service discovery."""

        def test_get_available_services(self):
            services = get_available_services()
            assert isinstance(services, list)
            assert len(services) > 100
            assert 'dynamodb' in services
            assert 's3' in services

        def test_load_bundles(self):
            bundles = load_bundles()
            assert isinstance(bundles, dict)
            assert 'serverless' in bundles
            assert 'lambda-dynamodb' in bundles

    class TestMoto3BasePackage:
        """Tests for moto3 base package generation."""

        def test_generate_base_package(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_base_package(output_dir)

                # Check package was created
                assert package_dir.exists()
                assert package_dir.name == 'moto3'

                # Check expected files
                assert (package_dir / 'pyproject.toml').exists()
                assert (package_dir / 'README.md').exists()

                module_dir = package_dir / 'moto3'
                assert module_dir.exists()
                assert (module_dir / '__init__.py').exists()

        def test_base_package_init_content(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_base_package(output_dir)

                init_content = (package_dir / 'moto3' / '__init__.py').read_text()

                # Check implements boto3-compatible API
                assert 'def client(' in init_content
                assert 'def resource(' in init_content
                assert 'class Session' in init_content

                # Check includes exceptions
                assert 'from botocore.exceptions import' in init_content
                assert 'ClientError' in init_content
                assert 'BotoCoreError' in init_content

                # Check version
                assert '__version__' in init_content

        def test_base_package_pyproject_content(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_base_package(output_dir)

                pyproject = (package_dir / 'pyproject.toml').read_text()

                # Check dependencies (only motocore-core required, boto3 optional)
                assert 'motocore-core' in pyproject

                # Check package name
                assert 'name = "moto3"' in pyproject

    class TestMoto3ServicePackage:
        """Tests for moto3 service package generation."""

        def test_generate_service_package(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_moto3_service_package('dynamodb', output_dir)

                # Check package was created
                assert package_dir.exists()
                assert package_dir.name == 'moto3-dynamodb'

                # Check expected files
                assert (package_dir / 'pyproject.toml').exists()
                assert (package_dir / 'README.md').exists()

                module_dir = package_dir / 'moto3_dynamodb'
                assert module_dir.exists()
                assert (module_dir / '__init__.py').exists()

        def test_service_package_dependencies(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_moto3_service_package('s3', output_dir)

                pyproject = (package_dir / 'pyproject.toml').read_text()

                # Check depends on moto3 and motocore service
                assert 'moto3>=' in pyproject
                assert 'motocore-s3' in pyproject

        def test_service_package_init_content(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_moto3_service_package('dynamodb', output_dir)

                init_content = (package_dir / 'moto3_dynamodb' / '__init__.py').read_text()

                # Check for service name (either quote style)
                assert '__service__' in init_content
                assert 'dynamodb' in init_content
                assert '__version__' in init_content

    class TestMoto3BundlePackage:
        """Tests for moto3 bundle package generation."""

        def test_generate_bundle_package(self):
            bundles = load_bundles()
            services = bundles['lambda-dynamodb']['services']

            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_moto3_bundle_package(
                    'lambda-dynamodb', services, output_dir
                )

                # Check package was created
                assert package_dir.exists()
                assert package_dir.name == 'moto3-bundle-lambda-dynamodb'

                # Check expected files
                assert (package_dir / 'pyproject.toml').exists()
                assert (package_dir / 'README.md').exists()

        def test_bundle_package_dependencies(self):
            bundles = load_bundles()
            services = bundles['serverless']['services']

            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_moto3_bundle_package(
                    'serverless', services, output_dir
                )

                pyproject = (package_dir / 'pyproject.toml').read_text()

                # Check depends on moto3 and motocore bundle
                assert 'moto3>=' in pyproject
                assert 'motocore-bundle-serverless' in pyproject

        def test_bundle_package_init_content(self):
            bundles = load_bundles()
            services = bundles['lambda-dynamodb']['services']

            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_moto3_bundle_package(
                    'lambda-dynamodb', services, output_dir
                )

                init_content = (
                    package_dir / 'moto3_bundle_lambda_dynamodb' / '__init__.py'
                ).read_text()

                # Check for bundle name (either quote style)
                assert '__bundle__' in init_content
                assert 'lambda-dynamodb' in init_content
                assert '__services__' in init_content

    class TestMoto3FullPackage:
        """Tests for moto3-full package generation."""

        def test_generate_full_package(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_moto3_full_package(output_dir)

                # Check package was created
                assert package_dir.exists()
                assert package_dir.name == 'moto3-full'

                # Check expected files
                assert (package_dir / 'pyproject.toml').exists()
                assert (package_dir / 'README.md').exists()

        def test_full_package_dependencies(self):
            with tempfile.TemporaryDirectory() as tmpdir:
                output_dir = Path(tmpdir)
                package_dir = generate_moto3_full_package(output_dir)

                pyproject = (package_dir / 'pyproject.toml').read_text()

                # Check depends on moto3 and motocore-full
                assert 'moto3>=' in pyproject
                assert 'motocore-full' in pyproject

except ImportError:
    # moto3 package generator not available
    pass
