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

"""EC2 event handlers.

This module contains handlers specific to Amazon EC2.
"""

import base64
import copy
import logging

from botocore.docs.utils import (
    AppendParamDocumentation,
    AutoPopulatedParam,
)

logger = logging.getLogger(__name__)


def decode_console_output(parsed, **kwargs):
    """Decode base64-encoded console output from EC2 instances."""
    if 'Output' in parsed:
        try:
            value = base64.b64decode(
                bytes(parsed['Output'], 'latin-1')
            ).decode('utf-8', 'replace')
            parsed['Output'] = value
        except (ValueError, TypeError, AttributeError):
            logger.debug('Error decoding base64', exc_info=True)


def base64_encode_user_data(params, **kwargs):
    """Base64 encode UserData parameter for EC2 RunInstances."""
    if 'UserData' in params:
        if isinstance(params['UserData'], str):
            params['UserData'] = params['UserData'].encode('utf-8')
        params['UserData'] = base64.b64encode(params['UserData']).decode(
            'utf-8'
        )


def document_base64_encoding(param):
    """Create documentation handler for base64 encoded parameters."""
    description = (
        '**This value will be base64 encoded automatically. Do '
        'not base64 encode this value prior to performing the '
        'operation.**'
    )
    append = AppendParamDocumentation(param, description)
    return append.append_documentation


def _get_cross_region_presigned_url(
    request_signer, request_dict, model, source_region, destination_region
):
    """Generate a cross-region presigned URL for EC2 operations."""
    request_dict_copy = copy.deepcopy(request_dict)
    request_dict_copy['body']['DestinationRegion'] = destination_region
    request_dict_copy['url'] = request_dict['url'].replace(
        destination_region, source_region
    )
    request_dict_copy['method'] = 'GET'
    request_dict_copy['headers'] = {}
    return request_signer.generate_presigned_url(
        request_dict_copy, region_name=source_region, operation_name=model.name
    )


def _get_presigned_url_source_and_destination_regions(request_signer, params):
    """Get source and destination regions for presigned URL generation."""
    destination_region = request_signer._region_name
    source_region = params.get('SourceRegion')
    return source_region, destination_region


def inject_presigned_url_ec2(params, request_signer, model, **kwargs):
    """Inject presigned URL for EC2 CopySnapshot operation."""
    if 'PresignedUrl' in params['body']:
        return
    src, dest = _get_presigned_url_source_and_destination_regions(
        request_signer, params['body']
    )
    url = _get_cross_region_presigned_url(
        request_signer, params, model, src, dest
    )
    params['body']['PresignedUrl'] = url
    params['body']['DestinationRegion'] = dest


# All EC2 handlers
ALL_HANDLERS = [
    ('after-call.ec2.GetConsoleOutput', decode_console_output),
    ('before-parameter-build.ec2.RunInstances', base64_encode_user_data),
    ('before-call.ec2.CopySnapshot', inject_presigned_url_ec2),
    # EC2 CopySnapshot documentation customizations
    (
        'docs.*.ec2.CopySnapshot.complete-section',
        AutoPopulatedParam('PresignedUrl').document_auto_populated_param,
    ),
    (
        'docs.*.ec2.CopySnapshot.complete-section',
        AutoPopulatedParam('DestinationRegion').document_auto_populated_param,
    ),
    # UserData base64 encoding documentation
    (
        'docs.*.ec2.RunInstances.complete-section',
        document_base64_encoding('UserData'),
    ),
]
