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

"""CloudSearch Domain event handlers.

This module contains handlers specific to Amazon CloudSearch Domain.
"""


def change_get_to_post(request, **kwargs):
    """Change GET request to POST with x-www-form-urlencoded encoding.

    This is useful when we need to change a potentially large GET request
    into a POST.
    """
    if request.method == 'GET' and '?' in request.url:
        request.headers['Content-Type'] = 'application/x-www-form-urlencoded'
        request.method = 'POST'
        request.url, request.data = request.url.split('?', 1)


# All CloudSearch Domain handlers
ALL_HANDLERS = [
    ('request-created.cloudsearchdomain.Search', change_get_to_post),
]
