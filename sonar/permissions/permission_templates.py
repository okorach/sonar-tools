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

"""Abstraction of the SonarQube permission template concept"""
from __future__ import annotations

import json
import re
from requests import RequestException

import sonar.logging as log
from sonar.util import types, cache
from sonar import sqobject, utilities
from sonar.permissions import template_permissions
import sonar.platform as pf
from sonar.audit.rules import get_rule, RuleId
import sonar.audit.problem as pb

_MAP = {}
_DEFAULT_TEMPLATES = {}
_QUALIFIER_REVERSE_MAP = {"projects": "TRK", "applications": "APP", "portfolios": "VW"}
_SEARCH_API = "permissions/search_templates"
_CREATE_API = "permissions/create_template"
_UPDATE_API = "permissions/update_template"

_IMPORTABLE_PROPERTIES = ("name", "description", "pattern", "permissions", "defaultFor")


class PermissionTemplate(sqobject.SqObject):
    """Abstraction of the Sonar permission template concept"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: pf.Platform, name: str, data: types.ApiPayload = None, create_data: types.ObjectJsonRepr = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=name)
        self.key = None
        self.name = name
        self.description = None
        self.project_key_pattern = None
        self._permissions = None
        if create_data is not None:
            log.info("Creating permission template '%s'", name)
            log.debug("from create_data %s", utilities.json_dump(create_data))
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
            log.info("Creating permission template '%s'", name)
            log.debug("from sync data %s", utilities.json_dump(data))
        self.sq_json = data
        self.name = name
        data.pop("name")
        self.key = data.pop("id", None)
        self.description = data.get("description", None)
        self.last_update = data.get("lastUpdate", None)
        self.project_key_pattern = data.pop("projectKeyPattern", "")
        self.creation_date = utilities.string_to_date(data.pop("createdAt", None))
        PermissionTemplate.CACHE.put(self)

    def __str__(self) -> str:
        """Returns the string representation of the object"""
        return f"permission template '{self.name}'"

    def __hash__(self) -> int:
        """Returns object unique id"""
        return hash((self.name.lower(), self.endpoint.url))

    def is_default_for(self, qualifier: str) -> bool:
        """Returns whether a template is the default for a type of qualifier"""
        return qualifier in _DEFAULT_TEMPLATES and _DEFAULT_TEMPLATES[qualifier] == self.key

    def is_projects_default(self) -> bool:
        """Returns whether a template is the default for projects"""
        return self.is_default_for("TRK")

    def is_applications_default(self) -> bool:
        """Returns whether a template is the default for apps"""
        return self.is_default_for("APP")

    def is_portfolios_default(self) -> bool:
        """Returns whether a template is the default for portfolios"""
        return self.is_default_for("VW")

    def set_permissions(self, perms: types.ObjectJsonRepr) -> PermissionTemplate:
        """Sets the permissions of a permission template"""
        if perms is None or len(perms) == 0:
            return self
        return self.permissions().set(perms)

    def update(self, **pt_data) -> PermissionTemplate:
        """Updates a permission template"""
        params = {"id": self.key}
        # Hack: On SQ 8.9 if you pass all params otherwise SQ does NPE
        params["name"] = pt_data.get("name", self.name if self.name else "")
        params["description"] = pt_data.get("description", self.description if self.description else "")
        params["projectKeyPattern"] = pt_data.get("pattern", self.project_key_pattern)
        log.info("Updating %s with %s", str(self), str(params))
        self.post(_UPDATE_API, params=params)
        _MAP.pop(self.name, None)
        self.name = params["name"]
        _MAP[self.name] = self.key
        self.description = params["description"]
        self.project_key_pattern = params["projectKeyPattern"]
        self.permissions().set(pt_data.get("permissions", None))
        return self

    def permissions(self) -> template_permissions.TemplatePermissions:
        """Returns the permissions of a template"""
        if self._permissions is None:
            self._permissions = template_permissions.TemplatePermissions(self)
        return self._permissions

    def set_as_default(self, what_list: list[str]) -> None:
        """Sets a permission template as default for projects or apps or portfolios"""
        log.debug("Setting %s as default for %s", str(self), str(what_list))
        ed = self.endpoint.edition()
        for d in what_list:
            qual = _QUALIFIER_REVERSE_MAP.get(d, d)
            if (ed == "community" and qual in ("VW", "APP")) or (ed == "developer" and qual == "VW"):
                log.warning("Can't set permission template as default for %s on a %s edition", qual, ed)
                continue
            try:
                self.post("permissions/set_default_template", params={"templateId": self.key, "qualifier": qual})
            except (ConnectionError, RequestException) as e:
                utilities.handle_error(e, f"setting {str(self)} as default")

    def set_pattern(self, pattern: str) -> PermissionTemplate:
        """Sets a permission template pattern"""
        if pattern is None:
            return self
        return self.update(pattern=pattern)

    def to_json(self, export_settings: types.ConfigSettings = None) -> types.ObjectJsonRepr:
        """Returns JSON representation of a permission template"""
        json_data = self.sq_json.copy()
        json_data.update(
            {
                "key": self.key,
                "name": self.name,
                "description": self.description if self.description != "" else None,
                "pattern": self.project_key_pattern,
                "permissions": self.permissions().export(export_settings=export_settings),
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
        if not self.project_key_pattern or self.project_key_pattern == "":
            json_data.pop("pattern")
        json_data["creationDate"] = utilities.date_to_string(self.creation_date)
        json_data["lastUpdate"] = utilities.date_to_string(self.last_update)
        return utilities.remove_nones(utilities.filter_export(json_data, _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False)))

    def _audit_pattern(self, audit_settings: types.ConfigSettings) -> list[pb.Problem]:
        log.debug("Auditing %s projectKeyPattern ('%s')", str(self), str(self.project_key_pattern))
        if not self.project_key_pattern or self.project_key_pattern == "":
            if not (self.is_applications_default() or self.is_portfolios_default() or self.is_projects_default()):
                return [pb.Problem(get_rule(RuleId.TEMPLATE_WITH_NO_PATTERN), self, str(self))]
        else:
            # Inspect regexp to detect suspicious pattern - Can't determine all bad cases but do our best
            # Currently detecting:
            # - Absence of '.' in the regexp
            # - '*' not preceded by '.' (confusion between wildcard and regexp)
            if not re.search(r"(^|[^\\])\.", self.project_key_pattern) or re.search(r"(^|[^.])\*", self.project_key_pattern):
                return [pb.Problem(get_rule(RuleId.TEMPLATE_WITH_SUSPICIOUS_PATTERN), self, str(self), self.project_key_pattern)]
        return []

    def audit(self, audit_settings: types.ConfigSettings) -> list[pb.Problem]:
        log.debug("Auditing %s", str(self))
        return self._audit_pattern(audit_settings) + self.permissions().audit(audit_settings)


def get_object(endpoint: pf.Platform, name: str) -> PermissionTemplate:
    """Returns Perm Template object corresponding to name"""
    if len(PermissionTemplate.CACHE) == 0:
        get_list(endpoint)
    return PermissionTemplate.CACHE.get(name.lower(), endpoint.url)


def create_or_update(endpoint: pf.Platform, name: str, data: types.ObjectJsonRepr) -> PermissionTemplate:
    """Creates or update a permission template with sonar-config JSON data"""
    log.debug("Create or update permission template '%s'", name)
    o = get_object(endpoint=endpoint, name=name)
    if o is None:
        log.debug("Permission template '%s' does not exist, creating...", name)
        return create(endpoint=endpoint, name=name, create_data=data)
    else:
        return o.update(name=name, **data)


def create(endpoint: pf.Platform, name: str, create_data: types.ObjectJsonRepr = None) -> PermissionTemplate:
    """Creates a permission template from sonar-config data"""
    o = get_object(endpoint=endpoint, name=name)
    if o is None:
        o = PermissionTemplate(name=name, endpoint=endpoint, create_data=create_data)
    else:
        log.info("%s already exists, skipping creation...", str(o))
    return o


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, PermissionTemplate]:
    """Searches permissions templates"""
    log.debug("Searching all permission templates")
    objects_list = {}
    data = json.loads(endpoint.get(_SEARCH_API, params=params).text)
    for obj in data["permissionTemplates"]:
        o = PermissionTemplate(name=obj["name"], endpoint=endpoint, data=obj)
        objects_list[o.key] = o
    _load_default_templates(endpoint=endpoint, data=data)
    return objects_list


def search_by_name(endpoint: pf.Platform, name: str) -> PermissionTemplate:
    """Searches permissions templates by name"""
    return utilities.search_by_name(endpoint=endpoint, name=name, api=_SEARCH_API, returned_field="permissionTemplates")


def get_list(endpoint: pf.Platform) -> dict[str, PermissionTemplate]:
    """Gets the list of all permissions templates"""
    return search(endpoint=endpoint)


def _load_default_templates(endpoint: pf.Platform, data: types.ApiPayload = None) -> None:
    """Loads default templates"""
    if data is None:
        data = json.loads(endpoint.get(_SEARCH_API).text)
    for d in data["defaultTemplates"]:
        _DEFAULT_TEMPLATES[d["qualifier"]] = d["templateId"]


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
    """Exports permission templates as JSON"""
    log.info("Exporting permission templates")
    pt_list = get_list(endpoint)
    json_data = {}
    for pt in pt_list.values():
        json_data[pt.name] = pt.to_json(export_settings)
        if not export_settings.get("FULL_EXPORT"):
            for k in ("name", "id", "key"):
                json_data[pt.name].pop(k, None)
    return json_data


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr) -> None:
    """Imports sonar-conmfig JSON as permission templates"""
    if "permissionTemplates" not in config_data:
        log.info("No permissions templates in config, skipping import...")
        return
    log.info("Importing permission templates")
    get_list(endpoint)
    for name, data in config_data["permissionTemplates"].items():
        utilities.json_dump_debug(data, f"Importing: {name}:")
        o = create_or_update(endpoint=endpoint, name=name, data=data)
        defs = data.get("defaultFor", None)
        if defs is not None and defs != "":
            o.set_as_default(utilities.csv_to_list(data.get("defaultFor", None)))


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings) -> list[pb.Problem]:
    """Audits permission templates and returns list of detected problems"""
    log.info("--- Auditing permission templates ---")
    problems = []
    for pt in get_list(endpoint=endpoint).values():
        problems += pt.audit(audit_settings)
    return problems
