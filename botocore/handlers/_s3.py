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

"""S3 and S3 Control event handlers.

This module contains handlers specific to Amazon S3 and S3 Control services.
"""

import base64
import logging
import re
from io import BytesIO

import botocore
from botocore.compat import (
    ETree,
    XMLParseError,
    ensure_bytes,
    get_md5,
    unquote_str,
)
from botocore.docs.utils import (
    AutoPopulatedParam,
    HideParamFromOperations,
)
from botocore.endpoint_provider import VALID_HOST_LABEL_RE
from botocore.exceptions import ParamValidationError
from botocore.handlers._core import REGISTER_FIRST, REGISTER_LAST
from botocore.regions import EndpointResolverBuiltins
from botocore.signers import add_generate_presigned_post
from botocore.utils import (
    SAFE_CHARS,
    ArnParser,
    is_s3express_bucket,
    percent_encode,
)

logger = logging.getLogger(__name__)

# S3 bucket name validation patterns
VALID_BUCKET = re.compile(r'^[a-zA-Z0-9.\-_]{1,255}$')
_ACCESSPOINT_ARN = (
    r'^arn:(aws).*:(s3|s3-object-lambda):[a-z\-0-9]*:[0-9]{12}:accesspoint[/:]'
    r'[a-zA-Z0-9\-.]{1,63}$'
)
_OUTPOST_ARN = (
    r'^arn:(aws).*:s3-outposts:[a-z\-0-9]+:[0-9]{12}:outpost[/:]'
    r'[a-zA-Z0-9\-]{1,63}[/:]accesspoint[/:][a-zA-Z0-9\-]{1,63}$'
)
VALID_S3_ARN = re.compile('|'.join([_ACCESSPOINT_ARN, _OUTPOST_ARN]))

# Signing names used for S3 services
S3_SIGNING_NAMES = ('s3', 's3-outposts', 's3-object-lambda', 's3express')

VERSION_ID_SUFFIX = re.compile(r'\?versionId=[^\s]+$')


def escape_xml_payload(params, **kwargs):
    """Escape \\r and \\n in XML payloads to avoid linebreak normalization."""
    body = params['body']
    if b'\r' in body:
        body = body.replace(b'\r', b'&#xD;')
    if b'\n' in body:
        body = body.replace(b'\n', b'&#xA;')
    params['body'] = body


def check_for_200_error(response, **kwargs):
    """This function has been deprecated, but is kept for backwards compatibility."""
    if response is None:
        return
    http_response, parsed = response
    if _looks_like_special_case_error(
        http_response.status_code, http_response.content
    ):
        logger.debug(
            "Error found for response with 200 status code, "
            "errors: %s, changing status code to "
            "500.",
            parsed,
        )
        http_response.status_code = 500


def _looks_like_special_case_error(status_code, body):
    """Check if a 200 response actually contains an error."""
    if status_code == 200 and body:
        try:
            parser = ETree.XMLParser(
                target=ETree.TreeBuilder(), encoding='utf-8'
            )
            parser.feed(body)
            root = parser.close()
        except XMLParseError:
            return True
        if root.tag == 'Error':
            return True
    return False


def validate_bucket_name(params, **kwargs):
    """Validate S3 bucket name format."""
    if 'Bucket' not in params:
        return
    bucket = params['Bucket']
    if not VALID_BUCKET.search(bucket) and not VALID_S3_ARN.search(bucket):
        error_msg = (
            f'Invalid bucket name "{bucket}": Bucket name must match '
            f'the regex "{VALID_BUCKET.pattern}" or be an ARN matching '
            f'the regex "{VALID_S3_ARN.pattern}"'
        )
        raise ParamValidationError(report=error_msg)


def sse_md5(params, **kwargs):
    """Handle S3 server-side encryption MD5 for SSECustomerKey."""
    _sse_md5(params, 'SSECustomer')


def copy_source_sse_md5(params, **kwargs):
    """Handle S3 server-side encryption MD5 for CopySourceSSECustomerKey."""
    _sse_md5(params, 'CopySourceSSECustomer')


def _sse_md5(params, sse_member_prefix='SSECustomer'):
    """Compute and set SSE MD5 hash."""
    if not _needs_s3_sse_customization(params, sse_member_prefix):
        return

    sse_key_member = sse_member_prefix + 'Key'
    sse_md5_member = sse_member_prefix + 'KeyMD5'
    key_as_bytes = params[sse_key_member]
    if isinstance(key_as_bytes, str):
        key_as_bytes = key_as_bytes.encode('utf-8')
    md5_val = get_md5(key_as_bytes, usedforsecurity=False).digest()
    key_md5_str = base64.b64encode(md5_val).decode('utf-8')
    key_b64_encoded = base64.b64encode(key_as_bytes).decode('utf-8')
    params[sse_key_member] = key_b64_encoded
    params[sse_md5_member] = key_md5_str


def _needs_s3_sse_customization(params, sse_member_prefix):
    """Check if SSE customization is needed."""
    return (
        params.get(sse_member_prefix + 'Key') is not None
        and sse_member_prefix + 'KeyMD5' not in params
    )


def document_copy_source_form(section, event_name, **kwargs):
    """Document the CopySource parameter format."""
    if 'request-example' in event_name:
        parent = section.get_section('structure-value')
        param_line = parent.get_section('CopySource')
        value_portion = param_line.get_section('member-value')
        value_portion.clear_text()
        value_portion.write(
            "'string' or {'Bucket': 'string', "
            "'Key': 'string', 'VersionId': 'string'}"
        )
    elif 'request-params' in event_name:
        param_section = section.get_section('CopySource')
        type_section = param_section.get_section('param-type')
        type_section.clear_text()
        type_section.write(':type CopySource: str or dict')
        doc_section = param_section.get_section('param-documentation')
        doc_section.clear_text()
        doc_section.write(
            "The name of the source bucket, key name of the source object, "
            "and optional version ID of the source object.  You can either "
            "provide this value as a string or a dictionary.  The "
            "string form is {bucket}/{key} or "
            "{bucket}/{key}?versionId={versionId} if you want to copy a "
            "specific version.  You can also provide this value as a "
            "dictionary.  The dictionary format is recommended over "
            "the string format because it is more explicit.  The dictionary "
            "format is: {'Bucket': 'bucket', 'Key': 'key', 'VersionId': 'id'}."
            "  Note that the VersionId key is optional and may be omitted."
            " To specify an S3 access point, provide the access point"
            " ARN for the ``Bucket`` key in the copy source dictionary. If you"
            " want to provide the copy source for an S3 access point as a"
            " string instead of a dictionary, the ARN provided must be the"
            " full S3 access point object ARN"
            " (i.e. {accesspoint_arn}/object/{key})"
        )


def handle_copy_source_param(params, **kwargs):
    """Convert CopySource param for CopyObject/UploadPartCopy."""
    source = params.get('CopySource')
    if source is None:
        return
    if isinstance(source, str):
        params['CopySource'] = _quote_source_header(source)
    elif isinstance(source, dict):
        params['CopySource'] = _quote_source_header_from_dict(source)


def _quote_source_header_from_dict(source_dict):
    """Build CopySource header from dictionary."""
    try:
        bucket = source_dict['Bucket']
        key = source_dict['Key']
        version_id = source_dict.get('VersionId')
        if VALID_S3_ARN.search(bucket):
            final = f'{bucket}/object/{key}'
        else:
            final = f'{bucket}/{key}'
    except KeyError as e:
        raise ParamValidationError(
            report=f'Missing required parameter: {str(e)}'
        )
    final = percent_encode(final, safe=SAFE_CHARS + '/')
    if version_id is not None:
        final += f'?versionId={version_id}'
    return final


def _quote_source_header(value):
    """Quote the CopySource header value."""
    result = VERSION_ID_SUFFIX.search(value)
    if result is None:
        return percent_encode(value, safe=SAFE_CHARS + '/')
    else:
        first, version_id = value[: result.start()], value[result.start() :]
        return percent_encode(first, safe=SAFE_CHARS + '/') + version_id


def parse_get_bucket_location(parsed, http_response, **kwargs):
    """Parse GetBucketLocation response."""
    if http_response.raw is None:
        return
    response_body = http_response.content
    parser = ETree.XMLParser(target=ETree.TreeBuilder(), encoding='utf-8')
    parser.feed(response_body)
    root = parser.close()
    region = root.text
    parsed['LocationConstraint'] = region


def validate_ascii_metadata(params, **kwargs):
    """Verify S3 Metadata only contains ASCII characters."""
    metadata = params.get('Metadata')
    if not metadata or not isinstance(metadata, dict):
        return
    for key, value in metadata.items():
        try:
            key.encode('ascii')
            value.encode('ascii')
        except UnicodeEncodeError:
            error_msg = (
                'Non ascii characters found in S3 metadata '
                f'for key "{key}", value: "{value}".  \nS3 metadata can only '
                'contain ASCII characters. '
            )
            raise ParamValidationError(report=error_msg)


def set_list_objects_encoding_type_url(params, context, **kwargs):
    """Set EncodingType to 'url' for ListObjects operations."""
    if 'EncodingType' not in params:
        context['encoding_type_auto_set'] = True
        params['EncodingType'] = 'url'


def decode_list_object(parsed, context, **kwargs):
    """Decode URL-encoded values from ListObjects response."""
    _decode_list_object(
        top_level_keys=['Delimiter', 'Marker', 'NextMarker'],
        nested_keys=[('Contents', 'Key'), ('CommonPrefixes', 'Prefix')],
        parsed=parsed,
        context=context,
    )


def decode_list_object_v2(parsed, context, **kwargs):
    """Decode URL-encoded values from ListObjectsV2 response."""
    _decode_list_object(
        top_level_keys=['Delimiter', 'Prefix', 'StartAfter'],
        nested_keys=[('Contents', 'Key'), ('CommonPrefixes', 'Prefix')],
        parsed=parsed,
        context=context,
    )


def decode_list_object_versions(parsed, context, **kwargs):
    """Decode URL-encoded values from ListObjectVersions response."""
    _decode_list_object(
        top_level_keys=[
            'KeyMarker',
            'NextKeyMarker',
            'Prefix',
            'Delimiter',
        ],
        nested_keys=[
            ('Versions', 'Key'),
            ('DeleteMarkers', 'Key'),
            ('CommonPrefixes', 'Prefix'),
        ],
        parsed=parsed,
        context=context,
    )


def _decode_list_object(top_level_keys, nested_keys, parsed, context):
    """Decode URL-encoded values from list responses."""
    if parsed.get('EncodingType') == 'url' and context.get(
        'encoding_type_auto_set'
    ):
        for key in top_level_keys:
            if key in parsed:
                parsed[key] = unquote_str(parsed[key])
        for top_key, child_key in nested_keys:
            if top_key in parsed:
                for member in parsed[top_key]:
                    member[child_key] = unquote_str(member[child_key])


def convert_body_to_file_like_object(params, **kwargs):
    """Convert string/bytes Body to file-like object."""
    if 'Body' in params:
        if isinstance(params['Body'], str):
            params['Body'] = BytesIO(ensure_bytes(params['Body']))
        elif isinstance(params['Body'], bytes):
            params['Body'] = BytesIO(params['Body'])


def remove_bucket_from_url_paths_from_model(params, model, context, **kwargs):
    """Strip leading {Bucket}/ from operation requestUri."""
    req_uri = model.http['requestUri']
    bucket_path = '/{Bucket}'
    if req_uri.startswith(bucket_path):
        model.http['requestUri'] = req_uri[len(bucket_path) :]
        req_uri = req_uri.split('?')[0]
        needs_slash = req_uri == bucket_path
        model.http['authPath'] = f'{req_uri}/' if needs_slash else req_uri


def remove_accid_host_prefix_from_model(params, model, context, **kwargs):
    """Remove {AccountId}. prefix from S3 Control operations."""
    has_ctx_param = any(
        ctx_param.name == 'RequiresAccountId' and ctx_param.value is True
        for ctx_param in model.static_context_parameters
    )
    if (
        model.endpoint is not None
        and model.endpoint.get('hostPrefix') == '{AccountId}.'
        and has_ctx_param
    ):
        del model.endpoint['hostPrefix']


def remove_arn_from_signing_path(request, **kwargs):
    """Remove ARN from the signing path."""
    from botocore.compat import unquote

    auth_path = request.auth_path
    if isinstance(auth_path, str) and auth_path.startswith('/arn%3A'):
        auth_path_parts = auth_path.split('/')
        if len(auth_path_parts) > 1 and ArnParser.is_arn(
            unquote(auth_path_parts[1])
        ):
            request.auth_path = '/'.join(['', *auth_path_parts[2:]])


def customize_endpoint_resolver_builtins(
    builtins, model, params, context, **kwargs
):
    """Modify builtin parameter values for S3 endpoint resolution."""
    bucket_name = params.get('Bucket')
    bucket_is_arn = bucket_name is not None and ArnParser.is_arn(bucket_name)

    if model.name == 'GetBucketLocation':
        builtins[EndpointResolverBuiltins.AWS_S3_FORCE_PATH_STYLE] = True
    elif bucket_is_arn:
        builtins[EndpointResolverBuiltins.AWS_S3_FORCE_PATH_STYLE] = False

    path_style_required = (
        bucket_name is not None and not VALID_HOST_LABEL_RE.match(bucket_name)
    )
    path_style_requested = builtins[
        EndpointResolverBuiltins.AWS_S3_FORCE_PATH_STYLE
    ]

    if (
        context.get('use_global_endpoint')
        and not path_style_required
        and not path_style_requested
        and not bucket_is_arn
        and not is_s3express_bucket(bucket_name)
    ):
        builtins[EndpointResolverBuiltins.AWS_REGION] = 'aws-global'
        builtins[EndpointResolverBuiltins.AWS_S3_USE_GLOBAL_ENDPOINT] = True


def remove_content_type_header_for_presigning(request, **kwargs):
    """Remove Content-Type header for presigned requests."""
    if (
        request.context.get('is_presign_request') is True
        and 'Content-Type' in request.headers
    ):
        del request.headers['Content-Type']


def handle_expires_header(
    operation_model, response_dict, customized_response_dict, **kwargs
):
    """Handle the Expires header, copying to ExpiresString."""
    if _has_expires_shape(operation_model.output_shape):
        if expires_value := response_dict.get('headers', {}).get('Expires'):
            customized_response_dict['ExpiresString'] = expires_value
            try:
                from botocore import utils

                utils.parse_timestamp(expires_value)
            except (ValueError, RuntimeError):
                logger.warning(
                    'Failed to parse the "Expires" member as a timestamp: %s. '
                    'The unparsed value is available in the response under "ExpiresString".',
                    expires_value,
                )
                del response_dict['headers']['Expires']


def _has_expires_shape(shape):
    """Check if shape has an Expires member."""
    if not shape:
        return False
    return any(
        member_shape.name == 'Expires'
        and member_shape.serialization.get('name') == 'Expires'
        for member_shape in shape.members.values()
    )


def document_expires_shape(section, event_name, **kwargs):
    """Document the ExpiresString synthetic member."""
    if 'response-example' in event_name:
        if not section.has_section('structure-value'):
            return
        parent = section.get_section('structure-value')
        if not parent.has_section('Expires'):
            return
        param_line = parent.get_section('Expires')
        param_line.add_new_section('ExpiresString')
        new_param_line = param_line.get_section('ExpiresString')
        new_param_line.write("'ExpiresString': 'string',")
        new_param_line.style.new_line()
    elif 'response-params' in event_name:
        if not section.has_section('Expires'):
            return
        param_section = section.get_section('Expires')
        doc_section = param_section.get_section('param-documentation')
        doc_section.style.start_note()
        doc_section.write(
            'This member has been deprecated. Please use ``ExpiresString`` instead.'
        )
        doc_section.style.end_note()
        new_param_section = param_section.add_new_section('ExpiresString')
        new_param_section.style.new_paragraph()
        new_param_section.write('- **ExpiresString** *(string) --*')
        new_param_section.style.indent()
        new_param_section.style.new_paragraph()
        new_param_section.write(
            'The raw, unparsed value of the ``Expires`` field.'
        )


def _handle_200_error(operation_model, response_dict, **kwargs):
    """Convert S3 200 responses with embedded errors to 500."""
    if not _should_handle_200_error(operation_model, response_dict):
        return
    if _looks_like_special_case_error(
        response_dict['status_code'], response_dict['body']
    ):
        response_dict['status_code'] = 500
        logger.debug(
            "Error found for response with 200 status code: %s.",
            response_dict['body'],
        )


def _should_handle_200_error(operation_model, response_dict):
    """Check if 200 error handling applies to this operation."""
    output_shape = operation_model.output_shape
    if (
        not response_dict
        or operation_model.has_event_stream_output
        or not output_shape
    ):
        return False
    payload = output_shape.serialization.get('payload')
    if payload is not None:
        payload_shape = output_shape.members[payload]
        if payload_shape.type_name in ('blob', 'string'):
            return False
    return True


def _update_status_code(response, **kwargs):
    """Update http_response status code when parsed response was modified."""
    if response is None:
        return
    http_response, parsed = response
    parsed_status_code = parsed.get('ResponseMetadata', {}).get(
        'HTTPStatusCode', http_response.status_code
    )
    if http_response.status_code != parsed_status_code:
        http_response.status_code = parsed_status_code


def _handle_request_validation_mode_member(params, model, **kwargs):
    """Handle request validation mode for checksum operations."""
    client_config = kwargs.get("context", {}).get("client_config")
    if client_config is None:
        return
    response_checksum_validation = client_config.response_checksum_validation
    http_checksum = model.http_checksum
    mode_member = http_checksum.get("requestValidationModeMember")
    if (
        mode_member is not None
        and response_checksum_validation == "when_supported"
    ):
        params.setdefault(mode_member, "ENABLED")


def _set_extra_headers_for_unsigned_request(
    request, signature_version, **kwargs
):
    """Set extra headers for unsigned chunked requests with checksums."""
    checksum_context = request.context.get("checksum", {})
    algorithm = checksum_context.get("request_algorithm", {})
    in_trailer = algorithm.get("in") == "trailer"
    headers = request.headers
    if signature_version == botocore.UNSIGNED and in_trailer:
        headers["X-Amz-Content-SHA256"] = "STREAMING-UNSIGNED-PAYLOAD-TRAILER"


# All S3 handlers
ALL_HANDLERS = [
    (
        'before-parameter-build.s3.UploadPart',
        convert_body_to_file_like_object,
        REGISTER_LAST,
    ),
    (
        'before-parameter-build.s3.PutObject',
        convert_body_to_file_like_object,
        REGISTER_LAST,
    ),
    ('creating-client-class.s3', add_generate_presigned_post),
    ('after-call.s3.GetBucketLocation', parse_get_bucket_location),
    ('before-parse.s3.*', handle_expires_header),
    ('before-parse.s3.*', _handle_200_error, REGISTER_FIRST),
    ('before-parameter-build', _handle_request_validation_mode_member),
    ('before-parameter-build.s3', validate_bucket_name),
    ('before-parameter-build.s3', remove_bucket_from_url_paths_from_model),
    (
        'before-parameter-build.s3.ListObjects',
        set_list_objects_encoding_type_url,
    ),
    (
        'before-parameter-build.s3.ListObjectsV2',
        set_list_objects_encoding_type_url,
    ),
    (
        'before-parameter-build.s3.ListObjectVersions',
        set_list_objects_encoding_type_url,
    ),
    ('before-parameter-build.s3.CopyObject', handle_copy_source_param),
    ('before-parameter-build.s3.UploadPartCopy', handle_copy_source_param),
    ('before-parameter-build.s3.CopyObject', validate_ascii_metadata),
    ('before-parameter-build.s3.PutObject', validate_ascii_metadata),
    (
        'before-parameter-build.s3.CreateMultipartUpload',
        validate_ascii_metadata,
    ),
    ('before-parameter-build.s3-control', remove_accid_host_prefix_from_model),
    ('docs.*.s3.CopyObject.complete-section', document_copy_source_form),
    ('docs.*.s3.UploadPartCopy.complete-section', document_copy_source_form),
    ('docs.response-example.s3.*.complete-section', document_expires_shape),
    ('docs.response-params.s3.*.complete-section', document_expires_shape),
    ('before-endpoint-resolution.s3', customize_endpoint_resolver_builtins),
    ('before-call.s3', 'botocore.handlers._core:add_expect_header'),
    ('before-call.s3.DeleteObjects', escape_xml_payload),
    ('before-call.s3.PutBucketLifecycleConfiguration', escape_xml_payload),
    ('needs-retry.s3.*', _update_status_code, REGISTER_FIRST),
    ('before-parameter-build.s3.HeadObject', sse_md5),
    ('before-parameter-build.s3.GetObject', sse_md5),
    ('before-parameter-build.s3.PutObject', sse_md5),
    ('before-parameter-build.s3.CopyObject', sse_md5),
    ('before-parameter-build.s3.CopyObject', copy_source_sse_md5),
    ('before-parameter-build.s3.CreateMultipartUpload', sse_md5),
    ('before-parameter-build.s3.UploadPart', sse_md5),
    ('before-parameter-build.s3.UploadPartCopy', sse_md5),
    ('before-parameter-build.s3.UploadPartCopy', copy_source_sse_md5),
    ('before-parameter-build.s3.CompleteMultipartUpload', sse_md5),
    ('before-parameter-build.s3.SelectObjectContent', sse_md5),
    ('before-sign.s3', remove_arn_from_signing_path),
    ('before-sign.s3', _set_extra_headers_for_unsigned_request),
    ('after-call.s3.ListObjects', decode_list_object),
    ('after-call.s3.ListObjectsV2', decode_list_object_v2),
    ('after-call.s3.ListObjectVersions', decode_list_object_versions),
    # S3 SSE documentation modifications
    (
        'docs.*.s3.*.complete-section',
        AutoPopulatedParam('SSECustomerKeyMD5').document_auto_populated_param,
    ),
    (
        'docs.*.s3.*.complete-section',
        AutoPopulatedParam(
            'CopySourceSSECustomerKeyMD5'
        ).document_auto_populated_param,
    ),
    # The following S3 operations cannot actually accept a ContentMD5
    (
        'docs.*.s3.*.complete-section',
        HideParamFromOperations(
            's3',
            'ContentMD5',
            [
                'DeleteObjects',
                'PutBucketAcl',
                'PutBucketCors',
                'PutBucketLifecycle',
                'PutBucketLogging',
                'PutBucketNotification',
                'PutBucketPolicy',
                'PutBucketReplication',
                'PutBucketRequestPayment',
                'PutBucketTagging',
                'PutBucketVersioning',
                'PutBucketWebsite',
                'PutObjectAcl',
            ],
        ).hide_param,
    ),
]

# Fix the add_expect_header reference - it's defined in _core
# We need to replace the string reference with the actual function
from botocore.handlers._core import add_expect_header

ALL_HANDLERS = [
    (h[0], add_expect_header if h[1] == 'botocore.handlers._core:add_expect_header' else h[1], *h[2:]) if len(h) >= 2 else h
    for h in ALL_HANDLERS
]
