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
"""Service data providers for modular botocore.

This module provides abstractions for loading service definitions from
multiple sources, enabling modular installation of AWS service support.

The data provider system allows service definitions to come from:
    * The filesystem (default botocore/data/ and ~/.aws/models/)
    * Separately installed Python packages (via entry points)
    * Custom sources (by implementing ServiceDataProvider)

Example usage::

    # Create a composite provider that checks multiple sources
    provider = CompositeDataProvider([
        FileSystemDataProvider('/path/to/custom/models'),
        FileSystemDataProvider(Loader.BUILTIN_DATA_PATH),
    ])

    # Check if a service is available
    if provider.has_service('dynamodb'):
        data = provider.load_service_data('dynamodb', 'service-2')

Entry Point Discovery::

    Service packages can register themselves via entry points in their
    pyproject.toml or setup.py:

    [project.entry-points."botocore.services"]
    dynamodb = "botocore_dynamodb:get_data_provider"

    The entry point should return a ServiceDataProvider instance.
"""

import importlib.metadata
import logging
import os
from abc import ABC, abstractmethod

from botocore.compat import HAS_GZIP, OrderedDict, json
from botocore.exceptions import DataNotFoundError

if HAS_GZIP:
    from gzip import open as gzip_open

logger = logging.getLogger(__name__)

# Entry point group name for service data providers
SERVICE_PROVIDER_ENTRY_POINT = 'botocore.services'

# Cache for discovered entry point providers
_entry_point_providers_cache = None


def _get_json_open_methods():
    """Get available JSON file open methods."""
    methods = {'.json': open}
    if HAS_GZIP:
        methods['.json.gz'] = gzip_open
    return methods


class ServiceDataProvider(ABC):
    """Abstract base class for service data providers.

    A service data provider is responsible for locating and loading
    service definition files (service models, paginators, waiters, etc.)
    from a specific source.

    Implementations must provide:
        * has_service() - Check if the provider can serve a given service
        * list_available_services() - List all services the provider can serve
        * list_api_versions() - List API versions for a service
        * load_service_data() - Load the actual service data
        * load_data() - Load arbitrary data files
    """

    @abstractmethod
    def has_service(self, service_name, type_name='service-2'):
        """Check if this provider can serve the given service.

        :type service_name: str
        :param service_name: The name of the service (e.g., 'dynamodb', 's3').

        :type type_name: str
        :param type_name: The type of data to check for (default 'service-2').

        :rtype: bool
        :return: True if the provider can serve the service, False otherwise.
        """
        pass

    @abstractmethod
    def list_available_services(self, type_name='service-2'):
        """List all services available from this provider.

        :type type_name: str
        :param type_name: The type of service data (service-2, paginators-1, etc.)

        :rtype: list
        :return: A sorted list of service names.
        """
        pass

    @abstractmethod
    def list_api_versions(self, service_name, type_name='service-2'):
        """List all API versions available for a service.

        :type service_name: str
        :param service_name: The name of the service.

        :type type_name: str
        :param type_name: The type of service data.

        :rtype: list
        :return: A sorted list of API version strings, or empty list if
            the service is not available.
        """
        pass

    @abstractmethod
    def load_service_data(self, service_name, type_name, api_version=None):
        """Load service definition data.

        :type service_name: str
        :param service_name: The name of the service (e.g., 'dynamodb').

        :type type_name: str
        :param type_name: The model type (e.g., 'service-2', 'paginators-1').

        :type api_version: str
        :param api_version: The API version to load. If None, loads the
            latest version.

        :rtype: dict
        :return: The loaded service data as a dictionary.

        :raises DataNotFoundError: If the service data cannot be found.
        """
        pass

    @abstractmethod
    def load_data(self, name):
        """Load arbitrary data by path.

        This is a lower-level method for loading non-service-specific
        data files like endpoints.json or _retry.json.

        :type name: str
        :param name: The data path (e.g., 'dynamodb/2012-08-10/service-2').

        :rtype: dict
        :return: The loaded data.

        :raises DataNotFoundError: If the data cannot be found.
        """
        pass

    def load_data_with_path(self, name):
        """Load data and return both the data and the source path.

        :type name: str
        :param name: The data path.

        :rtype: tuple
        :return: A tuple of (data, path) where path indicates where
            the data was loaded from.

        :raises DataNotFoundError: If the data cannot be found.
        """
        # Default implementation - subclasses may override for better paths
        data = self.load_data(name)
        return data, f'<{self.__class__.__name__}:{name}>'

    def is_builtin_path(self, path):
        """Check if a path is within the provider's builtin data.

        :type path: str
        :param path: The path to check.

        :rtype: bool
        :return: True if the path is builtin, False otherwise.
        """
        # Default implementation - subclasses should override
        return False


class FileSystemDataProvider(ServiceDataProvider):
    """Loads service data from the filesystem.

    This provider searches a directory tree for service definition files
    following the standard botocore data layout:

        <root>/<service_name>/<api_version>/<type_name>.json

    Example::

        provider = FileSystemDataProvider('/path/to/data')
        data = provider.load_service_data('dynamodb', 'service-2')
    """

    def __init__(self, data_path, file_loader=None):
        """Initialize the filesystem data provider.

        :type data_path: str
        :param data_path: The root directory to search for service data.

        :type file_loader: object
        :param file_loader: Optional custom file loader. If not provided,
            uses the default JSON file loader.
        """
        self._data_path = os.path.abspath(os.path.expanduser(data_path))
        self._file_loader = file_loader
        self._json_open_methods = _get_json_open_methods()
        self._cache = {}

    @property
    def data_path(self):
        """The root data path for this provider."""
        return self._data_path

    def _file_exists(self, file_path):
        """Check if a JSON file exists (with or without .gz extension)."""
        for ext in self._json_open_methods:
            if os.path.isfile(file_path + ext):
                return True
        return False

    def _load_file(self, file_path):
        """Load a JSON file from the filesystem."""
        for ext, open_method in self._json_open_methods.items():
            full_path = file_path + ext
            if os.path.isfile(full_path):
                with open_method(full_path, 'rb') as fp:
                    payload = fp.read().decode('utf-8')
                logger.debug("Loading JSON file: %s", full_path)
                return json.loads(payload, object_pairs_hook=OrderedDict)
        return None

    def has_service(self, service_name, type_name='service-2'):
        """Check if the service exists in this provider's data path."""
        service_dir = os.path.join(self._data_path, service_name)
        if not os.path.isdir(service_dir):
            return False

        # Check if any API version has the requested type
        try:
            for version_dir in os.listdir(service_dir):
                version_path = os.path.join(service_dir, version_dir)
                if os.path.isdir(version_path):
                    type_path = os.path.join(version_path, type_name)
                    if self._file_exists(type_path):
                        return True
        except OSError:
            pass
        return False

    def list_available_services(self, type_name='service-2'):
        """List all services available in the data path."""
        cache_key = ('list_available_services', type_name)
        if cache_key in self._cache:
            return self._cache[cache_key]

        services = set()
        if not os.path.isdir(self._data_path):
            return []

        try:
            for service_name in os.listdir(self._data_path):
                service_dir = os.path.join(self._data_path, service_name)
                if not os.path.isdir(service_dir):
                    continue

                # Check if this is a valid service directory
                for version_dir in os.listdir(service_dir):
                    version_path = os.path.join(service_dir, version_dir)
                    if os.path.isdir(version_path):
                        type_path = os.path.join(version_path, type_name)
                        if self._file_exists(type_path):
                            services.add(service_name)
                            break
        except OSError:
            pass

        result = sorted(services)
        self._cache[cache_key] = result
        return result

    def list_api_versions(self, service_name, type_name='service-2'):
        """List all API versions for a service."""
        cache_key = ('list_api_versions', service_name, type_name)
        if cache_key in self._cache:
            return self._cache[cache_key]

        versions = set()
        service_dir = os.path.join(self._data_path, service_name)

        if not os.path.isdir(service_dir):
            return []

        try:
            for version_dir in os.listdir(service_dir):
                version_path = os.path.join(service_dir, version_dir)
                if os.path.isdir(version_path):
                    type_path = os.path.join(version_path, type_name)
                    if self._file_exists(type_path):
                        versions.add(version_dir)
        except OSError:
            pass

        result = sorted(versions)
        self._cache[cache_key] = result
        return result

    def load_service_data(self, service_name, type_name, api_version=None):
        """Load service data from the filesystem."""
        if api_version is None:
            versions = self.list_api_versions(service_name, type_name)
            if not versions:
                raise DataNotFoundError(data_path=service_name)
            api_version = max(versions)

        file_path = os.path.join(
            self._data_path, service_name, api_version, type_name
        )
        data = self._load_file(file_path)
        if data is None:
            raise DataNotFoundError(
                data_path=f'{service_name}/{api_version}/{type_name}'
            )
        return data

    def load_data(self, name):
        """Load arbitrary data from the filesystem."""
        file_path = os.path.join(self._data_path, name)
        data = self._load_file(file_path)
        if data is None:
            raise DataNotFoundError(data_path=name)
        return data

    def load_data_with_path(self, name):
        """Load data and return the file path."""
        file_path = os.path.join(self._data_path, name)
        for ext in self._json_open_methods:
            full_path = file_path + ext
            if os.path.isfile(full_path):
                data = self._load_file(file_path)
                if data is not None:
                    return data, full_path

        raise DataNotFoundError(data_path=name)

    def is_builtin_path(self, path):
        """Check if path is within this provider's data directory."""
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
        return path.startswith(self._data_path)


class PackageDataProvider(ServiceDataProvider):
    """Loads service data from installed Python packages.

    This provider is used for modular service packages that are installed
    separately and register themselves via entry points.

    Example package structure::

        motocore_dynamodb/
        ├── __init__.py
        └── data/
            └── dynamodb/
                └── 2012-08-10/
                    ├── service-2.json
                    ├── paginators-1.json
                    └── waiters-2.json

    The package registers via entry point:

        [project.entry-points."botocore.services"]
        dynamodb = "motocore_dynamodb:get_data_provider"
    """

    def __init__(self, package_data_path, services=None):
        """Initialize the package data provider.

        :type package_data_path: str
        :param package_data_path: Path to the package's data directory.

        :type services: list
        :param services: Optional list of service names this package provides.
            If not provided, will be discovered from the data directory.
        """
        self._fs_provider = FileSystemDataProvider(package_data_path)
        self._services = services
        self._package_name = None

    @classmethod
    def from_package(cls, package_name, data_subpath='data', services=None):
        """Create a provider from an installed package.

        :type package_name: str
        :param package_name: The Python package name.

        :type data_subpath: str
        :param data_subpath: The subdirectory within the package containing
            service data (default 'data').

        :type services: list
        :param services: Optional list of service names.

        :rtype: PackageDataProvider
        :return: A configured provider instance.
        """
        import importlib.resources

        # Get the package's data directory
        try:
            # Python 3.9+
            files = importlib.resources.files(package_name)
            data_path = str(files.joinpath(data_subpath))
        except (AttributeError, TypeError):
            # Fallback for older Python
            import pkg_resources
            data_path = pkg_resources.resource_filename(
                package_name, data_subpath
            )

        provider = cls(data_path, services=services)
        provider._package_name = package_name
        return provider

    def has_service(self, service_name, type_name='service-2'):
        if self._services is not None:
            if service_name not in self._services:
                return False
        return self._fs_provider.has_service(service_name, type_name)

    def list_available_services(self, type_name='service-2'):
        if self._services is not None:
            # Filter to only declared services
            all_services = self._fs_provider.list_available_services(type_name)
            return sorted(s for s in all_services if s in self._services)
        return self._fs_provider.list_available_services(type_name)

    def list_api_versions(self, service_name, type_name='service-2'):
        if self._services is not None and service_name not in self._services:
            return []
        return self._fs_provider.list_api_versions(service_name, type_name)

    def load_service_data(self, service_name, type_name, api_version=None):
        if self._services is not None and service_name not in self._services:
            raise DataNotFoundError(data_path=service_name)
        return self._fs_provider.load_service_data(
            service_name, type_name, api_version
        )

    def load_data(self, name):
        return self._fs_provider.load_data(name)

    def load_data_with_path(self, name):
        return self._fs_provider.load_data_with_path(name)


class CompositeDataProvider(ServiceDataProvider):
    """Combines multiple data providers into a single interface.

    This provider checks each underlying provider in order until one
    can satisfy the request. This enables layered data sources, such as:

        1. Custom user models (~/.aws/models/)
        2. Separately installed service packages
        3. Builtin botocore models

    Example::

        provider = CompositeDataProvider([
            FileSystemDataProvider('~/.aws/models'),
            PackageDataProvider.from_package('motocore_dynamodb'),
            FileSystemDataProvider('/path/to/botocore/data'),
        ])
    """

    def __init__(self, providers=None):
        """Initialize the composite provider.

        :type providers: list
        :param providers: A list of ServiceDataProvider instances to check
            in order. Providers earlier in the list take precedence.
        """
        self._providers = list(providers) if providers else []
        self._cache = {}

    def add_provider(self, provider, priority='last'):
        """Add a data provider.

        :type provider: ServiceDataProvider
        :param provider: The provider to add.

        :type priority: str
        :param priority: Either 'first' to add at the beginning (highest
            priority) or 'last' to add at the end (lowest priority).
        """
        # Clear cache when providers change
        self._cache.clear()

        if priority == 'first':
            self._providers.insert(0, provider)
        else:
            self._providers.append(provider)

    def remove_provider(self, provider):
        """Remove a data provider.

        :type provider: ServiceDataProvider
        :param provider: The provider to remove.
        """
        self._cache.clear()
        self._providers.remove(provider)

    @property
    def providers(self):
        """List of underlying providers."""
        return list(self._providers)

    def has_service(self, service_name, type_name='service-2'):
        for provider in self._providers:
            if provider.has_service(service_name, type_name):
                return True
        return False

    def list_available_services(self, type_name='service-2'):
        cache_key = ('list_available_services', type_name)
        if cache_key in self._cache:
            return self._cache[cache_key]

        services = set()
        for provider in self._providers:
            services.update(provider.list_available_services(type_name))

        result = sorted(services)
        self._cache[cache_key] = result
        return result

    def list_api_versions(self, service_name, type_name='service-2'):
        cache_key = ('list_api_versions', service_name, type_name)
        if cache_key in self._cache:
            return self._cache[cache_key]

        versions = set()
        for provider in self._providers:
            versions.update(provider.list_api_versions(service_name, type_name))

        result = sorted(versions)
        self._cache[cache_key] = result
        return result

    def load_service_data(self, service_name, type_name, api_version=None):
        # If no api_version specified, find the latest across all providers
        if api_version is None:
            versions = self.list_api_versions(service_name, type_name)
            if not versions:
                raise DataNotFoundError(data_path=service_name)
            api_version = max(versions)

        # Try each provider in order
        for provider in self._providers:
            if provider.has_service(service_name, type_name):
                try:
                    return provider.load_service_data(
                        service_name, type_name, api_version
                    )
                except DataNotFoundError:
                    continue

        raise DataNotFoundError(
            data_path=f'{service_name}/{api_version}/{type_name}'
        )

    def load_data(self, name):
        for provider in self._providers:
            try:
                return provider.load_data(name)
            except DataNotFoundError:
                continue

        raise DataNotFoundError(data_path=name)

    def load_data_with_path(self, name):
        for provider in self._providers:
            try:
                return provider.load_data_with_path(name)
            except DataNotFoundError:
                continue

        raise DataNotFoundError(data_path=name)

    def is_builtin_path(self, path):
        for provider in self._providers:
            if provider.is_builtin_path(path):
                return True
        return False


def discover_entry_point_providers():
    """Discover service data providers from installed packages.

    This function scans Python package entry points for the
    'botocore.services' group and instantiates providers from them.

    :rtype: list
    :return: A list of ServiceDataProvider instances from entry points.
    """
    global _entry_point_providers_cache

    if _entry_point_providers_cache is not None:
        return _entry_point_providers_cache

    providers = []

    try:
        # Python 3.10+ / importlib.metadata 3.6+
        entry_points = importlib.metadata.entry_points(
            group=SERVICE_PROVIDER_ENTRY_POINT
        )
    except TypeError:
        # Older Python - entry_points() returns a dict
        all_eps = importlib.metadata.entry_points()
        entry_points = all_eps.get(SERVICE_PROVIDER_ENTRY_POINT, [])

    for ep in entry_points:
        try:
            logger.debug(
                "Loading service provider entry point: %s from %s",
                ep.name,
                ep.value,
            )
            factory = ep.load()
            provider = factory()
            if isinstance(provider, ServiceDataProvider):
                providers.append(provider)
            else:
                logger.warning(
                    "Entry point %s did not return a ServiceDataProvider",
                    ep.name,
                )
        except Exception as e:
            logger.warning(
                "Failed to load service provider entry point %s: %s",
                ep.name,
                e,
            )

    _entry_point_providers_cache = providers
    return providers


def clear_entry_point_cache():
    """Clear the cached entry point providers.

    This is useful for testing or when packages are installed/uninstalled
    during runtime.
    """
    global _entry_point_providers_cache
    _entry_point_providers_cache = None


def create_default_data_provider(
    extra_search_paths=None,
    include_default_paths=True,
    include_entry_points=True,
):
    """Create the default composite data provider.

    This creates a provider that searches:
        1. Extra search paths (if provided)
        2. Entry point providers (installed service packages)
        3. User models (~/.aws/models/)
        4. Builtin botocore models

    :type extra_search_paths: list
    :param extra_search_paths: Additional filesystem paths to search.

    :type include_default_paths: bool
    :param include_default_paths: Whether to include the default
        ~/.aws/models and botocore/data paths.

    :type include_entry_points: bool
    :param include_entry_points: Whether to include entry point providers.

    :rtype: CompositeDataProvider
    :return: A configured composite provider.
    """
    from botocore import BOTOCORE_ROOT

    providers = []

    # Add extra search paths first (highest priority)
    if extra_search_paths:
        for path in extra_search_paths:
            path = os.path.expanduser(os.path.expandvars(path))
            if os.path.isdir(path):
                providers.append(FileSystemDataProvider(path))

    # Add entry point providers
    if include_entry_points:
        providers.extend(discover_entry_point_providers())

    # Add default paths
    if include_default_paths:
        # User models
        customer_path = os.path.join(
            os.path.expanduser('~'), '.aws', 'models'
        )
        if os.path.isdir(customer_path):
            providers.append(FileSystemDataProvider(customer_path))

        # Builtin models
        builtin_path = os.path.join(BOTOCORE_ROOT, 'data')
        providers.append(FileSystemDataProvider(builtin_path))

    return CompositeDataProvider(providers)
