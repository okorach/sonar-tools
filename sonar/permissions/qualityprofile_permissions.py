#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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

"""Quality profiles permissions class"""

from __future__ import annotations
from typing import TYPE_CHECKING

from sonar.permissions import permissions, quality_permissions

if TYPE_CHECKING:
    from sonar.util.types import JsonPermissions


class QualityProfilePermissions(quality_permissions.QualityPermissions):
    """
    Abtraction of quality profiles permissions
    """

    APIS = {
        "get": {"users": "qualityprofiles/search_users", "groups": "qualityprofiles/search_groups"},
        "add": {"users": "qualityprofiles/add_user", "groups": "qualityprofiles/add_group"},
        "remove": {"users": "qualityprofiles/remove_user", "groups": "qualityprofiles/remove_group"},
    }
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "group"}

    def read(self) -> QualityProfilePermissions:
        self._read_perms(
            QualityProfilePermissions.APIS,
            QualityProfilePermissions.API_GET_FIELD,
            qualityProfile=self.concerned_object.name,
            language=self.concerned_object.language,
        )
        return self

    def set(self, new_perms: JsonPermissions) -> bool:
        return self._set_perms(
            new_perms,
            QualityProfilePermissions.APIS,
            QualityProfilePermissions.API_SET_FIELD,
            permissions.diffarray,
            qualityProfile=self.concerned_object.name,
            language=self.concerned_object.language,
        )
