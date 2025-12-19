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

"""Core builtin event handlers.

This module contains core handlers that are always registered with every
botocore session, regardless of which service is being used. These handlers
are essential for basic botocore functionality.
"""

import logging
import os
import uuid

import botocore
import botocore.auth
from botocore.args import ClientConfigString
from botocore.compat import quote
from botocore.signers import add_generate_presigned_url
from botocore.useragent import register_feature_id
from botocore.utils import (
    SERVICE_NAME_ALIASES,
    get_token_from_environment,
)

logger = logging.getLogger(__name__)


def handle_service_name_alias(service_name, **kwargs):
    """Handle service name aliases (e.g., 'runtime.sagemaker' -> 'sagemaker-runtime')."""
    return SERVICE_NAME_ALIASES.get(service_name, service_name)


def add_recursion_detection_header(params, **kwargs):
    """Add X-Amzn-Trace-Id header for Lambda recursion detection."""
    has_lambda_name = 'AWS_LAMBDA_FUNCTION_NAME' in os.environ
    trace_id = os.environ.get('_X_AMZN_TRACE_ID')
    if has_lambda_name and trace_id:
        headers = params['headers']
        if 'X-Amzn-Trace-Id' not in headers:
            headers['X-Amzn-Trace-Id'] = quote(trace_id, safe='-=;:+&[]{}"\',')


def generate_idempotent_uuid(params, model, **kwargs):
    """Auto-generate idempotency tokens for operations that require them."""
    for name in model.idempotent_members:
        if name not in params:
            params[name] = str(uuid.uuid4())
            logger.debug(
                "injecting idempotency token (%s) into param '%s'.",
                params[name],
                name,
            )


def set_operation_specific_signer(context, signing_name, **kwargs):
    """Choose the operation-specific signer.

    Individual operations may have a different auth type than the service as a
    whole. This will most often manifest as operations that should not be
    authenticated at all, but can include other auth modes such as sigv4
    without body signing.
    """
    auth_type = context.get('auth_type')

    # Auth type will be None if the operation doesn't have a configured auth
    # type.
    if not auth_type:
        return

    # Auth type will be the string value 'none' if the operation should not
    # be signed at all.
    if auth_type == 'none':
        return botocore.UNSIGNED

    if auth_type == 'bearer':
        return 'bearer'

    # If the operation needs an unsigned body, we set additional context
    # allowing the signer to be aware of this.
    if context.get('unsigned_payload') or auth_type == 'v4-unsigned-body':
        context['payload_signing_enabled'] = False

    if auth_type.startswith('v4'):
        if auth_type == 'v4-s3express':
            return auth_type

        if auth_type == 'v4a':
            # If sigv4a is chosen, we must add additional signing config for
            # global signature.
            region = _resolve_sigv4a_region(context)
            signing = {'region': region, 'signing_name': signing_name}
            if 'signing' in context:
                context['signing'].update(signing)
            else:
                context['signing'] = signing
            signature_version = 'v4a'
        else:
            signature_version = 'v4'

        # Signing names used by s3 and s3-control use customized signers "s3v4"
        # and "s3v4a".
        # Import here to avoid circular dependency
        from botocore.handlers._s3 import S3_SIGNING_NAMES

        if signing_name in S3_SIGNING_NAMES:
            signature_version = f's3{signature_version}'

        return signature_version


def _resolve_sigv4a_region(context):
    """Resolve the region for SigV4A signing."""
    region = None
    if 'client_config' in context:
        region = context['client_config'].sigv4a_signing_region_set
    if not region and context.get('signing', {}).get('region'):
        region = context['signing']['region']
    return region or '*'


def add_retry_headers(request, **kwargs):
    """Add retry-related headers to requests."""
    retries_context = request.context.get('retries')
    if not retries_context:
        return
    headers = request.headers
    headers['amz-sdk-invocation-id'] = retries_context['invocation-id']
    sdk_retry_keys = ('ttl', 'attempt', 'max')
    sdk_request_headers = [
        f'{key}={retries_context[key]}'
        for key in sdk_retry_keys
        if key in retries_context
    ]
    headers['amz-sdk-request'] = '; '.join(sdk_request_headers)


def inject_api_version_header_if_needed(model, params, **kwargs):
    """Inject x-amz-api-version header for endpoint discovery operations."""
    if not model.is_endpoint_discovery_operation:
        return
    params['headers']['x-amz-api-version'] = model.service_model.api_version


def add_expect_header(model, params, **kwargs):
    """Add Expect: 100-continue header for PUT/POST with streaming body."""
    from botocore import utils

    if model.http.get('method', '') not in ['PUT', 'POST']:
        return
    if 'body' in params:
        body = params['body']
        if hasattr(body, 'read'):
            check_body = utils.ensure_boolean(
                os.environ.get(
                    'BOTO_EXPERIMENTAL__NO_EMPTY_CONTINUE',
                    False,
                )
            )
            if check_body and utils.determine_content_length(body) == 0:
                return
            # Any file like object will use an expect 100-continue
            # header regardless of size.
            logger.debug("Adding expect 100 continue header to request.")
            params['headers']['Expect'] = '100-continue'


def disable_signing(**kwargs):
    """
    This handler disables request signing by setting the signer
    name to a special sentinel value.
    """
    return botocore.UNSIGNED


def _set_auth_scheme_preference_signer(context, signing_name, **kwargs):
    """
    Determines the appropriate signer to use based on the client configuration,
    authentication scheme preferences, and the availability of a bearer token.
    """
    client_config = context.get('client_config')
    if client_config is None:
        return

    signature_version = client_config.signature_version
    auth_scheme_preference = client_config.auth_scheme_preference
    auth_options = context.get('auth_options')

    signature_version_set_in_code = (
        isinstance(signature_version, ClientConfigString)
        or signature_version is botocore.UNSIGNED
    )
    auth_preference_set_in_code = isinstance(
        auth_scheme_preference, ClientConfigString
    )
    has_in_code_configuration = (
        signature_version_set_in_code or auth_preference_set_in_code
    )

    resolved_signature_version = signature_version

    # If signature version was not set in code, but an auth scheme preference
    # is available, resolve it based on the preferred schemes and supported auth
    # options for this service.
    if (
        not signature_version_set_in_code
        and auth_scheme_preference
        and auth_options
    ):
        preferred_schemes = auth_scheme_preference.split(',')
        resolved = botocore.auth.resolve_auth_scheme_preference(
            preferred_schemes, auth_options
        )
        resolved_signature_version = (
            botocore.UNSIGNED if resolved == 'none' else resolved
        )

    # Prefer 'bearer' signature version if a bearer token is available, and it
    # is allowed for this service. This can override earlier resolution if the
    # config object didn't explicitly set a signature version.
    if _should_prefer_bearer_auth(
        has_in_code_configuration,
        signing_name,
        resolved_signature_version,
        auth_options,
    ):
        register_feature_id('BEARER_SERVICE_ENV_VARS')
        resolved_signature_version = 'bearer'

    if resolved_signature_version == signature_version:
        return None
    return resolved_signature_version


def _should_prefer_bearer_auth(
    has_in_code_configuration,
    signing_name,
    resolved_signature_version,
    auth_options,
):
    """Check if bearer auth should be preferred."""
    if signing_name not in get_bearer_auth_supported_services():
        return False

    if not auth_options or 'smithy.api#httpBearerAuth' not in auth_options:
        return False

    has_token = get_token_from_environment(signing_name) is not None

    # Prefer 'bearer' if a bearer token is available, and either:
    #   Bearer was already resolved, or
    #   No auth-related values were explicitly set in code
    return has_token and (
        resolved_signature_version == 'bearer' or not has_in_code_configuration
    )


def get_bearer_auth_supported_services():
    """
    Returns a set of services that support bearer token authentication.
    These values correspond to the service's `signingName` property as defined
    in model.py, falling back to `endpointPrefix` if `signingName` is not set.

    Warning: This is a private interface and is subject to abrupt breaking changes,
    including removal, in any botocore release. It is not intended for external use,
    and its usage outside of botocore is not advised or supported.
    """
    return {'bedrock'}


# Sentinel values for handler registration priority
REGISTER_FIRST = object()
REGISTER_LAST = object()


# Core handlers that are always registered
CORE_HANDLERS = [
    ('choose-service-name', handle_service_name_alias),
    ('creating-client-class', add_generate_presigned_url),
    ('before-parameter-build', generate_idempotent_uuid),
    ('before-call', add_recursion_detection_header),
    ('request-created', add_retry_headers),
    ('choose-signer', set_operation_specific_signer),
    ('choose-signer', _set_auth_scheme_preference_signer),
    ('before-call', inject_api_version_header_if_needed),
]
