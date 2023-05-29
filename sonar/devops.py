#
# sonar-tools
# Copyright (C) 2022-2023 Olivier Korach
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


from http import HTTPStatus
import json

from requests.exceptions import HTTPError

from sonar import sqobject, exceptions
import sonar.utilities as util

#: DevOps platform types in SonarQube
DEVOPS_PLATFORM_TYPES = ("github", "azure", "bitbucket", "bitbucketcloud", "gitlab")


_OBJECTS = {}

_CREATE_API_GITHUB = "alm_settings/create_github"
_CREATE_API_GITLAB = "alm_settings/create_gitlab"
_CREATE_API_AZURE = "alm_settings/create_azure"
_CREATE_API_BITBUCKET = "alm_settings/create_bitbucket"
_CREATE_API_BBCLOUD = "alm_settings/create_bitbucketcloud"
APIS = {"list": "alm_settings/list_definitions"}

_TO_BE_SET = "TO_BE_SET"
_IMPORTABLE_PROPERTIES = ("key", "type", "url", "workspace", "clientId", "appId")


class DevopsPlatform(sqobject.SqObject):
    """
    Abstraction of the SonarQube ALM/DevOps Platform concept
    """

    @classmethod
    def read(cls, endpoint, key):
        if key in _OBJECTS:
            return _OBJECTS[key]
        data = json.loads(endpoint.get(APIS["list"]).text)
        for plt_type, platforms in data.items():
            for p in platforms:
                if p["key"] == key:
                    return cls.load(endpoint, plt_type, data)
        raise exceptions.ObjectNotFound(key, f"DevOps platform key '{key}' not found")

    @classmethod
    def load(cls, endpoint, plt_type, data):
        key = data["key"]
        if key in _OBJECTS:
            return _OBJECTS[key]
        o = DevopsPlatform(key, endpoint, plt_type)
        return o._load(data)

    @classmethod
    def create(cls, endpoint, key, plt_type, url_or_workspace):
        params = {"key": key}
        try:
            if plt_type == "github":
                params.update(
                    {"appId": _TO_BE_SET, "clientId": _TO_BE_SET, "clientSecret": _TO_BE_SET, "privateKey": _TO_BE_SET, "url": url_or_workspace}
                )
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
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.BAD_REQUEST and endpoint.edition() == "developer":
                util.logger.warning("Can't set DevOps platform '%s', don't you have more that 1 of that type?", key)
                raise exceptions.UnsupportedOperation(f"Can't set DevOps platform '{key}', don't you have more that 1 of that type?")
            raise
        o = DevopsPlatform(key, endpoint, plt_type)
        o.refresh()
        return o

    def __init__(self, key, endpoint, platform_type):
        super().__init__(key, endpoint)
        self.type = platform_type  #: DevOps platform type
        self.url = None  #: DevOps platform URL
        self._specific = None  #: DevOps platform specific settings
        _OBJECTS[key] = self
        util.logger.debug("Created object %s", str(self))

    def _load(self, data):
        self._json = data
        self.url = "https://bitbucket.org" if self.type == "bitbucketcloud" else data["url"]
        self._specific = data.copy()
        for k in ("key", "url"):
            self._specific.pop(k, None)
        return self

    def __str__(self):
        string = f"devops platform '{self.key}'"
        if self.type == "bitbucketcloud" and self._specific:
            string += f" workspace '{self._specific['workspace']}'"
        return string

    def refresh(self):
        """Reads / Refresh a DevOps platform information

        :return: Whether the operation succeeded
        :rtype: bool
        """
        data = json.loads(self.get(APIS["list"]).text)
        for alm_data in data.get(self.type, {}):
            if alm_data["key"] != self.key:
                self._json = alm_data
                return True
        return False

    def to_json(self, full=False):
        """Exports a DevOps platform configuration in JSON format

        :param full: Whether to export all properties, including those that can't be set, or not, defaults to False
        :type full: bool, optional
        :return: The configuration of the DevOps platform (except secrets)
        :rtype: dict
        """
        json_data = self._json.copy()
        json_data.update({"key": self.key, "type": self.type, "url": self.url})
        return util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full)

    def set_pat(self, pat, user_name=None):
        if self.type == "github":
            util.logger.warning("Can't set PAT for GitHub devops platform")
            return False
        return self.post("alm_integrations/set_pat", params={"almSettings": self.key, "pat": pat, "username": user_name}).ok

    def update(self, **kwargs):
        """Updates a DevOps platform with information from data

        :param dict data: data to update the DevOps platform configuration
                          (url, clientId, workspace, appId depending on the type of platform)
        :return: Whether the operation succeeded
        :rtype: bool
        """
        alm_type = kwargs["type"]
        if alm_type != self.type:
            util.logger.error("DevOps platform type '%s' for update of %s is incompatible", alm_type, str(self))
            return False

        params = {"key": self.key, "url": kwargs["url"]}
        if alm_type == "bitbucketcloud":
            params.update({"clientId": kwargs["clientId"], "workspace": kwargs["workspace"]})
        elif alm_type == "github":
            params.update({"clientId": kwargs["clientId"], "appId": kwargs["appId"]})

        self.post(f"alm_settings/update_{alm_type}", params=params)
        self.url = kwargs["url"]
        for k in ("key", "url"):
            params.pop(k)
        self._specific = params
        return self


def count(platf_type=None):
    """
    :param platf_type: Filter for a specific type, defaults to None (see DEVOPS_PLATFORM_TYPES set)
    :type platf_type: str or None
    :return: Count of DevOps platforms
    :rtype: int
    """
    if platf_type is None:
        return len(_OBJECTS)
    # Hack: check first 5 chars to that bitbucket cloud and bitbucket server match
    return sum(1 for o in _OBJECTS.values() if o.type[0:4] == platf_type[0:4])


def get_list(endpoint):
    """Reads all DevOps platforms from SonarQube

    :param Platform endpoint: Reference to the SonarQube platform
    :return: List of DevOps platforms
    :rtype: dict{<platformKey>: <DevopsPlatform>}
    """
    if endpoint.edition() == "community":
        return _OBJECTS
    data = json.loads(endpoint.get(APIS["list"]).text)
    for alm_type in DEVOPS_PLATFORM_TYPES:
        for alm_data in data.get(alm_type, {}):
            DevopsPlatform.load(endpoint, alm_type, alm_data)
    return _OBJECTS


def get_object(devops_platform_key, endpoint):
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :param str devops_platform_key: Key of the platform (its name)
    :return: The DevOps platforms corresponding to key, or None if not found
    :rtype: DevopsPlatform
    """
    if len(_OBJECTS) == 0:
        get_list(endpoint)
    return DevopsPlatform.read(endpoint, devops_platform_key)


def exists(devops_platform_key, endpoint):
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :param str devops_platform_key: Key of the platform (its name)
    :return: Whether the platform exists
    :rtype: bool
    """
    return get_object(devops_platform_key, endpoint) is not None


def export(endpoint, full=False):
    """
    :meta private:
    """
    util.logger.info("Exporting DevOps integration settings")
    json_data = {}
    for s in get_list(endpoint).values():
        json_data[s.uuid()] = s.to_json(full)
        json_data[s.uuid()].pop("key")
    return json_data


def import_config(endpoint, config_data):
    """
    :meta private:
    """
    devops_settings = config_data.get("devopsIntegration", {})
    if len(devops_settings) == 0:
        util.logger.info("No devops integration settings in config, skipping import...")
        return
    if endpoint.edition() == "community":
        util.logger.warning("Can't import devops integration settings on a community edition")
        return
    util.logger.info("Importing devops integration settings")
    if len(_OBJECTS) == 0:
        get_list(endpoint)
    for name, data in devops_settings.items():
        try:
            o = DevopsPlatform.read(endpoint, name)
        except exceptions.ObjectNotFound:
            info = data["workspace"] if data["type"] == "bitbucketcloud" else data["url"]
            o = DevopsPlatform.create(key=name, endpoint=endpoint, plt_type=data["type"], url_or_workspace=info)
        o.update(**data)


def devops_type(platform_key, endpoint):
    """
    :return: The type of a DevOps platform (see DEVOPS_PLATFORM_TYPES), or None if not found
    :rtype: str or None
    """
    o = get_object(platform_key, endpoint)
    if o is None:
        return None
    return o.type


def platform_exists(platform_key, endpoint):
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :param str platform_key: Key of the platform (its name)
    :return: Whether the platform exists in SonarQube
    :rtype: bool
    """
    return get_object(platform_key, endpoint) is not None
