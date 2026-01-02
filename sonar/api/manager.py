#
# sonar-tools
# Copyright (C) 2025 Olivier Korach
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
from typing import Any, Optional, TYPE_CHECKING

from enum import Enum
from pathlib import Path
import json
from collections import defaultdict
import inspect

from sonar.util import misc
import sonar.logging as log

if TYPE_CHECKING:
    from sonar.platform import Platform


class ApiOperation(Enum):
    """List of possible API operations"""

    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LIST = "LIST"
    SEARCH = "LIST"
    GET = "GET"
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


class ApiManager:
    """Abstraction of the SonarQube API"""

    __RETURN_FIELD_KEY = "return_field"
    __PAGE_FIELD_KEY = "page_field"
    __MAX_PAGE_SIZE_KEY = "max_page_size"
    __DEFAULT_MAX_PAGE_SIZE = 500

    API_DEFINITION: dict[str, dict[str, Any]] = {}

    def __init__(self, object_or_class: object, op: ApiOperation, endpoint: Optional[Platform] = None) -> None:
        """Constructor"""
        self.endpoint: Platform = endpoint
        self.api_class: object = object_or_class
        if not inspect.isclass(object_or_class):
            self.api_class = object_or_class.__class__
            self.endpoint = object_or_class.endpoint
        self.class_name = self.api_class.__name__
        if self.class_name not in self.__class__.API_DEFINITION:
            raise ValueError(f"API class {self.class_name} not found in API definitions")
        self.version = self.endpoint.version()
        data = next(v for k, v in self.__class__.API_DEFINITION[self.class_name].items() if self.version >= tuple(int(s) for s in k.split(".")))
        if op.value not in data:
            raise ValueError(f"Operation {op.value} not found in API definitions for {self.class_name}")
        self.api_def = data[op.value]

    def api(self, **kwargs: Any) -> str:
        """Returns the API string for the API call"""
        return self.api_def["api"].format(**kwargs)

    def method(self) -> str:
        """Returns the method for the API call"""
        return self.api_def["method"]

    def return_field(self) -> Optional[str]:
        """Returns the return field for the API call"""
        return self.api_def.get(ApiManager.__RETURN_FIELD_KEY)

    def max_page_size(self) -> int:
        """Returns the maximum page size for the API call"""
        return self.api_def.get(ApiManager.__MAX_PAGE_SIZE_KEY, ApiManager.__DEFAULT_MAX_PAGE_SIZE)

    def page_field(self) -> str:
        """Returns the page field for the API call"""
        return self.api_def.get(ApiManager.__PAGE_FIELD_KEY, "p")

    def params(self, **kwargs: Any) -> dict[str, Any]:
        """Returns the parameters for the API call"""
        params = self.api_def.get("params", {})
        if isinstance(params, list):
            params = {p: "{" + p + "}" for p in self.api_def.get("params", [])}
        return {k: v.format_map(defaultdict(str, **kwargs)) for k, v in params.items() if kwargs.get(k) is not None}

    def get_all(self, **kwargs: Any) -> tuple[str, str, dict[str, Any], Optional[str]]:
        """Returns the API call, method, parameters and return field"""
        return self.api(**kwargs), self.method(), self.params(**kwargs), self.return_field()

    @classmethod
    def load(cls) -> dict[str, Any]:
        """Loads the API definitions"""
        with misc.open_file(Path(__file__).parent / "api.json", "r") as f:
            api_data = json.load(f)
        log.debug("API data: %s", misc.json_dump(api_data))
        cls.API_DEFINITION = api_data
        return api_data
