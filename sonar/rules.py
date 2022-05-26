#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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
"""

    Abstraction of the SonarQube "rule" concept

"""
import json
import sonar.sqobject as sq
from sonar import env, utilities

_RULES = {}
API_RULES_SEARCH = "rules/search"


class Rule(sq.SqObject):
    def __init__(self, key, endpoint, data):
        super().__init__(key, endpoint)
        self.severity = data["severity"]
        self.tags = data["tags"]
        self.sys_tags = data["sysTags"]
        self.repo = data["repo"]
        self.type = data["type"]
        self.status = data["status"]
        self.scope = data["scope"]
        self.html_desc = data["htmlDesc"]
        self.md_desc = data["mdDesc"]
        self.name = data["name"]
        self.language = data["lang"]
        self.created_at = data["createdAt"]
        self.is_template = data["isTemplate"]
        self.template_key = data.get("templateKey", None)
        _RULES[self.key] = self


def get_facet(facet, endpoint=None):
    resp = env.get(API_RULES_SEARCH, ctxt=endpoint, params={"ps": 1, "facets": facet})
    data = json.loads(resp.text)
    facet_dict = {}
    for f in data["facets"][0]["values"]:
        facet_dict[f["val"]] = f["count"]
    return facet_dict


def count(endpoint=None, params=None):
    new_params = {} if params is None else params.copy()
    new_params.update({"ps": 1, "p": 1})
    data = json.loads(env.get(API_RULES_SEARCH, ctxt=endpoint, params=new_params).text)
    return data["total"]


def get_list(endpoint, params=None):
    new_params = {} if params is None else params.copy()
    new_params.update({"is_template": "false", "include_external": "true", "ps": 500})
    page, nb_pages = 1, 1
    rule_list = {}
    while page <= nb_pages:
        params["p"] = page
        data = json.loads(env.get(API_RULES_SEARCH, ctxt=endpoint, params=new_params).text)
        for r in data["rules"]:
            rule_list[r["key"]] = Rule(r["key"], endpoint=endpoint, data=r)
        nb_pages = utilities.int_div_ceil(data["total"], data["ps"])
        page += 1
    return rule_list


def get_object(key, data=None, endpoint=None):
    if key not in _RULES:
        _ = Rule(key=key, data=data, endpoint=endpoint)
    return _RULES[key]
