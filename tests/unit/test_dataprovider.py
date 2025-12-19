# Copyright 2024 Amazon.com, Inc. or its affiliates. All Rights Reserved.
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

import json
import os
import tempfile
import shutil

import pytest

from botocore.dataprovider import (
    ServiceDataProvider,
    FileSystemDataProvider,
    PackageDataProvider,
    CompositeDataProvider,
    discover_entry_point_providers,
    clear_entry_point_cache,
    create_default_data_provider,
)
from botocore.exceptions import DataNotFoundError
from tests import BaseEnvVar


class TestFileSystemDataProvider(BaseEnvVar):
    """Tests for FileSystemDataProvider."""

    def setUp(self):
        super().setUp()
        # Create a temporary directory structure for testing
        self.temp_dir = tempfile.mkdtemp()
        self._create_test_service_data()

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.temp_dir)

    def _create_test_service_data(self):
        """Create test service data in the temp directory."""
        # Create dynamodb service
        dynamodb_path = os.path.join(
            self.temp_dir, 'dynamodb', '2012-08-10'
        )
        os.makedirs(dynamodb_path)

        service_model = {
            'version': '2.0',
            'metadata': {
                'apiVersion': '2012-08-10',
                'endpointPrefix': 'dynamodb',
                'serviceFullName': 'Amazon DynamoDB',
            },
            'operations': {},
            'shapes': {},
        }
        with open(os.path.join(dynamodb_path, 'service-2.json'), 'w') as f:
            json.dump(service_model, f)

        paginators = {'pagination': {}}
        with open(os.path.join(dynamodb_path, 'paginators-1.json'), 'w') as f:
            json.dump(paginators, f)

        # Create s3 service with multiple versions
        for version in ['2006-03-01', '2010-01-01']:
            s3_path = os.path.join(self.temp_dir, 's3', version)
            os.makedirs(s3_path)
            s3_model = {
                'version': '2.0',
                'metadata': {
                    'apiVersion': version,
                    'endpointPrefix': 's3',
                },
                'operations': {},
                'shapes': {},
            }
            with open(os.path.join(s3_path, 'service-2.json'), 'w') as f:
                json.dump(s3_model, f)

        # Create a global data file
        endpoints = {'version': 3, 'partitions': []}
        with open(os.path.join(self.temp_dir, '_endpoints.json'), 'w') as f:
            json.dump(endpoints, f)

    def test_has_service_returns_true_for_existing_service(self):
        provider = FileSystemDataProvider(self.temp_dir)
        self.assertTrue(provider.has_service('dynamodb'))
        self.assertTrue(provider.has_service('s3'))

    def test_has_service_returns_false_for_nonexistent_service(self):
        provider = FileSystemDataProvider(self.temp_dir)
        self.assertFalse(provider.has_service('nonexistent'))

    def test_has_service_with_type_name(self):
        provider = FileSystemDataProvider(self.temp_dir)
        self.assertTrue(provider.has_service('dynamodb', 'service-2'))
        self.assertTrue(provider.has_service('dynamodb', 'paginators-1'))
        self.assertFalse(provider.has_service('dynamodb', 'waiters-2'))

    def test_list_available_services(self):
        provider = FileSystemDataProvider(self.temp_dir)
        services = provider.list_available_services('service-2')
        self.assertEqual(services, ['dynamodb', 's3'])

    def test_list_available_services_empty_for_nonexistent_type(self):
        provider = FileSystemDataProvider(self.temp_dir)
        services = provider.list_available_services('nonexistent-type')
        self.assertEqual(services, [])

    def test_list_api_versions(self):
        provider = FileSystemDataProvider(self.temp_dir)
        versions = provider.list_api_versions('s3', 'service-2')
        self.assertEqual(versions, ['2006-03-01', '2010-01-01'])

    def test_list_api_versions_single_version(self):
        provider = FileSystemDataProvider(self.temp_dir)
        versions = provider.list_api_versions('dynamodb', 'service-2')
        self.assertEqual(versions, ['2012-08-10'])

    def test_list_api_versions_empty_for_nonexistent_service(self):
        provider = FileSystemDataProvider(self.temp_dir)
        versions = provider.list_api_versions('nonexistent', 'service-2')
        self.assertEqual(versions, [])

    def test_load_service_data(self):
        provider = FileSystemDataProvider(self.temp_dir)
        data = provider.load_service_data('dynamodb', 'service-2')
        self.assertEqual(data['metadata']['endpointPrefix'], 'dynamodb')

    def test_load_service_data_specific_version(self):
        provider = FileSystemDataProvider(self.temp_dir)
        data = provider.load_service_data('s3', 'service-2', '2006-03-01')
        self.assertEqual(data['metadata']['apiVersion'], '2006-03-01')

    def test_load_service_data_latest_version(self):
        provider = FileSystemDataProvider(self.temp_dir)
        data = provider.load_service_data('s3', 'service-2')
        # Should load the latest version (2010-01-01)
        self.assertEqual(data['metadata']['apiVersion'], '2010-01-01')

    def test_load_service_data_not_found(self):
        provider = FileSystemDataProvider(self.temp_dir)
        with self.assertRaises(DataNotFoundError):
            provider.load_service_data('nonexistent', 'service-2')

    def test_load_data(self):
        provider = FileSystemDataProvider(self.temp_dir)
        data = provider.load_data('_endpoints')
        self.assertEqual(data['version'], 3)

    def test_load_data_not_found(self):
        provider = FileSystemDataProvider(self.temp_dir)
        with self.assertRaises(DataNotFoundError):
            provider.load_data('nonexistent')

    def test_load_data_with_path(self):
        provider = FileSystemDataProvider(self.temp_dir)
        data, path = provider.load_data_with_path('_endpoints')
        self.assertEqual(data['version'], 3)
        self.assertTrue(path.endswith('_endpoints.json'))

    def test_is_builtin_path(self):
        provider = FileSystemDataProvider(self.temp_dir)
        test_path = os.path.join(self.temp_dir, 'dynamodb', 'service-2.json')
        self.assertTrue(provider.is_builtin_path(test_path))

    def test_is_not_builtin_path(self):
        provider = FileSystemDataProvider(self.temp_dir)
        self.assertFalse(provider.is_builtin_path('/other/path/file.json'))

    def test_data_path_property(self):
        provider = FileSystemDataProvider(self.temp_dir)
        self.assertEqual(provider.data_path, self.temp_dir)

    def test_caching(self):
        provider = FileSystemDataProvider(self.temp_dir)
        # First call should cache the result
        services1 = provider.list_available_services('service-2')
        services2 = provider.list_available_services('service-2')
        self.assertEqual(services1, services2)


class TestPackageDataProvider(BaseEnvVar):
    """Tests for PackageDataProvider."""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self._create_test_package_data()

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.temp_dir)

    def _create_test_package_data(self):
        """Create test package data structure."""
        # Create lambda service
        lambda_path = os.path.join(
            self.temp_dir, 'lambda', '2015-03-31'
        )
        os.makedirs(lambda_path)

        service_model = {
            'version': '2.0',
            'metadata': {
                'apiVersion': '2015-03-31',
                'endpointPrefix': 'lambda',
            },
            'operations': {},
            'shapes': {},
        }
        with open(os.path.join(lambda_path, 'service-2.json'), 'w') as f:
            json.dump(service_model, f)

    def test_has_service_with_declared_services(self):
        provider = PackageDataProvider(
            self.temp_dir, services=['lambda']
        )
        self.assertTrue(provider.has_service('lambda'))

    def test_has_service_filters_undeclared_services(self):
        # Create another service that's not in the declared list
        ec2_path = os.path.join(self.temp_dir, 'ec2', '2016-11-15')
        os.makedirs(ec2_path)
        with open(os.path.join(ec2_path, 'service-2.json'), 'w') as f:
            json.dump({'version': '2.0', 'metadata': {}}, f)

        provider = PackageDataProvider(
            self.temp_dir, services=['lambda']
        )
        self.assertTrue(provider.has_service('lambda'))
        self.assertFalse(provider.has_service('ec2'))

    def test_list_available_services_filters_to_declared(self):
        # Create another service
        ec2_path = os.path.join(self.temp_dir, 'ec2', '2016-11-15')
        os.makedirs(ec2_path)
        with open(os.path.join(ec2_path, 'service-2.json'), 'w') as f:
            json.dump({'version': '2.0', 'metadata': {}}, f)

        provider = PackageDataProvider(
            self.temp_dir, services=['lambda']
        )
        services = provider.list_available_services('service-2')
        self.assertEqual(services, ['lambda'])

    def test_list_available_services_without_filter(self):
        provider = PackageDataProvider(self.temp_dir)
        services = provider.list_available_services('service-2')
        self.assertIn('lambda', services)

    def test_load_service_data_declared_service(self):
        provider = PackageDataProvider(
            self.temp_dir, services=['lambda']
        )
        data = provider.load_service_data('lambda', 'service-2')
        self.assertEqual(data['metadata']['endpointPrefix'], 'lambda')

    def test_load_service_data_undeclared_service_raises(self):
        provider = PackageDataProvider(
            self.temp_dir, services=['lambda']
        )
        with self.assertRaises(DataNotFoundError):
            provider.load_service_data('ec2', 'service-2')


class TestCompositeDataProvider(BaseEnvVar):
    """Tests for CompositeDataProvider."""

    def setUp(self):
        super().setUp()
        # Create two temp directories with different services
        self.temp_dir1 = tempfile.mkdtemp()
        self.temp_dir2 = tempfile.mkdtemp()
        self._create_test_data()

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.temp_dir1)
        shutil.rmtree(self.temp_dir2)

    def _create_test_data(self):
        """Create test data in both directories."""
        # First directory has dynamodb
        dynamodb_path = os.path.join(
            self.temp_dir1, 'dynamodb', '2012-08-10'
        )
        os.makedirs(dynamodb_path)
        with open(os.path.join(dynamodb_path, 'service-2.json'), 'w') as f:
            json.dump({
                'version': '2.0',
                'metadata': {'source': 'provider1'},
            }, f)

        # Second directory has s3
        s3_path = os.path.join(
            self.temp_dir2, 's3', '2006-03-01'
        )
        os.makedirs(s3_path)
        with open(os.path.join(s3_path, 'service-2.json'), 'w') as f:
            json.dump({
                'version': '2.0',
                'metadata': {'source': 'provider2'},
            }, f)

        # Both have ec2 (for priority testing)
        for temp_dir, source in [(self.temp_dir1, 'provider1'), (self.temp_dir2, 'provider2')]:
            ec2_path = os.path.join(temp_dir, 'ec2', '2016-11-15')
            os.makedirs(ec2_path)
            with open(os.path.join(ec2_path, 'service-2.json'), 'w') as f:
                json.dump({
                    'version': '2.0',
                    'metadata': {'source': source},
                }, f)

    def test_has_service_checks_all_providers(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        self.assertTrue(composite.has_service('dynamodb'))
        self.assertTrue(composite.has_service('s3'))
        self.assertTrue(composite.has_service('ec2'))
        self.assertFalse(composite.has_service('nonexistent'))

    def test_list_available_services_combines_all(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        services = composite.list_available_services('service-2')
        self.assertIn('dynamodb', services)
        self.assertIn('s3', services)
        self.assertIn('ec2', services)

    def test_list_api_versions_combines_all(self):
        # Add another version in provider2
        ec2_path = os.path.join(self.temp_dir2, 'ec2', '2017-01-01')
        os.makedirs(ec2_path)
        with open(os.path.join(ec2_path, 'service-2.json'), 'w') as f:
            json.dump({'version': '2.0', 'metadata': {}}, f)

        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        versions = composite.list_api_versions('ec2', 'service-2')
        self.assertIn('2016-11-15', versions)
        self.assertIn('2017-01-01', versions)

    def test_load_service_data_uses_first_provider(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        # ec2 exists in both, should get from provider1
        data = composite.load_service_data('ec2', 'service-2')
        self.assertEqual(data['metadata']['source'], 'provider1')

    def test_load_service_data_falls_back_to_second(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        # s3 only exists in provider2
        data = composite.load_service_data('s3', 'service-2')
        self.assertEqual(data['metadata']['source'], 'provider2')

    def test_load_service_data_not_found_in_any(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        with self.assertRaises(DataNotFoundError):
            composite.load_service_data('nonexistent', 'service-2')

    def test_add_provider_first(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1])

        composite.add_provider(provider2, priority='first')

        # Now provider2 should be first
        data = composite.load_service_data('ec2', 'service-2')
        self.assertEqual(data['metadata']['source'], 'provider2')

    def test_add_provider_last(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1])

        composite.add_provider(provider2, priority='last')

        # provider1 should still be first
        data = composite.load_service_data('ec2', 'service-2')
        self.assertEqual(data['metadata']['source'], 'provider1')

    def test_remove_provider(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        composite.remove_provider(provider1)

        # Should only have provider2 now
        self.assertEqual(len(composite.providers), 1)
        # ec2 should now come from provider2
        data = composite.load_service_data('ec2', 'service-2')
        self.assertEqual(data['metadata']['source'], 'provider2')

    def test_providers_property(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        providers = composite.providers
        self.assertEqual(len(providers), 2)
        # Should be a copy
        providers.append(None)
        self.assertEqual(len(composite.providers), 2)

    def test_is_builtin_path_checks_all(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        path1 = os.path.join(self.temp_dir1, 'dynamodb', 'service-2.json')
        path2 = os.path.join(self.temp_dir2, 's3', 'service-2.json')

        self.assertTrue(composite.is_builtin_path(path1))
        self.assertTrue(composite.is_builtin_path(path2))
        self.assertFalse(composite.is_builtin_path('/other/path'))

    def test_load_data(self):
        # Create a global data file in provider1
        with open(os.path.join(self.temp_dir1, '_retry.json'), 'w') as f:
            json.dump({'retry': {'version': 1}}, f)

        provider1 = FileSystemDataProvider(self.temp_dir1)
        provider2 = FileSystemDataProvider(self.temp_dir2)
        composite = CompositeDataProvider([provider1, provider2])

        data = composite.load_data('_retry')
        self.assertEqual(data['retry']['version'], 1)

    def test_load_data_not_found(self):
        provider1 = FileSystemDataProvider(self.temp_dir1)
        composite = CompositeDataProvider([provider1])

        with self.assertRaises(DataNotFoundError):
            composite.load_data('nonexistent')


class TestEntryPointDiscovery(BaseEnvVar):
    """Tests for entry point discovery."""

    def setUp(self):
        super().setUp()
        # Clear the cache before each test
        clear_entry_point_cache()

    def tearDown(self):
        super().tearDown()
        clear_entry_point_cache()

    def test_discover_entry_point_providers_returns_list(self):
        # This test just verifies the function runs without error
        # In a real environment with no service packages installed,
        # it should return an empty list
        providers = discover_entry_point_providers()
        self.assertIsInstance(providers, list)

    def test_clear_entry_point_cache(self):
        # Call discover to populate cache
        providers1 = discover_entry_point_providers()
        # Clear cache
        clear_entry_point_cache()
        # Call again - should work without error
        providers2 = discover_entry_point_providers()
        self.assertIsInstance(providers2, list)


class TestCreateDefaultDataProvider(BaseEnvVar):
    """Tests for create_default_data_provider function."""

    def test_creates_composite_provider(self):
        provider = create_default_data_provider(
            include_default_paths=True,
            include_entry_points=False,
        )
        self.assertIsInstance(provider, CompositeDataProvider)

    def test_includes_builtin_path(self):
        provider = create_default_data_provider(
            include_default_paths=True,
            include_entry_points=False,
        )
        # Should be able to find some service from builtin data
        services = provider.list_available_services('service-2')
        self.assertTrue(len(services) > 0)

    def test_extra_search_paths(self):
        temp_dir = tempfile.mkdtemp()
        try:
            # Create a custom service
            custom_path = os.path.join(temp_dir, 'custom', '2024-01-01')
            os.makedirs(custom_path)
            with open(os.path.join(custom_path, 'service-2.json'), 'w') as f:
                json.dump({'version': '2.0', 'metadata': {}}, f)

            provider = create_default_data_provider(
                extra_search_paths=[temp_dir],
                include_default_paths=True,
                include_entry_points=False,
            )

            self.assertTrue(provider.has_service('custom'))
        finally:
            shutil.rmtree(temp_dir)


class TestLoaderWithDataProvider(BaseEnvVar):
    """Tests for Loader integration with data providers."""

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self._create_test_data()

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.temp_dir)

    def _create_test_data(self):
        """Create test service data."""
        sqs_path = os.path.join(self.temp_dir, 'sqs', '2012-11-05')
        os.makedirs(sqs_path)
        with open(os.path.join(sqs_path, 'service-2.json'), 'w') as f:
            json.dump({
                'version': '2.0',
                'metadata': {
                    'apiVersion': '2012-11-05',
                    'endpointPrefix': 'sqs',
                },
                'operations': {},
                'shapes': {},
            }, f)

    def test_loader_with_custom_data_provider(self):
        from botocore.loaders import Loader

        provider = FileSystemDataProvider(self.temp_dir)
        loader = Loader(
            data_provider=provider,
            include_default_search_paths=False,
        )

        # Should find sqs from our custom provider
        services = loader.list_available_services('service-2')
        self.assertEqual(services, ['sqs'])

    def test_loader_with_use_data_providers_flag(self):
        from botocore.loaders import Loader

        loader = Loader(
            use_data_providers=True,
            include_default_search_paths=True,
        )

        # Should have a data provider set
        self.assertIsNotNone(loader.data_provider)

        # Should still find builtin services
        services = loader.list_available_services('service-2')
        self.assertTrue(len(services) > 0)

    def test_loader_backwards_compatible_without_data_provider(self):
        from botocore.loaders import Loader

        # Default loader should still work
        loader = Loader()

        # data_provider should be None
        self.assertIsNone(loader.data_provider)

        # Should find builtin services via legacy path
        services = loader.list_available_services('service-2')
        self.assertTrue(len(services) > 0)

    def test_loader_load_service_model_with_provider(self):
        from botocore.loaders import Loader

        provider = FileSystemDataProvider(self.temp_dir)
        loader = Loader(
            data_provider=provider,
            include_default_search_paths=False,
        )

        model = loader.load_service_model('sqs', 'service-2')
        self.assertEqual(model['metadata']['endpointPrefix'], 'sqs')
