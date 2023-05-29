#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

from sonar import utilities, exceptions
from sonar.permissions import permissions, quality_permissions


class QualityGatePermissions(quality_permissions.QualityPermissions):
    APIS = {
        "get": {"users": "qualitygates/search_users", "groups": "qualitygates/search_groups"},
        "add": {"users": "qualitygates/add_user", "groups": "qualitygates/add_group"},
        "remove": {"users": "qualitygates/remove_user", "groups": "qualitygates/remove_group"},
    }
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def __str__(self):
        return f"permissions of {str(self.concerned_object)}"

    def read(self):
        if self.endpoint.version() < (9, 2, 0):
            utilities.logger.debug("Can't read %s on SonarQube < 9.2", str(self))
            return self
        self._read_perms(QualityGatePermissions.APIS, QualityGatePermissions.API_GET_FIELD, gateName=self.concerned_object.name)
        return self

    def set(self, new_perms):
        if self.endpoint.version() < (9, 2, 0):
            raise exceptions.UnsupportedOperation(f"Can't set {str(self)} on SonarQube < 9.2")

        return self._set_perms(
            new_perms, QualityGatePermissions.APIS, QualityGatePermissions.API_SET_FIELD, permissions.diffarray, gateName=self.concerned_object.name
        )
