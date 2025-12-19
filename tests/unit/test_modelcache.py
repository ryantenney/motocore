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

"""Tests for lazy loading infrastructure (modelcache.py)."""

import pytest
from unittest import mock


class TestServiceModelCache:
    """Tests for the ServiceModelCache class."""

    def test_cache_initialization(self):
        """Test that cache initializes with empty caches."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        cache = ServiceModelCache(loader)

        assert cache._service_models == {}
        assert cache._paginator_models == {}
        assert cache._waiter_models == {}
        assert cache._service_list is None

    def test_get_service_model_loads_once(self):
        """Test that service model is only loaded once."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.return_value = {
            'metadata': {'serviceIdentifier': 'test'},
            'operations': {},
            'shapes': {},
        }

        cache = ServiceModelCache(loader)

        # First call should load
        model1 = cache.get_service_model('test-service')
        assert loader.load_service_model.call_count == 1

        # Second call should use cache
        model2 = cache.get_service_model('test-service')
        assert loader.load_service_model.call_count == 1

        # Models should be the same object
        assert model1 is model2

    def test_get_service_model_with_version(self):
        """Test getting service model with specific API version."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.return_value = {
            'metadata': {'serviceIdentifier': 'test'},
            'operations': {},
            'shapes': {},
        }

        cache = ServiceModelCache(loader)

        cache.get_service_model('test-service', api_version='2020-01-01')

        loader.load_service_model.assert_called_with(
            'test-service', 'service-2', '2020-01-01'
        )

    def test_different_versions_cached_separately(self):
        """Test that different API versions are cached separately."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.return_value = {
            'metadata': {'serviceIdentifier': 'test'},
            'operations': {},
            'shapes': {},
        }

        cache = ServiceModelCache(loader)

        cache.get_service_model('test-service', api_version='2020-01-01')
        cache.get_service_model('test-service', api_version='2021-01-01')

        assert loader.load_service_model.call_count == 2

    def test_get_paginator_model(self):
        """Test getting paginator model."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.return_value = {
            'pagination': {}
        }

        cache = ServiceModelCache(loader)

        model = cache.get_paginator_model('test-service')

        loader.load_service_model.assert_called_with(
            'test-service', 'paginators-1', None
        )
        assert model is not None

    def test_get_paginator_model_caches(self):
        """Test that paginator model is cached."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.return_value = {'pagination': {}}

        cache = ServiceModelCache(loader)

        model1 = cache.get_paginator_model('test-service')
        model2 = cache.get_paginator_model('test-service')

        assert loader.load_service_model.call_count == 1
        assert model1 is model2

    def test_get_paginator_model_returns_none_on_error(self):
        """Test that missing paginator model returns None."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.side_effect = Exception("Not found")

        cache = ServiceModelCache(loader)

        model = cache.get_paginator_model('test-service')

        assert model is None

    def test_get_waiter_model(self):
        """Test getting waiter model."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.return_value = {'waiters': {}}

        cache = ServiceModelCache(loader)

        model = cache.get_waiter_model('test-service')

        loader.load_service_model.assert_called_with(
            'test-service', 'waiters-2', None
        )
        assert model is not None

    def test_list_available_services(self):
        """Test listing available services."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.list_available_services.return_value = ['s3', 'ec2', 'dynamodb']

        cache = ServiceModelCache(loader)

        services = cache.list_available_services()

        assert services == ['s3', 'ec2', 'dynamodb']
        loader.list_available_services.assert_called_with('service-2')

    def test_list_available_services_caches(self):
        """Test that service list is cached."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.list_available_services.return_value = ['s3', 'ec2']

        cache = ServiceModelCache(loader)

        services1 = cache.list_available_services()
        services2 = cache.list_available_services()

        assert loader.list_available_services.call_count == 1
        assert services1 is services2

    def test_clear_cache_all(self):
        """Test clearing all caches."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.return_value = {
            'metadata': {'serviceIdentifier': 'test'},
            'operations': {},
            'shapes': {},
        }
        loader.list_available_services.return_value = ['s3', 'ec2']

        cache = ServiceModelCache(loader)

        # Populate caches
        cache.get_service_model('test')
        cache.list_available_services()

        cache.clear_cache()

        assert cache._service_models == {}
        assert cache._paginator_models == {}
        assert cache._waiter_models == {}
        assert cache._service_list is None

    def test_clear_cache_specific_service(self):
        """Test clearing cache for a specific service."""
        from botocore.modelcache import ServiceModelCache

        loader = mock.Mock()
        loader.load_service_model.return_value = {
            'metadata': {'serviceIdentifier': 'test'},
            'operations': {},
            'shapes': {},
        }

        cache = ServiceModelCache(loader)

        cache.get_service_model('service1')
        cache.get_service_model('service2')

        assert ('service1', None) in cache._service_models
        assert ('service2', None) in cache._service_models

        cache.clear_cache('service1')

        assert ('service1', None) not in cache._service_models
        assert ('service2', None) in cache._service_models


class TestLazyEndpointDataProvider:
    """Tests for the LazyEndpointDataProvider class."""

    def test_partition_data_loads_lazily(self):
        """Test that partition data is loaded lazily."""
        from botocore.modelcache import LazyEndpointDataProvider

        loader = mock.Mock()
        loader.load_data.return_value = {'partitions': []}

        provider = LazyEndpointDataProvider(loader)

        # Partition data should not be loaded yet
        assert provider._partition_data is None

        # Access partition data
        data = provider.partition_data

        # Now it should be loaded
        assert data is not None
        loader.load_data.assert_called_with('endpoints')

    def test_partition_data_caches(self):
        """Test that partition data is cached."""
        from botocore.modelcache import LazyEndpointDataProvider

        loader = mock.Mock()
        loader.load_data.return_value = {'partitions': []}

        provider = LazyEndpointDataProvider(loader)

        data1 = provider.partition_data
        data2 = provider.partition_data

        assert loader.load_data.call_count == 1
        assert data1 is data2

    def test_get_service_endpoint_ruleset(self):
        """Test getting service endpoint ruleset."""
        from botocore.modelcache import LazyEndpointDataProvider

        loader = mock.Mock()
        loader.load_service_model.return_value = {'rules': []}

        provider = LazyEndpointDataProvider(loader)

        ruleset = provider.get_service_endpoint_ruleset('s3')

        loader.load_service_model.assert_called_with(
            's3', 'endpoint-rule-set-1', None
        )
        assert ruleset is not None

    def test_get_service_endpoint_ruleset_caches(self):
        """Test that endpoint ruleset is cached."""
        from botocore.modelcache import LazyEndpointDataProvider

        loader = mock.Mock()
        loader.load_service_model.return_value = {'rules': []}

        provider = LazyEndpointDataProvider(loader)

        ruleset1 = provider.get_service_endpoint_ruleset('s3')
        ruleset2 = provider.get_service_endpoint_ruleset('s3')

        assert loader.load_service_model.call_count == 1
        assert ruleset1 is ruleset2

    def test_get_service_endpoint_ruleset_returns_none_on_error(self):
        """Test that missing ruleset returns None."""
        from botocore.modelcache import LazyEndpointDataProvider

        loader = mock.Mock()
        loader.load_service_model.side_effect = Exception("Not found")

        provider = LazyEndpointDataProvider(loader)

        ruleset = provider.get_service_endpoint_ruleset('unknown-service')

        assert ruleset is None

    def test_get_endpoints_data(self):
        """Test backwards-compatible endpoints data access."""
        from botocore.modelcache import LazyEndpointDataProvider

        loader = mock.Mock()
        loader.load_data.return_value = {'partitions': []}

        provider = LazyEndpointDataProvider(loader)

        data = provider.get_endpoints_data()

        assert data == {'partitions': []}


class TestDeferredImportModule:
    """Tests for the DeferredImportModule class."""

    def test_deferred_import_not_loaded_initially(self):
        """Test that module is not imported on creation."""
        from botocore.modelcache import DeferredImportModule

        proxy = DeferredImportModule('json')

        # Module should not be loaded yet
        assert proxy._module is None

    def test_deferred_import_loads_on_access(self):
        """Test that module is imported on first attribute access."""
        from botocore.modelcache import DeferredImportModule

        proxy = DeferredImportModule('json')

        # Access an attribute
        dumps = proxy.dumps

        # Module should now be loaded
        assert proxy._module is not None
        assert callable(dumps)

    def test_deferred_import_same_module_reused(self):
        """Test that same module instance is reused."""
        from botocore.modelcache import DeferredImportModule

        proxy = DeferredImportModule('json')

        # Access multiple attributes
        dumps = proxy.dumps
        loads = proxy.loads

        # Should be the same module
        import json
        assert proxy._module is json

    def test_create_deferred_import(self):
        """Test create_deferred_import helper function."""
        from botocore.modelcache import create_deferred_import

        proxy = create_deferred_import('os')

        # Should be a DeferredImportModule
        from botocore.modelcache import DeferredImportModule
        assert isinstance(proxy, DeferredImportModule)

        # Should work when used
        path = proxy.path
        assert path is not None


class TestLazyServiceHandlerLoader:
    """Tests for the LazyServiceHandlerLoader class."""

    def test_initialization(self):
        """Test handler loader initialization."""
        from botocore.modelcache import LazyServiceHandlerLoader

        event_emitter = mock.Mock()
        loader = LazyServiceHandlerLoader(event_emitter)

        assert loader._event_emitter is event_emitter
        assert loader._loaded_services == set()
        assert loader._core_loaded is False

    def test_ensure_core_handlers_loaded(self):
        """Test that core handlers are loaded."""
        from botocore.modelcache import LazyServiceHandlerLoader

        event_emitter = mock.Mock()
        loader = LazyServiceHandlerLoader(event_emitter)

        loader.ensure_core_handlers_loaded()

        assert loader._core_loaded is True
        # Core handlers should have registered events
        assert event_emitter.register.called or event_emitter.register_first.called

    def test_ensure_core_handlers_loaded_idempotent(self):
        """Test that core handlers are only loaded once."""
        from botocore.modelcache import LazyServiceHandlerLoader

        event_emitter = mock.Mock()
        loader = LazyServiceHandlerLoader(event_emitter)

        loader.ensure_core_handlers_loaded()
        first_call_count = event_emitter.register.call_count

        loader.ensure_core_handlers_loaded()
        second_call_count = event_emitter.register.call_count

        assert first_call_count == second_call_count

    def test_ensure_service_handlers_loaded(self):
        """Test loading service-specific handlers."""
        from botocore.modelcache import LazyServiceHandlerLoader

        event_emitter = mock.Mock()
        loader = LazyServiceHandlerLoader(event_emitter)

        loader.ensure_service_handlers_loaded('s3')

        assert 's3' in loader._loaded_services

    def test_ensure_service_handlers_loaded_idempotent(self):
        """Test that service handlers are only loaded once."""
        from botocore.modelcache import LazyServiceHandlerLoader

        event_emitter = mock.Mock()
        loader = LazyServiceHandlerLoader(event_emitter)

        loader.ensure_service_handlers_loaded('ec2')
        first_call_count = event_emitter.register.call_count

        loader.ensure_service_handlers_loaded('ec2')
        second_call_count = event_emitter.register.call_count

        assert first_call_count == second_call_count

    def test_multiple_services_loaded_independently(self):
        """Test that different services can be loaded independently."""
        from botocore.modelcache import LazyServiceHandlerLoader

        event_emitter = mock.Mock()
        loader = LazyServiceHandlerLoader(event_emitter)

        loader.ensure_service_handlers_loaded('s3')
        loader.ensure_service_handlers_loaded('ec2')

        assert 's3' in loader._loaded_services
        assert 'ec2' in loader._loaded_services


class TestSessionIntegration:
    """Tests for lazy loading integration with Session."""

    def test_session_creates_service_model_cache(self):
        """Test that session can create service model cache component."""
        from botocore.session import Session

        session = Session()

        # The component should be accessible via _get_internal_component
        cache = session._get_internal_component('service_model_cache')

        from botocore.modelcache import ServiceModelCache
        assert isinstance(cache, ServiceModelCache)

    def test_session_creates_lazy_handler_loader(self):
        """Test that session can create lazy handler loader component."""
        from botocore.session import Session

        session = Session()

        loader = session._get_internal_component('lazy_handler_loader')

        from botocore.modelcache import LazyServiceHandlerLoader
        assert isinstance(loader, LazyServiceHandlerLoader)

    def test_service_model_cache_uses_loader(self):
        """Test that service model cache uses the session's loader."""
        from botocore.session import Session

        session = Session()

        cache = session._get_internal_component('service_model_cache')

        # Should be able to list services using the loader
        services = cache.list_available_services()
        assert len(services) > 0
        assert 's3' in services
        assert 'ec2' in services

    def test_lazy_handler_loader_uses_event_emitter(self):
        """Test that lazy handler loader uses the session's event emitter."""
        from botocore.session import Session

        session = Session()

        loader = session._get_internal_component('lazy_handler_loader')
        event_emitter = session.get_component('event_emitter')

        assert loader._event_emitter is event_emitter
