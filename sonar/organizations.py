#
# sonar-tools
# Copyright (C) 2024-2025 Olivier Korach
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
"""

Abstraction of the SonarQube Cloud organization concept

"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

import json
from threading import Lock

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache
from sonar import exceptions
import sonar.util.misc as util
from sonar.api.manager import ApiOperation as op
from sonar.api.manager import ApiManager as Api

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr, KeyList

_CLASS_LOCK = Lock()

_IMPORTABLE_PROPERTIES = ("key", "name", "description", "url", "avatar", "newCodePeriod")
_NOT_SUPPORTED = "Organizations do not exist in SonarQube"


class Organization(SqObject):
    """Abstraction of the SonarQube Cloud "organization" concept"""

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "organizations"

    def __init__(self, endpoint: Platform, key: str, name: str) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint=endpoint, key=key)
        self.description: Optional[str] = None
        self.name = name
        log.debug("Created object %s", str(self))
        Organization.CACHE.put(self)

    @classmethod
    def get_object(cls, endpoint: Platform, key: str) -> Organization:
        """Gets an Organization object from SonarQube Cloud

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        if not endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        if o := Organization.CACHE.get(key, endpoint.local_url):
            return o
        api, _, params, ret = Api(cls, op.SEARCH, endpoint).get_all(organizations=key)
        data = json.loads(endpoint.get(api, params=params).text)
        if len(data[ret]) == 0:
            raise exceptions.ObjectNotFound(key, f"Organization '{key}' not found")
        return cls.load(endpoint, data[ret][0])

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> Organization:
        """Loads an Organization object with data retrieved from SonarQube Cloud

        :param endpoint: Reference to the SonarQube Cloud platform
        :param data: Data coming from api/organizations/search
        :raises UnsupportedOperation: If not running against SonarQube Cloud
        :raises ObjectNotFound: If Organization key not found
        :return: The found Organization object
        """
        if not endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        o = Organization.CACHE.get(data["key"], endpoint.local_url)
        if not o:
            o = cls(endpoint, data["key"], data["name"])
        o.sq_json = data
        o.name = data["name"]
        o.description = data["description"]
        return o

    def __str__(self) -> str:
        return f"organization key '{self.key}'"

    def export(self) -> ObjectJsonRepr:
        """Exports an organization"""
        log.info("Exporting %s", str(self))
        json_data = self.sq_json.copy()
        json_data.pop("defaultLeakPeriod", None)
        json_data.pop("defaultLeakPeriodType", None)
        (nctype, ncval) = self.new_code_period()
        json_data["newCodePeriod"] = nctype
        if ncval:
            json_data["newCodePeriod"] = f"{nctype} = {ncval}"
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, True))

    def search_params(self) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        return {"organizations": self.key}

    def new_code_period(self) -> tuple[str, str]:
        if "defaultLeakPeriodType" in self.sq_json and self.sq_json["defaultLeakPeriodType"] == "days":
            return "DAYS", self.sq_json["defaultLeakPeriod"]
        return "PREVIOUS_VERSION", None

    def subscription(self) -> str:
        return self.sq_json.get("subscription", "UNKNOWN")

    def alm(self) -> ApiPayload:
        return self.sq_json.get("alm", None)


def get_list(endpoint: Platform, key_list: KeyList = None, use_cache: bool = True) -> dict[str, Organization]:
    """
    :return: List of Organizations (all of them if key_list is None or empty)
    :param KeyList key_list: List of org keys to get, if None or empty all orgs are returned
    :param bool use_cache: Whether to use local cache or query SonarQube Cloud, default True (use cache)
    :rtype: dict{<orgName>: <Organization>}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            log.info("Listing organizations")
            return search(endpoint=endpoint)
        object_list = {}
        for key in util.csv_to_list(key_list):
            object_list[key] = Organization.get_object(endpoint, key)
    return object_list


def search(endpoint: Platform, params: ApiParams = None) -> dict[str, Organization]:
    """Searches organizations

    :param Platform endpoint: Reference to the SonarQube platform
    :param params: Search filters (see api/organizations/search parameters)
    :raises UnsupportedOperation: If not on a SonarQube Cloud platform
    :return: dict of organizations
    :rtype: dict {<orgKey>: Organization, ...}
    """
    if not endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
    return Organization.get_paginated(endpoint=endpoint, params={"member": "true"} | (params or {}))


def export(endpoint: Platform, key_list: KeyList = None) -> ObjectJsonRepr:
    """Exports organizations as JSON

    :param Platform endpoint: Reference to the SonarQube Cloud platform
    :param KeyList key_list: list of Organizations keys to export, defaults to all if None
    :return: Dict of organization settings
    :rtype: dict
    """
    org_settings = {k: org.export() for k, org in get_list(endpoint, key_list).items()}
    for k in org_settings:
        # remove key from JSON value, it's already the dict key
        org_settings[k].pop("key")
    return org_settings
