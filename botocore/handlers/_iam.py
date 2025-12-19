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

"""IAM event handlers.

This module contains handlers specific to AWS IAM.
"""

import logging

from botocore.compat import json, unquote

logger = logging.getLogger(__name__)


def decode_quoted_jsondoc(value):
    """Decode a URL-encoded JSON document."""
    try:
        value = json.loads(unquote(value))
    except (ValueError, TypeError):
        logger.debug('Error loading quoted JSON', exc_info=True)
    return value


def json_decode_policies(parsed, model, **kwargs):
    """Decode JSON policy documents in IAM responses.

    Any time an IAM operation returns a policy document it is a string
    that is json that has been urlencoded. To give users something more
    useful, we will urldecode this value and json.loads() the result
    so that they have the policy document as a dictionary.
    """
    output_shape = model.output_shape
    if output_shape is not None:
        _decode_policy_types(parsed, model.output_shape)


def _decode_policy_types(parsed, shape):
    """Recursively decode policy document types in parsed response."""
    shape_name = 'policyDocumentType'
    if shape.type_name == 'structure':
        for member_name, member_shape in shape.members.items():
            if (
                member_shape.type_name == 'string'
                and member_shape.name == shape_name
                and member_name in parsed
            ):
                parsed[member_name] = decode_quoted_jsondoc(
                    parsed[member_name]
                )
            elif member_name in parsed:
                _decode_policy_types(parsed[member_name], member_shape)
    if shape.type_name == 'list':
        shape_member = shape.member
        for item in parsed:
            _decode_policy_types(item, shape_member)


# All IAM handlers
ALL_HANDLERS = [
    ('after-call.iam', json_decode_policies),
]
