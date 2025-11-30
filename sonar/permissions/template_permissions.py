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
        read_perms = {}
        for p in permissions.PERMISSION_TYPES:
            read_perms[p] = self._get_api(
                TemplatePermissions.API_GET[p],
                p,
                TemplatePermissions.API_GET_FIELD[p],
                templateId=self.concerned_object.key,
                ps=permissions.MAX_PERMS,
            )
        self.permissions = permissions.dict_to_list(read_perms)
        # Hack: SonarQube returns application/portfoliocreator even for objects that don't have this permission
        # so these perms needs to be removed manually
        self.white_list(tuple(project_permissions.PROJECT_PERMISSIONS.keys()))
        return self

    def set(self, new_perms: list[types.PermissionDef]) -> TemplatePermissions:
        """Sets permissions of a permission template"""
        log.info("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        new_perms = new_perms or []
        # Remove all permissions of users or groups that are not in the new permissions
        for old_perm in self.permissions:
            ptype = "group" if "group" in old_perm else "user"
            is_in_new = any(new_perm.get(ptype, "") == old_perm[ptype] for new_perm in new_perms)
            if not is_in_new:
                self._post_api(
                    api=TemplatePermissions.API_REMOVE[ptype],
                    set_field=TemplatePermissions.API_SET_FIELD[ptype],
                    identifier=old_perm[ptype],
                    perms=old_perm["permissions"],
                )
        # Add or modify permissions of users or groups that are in the new permissions
        for new_perm in new_perms:
            ptype = "group" if "group" in new_perm else "user"
            current_perm: list[str] = next((p["permissions"] for p in self.permissions if p.get(ptype) == new_perm[ptype]), [])
            log.info("comparing current_perm: %s with new_perm: %s", str(current_perm), str(new_perm["permissions"]))
            to_remove = list(set(current_perm) - set(new_perm["permissions"]))
            to_add = list(set(new_perm["permissions"]) - set(current_perm))
            atype = f"{ptype}s"
            self._post_api(
                api=TemplatePermissions.API_SET[atype],
                set_field=TemplatePermissions.API_SET_FIELD[atype],
                identifier=new_perm[ptype],
                perms=to_add,
                templateId=self.concerned_object.key,
            )
            self._post_api(
                api=TemplatePermissions.API_REMOVE[atype],
                set_field=TemplatePermissions.API_SET_FIELD[atype],
                identifier=new_perm[ptype],
                perms=to_remove,
                templateId=self.concerned_object.key,
            )
        return self.read()
