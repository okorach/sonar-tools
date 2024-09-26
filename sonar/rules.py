#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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
from __future__ import annotations
import json
from typing import Optional
from http import HTTPStatus
from requests.exceptions import HTTPError

import sonar.logging as log
import sonar.sqobject as sq
from sonar.util import types
from sonar import platform, utilities, exceptions

_OBJECTS = {}

_DETAILS_API = "rules/show"
_UPDATE_API = "rules/update"
_CREATE_API = "rules/create"

TYPES = ("BUG", "VULNERABILITY", "CODE_SMELL", "SECURITY_HOTSPOT")

SONAR_REPOS = {
    "abap",
    "apex",
    "azureresourcemanager",
    "c",
    "cloudformation",
    "cobol",
    "cpp",
    "csharpsquid",
    "roslyn.sonaranalyzer.security.cs",
    "css",
    "docker",
    "flex",
    "go",
    "java",
    "javabugs",
    "javasecurity",
    "javascript",
    "jssecurity",
    "jcl",
    "kotlin",
    "kubernetes",
    "objc",
    "php",
    "phpsecurity",
    "pli",
    "plsql",
    "python",
    "pythonbugs",
    "pythonsecurity",
    "rpg",
    "ruby",
    "scala",
    "secrets",
    "swift",
    "terraform",
    "text",
    "tsql",
    "typescript",
    "tssecurity",
    "vb",
    "vbnet",
    "Web",
    "xml",
}


class Rule(sq.SqObject):
    """
    Abstraction of the Sonar Rule concept
    """

    SEARCH_API = "rules/search"
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "rules"

    def __init__(self, endpoint: platform.Platform, key: str, data: types.ApiPayload) -> None:
        super().__init__(endpoint=endpoint, key=key)
        log.debug("Creating rule object '%s'", key)  # utilities.json_dump(data))
        self._json = data
        self.severity = data.get("severity", None)
        self.repo = data.get("repo", None)
        self.type = data.get("type", None)
        self.tags = None if len(data.get("tags", [])) == 0 else data["tags"]
        self.systags = data.get("sysTags", [])
        self.name = data.get("name", None)
        self.language = data.get("lang", None)
        self.custom_desc = data.get("mdNote", None)
        self.created_at = data["createdAt"]
        self.is_template = data.get("isTemplate", False)
        self.template_key = data.get("templateKey", None)
        self._impacts = data.get("impacts", None)
        self._clean_code_attribute = {
            "attribute": data.get("cleanCodeAttribute", None),
            "attribute_category": data.get("cleanCodeAttributeCategory", None),
        }
        _OBJECTS[self.uuid()] = self

    @classmethod
    def get_object(cls, endpoint: platform.Platform, key: str) -> Rule:
        """Returns a rule object from the cache or from the platform itself"""
        uid = sq.uuid(key, endpoint.url)
        if uid in _OBJECTS:
            return _OBJECTS[uid]
        log.debug("Reading rule key '%s'", key)
        try:
            r = endpoint.get(_DETAILS_API, params={"key": key})
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(key=key, message=f"Rule key '{key}' does not exist")
        return Rule(endpoint=endpoint, key=key, data=json.loads(r.text)["rule"])

    @classmethod
    def create(cls, endpoint: platform.Platform, key: str, **kwargs) -> Optional[Rule]:
        """Creates a rule object"""
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't create or extend rules on SonarCloud")
        params = kwargs.copy()
        (_, params["customKey"]) = key.split(":")
        log.debug("Creating rule key '%s'", key)
        if not endpoint.post(_CREATE_API, params=params).ok:
            return None
        return cls.get_object(endpoint=endpoint, key=key)

    @classmethod
    def load(cls, endpoint: platform.Platform, key: str, data: types.ApiPayload) -> Rule:
        """Loads a rule object"""
        uid = sq.uuid(key, endpoint.url)
        if uid in _OBJECTS:
            _OBJECTS[uid]._json.update(data)
            return _OBJECTS[uid]
        return cls(key=key, endpoint=endpoint, data=data)

    @classmethod
    def instantiate(cls, endpoint: platform.Platform, key: str, template_key: str, data: types.ObjectJsonRepr) -> Rule:
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't instantiate rules on SonarCloud")
        try:
            rule = Rule.get_object(endpoint, key)
            log.info("Rule key '%s' already exists, instantiation skipped...", key)
            return rule
        except exceptions.ObjectNotFound:
            pass
        log.info("Instantiating rule key '%s' from template key '%s'", key, template_key)
        rule_params = ";".join([f"{k}={v}" for k, v in data["params"].items()])
        return Rule.create(
            key=key,
            endpoint=endpoint,
            templateKey=template_key,
            name=data.get("name", key),
            severity=data.get("severity", "MAJOR"),
            params=rule_params,
            markdownDescription=data.get("description", "NO DESCRIPTION"),
        )

    def __str__(self) -> str:
        return f"rule key '{self.key}'"

    def to_json(self) -> types.ObjectJsonRepr:
        return self._json

    def to_csv(self) -> list[str]:
        tags = self.systags
        if self.tags:
            tags += self.tags
        rule_type = "STANDARD"
        if self.is_template:
            rule_type = "TEMPLATE"
        elif self.template_key:
            rule_type = "INSTANTIATED"
        return [self.key, self.language, self.repo, self.type, self.name, rule_type, ",".join(tags)]

    def export(self, full: bool = False) -> types.ObjectJsonRepr:
        """Returns the JSON corresponding to a rule export"""
        return convert_for_export(self.to_json(), self.language, full=full)

    def set_tags(self, tags: list[str]) -> bool:
        """Sets rule custom tags"""
        log.debug("Settings custom tags of %s to '%s' ", str(self), str(tags))
        ok = self.post(_UPDATE_API, params={"key": self.key, "tags": utilities.list_to_csv(tags)}).ok
        if ok:
            self.tags = tags if len(tags) > 0 else None
        return ok

    def reset_tags(self) -> bool:
        """Removes all custom tags from the rule"""
        log.debug("Removing custom tags from %s", str(self))
        return self.set_tags([])

    def set_description(self, description: str) -> bool:
        """Extends rule description"""
        if self.endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't extend rules description on SonarCloud")
        log.debug("Settings custom description of %s to '%s'", str(self), description)
        ok = self.post(_UPDATE_API, params={"key": self.key, "markdown_note": description}).ok
        if ok:
            self.custom_desc = description if description != "" else None
        return ok

    def reset_description(self) -> bool:
        """Resets rule custom description"""
        return self.set_description("")

    def clean_code_attribute(self) -> dict[str, str]:
        """Returns the rule clean code attributes"""
        return self._clean_code_attribute

    def impacts(self) -> dict[str, str]:
        """Returns the rule clean code attributes"""
        return self._impacts


def get_facet(facet: str, endpoint: platform.Platform) -> dict[str, str]:
    """Returns a facet as a count per item in the facet"""
    data = json.loads(endpoint.get(Rule.SEARCH_API, params={"ps": 1, "facets": facet}).text)
    return {f["val"]: f["count"] for f in data["facets"][0]["values"]}


def search(endpoint: platform.Platform, **params) -> dict[str, Rule]:
    """Searches ruless with optional filters"""
    return sq.search_objects(endpoint=endpoint, object_class=Rule, params=params, threads=4)


def count(endpoint: platform.Platform, **params) -> int:
    """Count number of rules that correspond to certain filters"""
    return json.loads(endpoint.get(Rule.SEARCH_API, params={**params, "ps": 1}).text)["total"]


def get_list(endpoint: platform.Platform, use_cache: bool = True, **params) -> dict[str, Rule]:
    """Returns a list of rules corresponding to certain csearch filters"""
    if not use_cache or params or len(_OBJECTS) < 100:
        return search(endpoint, include_external="false", **params)
    return _OBJECTS


def get_object(endpoint: platform.Platform, key: str) -> Optional[Rule]:
    """Returns a Rule object from its key
    :return: The Rule object corresponding to the input rule key, or None if not found
    :param str key: The rule key
    :rtype: Rule or None
    """
    uid = sq.uuid(key, endpoint)
    if uid in _OBJECTS:
        return _OBJECTS[uid]
    try:
        return Rule.get_object(key=key, endpoint=endpoint)
    except exceptions.ObjectNotFound:
        return None


def export(endpoint: platform.Platform, export_settings: types.ConfigSettings, key_list: types.KeyList = None) -> types.ObjectJsonRepr:
    """Returns a JSON export of all rules"""
    log.info("Exporting rules")
    full = export_settings.get("FULL_EXPORT", False)
    rule_list, other_rules, instantiated_rules, extended_rules = {}, {}, {}, {}
    for rule_key, rule in get_list(endpoint=endpoint, use_cache=False).items():
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
    if len(other_rules) > 0 and full:
        rule_list["standard"] = other_rules
    if export_settings.get("MODE", "") == "MIGRATION":
        rule_list["thirdParty"] = {r.key: r.export() for r in third_party(endpoint=endpoint)}
    return rule_list


def import_config(endpoint: platform.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> bool:
    """Imports a sonar-config configuration"""
    if "rules" not in config_data:
        log.info("No customized rules (custom tags, extended description) to import")
        return True
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Can't import rules in SonarCloud")
    log.info("Importing customized (custom tags, extended description) rules")
    get_list(endpoint=endpoint, use_cache=False)
    for key, custom in config_data["rules"].get("extended", {}).items():
        try:
            rule = Rule.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            log.warning("Rule key '%s' does not exist, can't import it", key)
            continue
        rule.set_description(custom.get("description", ""))
        rule.set_tags(utilities.csv_to_list(custom.get("tags", None)))

    log.info("Importing custom rules (instantiated from rule templates)")
    for key, instantiation_data in config_data["rules"].get("instantiated", {}).items():
        try:
            rule = Rule.get_object(endpoint, key)
            log.debug("Instantiated rule key '%s' already exists, instantiation skipped", key)
            continue
        except exceptions.ObjectNotFound:
            pass
        try:
            template_rule = Rule.get_object(endpoint, instantiation_data["templateKey"])
        except exceptions.ObjectNotFound:
            log.warning("Rule template key '%s' does not exist, can't instantiate it", key)
            continue
        Rule.instantiate(endpoint=endpoint, key=key, template_key=template_rule.key, data=instantiation_data)
    return True


def convert_for_export(rule: types.ObjectJsonRepr, qp_lang: str, with_template_key: bool = True, full: bool = False) -> types.ObjectJsonRepr:
    """Converts rule data for export"""
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


def convert_rule_list_for_yaml(rule_list: types.ObjectJsonRepr) -> list[types.ObjectJsonRepr]:
    """Converts a rule dict (key: data) from a dict to a list ["key": key, **data]"""
    return utilities.dict_to_list(rule_list, "key", "severity")


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    new_json = {}
    for category in ("instantiated", "extended"):
        if category in original_json:
            new_json[category] = convert_rule_list_for_yaml(original_json[category])
    return new_json


def third_party(endpoint: platform.Platform) -> list[Rule]:
    """Returns the list of rules coming from 3rd party plugins"""
    return [r for r in get_list(endpoint=endpoint).values() if r.repo and r.repo not in SONAR_REPOS and not r.repo.startswith("external_")]
