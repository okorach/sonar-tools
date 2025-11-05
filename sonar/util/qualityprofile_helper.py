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
from sonar.util import types

KEY_PARENT = "parent"
KEY_CHILDREN = "children"


def flatten_language(language: str, qp_list: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Converts a hierarchical list of QP of a given language into a flat list"""
    flat_list = {}
    for qp_name, qp_data in qp_list.copy().items():
        if KEY_CHILDREN in qp_data:
            children = flatten_language(language, qp_data[KEY_CHILDREN])
            for child in children.values():
                if "parent" not in child:
                    child["parent"] = f"{language}:{qp_name}"
            qp_data.pop(KEY_CHILDREN)
            flat_list.update(children)
        flat_list[f"{language}:{qp_name}"] = qp_data
    return flat_list


def flatten(qp_list: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Organize a hierarchical list of QP in a flat list"""
    flat_list = {}
    for lang, lang_qp_list in qp_list.items():
        flat_list.update(flatten_language(lang, lang_qp_list))
    return flat_list


def __convert_children_to_list(qp_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts a profile's children profiles to list"""
    for v in qp_json.values():
        if "children" in v:
            v["children"] = __convert_children_to_list(v["children"])
    return util.dict_to_list(qp_json, "name")


def convert_qps_json(qp_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts a language top level list of profiles to list"""
    for k, v in qp_json.items():
        qp_json[k] = __convert_children_to_list(v)
    return util.dict_to_list(qp_json, "language", "profiles")
