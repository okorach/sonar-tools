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

from sonar import utilities
from sonar.permissions import permissions, quality_permissions


class QualityProfilePermissions(quality_permissions.QualityPermissions):

    APIS = {
        "get": {"users": "qualityprofiles/search_users", "groups": "qualityprofiles/search_groups"},
        "add": {"users": "qualityprofiles/add_user", "groups": "qualityprofiles/add_group"},
        "remove": {"users": "qualityprofiles/remove_user", "groups": "qualityprofiles/remove_group"},
    }
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "group"}

    def read(self):
        if self.endpoint.version() < (9, 2, 0):
            utilities.logger.debug("Can't read %s on SonarQube < 9.2", str(self))
            return self
        self._read_perms(
            QualityProfilePermissions.APIS,
            QualityProfilePermissions.API_GET_FIELD,
            qualityProfile=self.concerned_object.name,
            language=self.concerned_object.language,
        )
        return self

    def set(self, new_perms):
        if self.endpoint.version() < (6, 6, 0):
            utilities.logger.debug("Can set %s on SonarQube < 6.6", str(self))
            return self
        return self._set_perms(
            new_perms,
            QualityProfilePermissions.APIS,
            QualityProfilePermissions.API_SET_FIELD,
            permissions.diffarray,
            qualityProfile=self.concerned_object.name,
            language=self.concerned_object.language,
        )
