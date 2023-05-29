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


class GlobalPermissions(permissions.Permissions):
    API_GET = {"users": "permissions/users", "groups": "permissions/groups"}
    API_SET = {"users": "permissions/add_user", "groups": "permissions/add_group"}
    API_REMOVE = {"users": "permissions/remove_user", "groups": "permissions/remove_group"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def __str__(self):
        return "global permissions"

    def read(self):
        self.permissions = permissions.NO_PERMISSIONS
        for ptype in permissions.PERMISSION_TYPES:
            self.permissions[ptype] = self._get_api(
                GlobalPermissions.API_GET[ptype], ptype, GlobalPermissions.API_GET_FIELD[ptype], ps=permissions.MAX_PERMS
            )
        return self

    def set(self, new_perms):
        utilities.logger.debug("Setting %s to %s", str(self), str(new_perms))
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


def import_config(endpoint, config_data):
    my_permissions = config_data.get("permissions", {})
    if len(my_permissions) == 0:
        utilities.logger.info("No global permissions in config, skipping import...")
        return
    utilities.logger.info("Importing global permissions")
    global_perms = GlobalPermissions(endpoint)
    global_perms.set(my_permissions)


def edition_filter(perms, ed):
    for p in perms.copy():
        if ed == "community" and p in ("portfoliocreator", "applicationcreator") or ed == "developer" and p == "portfoliocreator":
            utilities.logger.warning("Can't remove permission '%s' on a %s edition", p, ed)
            perms.remove(p)
    return perms
