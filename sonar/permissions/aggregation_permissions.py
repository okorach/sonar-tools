#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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

from sonar.permissions import permissions, project_permissions

AGGREGATION_PERMISSIONS = {
    "user": "Browse",
    "admin": "Administer Project",
}


class AggregationPermissions(project_permissions.ProjectPermissions):
    def read(self):
        super().read()
        # Hack: SonarQube return permissions for aggregations that do not exist
        self.white_list(AGGREGATION_PERMISSIONS)
        return self

    def set(self, new_perms):
        return super().set(permissions.white_list(new_perms, AGGREGATION_PERMISSIONS))
