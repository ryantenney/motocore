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

"""Service model caching infrastructure for lazy loading.

This module provides caching mechanisms for service models, paginators,
waiters, and endpoint data to support lazy loading and reduce memory
usage when only a subset of services are needed.
"""

import logging
from functools import cached_property

logger = logging.getLogger(__name__)


class ServiceModelCache:
    """Caches service models, loading them lazily on first access.

    This class provides an efficient caching layer for service models,
    ensuring that models are only loaded when actually needed and are
    reused across multiple client creations for the same service.
    """

    def __init__(self, loader):
        """Initialize the service model cache.

        Args:
            loader: A botocore Loader instance for loading service data.
        """
        self._loader = loader
        self._service_models = {}
        self._paginator_models = {}
        self._waiter_models = {}
        self._service_list = None

    def get_service_model(self, service_name, api_version=None):
        """Get a service model, loading it lazily if needed.

        Args:
            service_name: The name of the service (e.g., 's3', 'ec2').
            api_version: Optional API version. If not specified, uses
                the latest available version.

        Returns:
            A ServiceModel instance for the requested service.
        """
        # Import here to avoid circular dependency
        from botocore.model import ServiceModel

        cache_key = (service_name, api_version)
        if cache_key not in self._service_models:
            service_data = self._loader.load_service_model(
                service_name, 'service-2', api_version
            )
            self._service_models[cache_key] = ServiceModel(
                service_data, service_name
            )
            logger.debug(
                "Loaded service model for %s (version=%s)",
                service_name,
                api_version or 'latest',
            )
        return self._service_models[cache_key]

    def get_paginator_model(self, service_name, api_version=None):
        """Get paginator model for a service, loading lazily if needed.

        Args:
            service_name: The name of the service.
            api_version: Optional API version.

        Returns:
            A PaginatorModel instance, or None if paginators are not
            available for the service.
        """
        from botocore.paginate import PaginatorModel

        cache_key = (service_name, api_version)
        if cache_key not in self._paginator_models:
            try:
                paginator_data = self._loader.load_service_model(
                    service_name, 'paginators-1', api_version
                )
                self._paginator_models[cache_key] = PaginatorModel(
                    paginator_data
                )
                logger.debug(
                    "Loaded paginator model for %s",
                    service_name,
                )
            except Exception:
                # Not all services have paginators
                self._paginator_models[cache_key] = None
        return self._paginator_models[cache_key]

    def get_waiter_model(self, service_name, api_version=None):
        """Get waiter model for a service, loading lazily if needed.

        Args:
            service_name: The name of the service.
            api_version: Optional API version.

        Returns:
            Waiter model data dict, or None if waiters are not available.
        """
        cache_key = (service_name, api_version)
        if cache_key not in self._waiter_models:
            try:
                waiter_data = self._loader.load_service_model(
                    service_name, 'waiters-2', api_version
                )
                self._waiter_models[cache_key] = waiter_data
                logger.debug(
                    "Loaded waiter model for %s",
                    service_name,
                )
            except Exception:
                # Not all services have waiters
                self._waiter_models[cache_key] = None
        return self._waiter_models[cache_key]

    def list_available_services(self, type_name='service-2'):
        """List all available services without loading any models.

        Args:
            type_name: The type of data to list (default: 'service-2').

        Returns:
            A list of available service names.
        """
        if self._service_list is None:
            self._service_list = self._loader.list_available_services(type_name)
        return self._service_list

    def clear_cache(self, service_name=None):
        """Clear cached models.

        Args:
            service_name: If specified, only clear cache for this service.
                If None, clear all cached models.
        """
        if service_name is None:
            self._service_models.clear()
            self._paginator_models.clear()
            self._waiter_models.clear()
            self._service_list = None
        else:
            # Clear all versions of the specified service
            for cache in [
                self._service_models,
                self._paginator_models,
                self._waiter_models,
            ]:
                keys_to_remove = [
                    k for k in cache.keys() if k[0] == service_name
                ]
                for key in keys_to_remove:
                    del cache[key]


class LazyEndpointDataProvider:
    """Provides endpoint data with lazy loading per service.

    This class defers loading of endpoint data until it's actually needed
    for a specific service, reducing memory usage and startup time.

    The provider supports two modes:
    1. Modular mode: Loads partition structure and per-service endpoint data
       from separate files (_endpoints_partitions.json and per-service
       endpoints.json files).
    2. Legacy mode: Falls back to loading the full endpoints.json file
       if modular files are not available.
    """

    def __init__(self, loader):
        """Initialize the lazy endpoint data provider.

        Args:
            loader: A botocore Loader instance for loading endpoint data.
        """
        self._loader = loader
        self._partition_data = None
        self._partition_structure = None
        self._service_endpoints = {}
        self._service_endpoint_rulesets = {}
        self._full_endpoints_data = None
        self._use_modular_endpoints = None

    def _check_modular_endpoints_available(self):
        """Check if modular endpoint files are available."""
        if self._use_modular_endpoints is None:
            try:
                # Try to load partition structure file
                self._loader.load_data('_endpoints_partitions')
                self._use_modular_endpoints = True
                logger.debug("Modular endpoint files available")
            except Exception:
                self._use_modular_endpoints = False
                logger.debug("Using legacy endpoints.json")
        return self._use_modular_endpoints

    def _load_partition_structure(self):
        """Load the partition structure without service data.

        Returns partition definitions (regions, defaults, etc.) without
        any service-specific endpoint data.
        """
        if self._partition_structure is None:
            try:
                self._partition_structure = self._loader.load_data(
                    '_endpoints_partitions'
                )
                logger.debug("Loaded partition structure")
            except Exception:
                # Fall back to extracting from full endpoints
                self._partition_structure = self._extract_partition_structure(
                    self._get_full_endpoints_data()
                )
        return self._partition_structure

    def _extract_partition_structure(self, endpoints_data):
        """Extract partition structure from full endpoints data.

        Creates a partition structure dict without service data.
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
                'services': {}
            }
            result['partitions'].append(partition_copy)
        return result

    def _load_service_endpoints(self, service_name, api_version=None):
        """Load endpoint data for a specific service.

        Tries to load from per-service endpoints.json file first,
        falling back to extracting from full endpoints.json.

        Args:
            service_name: The name of the service.
            api_version: Optional API version.

        Returns:
            Service endpoint data dict, or None if not found.
        """
        cache_key = (service_name, api_version)
        if cache_key in self._service_endpoints:
            return self._service_endpoints[cache_key]

        service_endpoints = None

        # Try to load per-service endpoint file
        if self._check_modular_endpoints_available():
            try:
                service_endpoints = self._loader.load_service_model(
                    service_name, 'endpoints', api_version
                )
                logger.debug("Loaded per-service endpoints for %s", service_name)
            except Exception:
                # Per-service file not available, will fall back
                pass

        # Fall back to extracting from full endpoints
        if service_endpoints is None:
            full_data = self._get_full_endpoints_data()
            service_endpoints = self._extract_service_endpoints(
                full_data, service_name
            )
            if service_endpoints:
                logger.debug(
                    "Extracted endpoints for %s from full file",
                    service_name,
                )

        self._service_endpoints[cache_key] = service_endpoints
        return service_endpoints

    def _extract_service_endpoints(self, endpoints_data, service_name):
        """Extract endpoint data for a specific service from full endpoints.

        Creates a minimal endpoints structure containing only the specified
        service's endpoint data across all partitions.
        """
        result = {
            'version': endpoints_data.get('version', '3'),
            'partitions': []
        }
        for partition in endpoints_data.get('partitions', []):
            services = partition.get('services', {})
            if service_name in services:
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
        return result if result['partitions'] else None

    def get_endpoints_for_service(self, service_name, api_version=None):
        """Get endpoint data for a specific service.

        This method provides per-service endpoint data, loading it lazily.
        It's more efficient than loading the full endpoints.json when only
        a single service is needed.

        Args:
            service_name: The name of the service.
            api_version: Optional API version.

        Returns:
            Endpoint data dict for the service.
        """
        return self._load_service_endpoints(service_name, api_version)

    @property
    def partition_data(self):
        """Get partition data, loading lazily.

        Returns the global partition definitions (aws, aws-cn, aws-gov, etc.)
        without loading per-service endpoint data.
        """
        if self._partition_data is None:
            # Load the full endpoints file - we need partition data
            # This is unavoidable for now until endpoints are split
            self._partition_data = self._get_full_endpoints_data()
        return self._partition_data

    def _get_full_endpoints_data(self):
        """Load the full endpoints data file.

        This is used for backwards compatibility until endpoint data
        is split into per-service files.
        """
        if self._full_endpoints_data is None:
            self._full_endpoints_data = self._loader.load_data('endpoints')
            logger.debug("Loaded full endpoints data")
        return self._full_endpoints_data

    def get_service_endpoint_ruleset(self, service_name, api_version=None):
        """Get endpoint ruleset for a specific service.

        The endpoint ruleset contains the rules for resolving endpoints
        for a specific service. This is loaded lazily per service.

        Args:
            service_name: The name of the service.
            api_version: Optional API version.

        Returns:
            The endpoint ruleset dict for the service, or None if not found.
        """
        cache_key = (service_name, api_version)
        if cache_key not in self._service_endpoint_rulesets:
            try:
                ruleset = self._loader.load_service_model(
                    service_name, 'endpoint-rule-set-1', api_version
                )
                self._service_endpoint_rulesets[cache_key] = ruleset
                logger.debug(
                    "Loaded endpoint ruleset for %s",
                    service_name,
                )
            except Exception:
                self._service_endpoint_rulesets[cache_key] = None
        return self._service_endpoint_rulesets[cache_key]

    def get_endpoints_data(self):
        """Get the full endpoints data.

        This method is provided for backwards compatibility with code
        that expects the full endpoints.json data.

        Returns:
            The full endpoints data dict.
        """
        return self._get_full_endpoints_data()


class DeferredImportModule:
    """A module proxy that defers importing until first attribute access.

    This class allows deferring the import of heavyweight modules until
    they are actually needed, reducing startup time.
    """

    def __init__(self, module_name):
        """Initialize the deferred import proxy.

        Args:
            module_name: The fully qualified name of the module to import.
        """
        self._module_name = module_name
        self._module = None

    def _load_module(self):
        """Actually import the module."""
        if self._module is None:
            import importlib

            self._module = importlib.import_module(self._module_name)
            logger.debug("Deferred import: loaded %s", self._module_name)
        return self._module

    def __getattr__(self, name):
        """Get an attribute from the module, loading it first if needed."""
        module = self._load_module()
        return getattr(module, name)


def create_deferred_import(module_name):
    """Create a deferred import proxy for a module.

    Args:
        module_name: The fully qualified name of the module to import.

    Returns:
        A DeferredImportModule proxy that will import the module on first use.
    """
    return DeferredImportModule(module_name)


class LazyServiceHandlerLoader:
    """Loads service-specific handlers lazily.

    This class ensures that handlers for a specific service are only
    loaded when a client for that service is created.
    """

    def __init__(self, event_emitter):
        """Initialize the lazy handler loader.

        Args:
            event_emitter: The botocore event emitter to register handlers with.
        """
        self._event_emitter = event_emitter
        self._loaded_services = set()
        self._core_loaded = False

    def ensure_core_handlers_loaded(self):
        """Ensure core handlers are registered.

        Core handlers are those needed by all services (service name aliases,
        recursion detection, retry headers, etc.).
        """
        if self._core_loaded:
            return

        from botocore.handlers._registry import LazyHandlerRegistry

        registry = LazyHandlerRegistry(self._event_emitter)
        registry.register_core_handlers()
        self._core_loaded = True
        logger.debug("Core handlers loaded")

    def ensure_service_handlers_loaded(self, service_name):
        """Ensure handlers for a specific service are registered.

        Args:
            service_name: The name of the service (e.g., 's3', 'ec2').
        """
        if service_name in self._loaded_services:
            return

        from botocore.handlers._registry import get_service_handlers

        handlers = get_service_handlers(service_name)
        for handler_entry in handlers:
            self._register_handler(handler_entry)

        self._loaded_services.add(service_name)
        logger.debug("Service handlers loaded for %s", service_name)

    def _register_handler(self, handler_entry):
        """Register a single handler entry."""
        from botocore.handlers._core import REGISTER_FIRST, REGISTER_LAST

        if len(handler_entry) == 2:
            event_name, handler = handler_entry
            self._event_emitter.register(event_name, handler)
        elif len(handler_entry) == 3:
            event_name, handler, priority = handler_entry
            if priority is REGISTER_FIRST:
                self._event_emitter.register_first(event_name, handler)
            elif priority is REGISTER_LAST:
                self._event_emitter.register_last(event_name, handler)
            else:
                self._event_emitter.register(
                    event_name, handler, unique_id=priority
                )
