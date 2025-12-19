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

"""Machine Learning event handlers.

This module contains handlers specific to Amazon Machine Learning.
"""

from botocore.utils import switch_host_with_param


def switch_host_machinelearning(request, **kwargs):
    """Switch host to PredictEndpoint for Predict operation."""
    switch_host_with_param(request, 'PredictEndpoint')


# All Machine Learning handlers
ALL_HANDLERS = [
    ('request-created.machinelearning.Predict', switch_host_machinelearning),
]
