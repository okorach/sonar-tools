#
# sonar-tools
# Copyright (C) 2025 Olivier Korach
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
"""Helper tools for the Rule object"""

from typing import Any
from sonar import utilities
from sonar import logging as log


def convert_common_fields(json_data: dict[str, Any], with_permissions: bool = True) -> dict[str, Any]:
    if with_permissions and "permissions" in json_data:
        json_data["permissions"] = utilities.perms_to_list(json_data["permissions"])
        for perm in json_data["permissions"]:
            perm["permissions"] = utilities.csv_to_list(perm["permissions"])
    if "tags" in json_data:
        log.info("CONVERTING TAGS %s", json_data["tags"])
        json_data["tags"] = utilities.csv_to_list(json_data["tags"])
    return json_data
