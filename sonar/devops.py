#
# sonar-tools
# Copyright (C) 2022-2026 Olivier Korach
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

"""Abstraction of the SonarQube DevOps platform concept"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
import json
from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache
from sonar import exceptions
import sonar.util.misc as util
import sonar.util.constants as c
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ConfigSettings, KeyList, ObjectJsonRepr

#: DevOps platform types in SonarQube
DEVOPS_AZURE = "azure"
DEVOPS_BITBUCKET = "bitbucket"
DEVOPS_BITBUCKET_CLOUD = "bitbucketcloud"
DEVOPS_GITHUB = "github"
DEVOPS_GITLAB = "gitlab"
DEVOPS_PLATFORM_TYPES = (DEVOPS_AZURE, DEVOPS_BITBUCKET, DEVOPS_BITBUCKET_CLOUD, DEVOPS_GITHUB, DEVOPS_GITLAB)


_TO_BE_SET = "TO_BE_SET"
_IMPORTABLE_PROPERTIES = ("key", "type", "url", "workspace", "appId", "clientId")


class DevopsPlatform(SqObject):
    """
    Abstraction of the SonarQube ALM/DevOps Platform concept
    """

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Constructor"""
        super().__init__(endpoint, data)
        self.key = data["key"]
        self.type: str = data["type"]  #: DevOps platform type
        self.url: str = "https://bitbucket.org" if self.type == "bitbucketcloud" else data["url"]  #: DevOps platform URL, except for bitbucket cloud
        self._specific: Optional[dict[str, str]] = None  #: DevOps platform specific settings
        self.__class__.CACHE.put(self)
        self.reload(data)
        log.debug("Constructed object %s", str(self))

    def __str__(self) -> str:
        """str() implementation"""
        string = f"devops platform '{self.key}'"
        if self.type == "bitbucketcloud" and self._specific:
            string += f" workspace '{self._specific['workspace']}'"
        return string

    @classmethod
    def get_object(cls, endpoint: Platform, key: str) -> DevopsPlatform:
        """Reads a devops platform object in Sonar instance"""
        if o := cls.CACHE.get(endpoint.local_url, key):
            return o
        cls.search(endpoint)
        if o := cls.CACHE.get(endpoint.local_url, key):
            return o
        raise exceptions.ObjectNotFound(key, f"DevOps platform key '{key}' not found")

    @classmethod
    def search(cls, endpoint: Platform) -> dict[str, DevopsPlatform]:
        """Reads all DevOps platforms from SonarQube

        :param endpoint: Reference to the SonarQube platform
        :return: List of DevOps platforms
        :rtype: dict{<platformKey>: <DevopsPlatform>}
        """
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't get list of DevOps platforms on SonarQube Cloud")
        api, _, _, _ = endpoint.api.get_details(cls, Oper.SEARCH)
        data = json.loads(endpoint.get(api).text)
        devops_platforms = {}
        for plt_type, plt_type_data in data.items():
            for plt_data in plt_type_data:
                devops_platforms[plt_data["key"]] = cls.load(endpoint, plt_data | {"type": plt_type})
        return devops_platforms

    @classmethod
    def create(cls, endpoint: Platform, key: str, plt_type: str, url_or_workspace: str) -> DevopsPlatform:
        """Creates a devops platform"""
        params = {"key": key}
        try:
            if plt_type == DEVOPS_GITHUB:
                params.update(dict.fromkeys(("appId", "clientId", "clientSecret", "privateKey"), _TO_BE_SET))
                params["url"] = url_or_workspace
                api, _, api_params, _ = endpoint.api.get_details(DevopsPlatform, Oper.CREATE_GITHUB, **params)
                endpoint.post(api, params=api_params)
            elif plt_type == DEVOPS_AZURE:
                # TODO: pass secrets on the cmd line
                params.update({"personalAccessToken": _TO_BE_SET, "url": url_or_workspace})
                api, _, api_params, _ = endpoint.api.get_details(DevopsPlatform, Oper.CREATE_AZURE, **params)
                endpoint.post(api, params=api_params)
            elif plt_type == DEVOPS_GITLAB:
                params.update({"personalAccessToken": _TO_BE_SET, "url": url_or_workspace})
                api, _, api_params, _ = endpoint.api.get_details(DevopsPlatform, Oper.CREATE_GITLAB, **params)
                endpoint.post(api, params=api_params)
            elif plt_type == DEVOPS_BITBUCKET:
                params.update({"personalAccessToken": _TO_BE_SET, "url": url_or_workspace})
                api, _, api_params, _ = endpoint.api.get_details(DevopsPlatform, Oper.CREATE_BITBUCKET, **params)
                endpoint.post(api, params=api_params)
            elif plt_type == DEVOPS_BITBUCKET_CLOUD:
                params.update({"clientSecret": _TO_BE_SET, "clientId": _TO_BE_SET, "workspace": url_or_workspace})
                api, _, api_params, _ = endpoint.api.get_details(DevopsPlatform, Oper.CREATE_BITBUCKETCLOUD, **params)
                endpoint.post(api, params=api_params)
        except exceptions.SonarException as e:
            if endpoint.edition() in (c.CE, c.DE):
                log.warning("Can't set DevOps platform '%s', don't you have more that 1 of that type?", key)
            raise exceptions.UnsupportedOperation(e.message) from e
        return cls.get_object(endpoint, key)

    def reload(self, data: ApiPayload) -> DevopsPlatform:
        """Loads a devops platform object with data"""
        super().reload(data)
        self.url = "https://bitbucket.org" if self.type == "bitbucketcloud" else data["url"]
        self._specific = {k: v for k, v in data.items() if k not in ("key", "url")}
        return self

    def delete(self) -> bool:
        """Deletes a DevOps platform"""
        return self.delete_object(key=self.key)

    def refresh(self) -> DevopsPlatform:
        """Reads / Refresh a DevOps platform information, and returns itself"""
        dop = self.search(self.endpoint)
        if self.key not in dop:
            self.__class__.CACHE.pop(self)
            raise exceptions.ObjectNotFound(self.key, f"DevOps platform key '{self.key} not found")
        return self

    def to_json(self, export_settings: ConfigSettings) -> ObjectJsonRepr:
        """Exports a DevOps platform configuration in JSON format

        :param ConfigSettings export_settings: Config params for the export
        :return: The configuration of the DevOps platform (except secrets)
        """
        json_data = {"key": self.key, "type": self.type, "url": self.url} | self.sq_json.copy()
        if self.type == "bitbucketcloud":
            json_data.pop("url", None)
        return util.filter_export(json_data, _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False))

    def set_pat(self, pat: str, user_name: Optional[str] = None) -> bool:
        """Sets the PAT for GitLab, BitBucket and Azure DevOps"""
        if self.type == DEVOPS_GITHUB:
            log.warning("Can't set PAT for GitHub devops platform")
            return False
        api, _, params, _ = self.endpoint.api.get_details(self, Oper.SET_PAT, almSettings=self.key, pat=pat, username=user_name)
        return self.post(api, params=params).ok

    def update(self, **kwargs) -> bool:
        """Updates a DevOps platform with information from data

        :param dict kwargs: data to update the DevOps platform configuration
                            (url, clientId, workspace, appId, privateKey, "clientSecret" depending on the type of platform)
        :return: Whether the operation succeeded
        """
        alm_type = kwargs["type"]
        if alm_type != self.type:
            log.error("DevOps platform type '%s' for update of %s is incompatible", alm_type, str(self))
            return False

        params = {"key": self.key, "url": kwargs.get("url")}
        additional = ()
        if alm_type == DEVOPS_BITBUCKET_CLOUD:
            additional = ("clientId", "workspace")
        elif alm_type == DEVOPS_GITHUB:
            additional = ("clientId", "appId", "privateKey", "clientSecret")
        for k in additional:
            params[k] = kwargs.get(k, _TO_BE_SET)
        try:
            update_op = {
                DEVOPS_GITHUB: Oper.UPDATE_GITHUB,
                DEVOPS_GITLAB: Oper.UPDATE_GITLAB,
                DEVOPS_AZURE: Oper.UPDATE_AZURE,
                DEVOPS_BITBUCKET: Oper.UPDATE_BITBUCKET,
                DEVOPS_BITBUCKET_CLOUD: Oper.UPDATE_BITBUCKETCLOUD,
            }[alm_type]
            api, _, api_params, _ = self.endpoint.api.get_details(self, update_op, **params)
            ok = self.post(api, params=api_params).ok
            self.url = kwargs.get("url")
            self._specific = {k: v for k, v in params.items() if k not in ("key", "url")}
        except exceptions.SonarException:
            ok = False
        return ok


def count(endpoint: Platform, platf_type: Optional[str] = None) -> int:
    """
    :param platf_type: Filter for a specific type, defaults to None (see DEVOPS_PLATFORM_TYPES set)
    :return: Count of DevOps platforms
    """
    return len([o for o in DevopsPlatform.search(endpoint=endpoint).values() if not platf_type or o.type == platf_type])


def export(endpoint: Platform, export_settings: ConfigSettings) -> ObjectJsonRepr:
    """
    :meta private:
    """
    log.info("Exporting DevOps integration settings")
    json_data = {}
    for s in DevopsPlatform.search(endpoint).values():
        export_data = s.to_json(export_settings)
        json_data[export_data.pop("key")] = export_data
        log.debug("Export devops: %s", util.json_dump(export_data))
    return json_data


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: KeyList = None) -> int:
    """Imports DevOps platform configuration in SonarQube/Cloud

    :param endpoint: Reference to the SonarQube platform
    :param config_data: Configuration data to import
    :param key_list: List of keys to import, defaults to None
    :raises: UnsupportedOperation if the target platform is SonarQube Cloud
    :return: Nbr of devops platforms imported
    """
    if not (devops_settings := config_data.get("devopsIntegration", {})):
        log.info("No devops integration settings in config, skipping import...")
        return 0
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Can't import DevOps platforms in SonarQube Cloud")
    log.info("Importing DevOps config %s", util.json_dump(devops_settings))
    if len(DevopsPlatform.CACHE) == 0:
        DevopsPlatform.search(endpoint)
    counter = 0
    devops_settings = util.list_to_dict(devops_settings, "key")
    for name, data in devops_settings.items():
        try:
            o = DevopsPlatform.get_object(endpoint, name)
        except exceptions.ObjectNotFound:
            info = data["workspace"] if data["type"] == DEVOPS_BITBUCKET_CLOUD else data["url"]
            try:
                o = DevopsPlatform.create(key=name, endpoint=endpoint, plt_type=data["type"], url_or_workspace=info)
            except exceptions.UnsupportedOperation as e:
                log.error(str(e))
                continue
        o.update(**data)
        counter += 1
    return counter


def devops_type(endpoint: Platform, key: str) -> str:
    """Returns the type of a DevOps platform (see DEVOPS_PLATFORM_TYPES)

    :param endpoint: Reference to the SonarQube platform
    :param key: Key of the devops platform (its name)
    :raises: ObjectNotFound if the devops key is not found
    :return: The type of a DevOps platform (see DEVOPS_PLATFORM_TYPES)
    """
    return DevopsPlatform.get_object(endpoint=endpoint, key=key).type
