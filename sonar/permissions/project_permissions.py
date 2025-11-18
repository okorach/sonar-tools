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

"""Projects permissions class"""

from __future__ import annotations
from typing import Callable
import sonar.logging as log
from sonar.util import types
from sonar.permissions import permissions
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
import sonar.utilities as util

PROJECT_PERMISSIONS = {
    "user": "Browse",
    "codeviewer": "See source code",
    "issueadmin": "Administer Issues",
    "securityhotspotadmin": "Create Projects",
    "scan": "Execute Analysis",
    "admin": "Administer Project",
}


class ProjectPermissions(permissions.Permissions):
    APIS = {
        "get": {"users": "permissions/users", "groups": "permissions/groups"},
        "add": {"users": "permissions/add_user", "groups": "permissions/add_group"},
        "remove": {"users": "permissions/remove_user", "groups": "permissions/remove_group"},
    }
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def read(self) -> ProjectPermissions:
        """Reads permissions in SonarQube"""
        self.permissions = permissions.NO_PERMISSIONS.copy()
        perms = {}
        for p in permissions.PERMISSION_TYPES:
            perms[p] = self._get_api(
                ProjectPermissions.APIS["get"][p],
                p,
                ProjectPermissions.API_GET_FIELD[p],
                projectKey=self.concerned_object.key,
                ps=permissions.MAX_PERMS,
            )
        self.permissions = permissions.dict_to_list(perms)
        # Hack: SonarQube returns application/portfoliocreator even for objects that don't have this permission
        # so these perms needs to be removed manually
        self.white_list(tuple(PROJECT_PERMISSIONS.keys()))
        self.permissions = [p for p in self.permissions if len(p["permissions"]) > 0]
        return self

    def _set_perms(
        self, new_perms: list[types.PermissionDef], apis: dict[str, dict[str, str]], field: dict[str, str], diff_func: Callable, **kwargs
    ) -> ProjectPermissions:
        log.info("Setting %s with %s", self, util.json_dump(new_perms))
        if self.permissions is None:
            self.read()
        # Remove all permissions of users or groups that are not in the new permissions
        for old_perm in self.permissions:
            ptype = "group" if "group" in old_perm else "user"
            atype = f"{ptype}s"
            is_in_new = any(new_perm.get(ptype, "") == old_perm[ptype] for new_perm in new_perms)
            if not is_in_new:
                self._post_api(apis["remove"][atype], field[atype], old_perm[ptype], old_perm["permissions"], **kwargs)
        # Add or modify permissions of users or groups that are in the new permissions
        for new_perm in new_perms:
            ptype = "group" if "group" in new_perm else "user"
            atype = f"{ptype}s"
            current_perm: list[str] = next((p["permissions"] for p in self.permissions if p.get(ptype) == new_perm[ptype]), [])
            to_remove = util.difference(current_perm, new_perm["permissions"])
            to_add = util.difference(new_perm["permissions"], current_perm)
            if ptype == "user" and new_perm[ptype] == "admin" and "admin" in to_remove:
                # Don't remove admin permission to the admin user, this is not possible anyway
                to_remove.remove("admin")
            self._post_api(apis["remove"][atype], field[atype], new_perm[ptype], to_remove, **kwargs)
            self._post_api(apis["add"][atype], field[atype], new_perm[ptype], to_add, **kwargs)
        return self.read()

    def set(self, new_perms: list[types.PermissionDef]) -> ProjectPermissions:
        """Sets permissions of a project

        :param JsonPermissions new_perms: New permissions to apply
        :return: Permissions associated to the project
        :rtype: ProjectPermissions
        """
        return self._set_perms(
            new_perms, ProjectPermissions.APIS, ProjectPermissions.API_SET_FIELD, permissions.diff, projectKey=self.concerned_object.key
        )

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project permissions"""
        if not audit_settings.get("audit.projects.permissions", True):
            log.debug("Auditing project permissions is disabled by configuration, skipping")
            return []
        log.debug("Auditing %s", str(self))
        return super().audit(audit_settings) + self.__audit_group_permissions(audit_settings)

    def __audit_group_permissions(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project group permissions"""
        problems = []
        max_scan = audit_settings.get("audit.projects.permissions.maxScanGroups", 1)
        counter = self.count(perm_type="groups", perm_filter=["scan"])
        if counter > max_scan:
            rule = get_rule(RuleId.PROJ_PERM_MAX_SCAN_GROUPS)
            problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), counter, max_scan))

        max_issue_adm = audit_settings.get("audit.projects.permissions.maxIssueAdminGroups", 2)
        counter = self.count(perm_type="groups", perm_filter=["issueadmin"])
        if counter > max_issue_adm:
            rule = get_rule(RuleId.PROJ_PERM_MAX_ISSUE_ADM_GROUPS)
            problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), counter, max_issue_adm))

        max_spots_adm = audit_settings.get("audit.projects.permissions.maxHotspotAdminGroups", 2)
        counter = self.count(perm_type="groups", perm_filter=["securityhotspotadmin"])
        if counter > max_spots_adm:
            rule = get_rule(RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS)
            problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), counter, max_spots_adm))
        return problems
