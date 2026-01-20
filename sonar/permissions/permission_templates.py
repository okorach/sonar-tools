#
# sonar-tools
# Copyright (C) 2022-2026 Olivier Korach
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
from typing import Optional, Any, TYPE_CHECKING

import json
import re

import sonar.logging as log
from sonar.util import cache
from sonar.util import platform_helper as phelp
from sonar import sqobject, exceptions
from sonar.permissions import template_permissions
from sonar.audit.rules import get_rule, RuleId
import sonar.audit.problem as pb
import sonar.util.constants as c
import sonar.util.misc as util
import sonar.utilities as sutil
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ConfigSettings, ObjectJsonRepr, PermissionDef

_MAP = {}
_DEFAULT_TEMPLATES = {}
_QUALIFIER_REVERSE_MAP = {"projects": "TRK", "applications": "APP", "portfolios": "VW"}
_CREATE_API = "permissions/create_template"
_UPDATE_API = "permissions/update_template"


class PermissionTemplate(sqobject.SqObject):
    """Abstraction of the Sonar permission template concept"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Constructor"""
        super().__init__(endpoint, data)
        self.key = data.get("id")
        self.name: str = data.get("name")
        self.description: Optional[str] = None
        self.project_key_pattern: Optional[str] = None
        self._permissions: Optional[template_permissions.TemplatePermissions] = None
        self.description = data.get("description")
        self.last_update = data.get("lastUpdate")
        self.project_key_pattern = data.get("projectKeyPattern", "")
        self.creation_date = sutil.string_to_datetime(data.get("createdAt"))
        self.__class__.CACHE.put(self)

    def __str__(self) -> str:
        """Returns the string representation of the object"""
        return f"permission template '{self.name}'"

    def hash_object(self) -> tuple[Any, ...]:
        """Returns the hash elements for a given object"""
        return (self.name.lower(),)

    @staticmethod
    def hash_payload(data: ApiPayload) -> tuple[Any, ...]:
        """Returns the hash items for a given object search payload"""
        return (data["name"].lower(),)

    @classmethod
    def search(cls, endpoint: Platform, use_cache: bool = False) -> dict[str, PermissionTemplate]:
        """Searches permissions templates"""
        if use_cache and len(cls.CACHE.from_platform(endpoint)) > 0:
            log.debug("Searching permission templates from cache")
            return cls.CACHE.from_platform(endpoint)
        log.info("Searching permission templates")
        api, _, params, ret = endpoint.api.get_details(cls, Oper.SEARCH)
        dataset = json.loads(endpoint.get(api, params=params).text)
        objects_list = {}
        for data in dataset[ret]:
            o = cls(endpoint, data)
            objects_list[o.key] = o
        # Record which template is the default for each type of Qualifier (Project, App, Portfolio)
        # FIXME: This only supports 1 platform, this should be per connected platform
        for data in dataset["defaultTemplates"]:
            _DEFAULT_TEMPLATES[data["qualifier"]] = data.get("templateId", data.get("id"))
        return objects_list

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

    def set_permissions(self, perms: list[PermissionDef]) -> template_permissions.TemplatePermissions:
        """Sets the permissions of a permission template"""
        log.debug("Setting %s permissions with %s", str(self), str(perms))
        return self.permissions().set(perms)

    def update(self, **pt_data) -> PermissionTemplate:
        """Updates a permission template"""
        log.debug("Updating %s with %s", str(self), str(pt_data))
        params = {"id": self.key}
        # Hack: On SQ 8.9 if you pass all params otherwise SQ does NPE

        for k, v in {"name": "name", "description": "description", "pattern": "projectKeyPattern"}.items():
            if k in pt_data:
                params[v] = pt_data[k]

        log.debug("Updating %s with params %s", str(self), str(params))
        self.post(_UPDATE_API, params=params)
        if "name" in pt_data and pt_data["name"] != self.name:
            # FIXME: This supports only 1 platform at at time
            _MAP.pop(self.name, None)
            self.name = params["name"]
            _MAP[self.name] = self.key
        self.description = params.get("description", self.description)
        self.project_key_pattern = params.get("projectKeyPattern", self.project_key_pattern)
        self.set_permissions(pt_data.get("permissions"))
        return self

    def permissions(self) -> template_permissions.TemplatePermissions:
        """Returns the permissions of a template"""
        if self._permissions is None:
            self._permissions = template_permissions.TemplatePermissions(self)
        return self._permissions

    def set_as_default(self, what_list: list[str]) -> bool:
        """Sets a permission template as default for projects or apps or portfolios"""
        log.debug("Setting %s as default for %s", str(self), str(what_list))
        ed = self.endpoint.edition()
        for d in what_list:
            qual = _QUALIFIER_REVERSE_MAP.get(d, d)
            if (ed == c.CE and qual in ("VW", "APP")) or (ed == c.DE and qual == "VW"):
                log.warning("Can't set permission template as default for %s on a %s edition", qual, ed)
                continue
            try:
                return self.post("permissions/set_default_template", params={"templateId": self.key, "qualifier": qual}).ok
            except exceptions.SonarException:
                return False
        return False

    def set_pattern(self, pattern: str) -> PermissionTemplate:
        """Sets a permission template pattern"""
        if pattern is None:
            return self
        return self.update(pattern=pattern)

    def to_json(self, export_settings: ConfigSettings = None) -> ObjectJsonRepr:
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
            json_data["defaultFor"] = util.list_to_csv(defaults, ", ")
        if not self.project_key_pattern or self.project_key_pattern == "":
            json_data.pop("pattern")
        json_data["creationDate"] = sutil.date_to_string(self.creation_date)
        json_data["lastUpdate"] = sutil.date_to_string(self.last_update)
        return phelp.convert_template_json(json_data, export_settings.get("FULL_EXPORT", False))

    def _audit_pattern(self, audit_settings: ConfigSettings) -> list[pb.Problem]:
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

    def audit(self, audit_settings: ConfigSettings) -> list[pb.Problem]:
        log.debug("Auditing %s", str(self))
        return self._audit_pattern(audit_settings) + self.permissions().audit(audit_settings)

    @classmethod
    def get_object(cls, endpoint: Platform, name: str) -> PermissionTemplate:
        """Returns Perm Template object corresponding to name"""
        if len(cls.CACHE.from_platform(endpoint)) == 0:
            cls.search(endpoint)
        return cls.CACHE.get(endpoint.local_url, name.lower())

    @classmethod
    def create(cls, endpoint: Platform, name: str) -> PermissionTemplate:
        """Creates a permission template from sonar-config data"""
        endpoint.post(_CREATE_API, params={"name": name})
        return cls.get_object(endpoint, name)


def create_or_update(endpoint: Platform, name: str, data: ObjectJsonRepr) -> PermissionTemplate:
    """Creates or update a permission template with sonar-config JSON data"""
    log.debug("Create or update permission template '%s'", name)
    o = PermissionTemplate.get_object(endpoint, name)
    if o is None:
        log.debug("Permission template '%s' does not exist, creating...", name)
        o = PermissionTemplate.create(endpoint, name=name)
    return o.update(name=name, **data)


def search_by_name(endpoint: Platform, name: str) -> ApiPayload:
    """Searches permissions templates by name"""
    api, _, _, ret = endpoint.api.get_details(PermissionTemplate, Oper.SEARCH)
    return sutil.search_by_name(endpoint=endpoint, name=name, api=api, returned_field=ret)


def export(endpoint: Platform, export_settings: ConfigSettings) -> ObjectJsonRepr:
    """Exports permission templates as JSON"""
    log.info("Exporting permission templates")
    json_data = {}
    for pt in PermissionTemplate.search(endpoint).values():
        json_data[pt.name] = pt.to_json(export_settings)
        if not export_settings.get("FULL_EXPORT"):
            for k in ("name", "id", "key"):
                json_data[pt.name].pop(k, None)
    return json_data


def import_config(endpoint: Platform, config_data: ObjectJsonRepr) -> int:
    """Imports sonar-conmfig JSON as permission templates
    :return: Number of permission templates imported sucessfully
    """
    if not (config_data := config_data.get("permissionTemplates", None)):
        log.info("No permissions templates in config, skipping import...")
        return 0
    log.info("Importing permission templates")
    PermissionTemplate.search(endpoint)
    count = 0
    config_data = util.list_to_dict(config_data, "key")
    for name, data in config_data.items():
        log.debug("Importing: %s: %s", name, util.json_dump(data))
        o = create_or_update(endpoint=endpoint, name=name, data=data)
        count += 1
        defs = data.get("defaultFor", None)
        if defs is not None and defs != "":
            o.set_as_default(util.csv_to_list(data.get("defaultFor", None)))
    return count


def audit(endpoint: Platform, audit_settings: ConfigSettings) -> list[pb.Problem]:
    """Audits permission templates and returns list of detected problems"""
    log.info("--- Auditing permission templates ---")
    problems = []
    for pt in PermissionTemplate.search(endpoint).values():
        problems += pt.audit(audit_settings)
    return problems
