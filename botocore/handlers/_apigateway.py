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

"""API Gateway event handlers.

This module contains handlers specific to Amazon API Gateway.
"""


def add_accept_header(model, params, **kwargs):
    """Add Accept: application/json header if not present."""
    if params['headers'].get('Accept', None) is None:
        request_dict = params
        request_dict['headers']['Accept'] = 'application/json'


# All API Gateway handlers
ALL_HANDLERS = [
    ('before-call.apigateway', add_accept_header),
]
