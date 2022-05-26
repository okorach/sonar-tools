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


def get_all(endpoint):
    """Gets several settings as bulk (returns a dict)"""
    object_list = {}
    resp = endpoint.get("api/alm_settings/list_definitions")
    data = json.loads(resp.text)
    for t in _DEVOPS_PLATFORM_TYPES:
        for d in data[t]:
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
