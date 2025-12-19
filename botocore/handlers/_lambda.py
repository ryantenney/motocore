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

"""Lambda event handlers.

This module contains handlers specific to AWS Lambda.
"""

from botocore.handlers._ec2 import document_base64_encoding


# All Lambda handlers
ALL_HANDLERS = [
    (
        'docs.*.lambda.UpdateFunctionCode.complete-section',
        document_base64_encoding('ZipFile'),
    ),
]
