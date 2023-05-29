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

from sonar import utilities
from sonar.permissions import permissions
from sonar.audit import rules, problem

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

    def __init__(self, concerned_object):
        self.concerned_object = concerned_object
        super().__init__(concerned_object.endpoint)

    def __str__(self):
        return f"permissions of {str(self.concerned_object)}"

    def read(self):
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
        return self

    def _set_perms(self, new_perms, apis, field, diff_func, **kwargs):
        utilities.logger.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in permissions.PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            to_remove = diff_func(self.permissions[p], new_perms[p])
            self._post_api(apis["remove"][p], field[p], to_remove, **kwargs)
            to_add = diff_func(new_perms[p], self.permissions[p])
            self._post_api(apis["add"][p], field[p], to_add, **kwargs)
        return self.read()

    def set(self, new_perms):
        """Sets permissions of a project

        :param new_perms:
        :type new_perms: dict {"users": {<user>: [<perm>, ...], <user>: [], ...}, "groups": {<group>: [<perm>, ...], <group>:[], ...}}
        :return: Permissions associated to the aggregation
        :rtype: self
        """
        return self._set_perms(
            new_perms, ProjectPermissions.APIS, ProjectPermissions.API_SET_FIELD, permissions.diff, projectKey=self.concerned_object.key
        )

    def audit(self, audit_settings):
        if not audit_settings["audit.projects.permissions"]:
            utilities.logger.debug("Auditing project permissions is disabled by configuration, skipping")
            return []
        utilities.logger.debug("Auditing %s", str(self))
        return self.__audit_user_permissions(audit_settings) + self.__audit_group_permissions(audit_settings)

    def __audit_user_permissions(self, audit_settings):
        problems = []
        user_count = self.count("users")
        max_users = audit_settings["audit.projects.permissions.maxUsers"]
        if user_count > max_users:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_USERS)
            msg = rule.msg.format(str(self.concerned_object), user_count)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_admins = audit_settings["audit.projects.permissions.maxAdminUsers"]
        admin_count = self.count("users", ("admin"))
        if admin_count > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_USERS)
            msg = rule.msg.format(str(self.concerned_object), admin_count, max_admins)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))

        return problems

    def __audit_group_permissions(self, audit_settings):
        problems = []
        groups = self.read().to_json(perm_type="groups")
        for gr_name, gr_perms in groups.items():
            if gr_name == "Anyone":
                rule = rules.get_rule(rules.RuleId.PROJ_PERM_ANYONE)
                problems.append(problem.Problem(rule.type, rule.severity, rule.msg.format(str(self.concerned_object)), concerned_object=self))
            if gr_name == "sonar-users" and (
                "issueadmin" in gr_perms or "scan" in gr_perms or "securityhotspotadmin" in gr_perms or "admin" in gr_perms
            ):
                rule = rules.get_rule(rules.RuleId.PROJ_PERM_SONAR_USERS_ELEVATED_PERMS)
                problems.append(
                    problem.Problem(rule.type, rule.severity, rule.msg.format(str(self.concerned_object)), concerned_object=self.concerned_object)
                )

        max_perms = audit_settings["audit.projects.permissions.maxGroups"]
        counter = self.count(perm_type="groups", perm_filter=permissions.PROJECT_PERMISSIONS)
        if counter > max_perms:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_GROUPS)
            msg = rule.msg.format(str(self.concerned_object), counter, max_perms)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_scan = audit_settings["audit.projects.permissions.maxScanGroups"]
        counter = self.count(perm_type="groups", perm_filter=("scan"))
        if counter > max_scan:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_SCAN_GROUPS)
            msg = rule.msg.format(str(self.concerned_object), counter, max_scan)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_issue_adm = audit_settings["audit.projects.permissions.maxIssueAdminGroups"]
        counter = self.count(perm_type="groups", perm_filter=("issueadmin"))
        if counter > max_issue_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ISSUE_ADM_GROUPS)
            msg = rule.msg.format(str(self.concerned_object), counter, max_issue_adm)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_spots_adm = audit_settings["audit.projects.permissions.maxHotspotAdminGroups"]
        counter = self.count(perm_type="groups", perm_filter=("securityhotspotadmin"))
        if counter > max_spots_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS)
            msg = rule.msg.format(str(self.concerned_object), counter, max_spots_adm)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_admins = audit_settings["audit.projects.permissions.maxAdminGroups"]
        counter = self.count(perm_type="groups", perm_filter=("admin"))
        if counter > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_GROUPS)
            msg = rule.msg.format(str(self.concerned_object), counter, max_admins)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))
        return problems
