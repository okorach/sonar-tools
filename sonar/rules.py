#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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
from http import HTTPStatus
from requests.exceptions import HTTPError
import sonar.sqobject as sq
from sonar import utilities, exceptions

_OBJECTS = {}
SEARCH_API = "rules/search"
_DETAILS_API = "rules/show"
_CREATE_API = "rules/create"

TYPES = ("BUG", "VULNERABILITY", "CODE_SMELL", "SECURITY_HOTSPOT")


class Rule(sq.SqObject):
    @classmethod
    def get_object(cls, endpoint, key):
        if key in _OBJECTS:
            return _OBJECTS[key]
        utilities.logger.debug("Reading rule key '%s'", key)
        try:
            r = endpoint.get(_DETAILS_API, params={"key": key})
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(key=key, message=f"Rule key '{key}' does not exist")
        return Rule(key, endpoint, json.loads(r.text)["rule"])

    @classmethod
    def create(cls, key, endpoint, **kwargs):
        params = kwargs.copy()
        (_, params["custom_key"]) = key.split(":")
        utilities.logger.debug("Creating rule key '%s'", key)
        r = endpoint.post(_CREATE_API, params=params)
        if not r.ok:
            return None
        o = cls.get_object(key=key, endpoint=endpoint)
        return o

    @classmethod
    def load(cls, key, endpoint, data):
        if key in _OBJECTS:
            _OBJECTS[key]._json.update(data)
            return _OBJECTS[key]
        return cls(key=key, endpoint=endpoint, data=data)

    @classmethod
    def instantiate(cls, key, template_key, endpoint, data):
        try:
            rule = Rule.get_object(endpoint, key)
            utilities.logger.info("Rule key '%s' already exists, instantiation skipped...", key)
            return rule
        except exceptions.ObjectNotFound:
            pass
        utilities.logger.info("Instantiating rule key '%s' from template key '%s'", key, template_key)
        rule_params = ";".join([f"{k}={v}" for k, v in data["params"].items()])
        return Rule.create(
            key=key,
            endpoint=endpoint,
            template_key=template_key,
            name=data.get("name", key),
            severity=data.get("severity", "MAJOR"),
            params=rule_params,
            markdown_description=data.get("description", "NO DESCRIPTION"),
        )

    def __init__(self, key, endpoint, data):
        super().__init__(key, endpoint)
        utilities.logger.debug("Creating rule object '%s'", key)  # utilities.json_dump(data))
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
        _OBJECTS[self.key] = self

    def __str__(self):
        return f"rule key '{self.key}'"

    def to_json(self):
        return self._json

    def export(self, full=False):
        return convert_for_export(self.to_json(), self.language, full=full)

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


def get_facet(facet, endpoint):
    data = json.loads(endpoint.get(SEARCH_API, params={"ps": 1, "facets": facet}).text)
    facet_dict = {}
    for f in data["facets"][0]["values"]:
        facet_dict[f["val"]] = f["count"]
    return facet_dict


def search(endpoint, **params):
    return sq.search_objects(SEARCH_API, endpoint, "key", "rules", Rule, params, threads=4)


def count(endpoint, **params):
    return json.loads(endpoint.get(SEARCH_API, params={**params, "ps": 1}).text)["total"]


def get_list(endpoint, **params):
    return search(endpoint, include_external="false", **params)


def get_object(key, endpoint):
    if key in _OBJECTS:
        return _OBJECTS[key]
    try:
        return Rule.get_object(key, endpoint)
    except exceptions.ObjectNotFound:
        return None


def export_all(endpoint, full=False):
    utilities.logger.info("Exporting rules")
    rule_list, other_rules, instantiated_rules, extended_rules = {}, {}, {}, {}
    for rule_key, rule in get_list(endpoint=endpoint).items():
        rule_export = rule.export(full)
        if rule.template_key is not None:
            instantiated_rules[rule_key] = rule_export
        elif rule.tags is not None or rule.custom_desc is not None:
            if full:
                extended_rules[rule_key] = rule_export
                continue
            extended_rules[rule_key] = {}
            if rule.tags is not None:
                extended_rules[rule_key]["tags"] = rule_export["tags"]
            if rule.custom_desc is not None:
                extended_rules[rule_key]["description"] = rule_export["description"]
        else:
            other_rules[rule_key] = rule_export
    if len(instantiated_rules) > 0:
        rule_list["instantiated"] = instantiated_rules
    if len(extended_rules) > 0:
        rule_list["extended"] = extended_rules
    if len(other_rules) > 0:
        rule_list["standard"] = other_rules
    return rule_list


def export_instantiated(endpoint, full=False):
    rule_list = {}
    for template_key in get_list(endpoint=endpoint, is_template="true"):
        for rule_key, rule in get_list(endpoint=endpoint, template_key=template_key).items():
            rule_list[rule_key] = rule.export(full)
    return rule_list if len(rule_list) > 0 else None


def export_customized(endpoint, full=False):
    rule_list = {}
    for rule_key, rule in get_list(endpoint=endpoint, is_template="false").items():
        if rule.tags is None and rule.custom_desc is None:
            continue
        if full:
            rule_list[rule_key] = rule.export(full)
            continue
        rule_list[rule_key] = {}
        if rule.tags:
            rule_list[rule_key]["tags"] = utilities.list_to_csv(rule.tags, ", ")
        if rule.custom_desc:
            rule_list[rule_key]["description"] = rule.custom_desc
    return rule_list if len(rule_list) > 0 else None


def export_needed(endpoint, instantiated=True, extended=True, full=False):
    rule_list = {}
    if instantiated:
        rule_list["instantiated"] = export_instantiated(endpoint, full)
    if extended:
        rule_list["extended"] = export_customized(endpoint, full)
    return utilities.remove_nones(rule_list)


def export(endpoint, instantiated=True, extended=True, standard=False, full=False):
    utilities.logger.info("Exporting rules")
    if standard:
        return export_all(endpoint, full)
    else:
        return export_needed(endpoint, instantiated, extended, full)


def import_config(endpoint, config_data):
    if "rules" not in config_data:
        utilities.logger.info("No customized rules (custom tags, extended description) to import")
        return
    utilities.logger.info("Importing customized (custom tags, extended description) rules")
    get_list(endpoint=endpoint)
    for key, custom in config_data["rules"].get("extended", {}).items():
        try:
            rule = Rule.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            utilities.logger.warning("Rule key '%s' does not exist, can't import it", key)
            continue
        rule.set_description(custom.get("description", None))
        rule.set_tags(custom.get("tags", None))

    utilities.logger.debug("get_list from import")
    get_list(endpoint=endpoint, templates=True)
    utilities.logger.info("Importing custom rules (instantiated from rule templates)")
    for key, instantiation_data in config_data["rules"].get("instantiated", {}).items():
        try:
            rule = Rule.get_object(endpoint, key)
            utilities.logger.debug("Instantiated rule key '%s' already exists, instantiation skipped", key)
            continue
        except exceptions.ObjectNotFound:
            pass
        try:
            template_rule = Rule.get_object(endpoint, instantiation_data["templateKey"])
        except exceptions.ObjectNotFound:
            utilities.logger.warning("Rule template key '%s' does not exist, can't instantiate it", key)
            continue
        Rule.instantiate(key, template_rule.key, endpoint, instantiation_data)


def convert_for_export(rule, qp_lang, with_template_key=True, full=False):
    d = {"severity": rule.get("severity", "")}
    if len(rule.get("params", {})) > 0:
        if not full:
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
    if full:
        for k, v in rule.items():
            if k not in ("severity", "params", "isTemplate", "tags", "mdNote", "templateKey", "lang"):
                d[f"_{k}"] = v
        d.pop("_key", None)
    if len(d) == 1:
        return d["severity"]
    return d
