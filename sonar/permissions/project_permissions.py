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
        for p in permissions.PERMISSION_TYPES:
            self.permissions[p] = self._get_api(
                ProjectPermissions.APIS["get"][p],
                p,
                ProjectPermissions.API_GET_FIELD[p],
                projectKey=self.concerned_object.key,
                ps=permissions.MAX_PERMS,
            )
        # Hack: SonarQube returns application/portfoliocreator even for objects that don't have this permission
        # so these perms needs to be removed manually
        self.white_list(tuple(PROJECT_PERMISSIONS.keys()))
        self.permissions = {p: k for p, k in self.permissions.items() if k and len(k) > 0}
        return self

    def _set_perms(
        self, new_perms: types.JsonPermissions, apis: dict[str, dict[str, str]], field: dict[str, str], diff_func: Callable, **kwargs
    ) -> ProjectPermissions:
        log.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in permissions.PERMISSION_TYPES:
            to_remove = diff_func(self.permissions.get(p, {}), new_perms.get(p, {}))
            self._post_api(apis["remove"][p], field[p], to_remove, **kwargs)
            to_add = diff_func(new_perms.get(p, {}), self.permissions.get(p, {}))
            self._post_api(apis["add"][p], field[p], to_add, **kwargs)
        return self.read()

    def set(self, new_perms: types.JsonPermissions) -> ProjectPermissions:
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
        return super().audit(audit_settings) + self.__audit_user_permissions(audit_settings) + self.__audit_group_permissions(audit_settings)

    def __audit_user_permissions(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project user permissions"""
        problems = []
        user_count = self.count("users")
        max_users = audit_settings.get("audit.projects.permissions.maxUsers", 5)
        if user_count > max_users:
            problems.append(Problem(get_rule(RuleId.PROJ_PERM_MAX_USERS), self, str(self.concerned_object), user_count))

        max_admins = audit_settings.get("audit.projects.permissions.maxAdminUsers", 2)
        admin_count = self.count("users", ("admin",))
        if admin_count > max_admins:
            rule = get_rule(RuleId.PROJ_PERM_MAX_ADM_USERS)
            problems.append(Problem(rule, self, str(self.concerned_object), admin_count, max_admins))

        return problems

    def __audit_group_permissions(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project group permissions"""
        problems = []
        groups = self.read().to_json(perm_type="groups")
        for gr_name, gr_perms in groups.items():
            if gr_name == "Anyone":
                problems.append(Problem(get_rule(RuleId.PROJ_PERM_ANYONE), self, str(self.concerned_object)))
            if gr_name == "sonar-users" and (
                "issueadmin" in gr_perms or "scan" in gr_perms or "securityhotspotadmin" in gr_perms or "admin" in gr_perms
            ):
                rule = get_rule(RuleId.PROJ_PERM_SONAR_USERS_ELEVATED_PERMS)
                problems.append(Problem(rule, self.concerned_object, str(self.concerned_object)))

        max_perms = audit_settings.get("audit.projects.permissions.maxGroups", 5)
        counter = self.count(perm_type="groups", perm_filter=permissions.PROJECT_PERMISSIONS)
        if counter > max_perms:
            rule = get_rule(RuleId.PROJ_PERM_MAX_GROUPS)
            problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), counter, max_perms))

        max_scan = audit_settings.get("audit.projects.permissions.maxScanGroups", 1)
        counter = self.count(perm_type="groups", perm_filter=("scan",))
        if counter > max_scan:
            rule = get_rule(RuleId.PROJ_PERM_MAX_SCAN_GROUPS)
            problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), counter, max_scan))

        max_issue_adm = audit_settings.get("audit.projects.permissions.maxIssueAdminGroups", 2)
        counter = self.count(perm_type="groups", perm_filter=("issueadmin",))
        if counter > max_issue_adm:
            rule = get_rule(RuleId.PROJ_PERM_MAX_ISSUE_ADM_GROUPS)
            problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), counter, max_issue_adm))

        max_spots_adm = audit_settings.get("audit.projects.permissions.maxHotspotAdminGroups", 2)
        counter = self.count(perm_type="groups", perm_filter=("securityhotspotadmin",))
        if counter > max_spots_adm:
            rule = get_rule(RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS)
            problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), counter, max_spots_adm))

        max_admins = audit_settings.get("audit.projects.permissions.maxAdminGroups", 2)
        counter = self.count(perm_type="groups", perm_filter=("admin",))
        if counter > max_admins:
            rule = get_rule(RuleId.PROJ_PERM_MAX_ADM_GROUPS)
            problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), counter, max_admins))
        return problems
