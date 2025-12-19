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

"""STS and Cognito Identity event handlers.

This module contains handlers for AWS STS and Cognito Identity services.
These services share common handlers for disabling signing on certain operations.
"""

from botocore.handlers._core import disable_signing


# All STS and Cognito Identity handlers
ALL_HANDLERS = [
    ('choose-signer.cognito-identity.GetId', disable_signing),
    ('choose-signer.cognito-identity.GetOpenIdToken', disable_signing),
    ('choose-signer.cognito-identity.UnlinkIdentity', disable_signing),
    (
        'choose-signer.cognito-identity.GetCredentialsForIdentity',
        disable_signing,
    ),
    ('choose-signer.sts.AssumeRoleWithSAML', disable_signing),
    ('choose-signer.sts.AssumeRoleWithWebIdentity', disable_signing),
]
