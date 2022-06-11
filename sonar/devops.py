#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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
    Abstraction of the SonarQube ALM/DevOps Platform concept
"""

import json
from sonar import sqobject
import sonar.utilities as util

_DEVOPS_PLATFORM_TYPES = ("github", "azure", "bitbucket", "bitbucketcloud", "gitlab")
_OBJECTS = {}
_CREATE_API_GITHUB = "alm_settings/create_github"
_CREATE_API_GITLAB = "alm_settings/create_gitlab"
_CREATE_API_AZURE = "alm_settings/create_azure"
_CREATE_API_BITBUCKET = "alm_settings/create_bitbucket"
_CREATE_API_BBCLOUD = "alm_settings/create_bitbucketcloud"
_LIST_API = "alm_settings/list_definitions"

class DevopsPlatform(sqobject.SqObject):
    def __init__(self, key, devops_platform_type, endpoint, data=None, create_data=None):
        super().__init__(key, endpoint)
        self.type = devops_platform_type
        if create_data is not None:
            self.type = create_data.pop("type")
            params = create_data
            params["key"] = self.key
            if self.type == "github":
                params["clientSecret"] = "TO_BE_SET"
                params["privateKey"] = "TO_BE_SET"
                self.post(_CREATE_API_GITHUB, params=params)
            elif self.type == "azure":
                # TODO: pass secrets on the cmd line
                params["personalAccessToken"] = "TO_BE_SET"
                self.post(_CREATE_API_AZURE, params=params)
            elif self.type == "gitlab":
                params["personalAccessToken"] = "TO_BE_SET"
                self.post(_CREATE_API_GITLAB, params=params)
            elif self.type == "bitbucket":
                params["personalAccessToken"] = "TO_BE_SET"
                self.post(_CREATE_API_BITBUCKET, params=params)
            elif self.type == "bitbucketcloud":
                params["clientSecret"] = "TO_BE_SET"
                self.post(_CREATE_API_BBCLOUD, params=params)
            self.read()
        elif data is None:
            self.read()
        else:
            self._json = data
            self.url = data.get("url", "")
        if devops_platform_type == "bitbucketcloud":
            self.url = "https://bitbucket.org"
        _OBJECTS[key] = self
        util.logger.debug("Created %s", str(self))

    def uuid(self):
        return f"{self.key}"

    def __str__(self):
        string = f"devops platform '{self.key}'"
        if self.type == "bitbucketcloud":
            string += f" workspace '{self._json['workspace']}'"
        return string

    def read(self):
        data = json.loads(self.get(_LIST_API).text)
        for alm_data in data.get(self.type, {}):
            if alm_data["key"] != self.key:
                continue
            self._json = alm_data
            break
        return self._json

    def to_json(self):
        json_data = self._json.copy()
        json_data.update({"key": self.key, "type": self.type, "url": self.url})
        return json_data

    def update(self, data):
        alm_type = data["type"]
        if alm_type != self.type:
            util.logger.error("DevOps platform type '%s' for update of %s is incompatible", alm_type, str(self))
            return False

        params = {"key": self.key, "url": data["url"]}
        if alm_type == "bitbucketcloud":
            params.update({"clientId": data["clientId"], "workspace": data["workspace"]})
        elif alm_type == "github":
            params.update({"clientId": data["clientId"], "appId": data["appId"]})

        return self.post(f"alm_settings/update_{alm_type}", params=params).ok

def get_list(endpoint):
    """Gets several settings as bulk (returns a dict)"""
    data = json.loads(endpoint.get(_LIST_API).text)
    for alm_type in _DEVOPS_PLATFORM_TYPES:
        for alm_data in data.get(alm_type, {}):
            if alm_data["key"] in _OBJECTS:
                _OBJECTS[alm_data["key"]].update(alm_data)
            else:
                _ = DevopsPlatform(alm_data["key"], endpoint=endpoint, devops_platform_type=alm_type, data=alm_data)
    return _OBJECTS


def get_object(devops_platform_key, endpoint):
    if len(_OBJECTS) == 0:
        get_list(endpoint)
    return _OBJECTS.get(devops_platform_key, None)


def exists(devops_platform_key, endpoint):
    return get_object(devops_platform_key, endpoint) is not None


def settings(endpoint):
    return get_list(endpoint)


def export(endpoint):
    util.logger.info("Exporting DevOps integration settings")
    json_data = {}
    for s in settings(endpoint).values():
        json_data[s.uuid()] = s.to_json()
        json_data[s.uuid()].pop("key")
    return json_data


def create_or_update_devops_platform(name, data, endpoint):
    o = _OBJECTS.get(name, None)
    if o is None:
        o = DevopsPlatform(key=name, devops_platform_type=data["type"], endpoint=endpoint, create_data=data)
    else:
        o.update(data)
    return o


def import_config(endpoint, config_data):
    devops_settings = config_data.get("devopsIntegration", {})
    if len(devops_settings) == 0:
        util.logger.info("No devops integration settings in config, skipping import...")
        return
    util.logger.info("Importing devops integration settings")
    if len(_OBJECTS) == 0:
        get_list(endpoint)
    for name, data in devops_settings.items():
        create_or_update_devops_platform(name=name, data=data, endpoint=endpoint)


def platform_type(platform_key, endpoint):
    o = get_object(platform_key, endpoint)
    if o is None:
        return None
    return o.type
