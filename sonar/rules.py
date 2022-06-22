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
from sonar import utilities

_RULES = {}
API_RULES_SEARCH = "rules/search"


class Rule(sq.SqObject):
    def __init__(self, key, endpoint, data):
        super().__init__(key, endpoint)
        utilities.logger.debug("Creating rule %s", key)  # utilities.json_dump(data))
        self._json = data
        self.severity = data.get("severity", None)
        self.repo = data.get("repo", None)
        self.type = data.get("type", None)
        self.tags = None if len(data.get("tags", [])) == 0 else data["tags"]
        self.name = data.get("name", None)
        self.language = data.get("lang", None)
        self.custom_desc = data.get("mdNote", None)
        self.created_at = data["createdAt"]
        self.is_template = data.get("isTemplate", False)
        self.template_key = data.get("templateKey", None)
        _RULES[self.key] = self

    def __str__(self):
        return f"rule key '{self.key}'"

    def to_json(self):
        return self._json

    def set_tags(self, tags):
        if tags is None:
            return
        if isinstance(tags, list):
            tags = utilities.list_to_csv(tags)
        utilities.logger.debug("Settings custom tags '%s' to %s", tags, str(self))
        self.post("rules/update", params={"key": self.key, "tags": tags})

    def set_description(self, description):
        if description is None:
            return
        utilities.logger.debug("Settings custom description '%s' to %s", description, str(self))
        self.post("rules/update", params={"key": self.key, "markdown_note": description})

    def instantiate(self, key, data):
        if get_object(key, self.endpoint) is not None:
            utilities.logger.info("Rule key '%s' already exists, creation skipped...", key)
            return
        utilities.logger.info("Creating rule key '%s' from template key '%s'", key, self.key)
        rule_params = ";".join([f"{k}={v}" for k, v in data["params"].items()])
        (_, key) = key.split(":")
        self.post(
            "rules/create",
            params={
                "custom_key": key,
                "template_key": self.key,
                "name": data.get("name", key),
                "severity": data.get("severity", "MAJOR"),
                "params": rule_params,
                "markdown_description": data.get("description", "NO DESCRIPTION"),
            },
        )


def get_facet(facet, endpoint):
    data = json.loads(endpoint.get(API_RULES_SEARCH, params={"ps": 1, "facets": facet}).text)
    facet_dict = {}
    for f in data["facets"][0]["values"]:
        facet_dict[f["val"]] = f["count"]
    return facet_dict


def count(endpoint, params=None):
    new_params = {} if params is None else params.copy()
    new_params.update({"ps": 1, "p": 1})
    data = json.loads(endpoint.get(API_RULES_SEARCH, params=new_params).text)
    return data["total"]


def get_list(endpoint, templates=False):
    new_params = {"is_template": str(templates).lower(), "include_external": "true", "ps": 500}
    page, nb_pages = 1, 1
    rule_list = {}
    while page <= nb_pages:
        new_params["p"] = page
        data = json.loads(endpoint.get(API_RULES_SEARCH, params=new_params).text)
        for r in data["rules"]:
            rule_list[r["key"]] = Rule(r["key"], endpoint=endpoint, data=r)
        nb_pages = utilities.int_div_ceil(data["total"], data["ps"])
        page += 1
    return rule_list


def get_object(key, endpoint):
    if key not in _RULES:
        get_list(endpoint=endpoint)
    return _RULES.get(key, None)


def export(endpoint, instantiated=True, extended=True, standard=False):
    utilities.logger.info("Exporting rules")
    rule_list, other_rules, instantiated_rules, extended_rules = {}, {}, {}, {}
    for rule_key, rule in get_list(endpoint=endpoint).items():
        rule_export = convert_for_export(rule.to_json(), rule.language)
        if instantiated and rule.template_key is not None:
            instantiated_rules[rule_key] = rule_export
        elif extended and rule.tags is not None or rule.custom_desc is not None:
            extended_rules[rule_key] = {}
            if rule.tags is not None:
                extended_rules[rule_key].update({"tags": rule_export["tags"]})
            if rule.custom_desc is not None:
                extended_rules[rule_key].update({"description": rule_export["description"]})
        elif standard:
            other_rules[rule_key] = rule_export
    if len(instantiated_rules) > 0:
        rule_list["instantiated"] = instantiated_rules
    if len(extended_rules) > 0:
        rule_list["extended"] = extended_rules
    if len(other_rules) > 0:
        rule_list["standard"] = other_rules
    return rule_list


def import_config(endpoint, config_data):
    if "rules" not in config_data:
        utilities.logger.info("No customized rules (custom tags, extended description) to import")
        return
    utilities.logger.info("Importing customized (custom tags, extended description) rules")
    for key, custom in config_data["rules"].get("extended", {}).items():
        rule = get_object(key, endpoint=endpoint)
        if rule is None:
            utilities.logger.warning("Rule key '%s' does not exist, can't import it", key)
            continue
        rule.set_description(custom.get("description", None))
        rule.set_tags(custom.get("tags", None))

    get_list(endpoint=endpoint, templates=True)
    utilities.logger.info("Importing custom rules (instantiated from rule templates)")
    for key, instantiation_data in config_data["rules"].get("instantiated", {}).items():
        template_rule = get_object(instantiation_data["templateKey"], endpoint=endpoint)
        if template_rule is None:
            utilities.logger.warning("Rule template key '%s' does not exist, can't instantiate it", key)
            continue
        template_rule.instantiate(key, instantiation_data)


def convert_for_export(rule, qp_lang, with_template_key=True, full_specs=False):
    d = {"severity": rule.get("severity", "")}
    if len(rule.get("params", {})) > 0:
        if not full_specs:
            d["params"] = {}
            for p in rule["params"]:
                d["params"][p["key"]] = p.get("defaultValue", "")
        else:
            d["params"] = rule["params"]
    if rule["isTemplate"]:
        d["isTemplate"] = True
    if "tags" in rule and len(rule["tags"]) > 0:
        d["tags"] = utilities.list_to_csv(rule["tags"])
    if rule.get("mdNote", None) is not None:
        d["description"] = rule["mdNote"]
    if with_template_key and "templateKey" in rule:
        d["templateKey"] = rule["templateKey"]
    if "lang" in rule and rule["lang"] != qp_lang:
        d["language"] = rule["lang"]
    if len(d) == 1:
        return d["severity"]
    return d
