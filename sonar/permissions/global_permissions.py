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


class GlobalPermissions(permissions.Permissions):
    """Abstraction of SonarQube global permissions"""

    API_GET = {"users": "permissions/users", "groups": "permissions/groups"}
    API_SET = {"users": "permissions/add_user", "groups": "permissions/add_group"}
    API_REMOVE = {"users": "permissions/remove_user", "groups": "permissions/remove_group"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def __init__(self, concerned_object: object) -> None:
        self.concerned_object = concerned_object
        self.endpoint = concerned_object
        self.permissions = None
        self.read()

    def __str__(self) -> str:
        return "global permissions"

    def read(self) -> GlobalPermissions:
        """Reads global permissions"""
        self.permissions = permissions.NO_PERMISSIONS
        for ptype in permissions.PERMISSION_TYPES:
            self.permissions[ptype] = self._get_api(
                GlobalPermissions.API_GET[ptype], ptype, GlobalPermissions.API_GET_FIELD[ptype], ps=permissions.MAX_PERMS
            )
        return self

    def set(self, new_perms: types.JsonPermissions) -> GlobalPermissions:
        log.debug("Setting %s to %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        ed = self.endpoint.edition()
        for perm_type in permissions.PERMISSION_TYPES:
            if new_perms is None or perm_type not in new_perms:
                continue
            decoded_perms = {k: permissions.decode(v) for k, v in new_perms[perm_type].items()}
            to_remove = edition_filter(permissions.diff(self.permissions[perm_type], decoded_perms), ed)
            self._post_api(GlobalPermissions.API_REMOVE[perm_type], GlobalPermissions.API_SET_FIELD[perm_type], to_remove)
            to_add = edition_filter(permissions.diff(decoded_perms, self.permissions[perm_type]), ed)
            self._post_api(GlobalPermissions.API_SET[perm_type], GlobalPermissions.API_SET_FIELD[perm_type], to_add)
        return self.read()


def import_config(endpoint: object, config_data: types.ObjectJsonRepr) -> None:
    """Imports global permissions in a SonarQube platform"""
    my_permissions = config_data.get("permissions", {})
    if len(my_permissions) == 0:
        log.info("No global permissions in config, skipping import...")
        return
    log.info("Importing global permissions")
    global_perms = GlobalPermissions(endpoint)
    global_perms.set(my_permissions)


def edition_filter(perms: types.JsonPermissions, ed: str) -> types.JsonPermissions:
    """Filters permissions available in a given edition"""
    for p in perms.copy():
        if ed == "community" and p in ("portfoliocreator", "applicationcreator") or ed == "developer" and p == "portfoliocreator":
            log.warning("Can't manage permission '%s' on a %s edition", p, ed)
            perms.remove(p)
    return perms
