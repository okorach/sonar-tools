#
# sonar-tools
# Copyright (C) 2026 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

"""SonarQube API manager"""

from __future__ import annotations
from typing import Any, Optional, ClassVar, TYPE_CHECKING

import os
from enum import Enum
from pathlib import Path
import json
from collections import defaultdict
import inspect

import sonar.utilities as sutil
import sonar.logging as log
from sonar.util import misc

if TYPE_CHECKING:
    from sonar.platform import Platform


class ApiOperation(Enum):
    """List of possible API operations"""

    CREATE = "CREATE"
    GET = "GET"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SEARCH = "SEARCH"

    RENAME = "RENAME"
    RECOMPUTE = "RECOMPUTE"
    LIST_MEMBERS = "LIST_MEMBERS"
    LIST_GROUPS = "LIST_GROUPS"
    ADD_USER = "ADD_USER"
    REMOVE_USER = "REMOVE_USER"
    ADD_PROJECT = "ADD_PROJECT"
    REMOVE_PROJECT = "REMOVE_PROJECT"
    GET_HISTORY = "GET_HISTORY"
    GET_PROJECTS = "GET_PROJECTS"
    ASSIGN = "ASSIGN"
    SET_TAGS = "SET_TAGS"
    GET_TAGS = "GET_TAGS"
    GET_CHANGELOG = "GET_CHANGELOG"
    ADD_COMMENT = "ADD_COMMENT"
    SET_SEVERITY = "SET_SEVERITY"
    SET_TYPE = "SET_TYPE"
    DO_TRANSITION = "DO_TRANSITION"
    CREATE_GITHUB = "CREATE_GITHUB"
    CREATE_GITLAB = "CREATE_GITLAB"
    CREATE_AZURE = "CREATE_AZURE"
    CREATE_BITBUCKET = "CREATE_BITBUCKET"
    CREATE_BITBUCKETCLOUD = "CREATE_BITBUCKETCLOUD"
    UPDATE_GITHUB = "UPDATE_GITHUB"
    UPDATE_GITLAB = "UPDATE_GITLAB"
    UPDATE_AZURE = "UPDATE_AZURE"
    UPDATE_BITBUCKET = "UPDATE_BITBUCKET"
    UPDATE_BITBUCKETCLOUD = "UPDATE_BITBUCKETCLOUD"
    SET_PAT = "SET_PAT"
    SET_DEFAULT = "SET_DEFAULT"
    ACTIVATE_RULE = "ACTIVATE_RULE"
    DEACTIVATE_RULE = "DEACTIVATE_RULE"
    COMPARE = "COMPARE"
    CHANGE_STATUS = "CHANGE_STATUS"
    CHANGE_PARENT = "CHANGE_PARENT"
    COPY = "COPY"
    GET_MQR_MODE = "GET_MQR_MODE"
    SET_MQR_MODE = "SET_MQR_MODE"
    GET_NEW_CODE_PERIOD = "GET_NEW_CODE_PERIOD"
    SET_NEW_CODE_PERIOD = "SET_NEW_CODE_PERIOD"
    LIST_DEFINITIONS = "LIST_DEFINITIONS"
    RESET = "RESET"
    KEEP_WHEN_INACTIVE = "KEEP_WHEN_INACTIVE"
    SET_MAIN = "SET_MAIN"
    LIST_NEW_CODE_PERIODS = "LIST_NEW_CODE_PERIODS"
    GET_SUBCOMPONENTS = "GET_SUBCOMPONENTS"
    EXPORT_FINDINGS = "EXPORT_FINDINGS"
    GET_LOGS = "GET_LOGS"


class ApiManager:
    """Abstraction of the SonarQube API"""

    __RETURN_FIELD_KEY = "return_field"
    __PAGE_FIELD_KEY = "page_field"
    __MAX_PAGE_SIZE_KEY = "max_page_size"
    __DEFAULT_MAX_PAGE_SIZE = 500

    SQS_API: ClassVar[dict[str, Any]] = {}
    SQC_API: ClassVar[dict[str, Any]] = {}

    def __init__(self, endpoint: Platform) -> None:
        """Constructor"""
        self.endpoint: Platform = endpoint
        if self.endpoint.is_sonarcloud():
            data = self.__class__.SQC_API
        else:
            api_versions = sorted([tuple(int(s) for s in v.split(".")) for v in self.__class__.SQS_API], reverse=True)
            api_version_to_use = sutil.version_to_string(next(v for v in api_versions if self.endpoint.version() >= v))
            data = self.__class__.SQS_API[api_version_to_use]
        self.api_def = data
        log.debug("%s API definition: %s", endpoint, misc.json_dump(data))

    def get_api_entry(self, object_or_class: object, operation: ApiOperation) -> dict[str, Any]:
        """Returns the specific API entry details for the API call"""
        if not inspect.isclass(object_or_class):
            object_or_class = object_or_class.__class__
        class_name = object_or_class.__name__
        if class_name not in self.api_def:
            raise ValueError(f"API for {class_name} in version {self.endpoint.version()} not found in API definition")
        if operation.value not in self.api_def[class_name]:
            raise ValueError(f"Operation {operation.value} not found in API definition for {class_name}")
        return self.api_def[class_name][operation.value]

    def api(self, object_or_class: object, operation: ApiOperation, **kwargs: Any) -> str:
        """Returns the API string for the API call"""
        return self.get_api_entry(object_or_class, operation)["api"].format(**kwargs)

    def method(self, object_or_class: object, operation: ApiOperation) -> str:
        """Returns the method for the API call"""
        return self.get_api_entry(object_or_class, operation)["method"]

    def return_field(self, object_or_class: object, operation: ApiOperation) -> Optional[str]:
        """Returns the return field for the API call"""
        return self.get_api_entry(object_or_class, operation).get(ApiManager.__RETURN_FIELD_KEY)

    def max_page_size(self, object_or_class: object, operation: ApiOperation) -> int:
        """Returns the maximum page size for the API call"""
        return self.get_api_entry(object_or_class, operation).get(ApiManager.__MAX_PAGE_SIZE_KEY, ApiManager.__DEFAULT_MAX_PAGE_SIZE)

    def page_field(self, object_or_class: object, operation: ApiOperation) -> str:
        """Returns the page field for the API call"""
        return self.get_api_entry(object_or_class, operation).get(ApiManager.__PAGE_FIELD_KEY, "p")

    def params(self, object_or_class: object, operation: ApiOperation, **kwargs: Any) -> dict[str, Any]:
        """Returns the parameters for the API call, removes any params not part of the API endpoint"""
        params = self.get_api_entry(object_or_class, operation).get("params", {})
        if isinstance(params, list):
            params = {p: "{" + p + "}" for p in params}
        # Add organization for SQC
        normalized = {"organization": self.endpoint.organization} | kwargs
        # Remove any parameter set to None
        normalized = {k: v for k, v in normalized.items() if v is not None}
        # Convert boolean values to strings
        normalized = {k: str(v).lower() if isinstance(v, bool) else v for k, v in normalized.items()}
        # Change list, set, tuple values to CSV strings
        normalized = {k: misc.list_to_csv(v) if isinstance(v, (list, set, tuple)) else v for k, v in normalized.items()}
        # Format the parameters using the API endpoint parameters, exclude anything not in the API endpoint parameters
        return {k: v.format_map(defaultdict(str, **normalized)) for k, v in params.items() if k in normalized}

    def get_details(self, object_or_class: object, operation: ApiOperation, **kwargs: Any) -> tuple[str, str, dict[str, Any], Optional[str]]:
        """Returns the details for the API call"""
        return (
            self.api(object_or_class, operation, **kwargs),
            self.method(object_or_class, operation),
            self.params(object_or_class, operation, **kwargs),
            self.return_field(object_or_class, operation),
        )

    @classmethod
    def load(cls) -> None:
        """Loads the API definitions"""
        # Get the list of all files and directories
        api_files = [f for f in os.listdir(Path(__file__).parent) if f.endswith(".json")]
        for api_file in api_files:
            with open(Path(__file__).parent / api_file) as f:
                api_data = json.load(f)
            basename = api_file.split(os.sep)[-1]
            if "cloud" in basename:
                cls.SQC_API = api_data
            else:
                version = ".".join(basename.split(".")[:-1])
                cls.SQS_API[version] = api_data
        log.debug("API definitions: SQS %s, SQC %s", misc.json_dump(cls.SQS_API), misc.json_dump(cls.SQC_API))
