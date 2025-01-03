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

    Abstraction of the SonarCloud organization concept

"""

from __future__ import annotations
import json
from http import HTTPStatus
from threading import Lock
from requests import RequestException

import sonar.logging as log
import sonar.platform as pf
from sonar.util import types, cache, constants as c

from sonar import sqobject, exceptions
import sonar.utilities as util

_CLASS_LOCK = Lock()

_IMPORTABLE_PROPERTIES = ("key", "name", "description", "url", "avatar", "newCodePeriod")
_NOT_SUPPORTED = "Organizations do not exist in SonarQube"


class Organization(sqobject.SqObject):
    """
    Abstraction of the SonarCloud "organization" concept
    """

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "organizations"
    API = {c.SEARCH: "organizations/search"}

    def __init__(self, endpoint: pf.Platform, key: str, name: str) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint=endpoint, key=key)
        self.description = None
        self.name = name
        log.debug("Created object %s", str(self))
        Organization.CACHE.put(self)

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str) -> Organization:
        """Gets an Organization object from SonarCloud

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        if not endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        o = Organization.CACHE.get(key, endpoint.url)
        if o:
            return o
        try:
            data = json.loads(endpoint.get(Organization.API[c.SEARCH], params={"organizations": key}).text)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"getting organization {key}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            raise exceptions.ObjectNotFound(key, f"Organization '{key}' not found")

        if len(data["organizations"]) == 0:
            raise exceptions.ObjectNotFound(key, f"Organization '{key}' not found")
        return cls.load(endpoint, data["organizations"][0])

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> Organization:
        """Loads an Organization object with data retrieved from SonarCloud

        :param Platform endpoint: Reference to the SonarCloud platform
        :param dict data: Data coming from api/organizations/search
        :raises UnsupportedOperation: If not running against SonarCloud
        :raises ObjectNotFound: If Organization key not found
        :return: The found Organization object
        :rtype: Organization
        """
        if not endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        o = Organization.CACHE.get(data["key"], endpoint.url)
        if not o:
            o = cls(endpoint, data["key"], data["name"])
        o.sq_json = data
        o.name = data["name"]
        o.description = data["description"]
        return o

    def __str__(self) -> str:
        return f"organization key '{self.key}'"

    def export(self) -> types.ObjectJsonRepr:
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

    def search_params(self) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        return {"organizations": self.key}

    def new_code_period(self) -> tuple[str, str]:
        if "defaultLeakPeriodType" in self.sq_json and self.sq_json["defaultLeakPeriodType"] == "days":
            return "DAYS", self.sq_json["defaultLeakPeriod"]
        return "PREVIOUS_VERSION", None

    def subscription(self) -> str:
        return self.sq_json.get("subscription", "UNKNOWN")

    def alm(self) -> types.ApiPayload:
        return self.sq_json.get("alm", None)


def get_list(endpoint: pf.Platform, key_list: types.KeyList = None, use_cache: bool = True) -> dict[str, Organization]:
    """
    :return: List of Organizations (all of them if key_list is None or empty)
    :param KeyList key_list: List of org keys to get, if None or empty all orgs are returned
    :param bool use_cache: Whether to use local cache or query SonarCloud, default True (use cache)
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


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, Organization]:
    """Searches organizations

    :param Platform endpoint: Reference to the SonarQube platform
    :param params: Search filters (see api/organizations/search parameters)
    :raises UnsupportedOperation: If not on a SonarCloud platform
    :return: dict of organizations
    :rtype: dict {<orgKey>: Organization, ...}
    """
    if not endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
    new_params = {"member": "true"}
    if params is not None:
        new_params.update(params)
    return sqobject.search_objects(endpoint=endpoint, object_class=Organization, params=new_params)


def export(endpoint: pf.Platform, key_list: types.KeyList = None) -> types.ObjectJsonRepr:
    """Exports organizations as JSON

    :param Platform endpoint: Reference to the SonarCloud platform
    :param KeyList key_list: list of Organizations keys to export, defaults to all if None
    :return: Dict of organization settings
    :rtype: dict
    """
    org_settings = {k: org.export() for k, org in get_list(endpoint, key_list).items()}
    for k in org_settings:
        # remove key from JSON value, it's already the dict key
        org_settings[k].pop("key")
    return org_settings
