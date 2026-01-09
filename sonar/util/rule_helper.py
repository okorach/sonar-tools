#
# sonar-tools
# Copyright (C) 2026 Olivier Korach
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
from sonar.util import constants as c
from sonar.util import common_json_helper
import sonar.util.issue_defs as idefs


def __convert_rule_json(json_to_convert: dict[str, Any]) -> dict[str, Any]:
    """Converts a rule JSON from old to new export format"""
    json_to_convert = common_json_helper.convert_common_fields(json_to_convert)
    for field in [f for f in ("severities", "impacts") if f in json_to_convert]:
        json_to_convert["impacts"] = {
            k.lower(): json_to_convert[field][k].lower()
            for k in idefs.MQR_QUALITIES
            if k in json_to_convert[field] and json_to_convert[field][k] != c.DEFAULT
        }
    if "severity" in json_to_convert:
        json_to_convert["severity"] = json_to_convert["severity"].lower()
    if "params" in json_to_convert:
        json_to_convert["params"] = util.dict_to_list(json_to_convert["params"], "key")
    return json_to_convert


def convert_rules_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts the sonar-config rules old JSON report format to the new one"""
    new_json = {}
    for k in ("instantiated", "extended", "standard", "thirdParty"):
        if k in old_json:
            for key, r in old_json[k].items():
                old_json[k][key] = __convert_rule_json(r)
            new_json[k] = util.dict_to_list(dict(sorted(old_json[k].items())), "key")
    return new_json
