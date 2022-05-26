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

import json
from sonar import sqobject, utilities, permissions

_PERMISSION_TEMPLATES = {}
_DEFAULT_TEMPLATES = {}

_SEARCH_API = "permissions/search_templates"


class PermissionTemplate(sqobject.SqObject):
    def __init__(self, key=None, endpoint=None, data=None):
        super().__init__(key, endpoint)
        if data is None:
            data = json.loads(self.get(_SEARCH_API).text)
            for p in data["permissionTemplates"]:
                if p["id"] == key:
                    perm_temp = p
                    break
            _load_default_templates(data)
            data = perm_temp
        self._json = data
        self.name = data["name"]
        self.description = data["description"]
        self.creation_date = utilities.string_to_date(data["createdAt"])
        self.last_update = utilities.string_to_date(data["updatedAt"])
        self.project_key_pattern = data["projectKeyPattern"]
        self._permissions = None

    def is_default_for(self, qualifier):
        return qualifier in _DEFAULT_TEMPLATES and _DEFAULT_TEMPLATES[qualifier] == self.key

    def is_projects_default(self):
        return self.is_default_for("TRK")

    def is_applications_default(self):
        return self.is_default_for("APP")

    def is_portfolios_default(self):
        return self.is_default_for("VW")

    def permissions(self):
        if self._permissions is None:
            self._permissions = {}
            for t in ("users", "groups"):
                self._permissions[t] = permissions.simplify(
                    permissions.get(
                        endpoint=self.endpoint,
                        perm_type=f"template_{t}",
                        templateId=self.key,
                    )
                )
        return self._permissions

    def to_json(self, full_specs=False):
        json_data = {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "pattern": self.project_key_pattern,
            "permissions": self.permissions(),
        }
        for t in ("users", "groups"):
            if len(json_data["permissions"][t]) == 0:
                json_data["permissions"].pop(t)

        defaults = []
        if self.is_projects_default():
            defaults.append("projects")
        if self.is_applications_default():
            defaults.append("applications")
        if self.is_portfolios_default():
            defaults.append("portfolios")
        if len(defaults) > 0:
            json_data["defaultFor"] = ", ".join(defaults)

        if full_specs:
            json_data["creationDate"] = utilities.date_to_string(self.creation_date)
            json_data["lastUpdate"] = utilities.date_to_string(self.last_update)
        return json_data


def get_object(key, data=None, endpoint=None):
    if key not in _PERMISSION_TEMPLATES:
        _ = PermissionTemplate(key=key, data=data, endpoint=endpoint)
    return _PERMISSION_TEMPLATES[key]


def search(endpoint, params=None):
    new_params = {} if params is None else params.copy()
    objects_list = {}
    data = json.loads(endpoint.get(_SEARCH_API, params=new_params).text)

    for obj in data["permissionTemplates"]:
        objects_list[obj["id"]] = PermissionTemplate(obj["id"], endpoint=endpoint, data=obj)
    _load_default_templates(data=data)
    return objects_list


def get_list(endpoint):
    return search(endpoint, None)


def _load_default_templates(data=None, endpoint=None):
    if data is None:
        data = json.loads(endpoint.get(_SEARCH_API).text)
    for d in data["defaultTemplates"]:
        _DEFAULT_TEMPLATES[d["qualifier"]] = d["templateId"]


def export(endpoint, full_specs=False):
    utilities.logger.info("Exporting permission templates")
    pt_list = get_list(endpoint)
    json_data = {}
    for pt in pt_list.values():
        json_data[pt.name] = pt.to_json(full_specs)
        if not full_specs:
            json_data[pt.name].pop("name", None)
            json_data[pt.name].pop("key", None)
    return json_data
