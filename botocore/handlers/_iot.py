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

"""IoT Data event handlers.

This module contains handlers specific to AWS IoT Data.
"""

import warnings

from botocore.exceptions import UnsupportedTLSVersionWarning


def check_openssl_supports_tls_version_1_2(**kwargs):
    """Check if OpenSSL supports TLS 1.2 for IoT Data."""
    import ssl

    try:
        openssl_version_tuple = ssl.OPENSSL_VERSION_INFO
        if openssl_version_tuple < (1, 0, 1):
            warnings.warn(
                f'Currently installed openssl version: {ssl.OPENSSL_VERSION} does not '
                'support TLS 1.2, which is required for use of iot-data. '
                'Please use python installed with openssl version 1.0.1 or '
                'higher.',
                UnsupportedTLSVersionWarning,
            )
    except AttributeError:
        pass


# All IoT Data handlers
ALL_HANDLERS = [
    ('creating-client-class.iot-data', check_openssl_supports_tls_version_1_2),
]
