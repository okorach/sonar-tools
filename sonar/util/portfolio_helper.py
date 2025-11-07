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
"""Helper tools for the Portfolio object"""

from typing import Any
from sonar import utilities as util
from sonar.util import common_json_helper


def convert_portfolio_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts the sonar-config old JSON report format for a single portfolio to the new one"""
    new_json = common_json_helper.convert_common_fields(old_json.copy())
    if "projects" in new_json:
        new_json["projects"] = common_json_helper.convert_common_fields(new_json["projects"])
    for key in "children", "portfolios":
        if key in new_json:
            new_json[key] = convert_portfolios_json(new_json[key])
    if "permissions" in old_json:
        new_json["permissions"] = util.perms_to_list(old_json["permissions"])
    if "branches" in old_json:
        new_json["branches"] = util.dict_to_list(old_json["branches"], "name")
    return new_json


def convert_portfolios_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts the sonar-config portfolios old JSON report format to the new one"""
    for k, v in old_json.items():
        old_json[k] = convert_portfolio_json(v)
    return util.dict_to_list(old_json, "key")
