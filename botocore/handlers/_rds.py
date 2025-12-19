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

"""RDS, Neptune, and DocDB event handlers.

This module contains handlers for Amazon RDS, Neptune, and DocumentDB services.
These services share common presigned URL handling.
"""

import copy

from botocore.docs.utils import AutoPopulatedParam
from botocore.signers import add_generate_db_auth_token


def _get_cross_region_presigned_url(
    request_signer, request_dict, model, source_region, destination_region
):
    """Generate a cross-region presigned URL."""
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


def inject_presigned_url_rds(params, request_signer, model, **kwargs):
    """Inject presigned URL for cross-region RDS/Neptune/DocDB operations.

    SourceRegion is not required for RDS operations, so it's possible that
    it isn't set. In that case it's probably a local copy so we don't need
    to do anything else.
    """
    if 'SourceRegion' not in params['body']:
        return

    src, dest = _get_presigned_url_source_and_destination_regions(
        request_signer, params['body']
    )

    # Since SourceRegion isn't actually modeled for RDS, it needs to be
    # removed from the request params before we send the actual request.
    del params['body']['SourceRegion']

    if 'PreSignedUrl' in params['body']:
        return

    url = _get_cross_region_presigned_url(
        request_signer, params, model, src, dest
    )
    params['body']['PreSignedUrl'] = url


# All RDS handlers
ALL_HANDLERS = [
    # RDS
    ('creating-client-class.rds', add_generate_db_auth_token),
    ('before-call.rds.CopyDBClusterSnapshot', inject_presigned_url_rds),
    ('before-call.rds.CreateDBCluster', inject_presigned_url_rds),
    ('before-call.rds.CopyDBSnapshot', inject_presigned_url_rds),
    ('before-call.rds.CreateDBInstanceReadReplica', inject_presigned_url_rds),
    (
        'before-call.rds.StartDBInstanceAutomatedBackupsReplication',
        inject_presigned_url_rds,
    ),
    # RDS PresignedUrl documentation customizations
    (
        'docs.*.rds.CopyDBClusterSnapshot.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
    (
        'docs.*.rds.CreateDBCluster.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
    (
        'docs.*.rds.CopyDBSnapshot.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
    (
        'docs.*.rds.CreateDBInstanceReadReplica.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
    (
        'docs.*.rds.StartDBInstanceAutomatedBackupsReplication.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
    # Neptune
    ('before-call.neptune.CopyDBClusterSnapshot', inject_presigned_url_rds),
    ('before-call.neptune.CreateDBCluster', inject_presigned_url_rds),
    # Neptune PresignedUrl documentation customizations
    (
        'docs.*.neptune.CopyDBClusterSnapshot.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
    (
        'docs.*.neptune.CreateDBCluster.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
    # DocDB
    ('before-call.docdb.CopyDBClusterSnapshot', inject_presigned_url_rds),
    ('before-call.docdb.CreateDBCluster', inject_presigned_url_rds),
    # DocDB PresignedUrl documentation customizations
    (
        'docs.*.docdb.CopyDBClusterSnapshot.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
    (
        'docs.*.docdb.CreateDBCluster.complete-section',
        AutoPopulatedParam('PreSignedUrl').document_auto_populated_param,
    ),
]
