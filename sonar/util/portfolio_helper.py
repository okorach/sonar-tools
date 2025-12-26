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
import sonar.util.misc as util
from sonar.util import constants as c
from sonar.util import common_json_helper


def __convert_projects_json(json_to_convert: dict[str, Any]) -> dict[str, Any]:
    """Converts the 'projects' section of a portfolio JSON"""
    json_to_convert["projects"] = common_json_helper.convert_common_fields(json_to_convert["projects"])
    if "manual" in json_to_convert["projects"]:
        projs = {}
        for k, v in json_to_convert["projects"]["manual"].items():
            projs[k] = {"key": k, "branches": sorted(["" if e == c.DEFAULT_BRANCH else e for e in util.csv_to_list(v)])}
            if projs[k]["branches"] == [""]:
                projs[k].pop("branches", None)
        json_to_convert["projectSelection"] = {"manual": json_to_convert["projects"]}
        json_to_convert["projectSelection"]["manual"] = util.dict_to_list(projs, "key", "branches")
    elif "regexp" in json_to_convert["projects"]:
        json_to_convert["projectSelection"] = "regexp"
        json_to_convert["projectSelection"] = {"regexp": json_to_convert["projects"]["regexp"]}
        if json_to_convert["projects"].get("branch", c.DEFAULT_BRANCH) != c.DEFAULT_BRANCH:
            json_to_convert["projectSelection"]["branch"] = json_to_convert["projects"]["branch"]
    elif "tags" in json_to_convert["projects"]:
        json_to_convert["projectSelection"] = {"tags": json_to_convert["projects"]["tags"]}
        if json_to_convert["projects"].get("branch", c.DEFAULT_BRANCH) != c.DEFAULT_BRANCH:
            json_to_convert["projectSelection"]["branch"] = json_to_convert["projects"]["branch"]
    elif "rest" in json_to_convert["projects"]:
        json_to_convert["projectSelection"] = {"rest": True}
        if json_to_convert["projects"].get("branch", c.DEFAULT_BRANCH) != c.DEFAULT_BRANCH:
            json_to_convert["projectSelection"]["branch"] = json_to_convert["projects"]["branch"]
    json_to_convert.pop("projects")
    return json_to_convert


def convert_portfolio_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts the sonar-config old JSON report format for a single portfolio to the new one"""
    new_json = common_json_helper.convert_common_fields(old_json.copy())
    if "projects" in new_json:
        new_json = __convert_projects_json(new_json)
    if "applications" in new_json:
        for k, v in new_json["applications"].items():
            new_json["applications"][k] = {"key": k, "branches": sorted(["" if e == c.DEFAULT_BRANCH else e for e in util.csv_to_list(v)])}
            if new_json["applications"][k]["branches"] == [""]:
                new_json["applications"][k].pop("branches", None)
        new_json["applications"] = util.dict_to_list(new_json["applications"], "key", "branches")

    for key in "children", "portfolios":
        if key in new_json:
            new_json[key] = convert_portfolios_json(new_json[key])
    if "branches" in old_json:
        new_json["branches"] = util.dict_to_list(old_json["branches"], "name")
    return util.order_keys(new_json, "key", "name", "visibility", "projectSelection", "applications", "portfolios", "permissions")


def convert_portfolios_json(old_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts the sonar-config portfolios old JSON report format to the new one"""
    for k, v in old_json.items():
        old_json[k] = convert_portfolio_json(v)
    return util.dict_to_list(old_json, "key")
