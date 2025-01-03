#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

"""Quality gates permissions class"""

from __future__ import annotations

import sonar.logging as log
from sonar import exceptions
from sonar.permissions import permissions, quality_permissions


class QualityGatePermissions(quality_permissions.QualityPermissions):
    """
    Abstraction of quality gates permissions
    """

    APIS = {
        "get": {"users": "qualitygates/search_users", "groups": "qualitygates/search_groups"},
        "add": {"users": "qualitygates/add_user", "groups": "qualitygates/add_group"},
        "remove": {"users": "qualitygates/remove_user", "groups": "qualitygates/remove_group"},
    }
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def read(self) -> QualityGatePermissions:
        if not self.endpoint.is_sonarcloud() and self.endpoint.version() < (9, 2, 0):
            log.debug("Can't read %s on SonarQube < 9.2", str(self))
            return self
        self._read_perms(QualityGatePermissions.APIS, QualityGatePermissions.API_GET_FIELD, gateName=self.concerned_object.name)
        return self

    def set(self, new_perms: dict[str, any]) -> QualityGatePermissions:
        """Sets permissions of a quality gate"""
        if not self.endpoint.is_sonarcloud() and self.endpoint.version() < (9, 2, 0):
            raise exceptions.UnsupportedOperation(f"Can't set {str(self)} on SonarQube < 9.2")

        return self._set_perms(
            new_perms, QualityGatePermissions.APIS, QualityGatePermissions.API_SET_FIELD, permissions.diffarray, gateName=self.concerned_object.name
        )
