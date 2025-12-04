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
"""Helper tools for the Project object"""

from typing import Any
from sonar import utilities as util
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


def __convert_qp_json(qp_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts a profile's children profiles to list"""
    for k, v in sorted(qp_json.items()):
        for rtype in "addedRules", "modifiedRules", "rules":
            for r in v.get(rtype, {}):
                if "severities" in r:
                    r["impacts"] = r.pop("severities")
                if "severity" in r:
                    r["severity"] = r["severity"].lower()
                if "impacts" in r:
                    r["impacts"] = {
                        k.lower(): r["impacts"][k].lower() for k in idefs.MQR_QUALITIES if k in r["impacts"] and r["impacts"][k] != c.DEFAULT
                    }
                if "params" in r:
                    r["params"] = util.dict_to_list(dict(sorted(r["params"].items())), "key")
        if "removedRules" in v:
            v["removedRules"] = list(v["removedRules"])
        for rule in v.get("rules", []):
            if "params" in rule:
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
