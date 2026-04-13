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

"""Abstraction of the SonarQube "license profile" concept (SCA / Advanced Security)"""

from __future__ import annotations
from typing import Any, Optional, TYPE_CHECKING

import json

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache
from sonar import exceptions
import sonar.util.misc as util
import sonar.utilities as sutil
from sonar.api.manager import ApiOperation as Oper
from sonar.util import constants as c

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ObjectJsonRepr, KeyList, ConfigSettings

_IMPORTABLE_PROPERTIES = ("name", "isDefault", "categories", "licenses")
_MIN_SQ_VERSION = (2025, 4, 0)
_CB_VERSION_OFFSET = 2000
_SUPPORTED_EDITIONS = ("enterprise", "datacenter")
_UNSUPPORTED_VERSION_MSG = "License profiles require SonarQube Server 2025.4 or later, or SonarQube Cloud"
_UNSUPPORTED_EDITION_MSG = "License profiles require Enterprise Edition or Data Center Edition"


def _check_supported(endpoint: Platform) -> None:
    """Raises UnsupportedOperation if the platform doesn't support license profiles"""
    if endpoint.is_sonarcloud():
        return
    vers = endpoint.version()
    # Community Build versions have major < 2000 (e.g. 25.x), adjust for comparison
    if vers > (10, 8, 0) and vers[0] < _CB_VERSION_OFFSET:
        vers = (vers[0] + _CB_VERSION_OFFSET, vers[1], vers[2])
    if vers < _MIN_SQ_VERSION:
        raise exceptions.UnsupportedOperation(_UNSUPPORTED_VERSION_MSG)
    if endpoint.edition() not in _SUPPORTED_EDITIONS:
        raise exceptions.UnsupportedOperation(_UNSUPPORTED_EDITION_MSG)


class LicenseProfile(SqObject):
    """Abstraction of the SonarQube License Profile concept (SCA)"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Constructor, don't use directly, use class methods instead"""
        _check_supported(endpoint)
        super().__init__(endpoint, data)
        self.name = data["name"]
        self.key = data.get("key", data.get("id", self.name))
        self.is_default = data.get("isDefault", False)
        self._categories = data.get("categories", [])
        self._licenses = data.get("licenses", [])
        log.debug("Created %s", str(self))
        self.__class__.CACHE.put(self)

    def __str__(self) -> str:
        """Returns the string formatting of the object"""
        return f"license profile '{self.name}'"

    @staticmethod
    def hash_payload(data: ApiPayload) -> tuple[Any, ...]:
        """Returns the hash items for a given object search payload"""
        return (data["name"],)

    def hash_object(self) -> tuple[Any, ...]:
        """Returns the hash elements for a given object"""
        return (self.name,)

    @classmethod
    def get_object(cls, endpoint: Platform, name: str) -> LicenseProfile:
        """Gets a license profile by name

        :param endpoint: Reference to the SonarQube platform
        :param name: License profile name
        :return: the LicenseProfile object
        :raises ObjectNotFound: if not found
        :raises UnsupportedOperation: if platform version is too old
        """
        _check_supported(endpoint)
        o: Optional[LicenseProfile] = cls.CACHE.get(endpoint.local_url, name)
        if o:
            return o
        # Search all profiles and try to find by name
        all_profiles = cls.search(endpoint)
        if name in all_profiles:
            return all_profiles[name]
        raise exceptions.ObjectNotFound(name, f"License profile '{name}' not found")

    @classmethod
    def create(cls, endpoint: Platform, name: str) -> LicenseProfile:
        """Creates a license profile

        :raises UnsupportedOperation: if platform version is too old
        """
        _check_supported(endpoint)
        api, _, params, _ = endpoint.api.get_details(cls, Oper.CREATE, name=name)
        endpoint.post(api, params=params)
        return cls.get_object(endpoint, name)

    @classmethod
    def search(cls, endpoint: Platform, use_cache: bool = False, **search_params: Any) -> dict[str, LicenseProfile]:
        """Returns all license profiles

        :param endpoint: Reference to the SonarQube platform
        :param use_cache: Whether to use local cache, default False
        :return: Dict of license profiles indexed by name
        :raises UnsupportedOperation: if platform version is too old
        """
        _check_supported(endpoint)
        log.info("Searching license profiles")
        if use_cache and len(search_params) == 0 and len(cls.CACHE.from_platform(endpoint)) > 0:
            return {lp.name: lp for lp in cls.CACHE.from_platform(endpoint).values()}
        api, _, params, ret = endpoint.api.get_details(cls, Oper.SEARCH, **search_params)
        data = json.loads(endpoint.get(api, params=params).text)
        profiles_list = data[ret] if ret else data
        result = {}
        for profile_data in profiles_list:
            # Fetch full profile details (including categories and licenses)
            full_data = _get_full_profile(endpoint, profile_data)
            lp = cls.load(endpoint, full_data)
            result[lp.name] = lp
        return result

    def reload(self, data: ApiPayload) -> LicenseProfile:
        """Reloads the license profile from the given data"""
        super().reload(data)
        self.is_default = data.get("isDefault", self.is_default)
        self._categories = data.get("categories", self._categories)
        self._licenses = data.get("licenses", self._licenses)
        return self

    def url(self) -> str:
        """Returns the object permalink"""
        return f"{self.base_url(local=False)}/sca/license-profiles/{self.key}"

    def delete(self) -> bool:
        """Deletes a license profile, returns whether the operation succeeded"""
        return self.delete_object(key=self.key)

    def to_json(self, export_settings: ConfigSettings) -> ObjectJsonRepr:
        """Returns JSON representation of object"""
        log.info("Exporting %s", str(self))
        full = export_settings.get("FULL_EXPORT", False)
        json_data = {"name": self.name}
        if self.is_default or full:
            json_data["isDefault"] = self.is_default
        if self._categories:
            json_data["categories"] = [{"key": cat["key"], "policy": cat["policy"]} for cat in self._categories]
        if self._licenses:
            json_data["licenses"] = [
                {"spdxLicenseId": lic.get("spdxLicenseId", ""), "name": lic.get("name", ""), "policy": lic["policy"]} for lic in self._licenses
            ]
        return util.remove_nones(json_data)

    def update(self, **data: Any) -> bool:
        """Updates a license profile

        :param data: Considered keys: "name", "isDefault", "categories", "licenses"
        """
        log.debug("Updating %s with data %s", str(self), util.json_dump(data))
        ok = True

        # Update name if changed
        if "name" in data and data["name"] != self.name:
            log.info("Renaming %s to %s", self, data["name"])
            try:
                api, _, params, _ = self.endpoint.api.get_details(self, Oper.UPDATE, key=self.key, name=data["name"])
                self.patch(api, params=params)
                self.__class__.CACHE.pop(self)
                self.name = data["name"]
                self.__class__.CACHE.put(self)
            except exceptions.SonarException:
                ok = False

        # Set as default if requested
        if data.get("isDefault", False) and not self.is_default:
            try:
                api, _, params, _ = self.endpoint.api.get_details(self, Oper.UPDATE, key=self.key, isDefault=True)
                ok = self.patch(api, params=params).ok and ok
                self.is_default = True
            except exceptions.SonarException:
                ok = False

        ok = self._update_categories(data.get("categories", []), ok)
        return self._update_licenses(data.get("licenses", []), ok)

    def _update_categories(self, categories: list[dict[str, str]], ok: bool) -> bool:
        """Updates category policies on this license profile"""
        for cat in categories:
            try:
                api, _, params, _ = self.endpoint.api.get_details(
                    self,
                    Oper.UPDATE_CATEGORY,
                    key=self.key,
                    categoryKey=cat["key"],
                    policy=cat["policy"],
                )
                ok = self.patch(api, params=params).ok and ok
            except exceptions.SonarException as e:
                log.warning("Failed to update category '%s' on %s: %s", cat["key"], self, e.message)
                ok = False
        return ok

    def _update_licenses(self, licenses: list[dict[str, str]], ok: bool) -> bool:
        """Updates individual license policies on this license profile"""
        # Fetch the full profile from the API to get the internal license policy IDs
        spdx_to_id = self._build_spdx_to_id_map()
        if not spdx_to_id:
            log.warning("No license entries found in %s, cannot update individual licenses", self)
            return False
        for lic in licenses:
            spdx = lic.get("spdxLicenseId", "")
            lic_policy_id = spdx_to_id.get(spdx)
            if not lic_policy_id:
                log.warning("License '%s' not found in %s, skipping", spdx, self)
                ok = False
                continue
            try:
                api, _, params, _ = self.endpoint.api.get_details(
                    self,
                    Oper.UPDATE_LICENSE,
                    key=self.key,
                    licensePolicyId=lic_policy_id,
                    policy=lic["policy"],
                )
                ok = self.patch(api, params=params).ok and ok
            except exceptions.SonarException as e:
                log.warning("Failed to update license '%s' on %s: %s", spdx, self, e.message)
                ok = False

        return ok

    def _build_spdx_to_id_map(self) -> dict[str, str]:
        """Builds a mapping from spdxLicenseId to internal license policy id by fetching the full profile from the API"""
        try:
            api, _, _, _ = self.endpoint.api.get_details(self, Oper.GET, key=self.key)
            full_data = json.loads(self.endpoint.get(api).text)
        except exceptions.SonarException:
            log.warning("Could not fetch full data for %s", self)
            return {}
        api_licenses = full_data.get("licenses", [])
        log.debug("Fetched %d licenses from API for %s", len(api_licenses), self)
        return {lic["spdxLicenseId"]: lic["id"] for lic in api_licenses if "spdxLicenseId" in lic and "id" in lic}


def _get_full_profile(endpoint: Platform, profile_data: ApiPayload) -> ApiPayload:
    """Fetches the full profile data including categories and licenses"""
    key = profile_data.get("key", profile_data.get("id", ""))
    if not key or ("categories" in profile_data and "licenses" in profile_data):
        return profile_data
    try:
        api, _, _, _ = endpoint.api.get_details(LicenseProfile, Oper.GET, key=key)
    except exceptions.SonarException:
        log.warning("Could not fetch full data for license profile '%s'", profile_data.get("name", key))
        return profile_data
    else:
        return profile_data | json.loads(endpoint.get(api).text)


def sca_enabled(endpoint: Platform) -> bool:
    """Checks if SCA feature is enabled on the platform"""
    try:
        _check_supported(endpoint)
        api, _, _, _ = endpoint.api.get_details(LicenseProfile, Oper.SELF_TEST)
        resp = endpoint.get(api)
    except (exceptions.SonarException, exceptions.UnsupportedOperation):
        return False
    else:
        return resp.ok


def export(endpoint: Platform, export_settings: ConfigSettings, **kwargs: Any) -> ObjectJsonRepr:
    """Exports license profiles as JSON

    :param endpoint: Reference to the Sonar platform
    :param export_settings: Options to use for export
    :return: License profiles representations as JSON
    """
    log.info("Exporting license profiles")
    if not sca_enabled(endpoint):
        log.info("SCA is not enabled on this platform, skipping license profiles export")
        write_q = kwargs.get("write_q", None)
        if write_q:
            write_q.put([])
            write_q.put(sutil.WRITE_END)
        return []
    lp_list = [util.clean_data(lp.to_json(export_settings), remove_none=True, remove_empty=True) for lp in LicenseProfile.search(endpoint).values()]
    write_q = kwargs.get("write_q", None)
    if write_q:
        write_q.put(lp_list)
        write_q.put(sutil.WRITE_END)
    return lp_list


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: KeyList = None) -> bool:
    """Imports license profiles in a SonarQube platform

    :param endpoint: Reference to the SonarQube platform
    :param config_data: JSON representation of the full config
    :param key_list: Optional key list filter
    :return: Whether the import succeeded
    """
    if c.CONFIG_KEY_LICENSE_PROFILES not in config_data:
        log.info("No license profiles to import")
        return True
    if not sca_enabled(endpoint):
        log.warning("SCA is not enabled on this platform, skipping license profiles import")
        return True
    log.info("Importing license profiles")
    ok = True
    converted_data = util.list_to_dict(config_data[c.CONFIG_KEY_LICENSE_PROFILES], "name")
    for name, data in converted_data.items():
        try:
            o = LicenseProfile.get_object(endpoint, name)
            log.debug("Found existing %s", str(o))
        except exceptions.ObjectNotFound:
            log.debug("License profile '%s' not found, creating it", name)
            o = LicenseProfile.create(endpoint, name)
        log.info("Importing %s", str(o))
        log.debug("Importing %s with %s", str(o), util.json_dump(data))
        ok = o.update(**data) and ok
    return ok
