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

    Abstraction of the SonarQube "webhook" concept

"""

import json
import sonar.utilities as util
import sonar.sqobject as sq

_WEBHOOKS = []


class WebHook(sq.SqObject):

    def __init__(self, name, endpoint, url=None, secret=None, project=None, data=None):
        super().__init__(name, endpoint)
        if data is None:
            params = util.remove_nones({"name": name, "url": url, "secret": secret, "project": project})
            data = json.loads(self.post("webhooks/create", params=params).text)["webhook"]
        self._json = data
        self.name = data["name"]
        self.key = data["key"]
        self.url = data["url"]
        self.secret = data.get("secret", None)
        _WEBHOOKS[self.uuid()] = self

    def __str__(self):
        return f"webhook '{self.name}'"

    def uuid(self):
        return self.name

    def update(self, **kwargs):
        params = util.remove_nones(kwargs)
        self.post("webhooks/update", params=params)


def search(endpoint, params=None):
    return sq.search_objects(
        api="webhooks/list",
        params=params,
        returned_field="webhooks",
        key_field="key",
        object_class=WebHook,
        endpoint=endpoint
    )


def get_list(endpoint):
    util.logger.info("Getting webhooks")
    return search(endpoint=endpoint)


def create(endpoint, name, url, secret=None, project=None):
    return WebHook(name, endpoint, url=url, secret=secret, project=project)


def update(endpoint, name, **kwargs):
    get_object(name, endpoint).update(**kwargs)


def get_object(name, endpoint):
    if name not in _WEBHOOKS:
        _ = WebHook(name=name, endpoint=endpoint)
    return _WEBHOOKS[name]
