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

import json
from sonar import sqobject, utilities
from sonar.permissions import template_permissions

_OBJECTS = {}
_MAP = {}
_DEFAULT_TEMPLATES = {}
_QUALIFIER_REVERSE_MAP = {"projects": "TRK", "applications": "APP", "portfolios": "VW"}
_SEARCH_API = "permissions/search_templates"
_CREATE_API = "permissions/create_template"
_UPDATE_API = "permissions/update_template"

_IMPORTABLE_PROPERTIES = ("name", "description", "pattern", "permissions", "defaultFor")


class PermissionTemplate(sqobject.SqObject):
    def __init__(self, endpoint, name, data=None, create_data=None):
        super().__init__(name, endpoint)
        self.key = None
        self.name = name
        self.description = None
        self.project_key_pattern = None
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
            self.key = data.get("id", None)
            self.permissions().read()
            utilities.logger.info("Creating permission template '%s'", name)
            utilities.logger.debug("from sync data %s", utilities.json_dump(data))
        self._json = data
        self.name = name
        data.pop("name")
        self.key = data.pop("id", None)
        self.description = data.get("description", None)
        self.project_key_pattern = data.pop("projectKeyPattern", "")
        self.creation_date = utilities.string_to_date(data.pop("createdAt", None))
        self.last_update = utilities.string_to_date(data.pop("updatedAt", None))
        self.__set_hash()
        _OBJECTS[self.key] = self
        _MAP[self.name.lower()] = self.key

    def __str__(self):
        return f"permission template '{self.name}'"

    def __set_hash(self):
        _OBJECTS[self.key] = self
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
        self.permissions().set(perms)

    def update(self, **pt_data):
        params = {"id": self.key}
        # Hack: On SQ 8.9 if you pass all params otherwise SQ does NPE
        params["name"] = pt_data.get("name", self.name if self.name else "")
        params["description"] = pt_data.get("description", self.description if self.description else "")
        params["projectKeyPattern"] = pt_data.get("pattern", self.project_key_pattern)
        utilities.logger.info("Updating %s with %s", str(self), str(params))
        self.post(_UPDATE_API, params=params)
        _MAP.pop(self.name, None)
        self.name = params["name"]
        _MAP[self.name] = self.key
        self.description = params["description"]
        self.project_key_pattern = params["projectKeyPattern"]
        self.permissions().set(pt_data.get("permissions", None))
        return self

    def permissions(self):
        if self._permissions is None:
            self._permissions = template_permissions.TemplatePermissions(self)
        return self._permissions

    def set_as_default(self, what_list):
        utilities.logger.debug("Setting %s as default for %s", str(self), str(what_list))
        ed = self.endpoint.edition()
        for d in what_list:
            qual = _QUALIFIER_REVERSE_MAP.get(d, d)
            if (ed == "community" and qual in ("VW", "APP")) or (ed == "developer" and qual == "VW"):
                utilities.logger.warning("Can't set permission template as default for %s on a %s edition", qual, ed)
                continue
            self.post("permissions/set_default_template", params={"templateId": self.key, "qualifier": qual})

    def set_pattern(self, pattern):
        if pattern is None:
            return None
        return self.update(pattern=pattern)

    def to_json(self, full=False):
        json_data = self._json.copy()
        json_data.update(
            {
                "key": self.key,
                "name": self.name,
                "description": self.description if self.description != "" else None,
                "pattern": self.project_key_pattern,
                "permissions": self.permissions().export(),
            }
        )

        defaults = []
        if self.is_projects_default():
            defaults.append("projects")
        if self.is_applications_default():
            defaults.append("applications")
        if self.is_portfolios_default():
            defaults.append("portfolios")
        if len(defaults) > 0:
            json_data["defaultFor"] = utilities.list_to_csv(defaults, ", ")

        json_data["creationDate"] = utilities.date_to_string(self.creation_date)
        json_data["lastUpdate"] = utilities.date_to_string(self.last_update)
        return utilities.remove_nones(utilities.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))

    def audit(self, audit_settings):
        utilities.logger.debug("Auditing %s", str(self))
        return self.permissions().audit(audit_settings)


def get_object(name, endpoint=None):
    if len(_OBJECTS) == 0:
        get_list(endpoint)
    lowername = name.lower()
    if lowername not in _MAP:
        return None
    return _OBJECTS.get(_MAP[lowername], None)


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
        o = PermissionTemplate(name=obj["name"], endpoint=endpoint, data=obj)
        objects_list[o.key] = o
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


def export(endpoint, full=False):
    utilities.logger.info("Exporting permission templates")
    pt_list = get_list(endpoint)
    json_data = {}
    for pt in pt_list.values():
        json_data[pt.name] = pt.to_json(full)
        if not full:
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


def audit(endpoint, audit_settings):
    utilities.logger.info("--- Auditing permission templates ---")
    problems = []
    for pt in get_list(endpoint=endpoint).values():
        problems += pt.audit(audit_settings)
    return problems
