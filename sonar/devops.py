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


class DevopsPlatform(sqobject.SqObject):
    def __init__(self, key, platform_type, endpoint, data=None):
        super().__init__(key, endpoint)
        self.type = platform_type
        self.json = data
        if platform_type == "bitbucketcloud":
            self.url = "https://bitbucket.org"
        else:
            self.url = data["url"]
        util.logger.debug("Created %s", str(self))

    def uuid(self):
        return f"{self.key}"

    def __str__(self):
        string = f"devops platform '{self.key}'"
        if self.type == "bitbucketcloud":
            string += f" workspace '{self.json['workspace']}'"
        return string

    def to_json(self):
        json_data = self.json.copy()
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

def get_all(endpoint):
    """Gets several settings as bulk (returns a dict)"""
    object_list = {}
    data = json.loads(endpoint.get("api/alm_settings/list_definitions").text)
    for t in _DEVOPS_PLATFORM_TYPES:
        for d in data.get(t, {}):
            o = DevopsPlatform(d["key"], endpoint=endpoint, platform_type=t, data=d)
            object_list[o.uuid()] = o
    return object_list


def settings(endpoint):
    return get_all(endpoint)


def export(endpoint):
    util.logger.info("Exporting DevOps integration settings")
    json_data = {}
    for s in settings(endpoint).values():
        json_data[s.uuid()] = s.to_json()
        json_data[s.uuid()].pop("key")
    return json_data

def create_or_update_devops_platform(name, data, endpoint):
    existing_platforms = get_all(endpoint=endpoint)
    if name in existing_platforms:
        existing_platforms[name].update(data)
    else:
        o = DevopsPlatform(key=name, platform_type=data["type"], endpoint=endpoint, data=data)


def import_config(endpoint, config_data):
    devops_settings = config_data.get("devopsIntegration", {})
    if len(devops_settings) == 0:
        util.logger.info("No devops integration settings in config, skipping import...")
        return
    util.logger.info("Importing devops integration settings")
    for name, data in devops_settings.items():
        create_or_update_devops_platform(name=name, data=data, endpoint=endpoint)


def platform_type(platform_key, endpoint):
    p_list = get_all(endpoint=endpoint)
    for platform in p_list.values():
        if platform.key == platform_key:
            return platform.type
    return None


def set_devops_binding(project_key, data, endpoint):
    alm_key = data["key"]
    alm_type = platform_type(platform_key=alm_key, endpoint=endpoint)
    if alm_type == "github":
        set_github_binding(endpoint, project_key, alm_key, repository=data["repository"],
                           summary_comment=data.get("summaryComment", True), monorepo=data.get("monorepo", False))
    elif alm_type == "gitlab":
        set_gitlab_binding(endpoint, project_key, alm_key, repository=data["repository"], monorepo=data.get("monorepo", False))
    elif alm_type == "azure":
        set_azure_devops_binding(endpoint, project_key, alm_key, repository=data["repository"], monorepo=data.get("monorepo", False),
                                 slug=data["slug"])


def __std_params(alm_key, proj_key, repo, monorepo):
    return {"almSetting": alm_key, "project": proj_key, "repository": repo, "monorepo": str(monorepo).lower()}


def set_github_binding(endpoint, project_key, devops_platform_key, repository, monorepo=False, summary_comment=True):
    params = __std_params(devops_platform_key, project_key, repository, monorepo)
    params["summaryCommentEnabled"] = str(summary_comment).lower()
    endpoint.post("alm_settings/set_github_binding", params=params)


def set_gitlab_binding(endpoint, project_key, devops_platform_key, repository,  monorepo=False):
    params = __std_params(devops_platform_key, project_key, repository, monorepo)
    endpoint.post("alm_settings/set_gitlab_binding", params=params)


def set_bitbucket_binding(endpoint, project_key, devops_platform_key, repository,  slug, monorepo=False):
    params = __std_params(devops_platform_key, project_key, repository, monorepo)
    params["slug"] = slug
    endpoint.post("alm_settings/set_bitbucket_binding", params=params)


def set_bitbucketcloud_binding(endpoint, project_key, devops_platform_key, repository,  monorepo=False):
    params = __std_params(devops_platform_key, project_key, repository, monorepo)
    endpoint.post("alm_settings/set_bitbucketcloud_binding", params=params)


def set_azure_devops_binding(endpoint, project_key, devops_platform_key, slug, repository,  monorepo=False):
    params = __std_params(devops_platform_key, project_key, repository, monorepo)
    params["projectName"] = slug
    endpoint.post("alm_settings/set_azure_binding", params=params)
