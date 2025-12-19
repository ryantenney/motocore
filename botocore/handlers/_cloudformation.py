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

"""CloudFormation event handlers.

This module contains handlers specific to AWS CloudFormation.
"""

import logging

from botocore.compat import OrderedDict, json

logger = logging.getLogger(__name__)


def json_decode_template_body(parsed, **kwargs):
    """Decode JSON TemplateBody in CloudFormation GetTemplate response."""
    if 'TemplateBody' in parsed:
        try:
            value = json.loads(
                parsed['TemplateBody'], object_pairs_hook=OrderedDict
            )
            parsed['TemplateBody'] = value
        except (ValueError, TypeError):
            logger.debug('error loading JSON', exc_info=True)


def document_cloudformation_get_template_return_type(
    section, event_name, **kwargs
):
    """Document GetTemplate TemplateBody return type as dict."""
    if 'response-params' in event_name:
        template_body_section = section.get_section('TemplateBody')
        type_section = template_body_section.get_section('param-type')
        type_section.clear_text()
        type_section.write('(*dict*) --')
    elif 'response-example' in event_name:
        parent = section.get_section('structure-value')
        param_line = parent.get_section('TemplateBody')
        value_portion = param_line.get_section('member-value')
        value_portion.clear_text()
        value_portion.write('{}')


# All CloudFormation handlers
ALL_HANDLERS = [
    ('after-call.cloudformation.GetTemplate', json_decode_template_body),
    (
        'docs.*.cloudformation.GetTemplate.complete-section',
        document_cloudformation_get_template_return_type,
    ),
]
