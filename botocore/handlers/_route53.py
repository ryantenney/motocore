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

"""Route53 event handlers.

This module contains handlers specific to Amazon Route 53.
"""

import logging

logger = logging.getLogger(__name__)


def fix_route53_ids(params, model, **kwargs):
    """
    Check for and split apart Route53 resource IDs, setting
    only the last piece. This allows the output of one operation
    (e.g. ``'foo/1234'``) to be used as input in another
    operation (e.g. it expects just ``'1234'``).
    """
    input_shape = model.input_shape
    if not input_shape or not hasattr(input_shape, 'members'):
        return

    members = [
        name
        for (name, shape) in input_shape.members.items()
        if shape.name in ['ResourceId', 'DelegationSetId', 'ChangeId']
    ]

    for name in members:
        if name in params:
            orig_value = params[name]
            params[name] = orig_value.split('/')[-1]
            logger.debug('%s %s -> %s', name, orig_value, params[name])


# All Route53 handlers
ALL_HANDLERS = [
    ('before-parameter-build.route53', fix_route53_ids),
]
