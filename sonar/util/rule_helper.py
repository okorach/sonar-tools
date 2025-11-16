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
from sonar.util import constants as c
from sonar.util import common_json_helper


def __convert_rule_json(json_to_convert: dict[str, Any]) -> dict[str, Any]:
    """Converts a rule JSON from old to new export format"""
    json_to_convert = common_json_helper.convert_common_fields(json_to_convert)
    if "impacts" in json_to_convert:
        json_to_convert["impacts"] = {
            k: json_to_convert["impacts"][k]
            for k in ("SECURITY", "RELIABILITY", "MAINTAINABILITY")
            if k in json_to_convert["impacts"] and json_to_convert["impacts"][k] != c.DEFAULT
        }
    if "params" in json_to_convert:
        json_to_convert["params"] = utilities.dict_to_list(json_to_convert["params"], "key")
    return json_to_convert


def convert_rules_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts the sonar-config rules old JSON report format to the new one"""
    new_json = {}
    for k in ("instantiated", "extended", "standard", "thirdParty"):
        if k in old_json:
            for key, r in old_json[k].items():
                old_json[k][key] = __convert_rule_json(r)
            new_json[k] = utilities.dict_to_list(dict(sorted(old_json[k].items())), "key")
    return new_json
