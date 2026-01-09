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
"""Helper tools for the Project object"""

from typing import Any
import sonar.util.misc as util

from sonar.util import constants as c
from sonar.util import common_json_helper
import sonar.util.issue_defs as idefs


KEY_PARENT = "parent"
KEY_CHILDREN = "children"
KEY_ORDER = ("name", "isBuiltIn", "isDefault", "children", "addedRules", "modifiedRules", "permissions")


def flatten_language(language: str, qp_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converts a hierarchical list of QP of a given language into a flat list"""
    flat_list = []
    for qp_data in [qp.copy() for qp in qp_list]:
        qp_name = qp_data["name"]
        qp_data["name"] = f"{language}:{qp_name}"
        qp_data["language"] = language
        flat_list.append(qp_data)
        if KEY_CHILDREN in qp_data:
            children = flatten_language(language, qp_data[KEY_CHILDREN])
            for child in children:
                if "parent" not in child:
                    child["parent"] = f"{language}:{qp_name}"
                    child["language"] = language
            qp_data.pop(KEY_CHILDREN)
            flat_list += children
    return flat_list


def flatten(qp_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Organize a hierarchical list of QP in a flat list"""
    flat_list = []
    for lang_data in qp_list:
        flat_list += flatten_language(lang_data["language"], lang_data["profiles"])
    return flat_list


def __convert_rule_json(rule_json: dict[str, Any]) -> dict[str, Any]:
    """Converts a rule JSON from old to new export format"""
    if "severities" in rule_json:
        rule_json["impacts"] = rule_json.pop("severities")
    if "severity" in rule_json:
        rule_json["severity"] = rule_json["severity"].lower()
    if "impacts" in rule_json:
        rule_json["impacts"] = {
            k.lower(): rule_json["impacts"][k].lower()
            for k in idefs.MQR_QUALITIES
            if k in rule_json["impacts"] and rule_json["impacts"][k] != c.DEFAULT
        }
    if "params" in rule_json:
        rule_json["params"] = util.dict_to_list(dict(sorted(rule_json["params"].items())), "key")
    return rule_json


def __convert_qp_json(qp_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts a profile's children profiles to list"""
    for qp in [q for q in qp_json.values() if "permissions" in q]:
        for ptype in [p for p in ("users", "groups") if p in qp["permissions"]]:
            qp["permissions"][ptype] = util.csv_to_list(qp["permissions"][ptype])
    for k, v in sorted(qp_json.items()):
        for r in v.get("rules", {}):
            r.pop("severities", None)
            r.pop("severity", None)
            r.pop("impacts", None)
            r.pop("params", None)
        for rtype in "addedRules", "modifiedRules", "rules":
            for r in v.get(rtype, {}):
                r = __convert_rule_json(r)
        if "removedRules" in v:
            v["removedRules"] = list(v["removedRules"])
        for rule in [r for r in v.get("rules", []) if "params" in r]:
            rule["params"] = util.dict_to_list(rule["params"], "key")
        if "children" in v:
            v["children"] = __convert_qp_json(v["children"])
        qp_json[k] = util.order_keys(common_json_helper.convert_common_fields(v, with_permissions=False), *KEY_ORDER)
    return util.dict_to_list(qp_json, "name")


def convert_qps_json(qp_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts a language top level list of profiles to list"""
    for k, v in sorted(qp_json.items()):
        qp_json[k] = __convert_qp_json(v)
    return util.dict_to_list(qp_json, "language", "profiles")
