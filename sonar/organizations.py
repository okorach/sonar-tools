#
# sonar-tools
# Copyright (C) 2024-2026 Olivier Korach
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
"""Abstraction of the SonarQube Cloud organization concept"""

from __future__ import annotations

import json
from threading import Lock
from typing import TYPE_CHECKING, Any, Optional, Union

import sonar.logging as log
import sonar.util.misc as util
from sonar import exceptions
from sonar.api.manager import ApiOperation as Oper
from sonar.sqobject import SqObject
from sonar.util import cache

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, KeyList, ObjectJsonRepr


_IMPORTABLE_PROPERTIES = ("key", "name", "description", "url", "avatar", "newCodePeriod")
_NOT_SUPPORTED = "Organizations do not exist in SonarQube"


class Organization(SqObject):
    """Abstraction of the SonarQube Cloud "organization" concept"""

    CACHE = cache.Cache()
    CLASS_LOCK = Lock()

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint, data)
        self.key = data["key"]
        self.description: Optional[str] = None
        self.name = data["name"]
        log.debug("Created object %s", str(self))
        with self.__class__.CLASS_LOCK:
            self.__class__.CACHE.put(self)

    def __str__(self) -> str:
        return f"organization key '{self.key}'"

    @classmethod
    def search(cls, endpoint: Platform, **search_params: Any) -> dict[str, Organization]:
        """Searches organizations

        :param Platform endpoint: Reference to the SonarQube platform
        :param search_params: Search filters (see api/organizations/search parameters)
        :raises UnsupportedOperation: If not on a SonarQube Cloud platform
        :return: dict of organizations
        :rtype: dict {<orgKey>: Organization, ...}
        """
        if not endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        return cls.get_paginated(endpoint=endpoint, params=search_params | {"member": "true"})

    @classmethod
    def get_object(cls, endpoint: Platform, key: str, use_cache: bool = True) -> Organization:
        """Gets an Organization object from SonarQube Cloud

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :param use_cache: Whether to use cached object, default True
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        if not endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        if use_cache and (o := Organization.CACHE.get(endpoint.local_url, key)):
            return o
        api, _, params, ret = endpoint.api.get_details(cls, Oper.SEARCH, organizations=key)
        data = json.loads(endpoint.get(api, params=params).text)
        if len(data[ret]) == 0:
            raise exceptions.ObjectNotFound(key, f"Organization '{key}' not found")
        return cls.load(endpoint, data[ret][0])

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> Organization:
        """Loads an Organization object with data retrieved from SonarQube Cloud

        :param endpoint: Reference to the SonarQube Cloud platform
        :param data: Search payload of an organization
        :raises UnsupportedOperation: If not running against SonarQube Cloud
        :raises ObjectNotFound: If Organization key not found
        :return: The found Organization object
        """
        if not endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        return super().load(endpoint, data)

    def reload(self, data: ApiPayload) -> Organization:
        """Reloads an Organization object with data retrieved from SonarQube Cloud, returns self"""
        super().reload(data)
        self.name = data["name"]
        self.description = data["description"]
        return self

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
            return "NUMBER_OF_DAYS", self.sq_json["defaultLeakPeriod"]
        return "PREVIOUS_VERSION", None

    def _resolve_id(self) -> str:
        """Returns the v2 internal id for this organization, fetching and caching it on demand.

        The legacy ``api/organizations/search`` payload only exposes the key,
        but the v2 ``/organizations/{id}`` endpoint on ``api.sonarcloud.io``
        needs the internal id. ``GET api.sonarcloud.io/organizations?organizationKey=<key>``
        returns the mapping; the result is cached on ``self.sq_json`` so
        subsequent lookups don't re-hit the API.
        """
        if cached := self.sq_json.get("id"):
            return cached
        api, _, params, _ = self.endpoint.api.get_details(self.__class__, Oper.GET, organizationKey=self.key)
        base_url = self.endpoint.api.base_url(self.__class__, Oper.GET)
        data = json.loads(self.endpoint.get(api, params=params, base_url=base_url).text)
        if not data:
            raise exceptions.ObjectNotFound(self.key, f"v2 endpoint returned no organization for key '{self.key}'")
        org_id = data[0].get("id")
        if not org_id:
            raise exceptions.ObjectNotFound(self.key, f"v2 endpoint response for '{self.key}' did not include an id field")
        self.sq_json["id"] = org_id
        return org_id

    def set_new_code_period(self, nc_type: str, nc_value: Union[int, str, None]) -> bool:
        """Sets the organization-level default new code period on SonarQube Cloud.

        Uses ``PATCH api.sonarcloud.io/organizations/{organizationId}`` with a
        JSON body of ``{defaultLeakPeriod, defaultLeakPeriodType}``. The id is
        resolved via ``GET api.sonarcloud.io/organizations?organizationKey=<key>``
        because the legacy v1 search response only exposes the key.

        SonarQube Cloud only supports three types at the organization level —
        PREVIOUS_VERSION, NUMBER_OF_DAYS, SPECIFIC_DATE — which map to the API
        enum values previous_version, days, date respectively.

        :raises UnsupportedOperation: for nc_type values SonarQube Cloud does
            not accept at the organization level.
        :raises ObjectNotFound: when the v2 endpoint cannot resolve an id for
            this organization's key.
        """
        if nc_type == "PREVIOUS_VERSION":
            api_type, api_value = "previous_version", "previous_version"
        elif nc_type in ("NUMBER_OF_DAYS", "DAYS"):
            api_type, api_value = "days", str(nc_value)
        elif nc_type in ("SPECIFIC_DATE", "DATE"):
            api_type, api_value = "date", str(nc_value)
        else:
            raise exceptions.UnsupportedOperation(f"New code period type '{nc_type}' is not supported at organization level on SonarQube Cloud")

        org_id = self._resolve_id()
        log.info("Setting %s default new code period to %s = %s (id=%s)", self, nc_type, nc_value, org_id)
        api, _, body, _ = self.endpoint.api.get_details(
            self.__class__,
            Oper.UPDATE,
            organizationId=org_id,
            defaultLeakPeriod=api_value,
            defaultLeakPeriodType=api_type,
        )
        ct = self.endpoint.api.content_type(self.__class__, Oper.UPDATE)
        base_url = self.endpoint.api.base_url(self.__class__, Oper.UPDATE)
        return self.endpoint.patch(api, params=body, content_type=ct, base_url=base_url).ok

    def subscription(self) -> str:
        return self.sq_json.get("subscription", "UNKNOWN")

    def alm(self) -> ApiPayload:
        """Returns The DevOps platform bound to the organization, or None if not set"""
        return self.sq_json.get("alm")


def export(endpoint: Platform, key_list: KeyList = None) -> ObjectJsonRepr:
    """Exports organizations as JSON

    :param Platform endpoint: Reference to the SonarQube Cloud platform
    :param KeyList key_list: list of Organizations keys to export, defaults to all if None
    :return: Dict of organization settings
    :rtype: dict
    """
    org_settings = {k: org.export() for k, org in Organization.search(endpoint).items()}
    for k in org_settings:
        # remove key from JSON value, it's already the dict key
        org_settings[k].pop("key")
    return org_settings
