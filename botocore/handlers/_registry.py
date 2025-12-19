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

"""Handler registry for lazy loading of service-specific handlers.

This module provides infrastructure for registering handlers on-demand based
on the services being used, reducing import time and memory usage when only
a subset of AWS services are needed.
"""

import importlib
import logging

logger = logging.getLogger(__name__)


# Mapping of service names to their handler modules.
# Format: 'service-name': 'module_name' (relative to botocore.handlers)
SERVICE_HANDLER_MODULES = {
    # S3 and S3 Control
    's3': '_s3',
    's3-control': '_s3',
    's3control': '_s3',
    # EC2
    'ec2': '_ec2',
    # Database services (RDS, Neptune, DocDB)
    'rds': '_rds',
    'neptune': '_rds',
    'docdb': '_rds',
    # Glacier
    'glacier': '_glacier',
    # Route53
    'route53': '_route53',
    # IAM
    'iam': '_iam',
    # STS and Cognito Identity (shared disable_signing)
    'sts': '_sts',
    'cognito-identity': '_sts',
    # CloudFormation
    'cloudformation': '_cloudformation',
    # Machine Learning
    'machinelearning': '_machinelearning',
    # IoT Data
    'iot-data': '_iot',
    # CloudSearch Domain
    'cloudsearchdomain': '_cloudsearch',
    # Mechanical Turk
    'mturk': '_mturk',
    # SQS
    'sqs': '_sqs',
    # Lex Runtime V2
    'lex-runtime-v2': '_lex',
    # Q Business
    'qbusiness': '_qbusiness',
    # Bedrock Runtime
    'bedrock-runtime': '_bedrock',
    # Bedrock Agent Core
    'bedrock-agentcore': '_bedrock',
    # Polly
    'polly': '_polly',
    # AutoScaling (shares base64 handler with EC2)
    'autoscaling': '_autoscaling',
    # API Gateway
    'apigateway': '_apigateway',
    # Lambda
    'lambda': '_lambda',
    # DSQL
    'dsql': '_dsql',
    # Social Messaging
    'socialmessaging': '_socialmessaging',
    # Logs (CloudWatch Logs)
    'logs': '_logs',
}

# Cache of loaded handler modules
_loaded_modules = {}


def get_service_handlers(service_name):
    """Get the handler list for a specific service.

    This function lazily loads the handler module for the given service
    and returns the list of handlers to register.

    Args:
        service_name: The name of the AWS service (e.g., 's3', 'ec2')

    Returns:
        A list of (event_name, handler[, priority]) tuples, or an empty list
        if no service-specific handlers exist.
    """
    if service_name not in SERVICE_HANDLER_MODULES:
        return []

    module_name = SERVICE_HANDLER_MODULES[service_name]

    # Check cache first
    if module_name in _loaded_modules:
        module = _loaded_modules[module_name]
    else:
        try:
            full_module_name = f'botocore.handlers.{module_name}'
            module = importlib.import_module(full_module_name)
            _loaded_modules[module_name] = module
        except ImportError as e:
            logger.warning(
                f"Failed to import handler module {module_name} for "
                f"service {service_name}: {e}"
            )
            return []

    # Get service-specific handlers from the module
    # First try ALL_HANDLERS (used by our modular handler files)
    if hasattr(module, 'ALL_HANDLERS'):
        return module.ALL_HANDLERS

    # Then try service-specific attribute (e.g., S3_HANDLERS)
    handlers_attr = f'{service_name.upper().replace("-", "_")}_HANDLERS'
    if hasattr(module, handlers_attr):
        return getattr(module, handlers_attr)

    # Finally try SERVICE_HANDLERS dict
    if hasattr(module, 'SERVICE_HANDLERS'):
        return module.SERVICE_HANDLERS.get(service_name, [])

    return []


def get_all_service_handlers():
    """Get all service handlers from all modules.

    This function is used for backwards compatibility to build the complete
    BUILTIN_HANDLERS list. It loads all handler modules and combines their
    handlers.

    Returns:
        A list of all service-specific handlers.
    """
    all_handlers = []
    seen_modules = set()

    for service_name, module_name in SERVICE_HANDLER_MODULES.items():
        if module_name in seen_modules:
            continue
        seen_modules.add(module_name)

        try:
            full_module_name = f'botocore.handlers.{module_name}'
            module = importlib.import_module(full_module_name)
            _loaded_modules[module_name] = module

            # Get all handlers from the module's ALL_HANDLERS attribute
            if hasattr(module, 'ALL_HANDLERS'):
                all_handlers.extend(module.ALL_HANDLERS)
        except ImportError as e:
            logger.warning(
                f"Failed to import handler module {module_name}: {e}"
            )

    return all_handlers


class LazyHandlerRegistry:
    """Registry for lazy loading of service-specific handlers.

    This class manages the registration of handlers on-demand based on
    which services are actually being used.
    """

    def __init__(self, event_emitter):
        """Initialize the lazy handler registry.

        Args:
            event_emitter: The botocore event emitter to register handlers with.
        """
        self._event_emitter = event_emitter
        self._registered_services = set()
        self._core_registered = False

    def register_core_handlers(self):
        """Register core handlers that are always needed."""
        if self._core_registered:
            return

        from botocore.handlers._core import CORE_HANDLERS, REGISTER_FIRST

        for handler_entry in CORE_HANDLERS:
            self._register_handler(handler_entry)

        self._core_registered = True

    def register_service_handlers(self, service_name):
        """Register handlers for a specific service.

        This method is idempotent - calling it multiple times for the same
        service will only register the handlers once.

        Args:
            service_name: The name of the AWS service.
        """
        if service_name in self._registered_services:
            return

        handlers = get_service_handlers(service_name)
        for handler_entry in handlers:
            self._register_handler(handler_entry)

        self._registered_services.add(service_name)

    def _register_handler(self, handler_entry):
        """Register a single handler entry.

        Args:
            handler_entry: A tuple of (event_name, handler[, priority])
        """
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


def register_lazy_handlers(event_emitter, service_name):
    """Convenience function to register handlers for a service.

    This function ensures core handlers are registered and then registers
    any service-specific handlers.

    Args:
        event_emitter: The botocore event emitter.
        service_name: The name of the AWS service.
    """
    registry = LazyHandlerRegistry(event_emitter)
    registry.register_core_handlers()
    registry.register_service_handlers(service_name)
