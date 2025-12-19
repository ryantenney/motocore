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

"""SQS event handlers.

This module contains handlers specific to Amazon SQS.
"""


def _handle_sqs_compatible_error(parsed, context, **kwargs):
    """
    Ensures backward compatibility for SQS errors.

    SQS's migration from the Query protocol to JSON was done prior to SDKs allowing a
    service to support multiple protocols. Because of this, SQS is missing the "error"
    key from its modeled exceptions, which is used by most query compatible services
    to map error codes to the proper exception. Instead, SQS uses the error's shape name,
    which is preserved in the QueryErrorCode key.
    """
    parsed_error = parsed.get("Error", {})
    if not parsed_error:
        return

    if query_code := parsed_error.get("QueryErrorCode"):
        context['error_code_override'] = query_code


# All SQS handlers
ALL_HANDLERS = [
    ('after-call.sqs.*', _handle_sqs_compatible_error),
]
