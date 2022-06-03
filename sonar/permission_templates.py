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
_MAP = {}
_DEFAULT_TEMPLATES = {}
_QUALIFIER_REVERSE_MAP = {"projects": "TRK", "applications": "APP", "portfolios": "VW"}
_SEARCH_API = "permissions/search_templates"
_CREATE_API = "permissions/create_template"
_UPDATE_API = "permissions/update_template"


class PermissionTemplate(sqobject.SqObject):
    def __init__(self, endpoint, name, data=None, create_data=None):
        super().__init__(name, endpoint)
        self.key = None
        self.name = name
        self._permissions = None
        if create_data is not None:
            utilities.logger.info("Creating permission template '%s'", name)
            utilities.logger.debug("from create_data %s", utilities.json_dump(create_data))
            create_data["name"] = name
            self.post(_CREATE_API, params=create_data)
            data = search_by_name(endpoint, name)
            self.key = data.get("id", None)
            self.set_pattern(create_data.pop("pattern", None))
            self.set_permissions(create_data.pop("permissions", None))
        elif data is None:
            data = search_by_name(endpoint, name)
            self.permissions()
            utilities.logger.info("Creating permission template '%s'", name)
            utilities.logger.debug("from sync data %s", utilities.json_dump(data))
        self._json = data
        self.name = name
        self.key = data.get("id", None)
        self.description = data.get("description", None)
        self.project_key_pattern = data.get("projectKeyPattern", "")
        self.creation_date = utilities.string_to_date(data.get("createdAt", None))
        self.last_update = utilities.string_to_date(data.get("updatedAt", None))
        self.__set_hash()

    def __str__(self):
        return f"permission template '{self.name}'"

    def __set_hash(self):
        _PERMISSION_TEMPLATES[self.key] = self
        _MAP[self.name] = self.key

    def is_default_for(self, qualifier):
        return qualifier in _DEFAULT_TEMPLATES and _DEFAULT_TEMPLATES[qualifier] == self.key

    def is_projects_default(self):
        return self.is_default_for("TRK")

    def is_applications_default(self):
        return self.is_default_for("APP")

    def is_portfolios_default(self):
        return self.is_default_for("VW")

    def set_permissions(self, perms):
        if perms is None or len(perms) == 0:
            return
        utilities.logger.debug("Setting permissions %s for %s", str(perms), str(self))
        permissions.set_permissions(endpoint=self.endpoint, permissions=perms, template=self.name)
        self._permissions = self.permissions()

    def update(self, **pt_data):
        name = pt_data.get("name", None)
        desc = pt_data.get("description", None)
        pattern = pt_data.get("pattern", None)
        params = {"id": self.key, "name": name, "description": desc, "projectKeyPattern": pattern}
        utilities.logger.info("Updating %s, %s with %s", self.key, self.name, str(params))
        self.post(_UPDATE_API, params=params)
        if name is not None:
            _MAP.pop(self.name, None)
            self.name = name
            _MAP[self.name] = self.key
        if desc is not None:
            self.description = desc
        if pattern is not None:
            self.project_key_pattern = pattern
        self.set_permissions(pt_data.get("permissions", None))
        return self

    def permissions(self):
        if self._permissions is None:
            self._permissions = {}
            for t in ("users", "groups"):
                self._permissions[t] = permissions.simplify(
                    permissions.get(endpoint=self.endpoint, perm_type=f"template_{t}", templateId=self.key)
                )
        return self._permissions

    def set_as_default(self, what_list):
        params = {"templateId": self.key}
        utilities.logger.debug("Setting %s as default for %s", str(self), str(what_list))
        for d in what_list:
            # utilities.logger.debug("Setting %s as default for %s", str(self), d)
            params["qualifier"] = _QUALIFIER_REVERSE_MAP.get(d, d)
            self.post("permissions/set_default_template", params=params)

    def set_pattern(self, pattern):
        if pattern is None:
            return None
        r = self.post(_UPDATE_API, params={"id": self.key, "projectKeyPattern": pattern})
        self.project_key_pattern = pattern
        return r

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
            json_data["defaultFor"] = utilities.list_to_csv(defaults, ", ")

        if full_specs:
            json_data["creationDate"] = utilities.date_to_string(self.creation_date)
            json_data["lastUpdate"] = utilities.date_to_string(self.last_update)
        return json_data


def get_object(name, endpoint=None):
    if len(_PERMISSION_TEMPLATES) == 0:
        get_list(endpoint)
    if name not in _MAP:
        return None
    return _PERMISSION_TEMPLATES[_MAP[name]]


def create_or_update(name, endpoint, kwargs):
    utilities.logger.debug("Create or update permission template '%s'", name)
    o = get_object(endpoint=endpoint, name=name)
    if o is None:
        utilities.logger.debug("Permission template '%s' does not exist, creating...", name)
        return create(name, endpoint, create_data=kwargs)
    else:
        return o.update(name=name, **kwargs)


def create(name, endpoint=None, create_data=None):
    o = get_object(name=name, endpoint=endpoint)
    if o is None:
        o = PermissionTemplate(name=name, endpoint=endpoint, create_data=create_data)
    else:
        utilities.logger.info("%s already exists, skipping creation...", str(o))
    return o


def search(endpoint, params=None):
    utilities.logger.debug("Searching all permission templates")
    objects_list = {}
    data = json.loads(endpoint.get(_SEARCH_API, params=params).text)
    for obj in data["permissionTemplates"]:
        objects_list[obj["id"]] = PermissionTemplate(name=obj["name"], endpoint=endpoint, data=obj)
    _load_default_templates(data=data)
    return objects_list


def search_by_name(endpoint, name):
    return utilities.search_by_name(endpoint, name, _SEARCH_API, "permissionTemplates")


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
            for k in ("name", "id", "key"):
                json_data[pt.name].pop(k, None)
    return json_data


def import_config(endpoint, config_data):
    if "permissionTemplates" not in config_data:
        utilities.logger.info("No permissions templates in config, skipping import...")
        return
    utilities.logger.info("Importing permission templates")
    get_list(endpoint)
    for name, data in config_data["permissionTemplates"].items():
        utilities.json_dump_debug(data, f"Importing: {name}:")
        o = create_or_update(name, endpoint, data)
        defs = data.get("defaultFor", None)
        if defs is not None and defs != "":
            o.set_as_default(utilities.csv_to_list(data.get("defaultFor", None)))
