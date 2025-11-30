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

"""Abstraction of SonarQube global permissions"""

from __future__ import annotations

import sonar.logging as log
from sonar.permissions import permissions
from sonar.util import types
import sonar.util.constants as c


class GlobalPermissions(permissions.Permissions):
    """Abstraction of SonarQube global permissions"""

    API_GET = {"users": "permissions/users", "groups": "permissions/groups"}
    API_SET = {"users": "permissions/add_user", "groups": "permissions/add_group"}
    API_REMOVE = {"users": "permissions/remove_user", "groups": "permissions/remove_group"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def __init__(self, concerned_object: object) -> None:
        super().__init__(concerned_object)
        self.endpoint = concerned_object
        self.read()

    def __str__(self) -> str:
        return "global permissions"

    def read(self) -> GlobalPermissions:
        """Reads global permissions"""
        read_perms = {}
        for ptype in permissions.PERMISSION_TYPES:
            read_perms[ptype] = self._get_api(
                GlobalPermissions.API_GET[ptype], ptype, GlobalPermissions.API_GET_FIELD[ptype], ps=permissions.MAX_PERMS
            )
        self.permissions = permissions.dict_to_list(read_perms)
        return self

    def set(self, new_perms: list[types.PermissionDef]) -> GlobalPermissions:
        log.debug("Setting %s to %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        ed = self.endpoint.edition()
        # Remove all permissions of users or groups that are not in the new permissions
        for old_perm in self.permissions:
            ptype = "group" if "group" in old_perm else "user"
            atype = f"{ptype}s"
            is_in_new = any(new_perm.get(ptype, "") == old_perm[ptype] for new_perm in new_perms)
            if not is_in_new:
                self._post_api(
                    api=GlobalPermissions.API_REMOVE[atype],
                    set_field=GlobalPermissions.API_SET_FIELD[atype],
                    identifier=old_perm[ptype],
                    perms=old_perm["permissions"],
                )
        # Add or modify permissions of users or groups that are in the new permissions
        for new_perm in new_perms:
            ptype = "group" if "group" in new_perm else "user"
            atype = f"{ptype}s"
            current_perm: list[str] = next((p["permissions"] for p in self.permissions if p.get(ptype) == new_perm[ptype]), [])
            to_remove = edition_filter(list(set(current_perm) - set(new_perm["permissions"])), ed)
            to_add = edition_filter(list(set(new_perm["permissions"]) - set(current_perm)), ed)
            self._post_api(
                api=GlobalPermissions.API_SET[atype], set_field=GlobalPermissions.API_SET_FIELD[atype], identifier=new_perm[ptype], perms=to_add
            )
            self._post_api(
                api=GlobalPermissions.API_REMOVE[atype], set_field=GlobalPermissions.API_SET_FIELD[atype], identifier=new_perm[ptype], perms=to_remove
            )
        return self.read()


def import_config(endpoint: object, config_data: types.ObjectJsonRepr) -> int:
    """Imports global permissions in a SonarQube platform
    :return: number of global permissions imported
    """
    my_permissions = config_data.get("permissions", [])
    if len(my_permissions) == 0:
        log.info("No global permissions in config, skipping import...")
        return 0
    log.info("Importing global permissions")
    global_perms = GlobalPermissions(endpoint)
    global_perms.set(my_permissions)
    return len(my_permissions)


def edition_filter(perms: list[str], ed: str) -> list[str]:
    """Filters permissions available in a given edition"""
    for p in perms.copy():
        if ed == c.CE and p in ("portfoliocreator", "applicationcreator") or ed == c.DE and p == "portfoliocreator":
            log.warning("Can't manage permission '%s' on a %s edition", p, ed)
            perms.remove(p)
    return perms
