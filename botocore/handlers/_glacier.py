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

"""Glacier event handlers.

This module contains handlers specific to Amazon Glacier.
"""

from io import BytesIO

from botocore import utils
from botocore.docs.utils import (
    AppendParamDocumentation,
    AutoPopulatedParam,
)


def inject_account_id(params, **kwargs):
    """Inject default accountId if not provided."""
    if params.get('accountId') is None:
        # Glacier requires accountId, but allows you
        # to specify '-' for the current owners account.
        # We add this default value if the user does not
        # provide the accountId as a convenience.
        params['accountId'] = '-'


def add_glacier_version(model, params, **kwargs):
    """Add x-amz-glacier-version header."""
    request_dict = params
    request_dict['headers']['x-amz-glacier-version'] = model.metadata[
        'apiVersion'
    ]


def add_accept_header(model, params, **kwargs):
    """Add Accept: application/json header if not present."""
    if params['headers'].get('Accept', None) is None:
        request_dict = params
        request_dict['headers']['Accept'] = 'application/json'


def add_glacier_checksums(params, **kwargs):
    """Add glacier checksums to the http request.

    This will add two headers to the http request:

        * x-amz-content-sha256
        * x-amz-sha256-tree-hash

    These values will only be added if they are not present
    in the HTTP request.
    """
    request_dict = params
    headers = request_dict['headers']
    body = request_dict['body']
    if isinstance(body, bytes):
        body = BytesIO(body)
    starting_position = body.tell()
    if 'x-amz-content-sha256' not in headers:
        headers['x-amz-content-sha256'] = utils.calculate_sha256(
            body, as_hex=True
        )
    body.seek(starting_position)
    if 'x-amz-sha256-tree-hash' not in headers:
        headers['x-amz-sha256-tree-hash'] = utils.calculate_tree_hash(body)
    body.seek(starting_position)


def document_glacier_tree_hash_checksum():
    """Create documentation for glacier checksum parameter."""
    doc = '''
        This is a required field.

        Ideally you will want to compute this value with checksums from
        previous uploaded parts, using the algorithm described in
        `Glacier documentation <http://docs.aws.amazon.com/amazonglacier/latest/dev/checksum-calculations.html>`_.

        But if you prefer, you can also use botocore.utils.calculate_tree_hash()
        to compute it from raw file by::

            checksum = calculate_tree_hash(open('your_file.txt', 'rb'))

        '''
    return AppendParamDocumentation('checksum', doc).append_documentation


# All Glacier handlers
ALL_HANDLERS = [
    ('before-parameter-build.glacier', inject_account_id),
    ('before-call.glacier', add_glacier_version),
    ('before-call.glacier.UploadArchive', add_glacier_checksums),
    ('before-call.glacier.UploadMultipartPart', add_glacier_checksums),
    # Glacier documentation customizations
    (
        'docs.*.glacier.*.complete-section',
        AutoPopulatedParam(
            'accountId',
            'Note: this parameter is set to "-" by'
            'default if no value is not specified.',
        ).document_auto_populated_param,
    ),
    (
        'docs.*.glacier.UploadArchive.complete-section',
        AutoPopulatedParam('checksum').document_auto_populated_param,
    ),
    (
        'docs.*.glacier.UploadMultipartPart.complete-section',
        AutoPopulatedParam('checksum').document_auto_populated_param,
    ),
    (
        'docs.request-params.glacier.CompleteMultipartUpload.complete-section',
        document_glacier_tree_hash_checksum(),
    ),
]
