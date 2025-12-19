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

"""Parameter alias handlers.

This module contains the ParameterAlias class and handler registration
for parameter aliases across various services.
"""

from botocore.exceptions import AliasConflictParameterError
from botocore.handlers._core import REGISTER_FIRST


class ParameterAlias:
    """Handles parameter aliasing for API operations."""

    def __init__(self, original_name, alias_name):
        self._original_name = original_name
        self._alias_name = alias_name

    def alias_parameter_in_call(self, params, model, **kwargs):
        """Replace alias parameter with original parameter name."""
        if model.input_shape:
            if self._original_name in model.input_shape.members:
                if self._alias_name in params:
                    if self._original_name in params:
                        raise AliasConflictParameterError(
                            original=self._original_name,
                            alias=self._alias_name,
                            operation=model.name,
                        )
                    params[self._original_name] = params.pop(self._alias_name)

    def alias_parameter_in_documentation(self, event_name, section, **kwargs):
        """Update documentation to show alias instead of original name."""
        if event_name.startswith('docs.request-params'):
            if self._original_name not in section.available_sections:
                return
            param_section = section.get_section(self._original_name)
            param_type_section = param_section.get_section('param-type')
            self._replace_content(param_type_section)

            param_name_section = param_section.get_section('param-name')
            self._replace_content(param_name_section)
        elif event_name.startswith('docs.request-example'):
            section = section.get_section('structure-value')
            if self._original_name not in section.available_sections:
                return
            param_section = section.get_section(self._original_name)
            self._replace_content(param_section)

    def _replace_content(self, section):
        """Replace original name with alias in section content."""
        content = section.getvalue().decode('utf-8')
        updated_content = content.replace(
            self._original_name, self._alias_name
        )
        section.clear_text()
        section.write(updated_content)


# Parameter aliases configuration
# Format: 'service.operation.parameter': 'alias_name'
PARAMETER_ALIASES = {
    'ec2.*.Filter': 'Filters',
    'logs.CreateExportTask.from': 'fromTime',
    'cloudsearchdomain.Search.return': 'returnFields',
}


def _add_parameter_aliases(handler_list):
    """Add parameter alias handlers to the handler list."""
    for original, new_name in PARAMETER_ALIASES.items():
        event_portion, original_name = original.rsplit('.', 1)
        parameter_alias = ParameterAlias(original_name, new_name)

        parameter_build_event_handler_tuple = (
            'before-parameter-build.' + event_portion,
            parameter_alias.alias_parameter_in_call,
            REGISTER_FIRST,
        )
        docs_event_handler_tuple = (
            'docs.*.' + event_portion + '.complete-section',
            parameter_alias.alias_parameter_in_documentation,
        )
        handler_list.append(parameter_build_event_handler_tuple)
        handler_list.append(docs_event_handler_tuple)


def get_alias_handlers():
    """Get all parameter alias handlers."""
    handlers = []
    _add_parameter_aliases(handlers)
    return handlers


# All alias handlers
ALL_HANDLERS = get_alias_handlers()
