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

"""Abstraction of aggregations (portfolios or apps) permissions"""

from __future__ import annotations
from sonar.util import types
from sonar.permissions import permissions, project_permissions

AGGREGATION_PERMISSIONS = {
    "user": "Browse",
    "admin": "Administer Project",
}


class AggregationPermissions(project_permissions.ProjectPermissions):
    """
    Abstraction of aggregations (Portfolios and Applications) permissions
    """

    def read(self) -> AggregationPermissions:
        """Reads permissions of an aggregation (Portfolio or Application) in SonarQube"""
        super().read()
        # Hack: SonarQube return permissions for aggregations that do not exist
        self.white_list(AGGREGATION_PERMISSIONS)
        return self

    def set(self, new_perms: types.JsonPermissions) -> AggregationPermissions:
        """Sets permissions of an aggregation

        :param JsonPermissions new_perms:
        :return: Permissions associated to the aggregation
        :rtype: self
        """
        return super().set(permissions.white_list(new_perms, AGGREGATION_PERMISSIONS))
