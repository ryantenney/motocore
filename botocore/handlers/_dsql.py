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

"""DSQL event handlers.

This module contains handlers specific to Amazon DSQL.
"""

from botocore.signers import add_dsql_generate_db_auth_token_methods


# All DSQL handlers
ALL_HANDLERS = [
    ('creating-client-class.dsql', add_dsql_generate_db_auth_token_methods),
]
