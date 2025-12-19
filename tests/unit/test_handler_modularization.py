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

"""Tests for handler modularization infrastructure."""

import pytest
from unittest import mock


class TestCoreHandlers:
    """Tests for the core handlers module."""

    def test_core_handlers_are_defined(self):
        """Test that core handlers list exists and has handlers."""
        from botocore.handlers._core import CORE_HANDLERS

        assert len(CORE_HANDLERS) > 0
        # Verify it's a list of tuples
        for handler in CORE_HANDLERS:
            assert isinstance(handler, tuple)
            assert len(handler) >= 2

    def test_register_sentinels_are_available(self):
        """Test that REGISTER_FIRST and REGISTER_LAST are available."""
        from botocore.handlers._core import REGISTER_FIRST, REGISTER_LAST

        assert REGISTER_FIRST is not None
        assert REGISTER_LAST is not None
        # They should be different objects
        assert REGISTER_FIRST is not REGISTER_LAST

    def test_handle_service_name_alias(self):
        """Test service name aliasing."""
        from botocore.handlers._core import handle_service_name_alias

        # Test known alias
        result = handle_service_name_alias('runtime.sagemaker')
        assert result == 'sagemaker-runtime'

        # Test non-alias (returns original)
        result = handle_service_name_alias('s3')
        assert result == 's3'

    def test_generate_idempotent_uuid(self):
        """Test idempotent UUID generation."""
        from botocore.handlers._core import generate_idempotent_uuid

        # Create a mock model with idempotent members
        model = mock.Mock()
        model.idempotent_members = ['ClientToken']

        params = {}
        generate_idempotent_uuid(params, model)

        # UUID should have been added
        assert 'ClientToken' in params
        assert len(params['ClientToken']) == 36  # UUID format

    def test_generate_idempotent_uuid_does_not_override(self):
        """Test that existing idempotent tokens are not overwritten."""
        from botocore.handlers._core import generate_idempotent_uuid

        model = mock.Mock()
        model.idempotent_members = ['ClientToken']

        params = {'ClientToken': 'my-existing-token'}
        generate_idempotent_uuid(params, model)

        assert params['ClientToken'] == 'my-existing-token'

    def test_disable_signing(self):
        """Test disable_signing returns UNSIGNED."""
        import botocore
        from botocore.handlers._core import disable_signing

        result = disable_signing()
        assert result is botocore.UNSIGNED


class TestHandlerRegistry:
    """Tests for the handler registry."""

    def test_get_service_handlers_for_known_service(self):
        """Test getting handlers for a known service."""
        from botocore.handlers._registry import get_service_handlers

        handlers = get_service_handlers('s3')
        assert isinstance(handlers, list)
        # S3 has many handlers
        assert len(handlers) > 10

    def test_get_service_handlers_for_unknown_service(self):
        """Test getting handlers for an unknown service."""
        from botocore.handlers._registry import get_service_handlers

        handlers = get_service_handlers('unknown-service-xyz')
        assert handlers == []

    def test_service_handler_modules_mapping(self):
        """Test that service handler modules are properly mapped."""
        from botocore.handlers._registry import SERVICE_HANDLER_MODULES

        # Key services should be mapped
        assert 's3' in SERVICE_HANDLER_MODULES
        assert 'ec2' in SERVICE_HANDLER_MODULES
        assert 'rds' in SERVICE_HANDLER_MODULES
        assert 'neptune' in SERVICE_HANDLER_MODULES
        assert 'docdb' in SERVICE_HANDLER_MODULES
        assert 'glacier' in SERVICE_HANDLER_MODULES

    def test_shared_module_for_related_services(self):
        """Test that related services share the same module."""
        from botocore.handlers._registry import SERVICE_HANDLER_MODULES

        # RDS, Neptune, and DocDB should share the same module
        assert SERVICE_HANDLER_MODULES['rds'] == SERVICE_HANDLER_MODULES['neptune']
        assert SERVICE_HANDLER_MODULES['rds'] == SERVICE_HANDLER_MODULES['docdb']

    def test_get_all_service_handlers(self):
        """Test getting all handlers from all modules."""
        from botocore.handlers._registry import get_all_service_handlers

        handlers = get_all_service_handlers()
        assert isinstance(handlers, list)
        # Should have many handlers across all services
        assert len(handlers) > 50


class TestLazyHandlerRegistry:
    """Tests for the LazyHandlerRegistry class."""

    def test_lazy_registry_initialization(self):
        """Test LazyHandlerRegistry initialization."""
        from botocore.handlers._registry import LazyHandlerRegistry

        event_emitter = mock.Mock()
        registry = LazyHandlerRegistry(event_emitter)

        assert registry._event_emitter is event_emitter
        assert registry._registered_services == set()
        assert registry._core_registered is False

    def test_register_core_handlers(self):
        """Test registering core handlers."""
        from botocore.handlers._registry import LazyHandlerRegistry

        event_emitter = mock.Mock()
        registry = LazyHandlerRegistry(event_emitter)

        registry.register_core_handlers()

        # Should have registered some handlers
        assert event_emitter.register.called or event_emitter.register_first.called
        assert registry._core_registered is True

    def test_register_core_handlers_idempotent(self):
        """Test that registering core handlers twice does nothing."""
        from botocore.handlers._registry import LazyHandlerRegistry

        event_emitter = mock.Mock()
        registry = LazyHandlerRegistry(event_emitter)

        registry.register_core_handlers()
        first_call_count = event_emitter.register.call_count

        registry.register_core_handlers()
        second_call_count = event_emitter.register.call_count

        # No additional registrations
        assert first_call_count == second_call_count

    def test_register_service_handlers(self):
        """Test registering service-specific handlers."""
        from botocore.handlers._registry import LazyHandlerRegistry

        event_emitter = mock.Mock()
        registry = LazyHandlerRegistry(event_emitter)

        registry.register_service_handlers('s3')

        assert 's3' in registry._registered_services

    def test_register_service_handlers_idempotent(self):
        """Test that registering service handlers twice does nothing."""
        from botocore.handlers._registry import LazyHandlerRegistry

        event_emitter = mock.Mock()
        registry = LazyHandlerRegistry(event_emitter)

        registry.register_service_handlers('ec2')
        first_call_count = event_emitter.register.call_count

        registry.register_service_handlers('ec2')
        second_call_count = event_emitter.register.call_count

        assert first_call_count == second_call_count


class TestS3Handlers:
    """Tests for S3-specific handlers."""

    def test_s3_signing_names(self):
        """Test S3 signing names constant."""
        from botocore.handlers._s3 import S3_SIGNING_NAMES

        assert 's3' in S3_SIGNING_NAMES
        assert 's3-outposts' in S3_SIGNING_NAMES
        assert 's3-object-lambda' in S3_SIGNING_NAMES
        assert 's3express' in S3_SIGNING_NAMES

    def test_valid_bucket_pattern(self):
        """Test valid bucket name pattern."""
        from botocore.handlers._s3 import VALID_BUCKET

        assert VALID_BUCKET.match('my-bucket')
        assert VALID_BUCKET.match('my.bucket.name')
        assert VALID_BUCKET.match('my_bucket_123')
        assert not VALID_BUCKET.match('')
        assert not VALID_BUCKET.match('a' * 256)  # Too long

    def test_validate_bucket_name_valid(self):
        """Test bucket name validation with valid name."""
        from botocore.handlers._s3 import validate_bucket_name

        params = {'Bucket': 'valid-bucket-name'}
        validate_bucket_name(params)  # Should not raise

    def test_validate_bucket_name_invalid(self):
        """Test bucket name validation with invalid name."""
        from botocore.handlers._s3 import validate_bucket_name
        from botocore.exceptions import ParamValidationError

        params = {'Bucket': 'invalid bucket name with spaces'}
        with pytest.raises(ParamValidationError):
            validate_bucket_name(params)

    def test_s3_handlers_list(self):
        """Test that S3 handlers list is properly defined."""
        from botocore.handlers._s3 import ALL_HANDLERS

        assert isinstance(ALL_HANDLERS, list)
        assert len(ALL_HANDLERS) > 20  # S3 has many handlers


class TestEC2Handlers:
    """Tests for EC2-specific handlers."""

    def test_decode_console_output(self):
        """Test console output decoding."""
        import base64
        from botocore.handlers._ec2 import decode_console_output

        # Base64 encoded "Hello, World!"
        encoded = base64.b64encode(b"Hello, World!").decode('latin-1')
        parsed = {'Output': encoded}

        decode_console_output(parsed)

        assert parsed['Output'] == "Hello, World!"

    def test_base64_encode_user_data_string(self):
        """Test base64 encoding of UserData string."""
        import base64
        from botocore.handlers._ec2 import base64_encode_user_data

        params = {'UserData': 'echo "hello"'}
        base64_encode_user_data(params)

        decoded = base64.b64decode(params['UserData']).decode('utf-8')
        assert decoded == 'echo "hello"'

    def test_base64_encode_user_data_bytes(self):
        """Test base64 encoding of UserData bytes."""
        import base64
        from botocore.handlers._ec2 import base64_encode_user_data

        params = {'UserData': b'binary data'}
        base64_encode_user_data(params)

        decoded = base64.b64decode(params['UserData'])
        assert decoded == b'binary data'

    def test_ec2_handlers_list(self):
        """Test that EC2 handlers list is properly defined."""
        from botocore.handlers._ec2 import ALL_HANDLERS

        assert isinstance(ALL_HANDLERS, list)
        assert len(ALL_HANDLERS) > 0


class TestRDSHandlers:
    """Tests for RDS/Neptune/DocDB handlers."""

    def test_rds_handlers_list(self):
        """Test that RDS handlers list includes all related services."""
        from botocore.handlers._rds import ALL_HANDLERS

        # Convert to event names for checking
        event_names = [h[0] for h in ALL_HANDLERS]

        # Should have handlers for RDS, Neptune, and DocDB
        assert any('rds' in e for e in event_names)
        assert any('neptune' in e for e in event_names)
        assert any('docdb' in e for e in event_names)


class TestGlacierHandlers:
    """Tests for Glacier handlers."""

    def test_inject_account_id(self):
        """Test account ID injection."""
        from botocore.handlers._glacier import inject_account_id

        params = {}
        inject_account_id(params)
        assert params['accountId'] == '-'

    def test_inject_account_id_no_override(self):
        """Test that existing account ID is not overwritten."""
        from botocore.handlers._glacier import inject_account_id

        params = {'accountId': '123456789012'}
        inject_account_id(params)
        assert params['accountId'] == '123456789012'


class TestAliasHandlers:
    """Tests for parameter alias handlers."""

    def test_parameter_alias_class(self):
        """Test ParameterAlias class initialization."""
        from botocore.handlers._aliases import ParameterAlias

        alias = ParameterAlias('Filter', 'Filters')
        assert alias._original_name == 'Filter'
        assert alias._alias_name == 'Filters'

    def test_parameter_aliases_config(self):
        """Test that parameter aliases are configured."""
        from botocore.handlers._aliases import PARAMETER_ALIASES

        assert 'ec2.*.Filter' in PARAMETER_ALIASES
        assert 'logs.CreateExportTask.from' in PARAMETER_ALIASES
        assert 'cloudsearchdomain.Search.return' in PARAMETER_ALIASES


class TestBackwardsCompatibility:
    """Tests for backwards compatibility of the handlers package."""

    def test_builtin_handlers_exists(self):
        """Test that BUILTIN_HANDLERS is exported."""
        from botocore.handlers import BUILTIN_HANDLERS

        assert isinstance(BUILTIN_HANDLERS, list)
        assert len(BUILTIN_HANDLERS) > 100

    def test_core_exports_available(self):
        """Test that core handler functions are exported."""
        from botocore.handlers import (
            handle_service_name_alias,
            add_recursion_detection_header,
            generate_idempotent_uuid,
            set_operation_specific_signer,
            add_retry_headers,
            disable_signing,
            REGISTER_FIRST,
            REGISTER_LAST,
        )

        # Just verify they're callable/accessible
        assert callable(handle_service_name_alias)
        assert callable(add_recursion_detection_header)
        assert callable(generate_idempotent_uuid)
        assert callable(set_operation_specific_signer)
        assert callable(add_retry_headers)
        assert callable(disable_signing)
        assert REGISTER_FIRST is not None
        assert REGISTER_LAST is not None

    def test_s3_exports_available(self):
        """Test that S3 handler functions are exported."""
        from botocore.handlers import (
            validate_bucket_name,
            sse_md5,
            copy_source_sse_md5,
            handle_copy_source_param,
            parse_get_bucket_location,
            set_list_objects_encoding_type_url,
            decode_list_object,
            S3_SIGNING_NAMES,
            VALID_BUCKET,
        )

        assert callable(validate_bucket_name)
        assert callable(sse_md5)
        assert callable(copy_source_sse_md5)
        assert callable(handle_copy_source_param)
        assert callable(parse_get_bucket_location)
        assert callable(set_list_objects_encoding_type_url)
        assert callable(decode_list_object)
        assert isinstance(S3_SIGNING_NAMES, tuple)
        assert VALID_BUCKET is not None

    def test_ec2_exports_available(self):
        """Test that EC2 handler functions are exported."""
        from botocore.handlers import (
            decode_console_output,
            base64_encode_user_data,
            inject_presigned_url_ec2,
        )

        assert callable(decode_console_output)
        assert callable(base64_encode_user_data)
        assert callable(inject_presigned_url_ec2)

    def test_glacier_exports_available(self):
        """Test that Glacier handler functions are exported."""
        from botocore.handlers import (
            inject_account_id,
            add_glacier_version,
            add_glacier_checksums,
        )

        assert callable(inject_account_id)
        assert callable(add_glacier_version)
        assert callable(add_glacier_checksums)

    def test_iam_exports_available(self):
        """Test that IAM handler functions are exported."""
        from botocore.handlers import (
            json_decode_policies,
            decode_quoted_jsondoc,
        )

        assert callable(json_decode_policies)
        assert callable(decode_quoted_jsondoc)

    def test_class_exports_available(self):
        """Test that handler classes are exported."""
        from botocore.handlers import (
            ParameterAlias,
            ClientMethodAlias,
            HeaderToHostHoister,
            DeprecatedServiceDocumenter,
        )

        assert ParameterAlias is not None
        assert ClientMethodAlias is not None
        assert HeaderToHostHoister is not None
        assert DeprecatedServiceDocumenter is not None

    def test_legacy_imports_available(self):
        """Test that legacy re-exports are available."""
        from botocore.handlers import (
            retryhandler,
            translate,
            utils,
            MD5_AVAILABLE,
            SERVICE_NAME_ALIASES,
        )

        assert retryhandler is not None
        assert translate is not None
        assert utils is not None
        assert isinstance(MD5_AVAILABLE, bool)
        assert isinstance(SERVICE_NAME_ALIASES, dict)
