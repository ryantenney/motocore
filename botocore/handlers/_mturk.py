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

"""Mechanical Turk event handlers.

This module contains handlers specific to Amazon Mechanical Turk.
"""


class ClientMethodAlias:
    """Aliases a non-extant method to an existing method."""

    def __init__(self, actual_name):
        """Initialize the alias.

        :param actual_name: The name of the method that actually exists on
            the client.
        """
        self._actual = actual_name

    def __call__(self, client, **kwargs):
        return getattr(client, self._actual)


# All MTurk handlers
ALL_HANDLERS = [
    (
        'getattr.mturk.list_hi_ts_for_qualification_type',
        ClientMethodAlias('list_hits_for_qualification_type'),
    ),
]
