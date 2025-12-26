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
import sonar.util.misc as util
import sonar.utilities as sutil


def convert_common_fields(json_data: dict[str, Any], with_permissions: bool = True) -> dict[str, Any]:
    """Converts Sonar objects common fields from old to new JSON format"""
    if "permissions" in json_data and json_data["permissions"] is None:
        json_data.pop("permissions")
    if with_permissions and "permissions" in json_data:
        json_data["permissions"] = sutil.perms_to_list(json_data["permissions"])
        for perm in json_data["permissions"]:
            perm["permissions"] = util.csv_to_list(perm["permissions"])
    if "tags" in json_data:
        json_data["tags"] = util.csv_to_list(json_data["tags"])
    return json_data
