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

"""Bedrock event handlers.

This module contains handlers specific to Amazon Bedrock Runtime and Agent Core.
"""

from botocore.serialize import TIMESTAMP_PRECISION_MILLISECOND


def remove_bedrock_runtime_invoke_model_with_bidirectional_stream(
    class_attributes, **kwargs
):
    """Remove bidirectional stream operation (requires h2 which is unsupported)."""
    if 'invoke_model_with_bidirectional_stream' in class_attributes:
        del class_attributes['invoke_model_with_bidirectional_stream']


def enable_millisecond_timestamp_precision(serializer_kwargs, **kwargs):
    """Enable millisecond precision for timestamps."""
    serializer_kwargs['timestamp_precision'] = TIMESTAMP_PRECISION_MILLISECOND


# All Bedrock handlers
ALL_HANDLERS = [
    (
        'creating-client-class.bedrock-runtime',
        remove_bedrock_runtime_invoke_model_with_bidirectional_stream,
    ),
    (
        'creating-serializer.bedrock-agentcore',
        enable_millisecond_timestamp_precision,
    ),
]
