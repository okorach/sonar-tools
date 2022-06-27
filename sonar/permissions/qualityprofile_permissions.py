#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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

import json
from http import HTTPStatus
from sonar import utilities, options
from sonar.permissions import permissions, quality_permissions


class QualityProfilePermissions(quality_permissions.QualityPermissions):

    API_GET = {"users": "qualityprofiles/search_users", "groups": "qualityprofiles/search_groups"}
    API_SET = {"users": "qualityprofiles/add_user", "groups": "qualityprofiles/add_group"}
    API_REMOVE = {"users": "qualityprofiles/remove_user", "groups": "qualityprofiles/remove_group"}
    API_GET_ID = "qualityProfile"
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "group"}

    def read(self, perm_type=None):
        self.permissions = {p: [] for p in permissions.PERMISSION_TYPES}
        if self.concerned_object.is_built_in:
            utilities.logger.debug("Won't read %s since it is built-in", str(self))
            return self
        if self.endpoint.version() < (6, 6, 0):
            utilities.logger.debug("Won't read %s on SonarQube < 6.6", str(self))
            return self
        for p in permissions.normalize(perm_type):
            self.permissions[p] = self._get_api(
                QualityProfilePermissions.API_GET[p],
                p,
                QualityProfilePermissions.API_GET_FIELD[p],
                qualityProfile=self.concerned_object.name,
                language=self.concerned_object.language,
            )
        return self

    def set(self, new_perms):
        if self.concerned_object.is_built_in:
            utilities.logger.debug("Can set %s because it's built-in", str(self))
            return self
        if self.endpoint.version() < (6, 6, 0):
            utilities.logger.debug("Can set %s on SonarQube < 6.6", str(self))
            return self
        utilities.logger.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in permissions.PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = permissions.decode(new_perms[p])
            to_remove = permissions.diffarray(self.permissions[p], decoded_perms)
            self._post_api(
                QualityProfilePermissions.API_REMOVE[p],
                QualityProfilePermissions.API_SET_FIELD[p],
                to_remove,
                qualityProfile=self.concerned_object.name,
                language=self.concerned_object.language,
            )
            to_add = permissions.diffarray(decoded_perms, self.permissions[p])
            return self._post_api(
                QualityProfilePermissions.API_SET[p],
                QualityProfilePermissions.API_SET_FIELD[p],
                to_add,
                qualityProfile=self.concerned_object.name,
                language=self.concerned_object.language,
            )
        return self.read()

