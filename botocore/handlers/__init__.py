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

"""Builtin event handlers.

This module contains builtin handlers for events emitted by botocore.

This module maintains backwards compatibility by re-exporting all handlers
and constants from the modular handler files. New code should import from
the specific handler modules (e.g., botocore.handlers._s3) when only specific
functionality is needed.
"""

# Re-export core components
from botocore.handlers._core import (
    REGISTER_FIRST,
    REGISTER_LAST,
    _resolve_sigv4a_region,
    _set_auth_scheme_preference_signer,
    _should_prefer_bearer_auth,
    add_expect_header,
    add_recursion_detection_header,
    add_retry_headers,
    disable_signing,
    generate_idempotent_uuid,
    get_bearer_auth_supported_services,
    handle_service_name_alias,
    inject_api_version_header_if_needed,
    set_operation_specific_signer,
)

# Re-export S3 components for backwards compatibility
from botocore.handlers._s3 import (
    S3_SIGNING_NAMES,
    VALID_BUCKET,
    VALID_S3_ARN,
    VERSION_ID_SUFFIX,
    _decode_list_object,
    _handle_200_error,
    _handle_request_validation_mode_member,
    _has_expires_shape,
    _looks_like_special_case_error,
    _needs_s3_sse_customization,
    _quote_source_header,
    _quote_source_header_from_dict,
    _set_extra_headers_for_unsigned_request,
    _should_handle_200_error,
    _sse_md5,
    _update_status_code,
    check_for_200_error,
    convert_body_to_file_like_object,
    copy_source_sse_md5,
    customize_endpoint_resolver_builtins,
    decode_list_object,
    decode_list_object_v2,
    decode_list_object_versions,
    document_copy_source_form,
    document_expires_shape,
    escape_xml_payload,
    handle_copy_source_param,
    handle_expires_header,
    parse_get_bucket_location,
    remove_accid_host_prefix_from_model,
    remove_arn_from_signing_path,
    remove_bucket_from_url_paths_from_model,
    remove_content_type_header_for_presigning,
    set_list_objects_encoding_type_url,
    sse_md5,
    validate_ascii_metadata,
    validate_bucket_name,
)

# Re-export EC2 components
from botocore.handlers._ec2 import (
    base64_encode_user_data,
    decode_console_output,
    document_base64_encoding,
    inject_presigned_url_ec2,
)

# Re-export RDS components
from botocore.handlers._rds import inject_presigned_url_rds

# Re-export Glacier components
from botocore.handlers._glacier import (
    add_accept_header,
    add_glacier_checksums,
    add_glacier_version,
    document_glacier_tree_hash_checksum,
    inject_account_id,
)

# Re-export Route53 components
from botocore.handlers._route53 import fix_route53_ids

# Re-export IAM components
from botocore.handlers._iam import (
    decode_quoted_jsondoc,
    json_decode_policies,
)

# Re-export CloudFormation components
from botocore.handlers._cloudformation import (
    document_cloudformation_get_template_return_type,
    json_decode_template_body,
)

# Re-export Machine Learning components
from botocore.handlers._machinelearning import switch_host_machinelearning
from botocore.utils import switch_host_with_param

# Re-export IoT components
from botocore.handlers._iot import check_openssl_supports_tls_version_1_2

# Re-export CloudSearch components
from botocore.handlers._cloudsearch import change_get_to_post

# Re-export SQS components
from botocore.handlers._sqs import _handle_sqs_compatible_error

# Re-export Lex components
from botocore.handlers._lex import remove_lex_v2_start_conversation

# Re-export Q Business components
from botocore.handlers._qbusiness import remove_qbusiness_chat

# Re-export Bedrock components
from botocore.handlers._bedrock import (
    enable_millisecond_timestamp_precision,
    remove_bedrock_runtime_invoke_model_with_bidirectional_stream,
)

# Re-export alias components
from botocore.handlers._aliases import ParameterAlias, _add_parameter_aliases

# Re-export MTurk/Social Messaging components
from botocore.handlers._mturk import ClientMethodAlias

# Import for lazy loading support
from botocore.handlers._registry import (
    LazyHandlerRegistry,
    get_all_service_handlers,
    get_service_handlers,
    register_lazy_handlers,
)

# Backwards compatibility imports
import botocore
from botocore import retryhandler, translate, utils
from botocore.compat import MD5_AVAILABLE
from botocore.docs.utils import (
    AppendParamDocumentation,
    AutoPopulatedParam,
    HideParamFromOperations,
)
from botocore.exceptions import MissingServiceIdError
from botocore.signers import (
    add_dsql_generate_db_auth_token_methods,
    add_generate_db_auth_token,
    add_generate_presigned_post,
    add_generate_presigned_url,
)
from botocore.utils import (
    SERVICE_NAME_ALIASES,
    hyphenize_service_id,
    is_global_accesspoint,
)


# TODO: Remove this class as it is no longer used
class HeaderToHostHoister:
    """Takes a header and moves it to the front of the hoststring."""

    import re
    from botocore.compat import urlsplit, urlunsplit
    from botocore.exceptions import ParamValidationError

    _VALID_HOSTNAME = re.compile(r'(?!-)[a-z\d-]{1,63}(?<!-)$', re.IGNORECASE)

    def __init__(self, header_name):
        self._header_name = header_name

    def hoist(self, params, **kwargs):
        """Hoist a header to the hostname."""
        if self._header_name not in params['headers']:
            return
        header_value = params['headers'][self._header_name]
        self._ensure_header_is_valid_host(header_value)
        original_url = params['url']
        new_url = self._prepend_to_host(original_url, header_value)
        params['url'] = new_url

    def _ensure_header_is_valid_host(self, header):
        match = self._VALID_HOSTNAME.match(header)
        if not match:
            from botocore.exceptions import ParamValidationError
            raise ParamValidationError(
                report=(
                    'Hostnames must contain only - and alphanumeric characters, '
                    'and between 1 and 63 characters long.'
                )
            )

    def _prepend_to_host(self, url, prefix):
        from botocore.compat import urlsplit, urlunsplit
        url_components = urlsplit(url)
        parts = url_components.netloc.split('.')
        parts = [prefix] + parts
        new_netloc = '.'.join(parts)
        new_components = (
            url_components.scheme,
            new_netloc,
            url_components.path,
            url_components.query,
            '',
        )
        new_url = urlunsplit(new_components)
        return new_url


class DeprecatedServiceDocumenter:
    """Document deprecated services with replacement notice."""

    def __init__(self, replacement_service_name):
        self._replacement_service_name = replacement_service_name

    def inject_deprecation_notice(self, section, event_name, **kwargs):
        section.style.start_important()
        section.write('This service client is deprecated. Please use ')
        section.style.ref(
            self._replacement_service_name,
            self._replacement_service_name,
        )
        section.write(' instead.')
        section.style.end_important()


def _build_builtin_handlers():
    """Build the complete BUILTIN_HANDLERS list from all modules.

    This function combines handlers from all service modules to create
    the complete list for backwards compatibility.
    """
    from botocore.handlers._core import CORE_HANDLERS
    from botocore.handlers._s3 import ALL_HANDLERS as S3_HANDLERS
    from botocore.handlers._ec2 import ALL_HANDLERS as EC2_HANDLERS
    from botocore.handlers._rds import ALL_HANDLERS as RDS_HANDLERS
    from botocore.handlers._glacier import ALL_HANDLERS as GLACIER_HANDLERS
    from botocore.handlers._route53 import ALL_HANDLERS as ROUTE53_HANDLERS
    from botocore.handlers._iam import ALL_HANDLERS as IAM_HANDLERS
    from botocore.handlers._sts import ALL_HANDLERS as STS_HANDLERS
    from botocore.handlers._cloudformation import ALL_HANDLERS as CF_HANDLERS
    from botocore.handlers._machinelearning import ALL_HANDLERS as ML_HANDLERS
    from botocore.handlers._iot import ALL_HANDLERS as IOT_HANDLERS
    from botocore.handlers._cloudsearch import ALL_HANDLERS as CS_HANDLERS
    from botocore.handlers._mturk import ALL_HANDLERS as MTURK_HANDLERS
    from botocore.handlers._sqs import ALL_HANDLERS as SQS_HANDLERS
    from botocore.handlers._lex import ALL_HANDLERS as LEX_HANDLERS
    from botocore.handlers._qbusiness import ALL_HANDLERS as QB_HANDLERS
    from botocore.handlers._bedrock import ALL_HANDLERS as BEDROCK_HANDLERS
    from botocore.handlers._polly import ALL_HANDLERS as POLLY_HANDLERS
    from botocore.handlers._autoscaling import ALL_HANDLERS as AS_HANDLERS
    from botocore.handlers._apigateway import ALL_HANDLERS as APIGW_HANDLERS
    from botocore.handlers._lambda import ALL_HANDLERS as LAMBDA_HANDLERS
    from botocore.handlers._dsql import ALL_HANDLERS as DSQL_HANDLERS
    from botocore.handlers._socialmessaging import ALL_HANDLERS as SM_HANDLERS
    from botocore.handlers._aliases import ALL_HANDLERS as ALIAS_HANDLERS

    handlers = list(CORE_HANDLERS)
    handlers.extend(S3_HANDLERS)
    handlers.extend(EC2_HANDLERS)
    handlers.extend(RDS_HANDLERS)
    handlers.extend(GLACIER_HANDLERS)
    handlers.extend(ROUTE53_HANDLERS)
    handlers.extend(IAM_HANDLERS)
    handlers.extend(STS_HANDLERS)
    handlers.extend(CF_HANDLERS)
    handlers.extend(ML_HANDLERS)
    handlers.extend(IOT_HANDLERS)
    handlers.extend(CS_HANDLERS)
    handlers.extend(MTURK_HANDLERS)
    handlers.extend(SQS_HANDLERS)
    handlers.extend(LEX_HANDLERS)
    handlers.extend(QB_HANDLERS)
    handlers.extend(BEDROCK_HANDLERS)
    handlers.extend(POLLY_HANDLERS)
    handlers.extend(AS_HANDLERS)
    handlers.extend(APIGW_HANDLERS)
    handlers.extend(LAMBDA_HANDLERS)
    handlers.extend(DSQL_HANDLERS)
    handlers.extend(SM_HANDLERS)
    handlers.extend(ALIAS_HANDLERS)

    return handlers


# Build the complete handler list for backwards compatibility
# This is a list of (event_name, handler).
# When a Session is created, everything in this list will be
# automatically registered with that Session.
BUILTIN_HANDLERS = _build_builtin_handlers()
