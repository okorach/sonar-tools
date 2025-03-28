#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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
from typing import Optional, Union
from http import HTTPStatus
import json

from requests import RequestException

import sonar.logging as log
from sonar.util import types, cache, constants as c
from sonar import platform
import sonar.sqobject as sq
from sonar import exceptions
import sonar.utilities as util

#: DevOps platform types in SonarQube
DEVOPS_PLATFORM_TYPES = ("github", "azure", "bitbucket", "bitbucketcloud", "gitlab")

_CREATE_API_GITHUB = "alm_settings/create_github"
_CREATE_API_GITLAB = "alm_settings/create_gitlab"
_CREATE_API_AZURE = "alm_settings/create_azure"
_CREATE_API_BITBUCKET = "alm_settings/create_bitbucket"
_CREATE_API_BBCLOUD = "alm_settings/create_bitbucketcloud"

_TO_BE_SET = "TO_BE_SET"
_IMPORTABLE_PROPERTIES = ("key", "type", "url", "workspace", "clientId", "appId")


class DevopsPlatform(sq.SqObject):
    """
    Abstraction of the SonarQube ALM/DevOps Platform concept
    """

    CACHE = cache.Cache()
    API = {c.LIST: "alm_settings/list_definitions"}

    def __init__(self, endpoint: platform.Platform, key: str, platform_type: str) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.type: str = platform_type  #: DevOps platform type
        self.url: Union[str, None] = None  #: DevOps platform URL
        self._specific: Union[dict[str, str], None] = None  #: DevOps platform specific settings
        DevopsPlatform.CACHE.put(self)
        log.debug("Created object %s", str(self))

    @classmethod
    def read(cls, endpoint: platform.Platform, key: str) -> DevopsPlatform:
        """Reads a devops platform object in Sonar instance"""
        o = DevopsPlatform.CACHE.get(key, endpoint.url)
        if o:
            return o
        data = json.loads(endpoint.get(DevopsPlatform.API[c.LIST]).text)
        for plt_type, platforms in data.items():
            for p in platforms:
                if p["key"] == key:
                    return cls.load(endpoint, plt_type, p)
        raise exceptions.ObjectNotFound(key, f"DevOps platform key '{key}' not found")

    @classmethod
    def load(cls, endpoint: platform.Platform, plt_type: str, data: types.ApiPayload) -> DevopsPlatform:
        """Finds a devops platform object and loads it with data"""
        key = data["key"]
        o = DevopsPlatform.CACHE.get(key, endpoint.url)
        if not o:
            o = DevopsPlatform(endpoint=endpoint, key=key, platform_type=plt_type)
        return o._load(data)

    @classmethod
    def create(cls, endpoint: platform.Platform, key: str, plt_type: str, url_or_workspace: str) -> DevopsPlatform:
        """Creates a devops platform"""
        params = {"key": key}
        try:
            if plt_type == "github":
                params.update({k: _TO_BE_SET for k in ("appId", "clientId", "clientSecret", "privateKey")})
                params["url"] = url_or_workspace
                endpoint.post(_CREATE_API_GITHUB, params=params)
            elif plt_type == "azure":
                # TODO: pass secrets on the cmd line
                params.update({"personalAccessToken": _TO_BE_SET, "url": url_or_workspace})
                endpoint.post(_CREATE_API_AZURE, params=params)
            elif plt_type == "gitlab":
                params.update({"personalAccessToken": _TO_BE_SET, "url": url_or_workspace})
                endpoint.post(_CREATE_API_GITLAB, params=params)
            elif plt_type == "bitbucket":
                params.update({"personalAccessToken": _TO_BE_SET, "url": url_or_workspace})
                endpoint.post(_CREATE_API_BITBUCKET, params=params)
            elif plt_type == "bitbucketcloud":
                params.update({"clientSecret": _TO_BE_SET, "clientId": _TO_BE_SET, "workspace": url_or_workspace})
                endpoint.post(_CREATE_API_BBCLOUD, params=params)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"creating devops platform {key}/{plt_type}/{url_or_workspace}", catch_http_statuses=(HTTPStatus.BAD_REQUEST,))
            if endpoint.edition() in ("community", "developer"):
                log.warning("Can't set DevOps platform '%s', don't you have more that 1 of that type?", key)
            raise exceptions.UnsupportedOperation(f"Can't set DevOps platform '{key}', don't you have more that 1 of that type?")
        o = DevopsPlatform(endpoint=endpoint, key=key, platform_type=plt_type)
        o.refresh()
        return o

    def _load(self, data: types.ApiPayload) -> DevopsPlatform:
        """Loads a devops platform object with data"""
        self.sq_json = data
        self.url = "https://bitbucket.org" if self.type == "bitbucketcloud" else data["url"]
        self._specific = {k: v for k, v in data.items() if k not in ("key", "url")}
        return self

    def __str__(self) -> str:
        """str() implementation"""
        string = f"devops platform '{self.key}'"
        if self.type == "bitbucketcloud" and self._specific:
            string += f" workspace '{self._specific['workspace']}'"
        return string

    def refresh(self) -> bool:
        """Reads / Refresh a DevOps platform information

        :return: Whether the operation succeeded
        """
        data = json.loads(self.get(DevopsPlatform.API[c.LIST]).text)
        for alm_data in data.get(self.type, {}):
            if alm_data["key"] != self.key:
                self.sq_json = alm_data
                return True
        return False

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Exports a DevOps platform configuration in JSON format

        :param ConfigSettings export_settings: Config params for the export
        :return: The configuration of the DevOps platform (except secrets)
        """
        json_data = {"key": self.key, "type": self.type, "url": self.url}
        json_data.update(self.sq_json.copy())
        return util.filter_export(json_data, _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False))

    def set_pat(self, pat: str, user_name: Optional[str] = None) -> bool:
        """Sets the PAT for GitLab, BitBucket and Azure DevOps"""
        if self.type == "github":
            log.warning("Can't set PAT for GitHub devops platform")
            return False
        return self.post("alm_integrations/set_pat", params={"almSettings": self.key, "pat": pat, "username": user_name}).ok

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

        params = {"key": self.key, "url": kwargs["url"]}
        additional = ()
        if alm_type == "bitbucketcloud":
            additional = ("clientId", "workspace")
        elif alm_type == "github":
            additional = ("clientId", "appId", "privateKey", "clientSecret")
        for k in additional:
            params[k] = kwargs.get(k, _TO_BE_SET)
        try:
            ok = self.post(f"alm_settings/update_{alm_type}", params=params).ok
            self.url = kwargs["url"]
            self._specific = {k: v for k, v in params.items() if k not in ("key", "url")}
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"updating devops platform {self.key}/{alm_type}", catch_http_statuses=(HTTPStatus.BAD_REQUEST,))
            ok = False
        return ok


def count(endpoint: platform.Platform, platf_type: Optional[str] = None) -> int:
    """
    :param platf_type: Filter for a specific type, defaults to None (see DEVOPS_PLATFORM_TYPES set)
    :return: Count of DevOps platforms
    """
    get_list(endpoint=endpoint)
    if platf_type is None:
        return len(DevopsPlatform.CACHE)
    # Hack: check first 5 chars to that bitbucket cloud and bitbucket server match
    return sum(1 for o in DevopsPlatform.CACHE.values() if o.type[0:4] == platf_type[0:4])


def get_list(endpoint: platform.Platform) -> dict[str, DevopsPlatform]:
    """Reads all DevOps platforms from SonarQube

    :param endpoint: Reference to the SonarQube platform
    :return: List of DevOps platforms
    :rtype: dict{<platformKey>: <DevopsPlatform>}
    """
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Can't get list of DevOps platforms on SonarCloud")
    data = json.loads(endpoint.get(DevopsPlatform.API[c.LIST]).text)
    for alm_type in DEVOPS_PLATFORM_TYPES:
        for alm_data in data.get(alm_type, {}):
            DevopsPlatform.load(endpoint, alm_type, alm_data)
    return {o.key: o for o in DevopsPlatform.CACHE.values()}


def get_object(endpoint: platform.Platform, key: str) -> DevopsPlatform:
    """
    :param endpoint: Reference to the SonarQube platform
    :param key: Key of the devops platform (its name)
    :return: The DevOps platforms corresponding to key, or None if not found
    """
    if len(DevopsPlatform.CACHE) == 0:
        get_list(endpoint)
    return DevopsPlatform.read(endpoint, key)


def exists(endpoint: platform.Platform, key: str) -> bool:
    """
    :param endpoint: Reference to the SonarQube platform
    :param key: Key of the devops platform (its name)
    :return: Whether the platform exists
    """
    return get_object(endpoint=endpoint, key=key) is not None


def export(endpoint: platform.Platform, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
    """
    :meta private:
    """
    log.info("Exporting DevOps integration settings")
    json_data = {}
    for s in get_list(endpoint).values():
        export_data = s.to_json(export_settings)
        key = export_data.pop("key")
        json_data[key] = export_data
    return json_data


def import_config(endpoint: platform.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> None:
    """Imports DevOps platform configuration in SonarQube/Cloud"""
    devops_settings = config_data.get("devopsIntegration", {})
    if len(devops_settings) == 0:
        log.info("No devops integration settings in config, skipping import...")
        return
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Can't get import DevOps platforms in SonarCloud")
    log.info("Importing DevOps config %s", util.json_dump(devops_settings))
    if len(DevopsPlatform.CACHE) == 0:
        get_list(endpoint)
    for name, data in devops_settings.items():
        try:
            o = DevopsPlatform.read(endpoint, name)
        except exceptions.ObjectNotFound:
            info = data["workspace"] if data["type"] == "bitbucketcloud" else data["url"]
            try:
                o = DevopsPlatform.create(key=name, endpoint=endpoint, plt_type=data["type"], url_or_workspace=info)
            except exceptions.UnsupportedOperation as e:
                log.error(str(e))
                continue
        o.update(**data)


def devops_type(endpoint: platform.Platform, key: str) -> Optional[str]:
    """
    :return: The type of a DevOps platform (see DEVOPS_PLATFORM_TYPES), or None if not found
    """
    o = get_object(endpoint=endpoint, key=key)
    if o is None:
        return None
    return o.type
