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
from typing import Union
from http import HTTPStatus
from requests.exceptions import HTTPError

import sonar.logging as log
import sonar.sqobject as sq
from sonar import platform, utilities, exceptions

_OBJECTS = {}
SEARCH_API = "rules/search"
_DETAILS_API = "rules/show"
_UPDATE_API = "rules/update"
_CREATE_API = "rules/create"

TYPES = ("BUG", "VULNERABILITY", "CODE_SMELL", "SECURITY_HOTSPOT")


class Rule(sq.SqObject):
    """
    Abstraction of the Sonar Rule concept
    """

    def __init__(self, endpoint: platform.Platform, key: str, data: dict[str, str]) -> None:
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
    def create(cls, endpoint: platform.Platform, key: str, **kwargs) -> Union[None, Rule]:
        """Creates a rule object"""
        params = kwargs.copy()
        (_, params["custom_key"]) = key.split(":")
        log.debug("Creating rule key '%s'", key)
        if not endpoint.post(_CREATE_API, params=params).ok:
            return None
        return cls.get_object(endpoint=endpoint, key=key)

    @classmethod
    def load(cls, endpoint: platform.Platform, key: str, data: dict[str, str]) -> Rule:
        """Loads a rule object"""
        uid = sq.uuid(key, endpoint.url)
        if uid in _OBJECTS:
            _OBJECTS[uid]._json.update(data)
            return _OBJECTS[uid]
        return cls(key=key, endpoint=endpoint, data=data)

    @classmethod
    def instantiate(cls, endpoint: platform.Platform, key: str, template_key: str, data: dict[str, str]) -> Rule:
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
            template_key=template_key,
            name=data.get("name", key),
            severity=data.get("severity", "MAJOR"),
            params=rule_params,
            markdown_description=data.get("description", "NO DESCRIPTION"),
        )

    def __str__(self) -> str:
        return f"rule key '{self.key}'"

    def to_json(self) -> dict[str, str]:
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

    def export(self, full: bool = False) -> dict[str, str]:
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
    data = json.loads(endpoint.get(SEARCH_API, params={"ps": 1, "facets": facet}).text)
    return {f["val"]: f["count"] for f in data["facets"][0]["values"]}


def search(endpoint: platform.Platform, **params) -> dict[str, Rule]:
    """Searches ruless with optional filters"""
    return sq.search_objects(SEARCH_API, endpoint, "key", "rules", Rule, params, threads=4)


def count(endpoint: platform.Platform, **params) -> int:
    """Count number of rules that correspond to certain filters"""
    return json.loads(endpoint.get(SEARCH_API, params={**params, "ps": 1}).text)["total"]


def get_list(endpoint: platform.Platform, **params) -> dict[str, Rule]:
    """Returns a list of rules corresponding to certain csearch filters"""
    return search(endpoint, include_external="false", **params)


def get_object(endpoint: platform.Platform, key: str) -> Union[Rule, None]:
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


def export_all(endpoint: platform.Platform, full: bool = False) -> dict[str, str]:
    """Returns a JSON export of all rules"""
    log.info("Exporting rules")
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


def export_instantiated(endpoint: platform.Platform, full: bool = False) -> Union[None, dict[str, str]]:
    """Returns a JSON of all instantiated rules"""
    rule_list = {}
    for template_key in get_list(endpoint=endpoint, is_template="true"):
        for rule_key, rule in get_list(endpoint=endpoint, template_key=template_key).items():
            rule_list[rule_key] = rule.export(full)
    return rule_list if len(rule_list) > 0 else None


def export_customized(endpoint: platform.Platform, full: bool = False) -> Union[None, dict[str, str]]:
    """Returns a JSON export of all customized rules (custom tags or description added)"""
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


def export_needed(endpoint: platform.Platform, instantiated: bool = True, extended: bool = True, full: bool = False) -> dict[str, str]:
    """Returns a JSON export selected / needed rules"""
    rule_list = {}
    if instantiated:
        rule_list["instantiated"] = export_instantiated(endpoint, full)
    if extended:
        rule_list["extended"] = export_customized(endpoint, full)
    return utilities.remove_nones(rule_list)


def export(
    endpoint: platform.Platform, export_settings: dict[str, str], instantiated: bool = True, extended: bool = True, standard: bool = False
) -> dict[str, Rule]:
    """Returns a dict of rules for export
    :return: a dict of rule onbjects indexed with rule key
    :param object endpoint: The SonarQube Platform object to connect to
    :param dict[str, str] export_settings: parameters to export
    :param bool instantiated: Include instantiated rules in the list
    :param bool extended: Include extended rules in the list
    :param bool standard: Include standard rules in the list
    :param full standard: Include full rule information in the export
    :rtype: dict{ruleKey: Rule}
    """
    log.info("Exporting rules")
    if standard:
        return export_all(endpoint, export_settings["FULL_EXPORT"])
    else:
        return export_needed(endpoint, instantiated, extended, export_settings["FULL_EXPORT"])


def import_config(endpoint: platform.Platform, config_data: dict[str, str]) -> bool:
    """Imports a sonar-config configuration"""
    if "rules" not in config_data:
        log.info("No customized rules (custom tags, extended description) to import")
        return True
    log.info("Importing customized (custom tags, extended description) rules")
    get_list(endpoint=endpoint)
    for key, custom in config_data["rules"].get("extended", {}).items():
        try:
            rule = Rule.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            log.warning("Rule key '%s' does not exist, can't import it", key)
            continue
        rule.set_description(custom.get("description", ""))
        rule.set_tags(utilities.csv_to_list(custom.get("tags", None)))

    log.debug("get_list from import")
    get_list(endpoint=endpoint, templates=True)
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


def convert_for_export(rule: dict[str, str], qp_lang: str, with_template_key: bool = True, full: bool = False) -> dict[str, str]:
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
