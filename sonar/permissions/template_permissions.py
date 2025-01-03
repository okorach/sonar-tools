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

"""Permissions templates permissions class"""

from __future__ import annotations
import sonar.logging as log
from sonar.util import types
from sonar.permissions import permissions, project_permissions


class TemplatePermissions(project_permissions.ProjectPermissions):
    """
    Abstraction of the permission templates permissions
    """

    API_GET = {"users": "permissions/template_users", "groups": "permissions/template_groups"}
    API_SET = {"users": "permissions/add_user_to_template", "groups": "permissions/add_group_to_template"}
    API_REMOVE = {"users": "permissions/remove_user_from_template", "groups": "permissions/remove_group_from_template"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def read(self) -> TemplatePermissions:
        """Reads permissions of a permission template"""
        self.permissions = permissions.NO_PERMISSIONS
        for p in permissions.PERMISSION_TYPES:
            self.permissions[p] = self._get_api(
                TemplatePermissions.API_GET[p],
                p,
                TemplatePermissions.API_GET_FIELD[p],
                templateId=self.concerned_object.key,
                ps=permissions.MAX_PERMS,
            )
        # Hack: SonarQube returns application/portfoliocreator even for objects that don't have this permission
        # so these perms needs to be removed manually
        self.white_list(tuple(project_permissions.PROJECT_PERMISSIONS.keys()))
        return self

    def set(self, new_perms: types.JsonPermissions) -> TemplatePermissions:
        """Sets permissions of a permission template"""
        log.info("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in permissions.PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = {k: permissions.decode(v) for k, v in new_perms[p].items()}
            to_remove = permissions.diff(self.permissions[p], decoded_perms)
            self._post_api(TemplatePermissions.API_REMOVE[p], TemplatePermissions.API_SET_FIELD[p], to_remove, templateId=self.concerned_object.key)
            to_add = permissions.diff(decoded_perms, self.permissions[p])
            self._post_api(TemplatePermissions.API_SET[p], TemplatePermissions.API_SET_FIELD[p], to_add, templateId=self.concerned_object.key)
        return self.read()
