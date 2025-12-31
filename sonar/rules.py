#!/usr/bin/env python3
#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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
"""Abstraction of the SonarQube "rule" concept"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

import json
import concurrent.futures
from threading import Lock

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache, constants as c, issue_defs as idefs
from sonar import exceptions, languages
import sonar.util.misc as util
import sonar.utilities as sutil
from sonar.util import rule_helper as rhelp

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ConfigSettings, KeyList, ObjectJsonRepr

TYPE_TO_QUALITY = {
    idefs.TYPE_BUG: idefs.QUALITY_RELIABILITY,
    idefs.TYPE_VULN: idefs.QUALITY_SECURITY,
    idefs.TYPE_HOTSPOT: idefs.QUALITY_SECURITY,
    idefs.TYPE_CODE_SMELL: idefs.QUALITY_MAINTAINABILITY,
}

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
    "dart",
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
    "ipython",
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

EXTERNAL_REPOS = {
    "external_pylint": "py",
    "external_bandit": "py",
    "external_flake8": "py",
    "external_mypy": "py",
    "external_ruff": "py",
    "external_shellcheck": "shell",
    "external_tflint": "terraform",
    "external_hadolint": "docker",
    "external_eslint_repo": "js",
    "external_tslint_repo": "ts",
    "external_psalm": "php",
    "external_phpstan": "php",
    "external_detekt": "kotlin",
    "external_ktlint": "kotlin",
    "external_govet": "go",
    "external_gometalinter": "go",
    "external_golangci-lint": "go",
    "external_golint": "go",
    "external_valgrind-cpp": "cpp",
    "external_rubocop": "ruby",
    "external_pmd": "java",
    "external_checkstyle": "java",
    "external_spotbugs": "java",
    "fb-contrib": "java",
    "findbugs": "java",
    "external_scalastyle": "scala",
    "external_scapegoat": "scala",
    "external_roslyn": "cs",
    "external_swiftLint": "swift",
    "external_stylelint": "css",
}

CSV_EXPORT_FIELDS = [
    "key",
    "language",
    "repo",
    "securityImpact",
    "reliabilityImpact",
    "maintainabilityImpact",
    "name",
    "ruleType",
    "tags",
    "legacySeverity",
    "legacyType",
]

LEGACY_CSV_EXPORT_FIELDS = ["key", "language", "repo", "type", "severity", "name", "ruleType", "tags"]

_CLASS_LOCK = Lock()


class Rule(SqObject):
    """
    Abstraction of the Sonar Rule concept
    """

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "rules"

    API: dict[str, str] = {c.CREATE: "rules/create", c.READ: "rules/show", c.UPDATE: "rules/update", c.DELETE: "rules/delete", c.LIST: "rules/search"}  # type: ignore

    def __init__(self, endpoint: Platform, key: str, data: ApiPayload) -> None:
        super().__init__(endpoint=endpoint, key=key)
        log.debug("Loading rule object '%s'", key)
        self.sq_json = data.copy()
        self.severity = data.get("severity", None)
        self.repo = data.get("repo", None)
        self.type = data.get("type", None)
        self._impacts = {}
        if "impacts" in data:
            self._impacts = {imp["softwareQuality"]: imp["severity"] for imp in data["impacts"]}
        else:
            if self.type in idefs.STD_TYPES:
                self._impacts = {TYPE_TO_QUALITY[self.type]: self.severity}

        self.tags: Optional[list[str]] = None if len(data.get("tags", [])) == 0 else data["tags"]
        self.systags = data.get("sysTags", [])
        self.name = data.get("name", None)
        self.language = data.get("lang", None)
        if not self.language:
            log.debug("Guessing rule '%s' language from repo '%s'", self.key, str(data.get("repo", "")))
            self.language = EXTERNAL_REPOS.get(data.get("repo", ""), "UNKNOWN")
        self.template_key = data.get("templateKey")
        self.description = data.get("mdDesc")
        self.custom_desc = data.get("mdDesc" if self.template_key else "mdNote")
        self.created_at = data["createdAt"]
        self.is_template = data.get("isTemplate", False)
        self._clean_code_attribute = {
            "attribute": data.get("cleanCodeAttribute", None),
            "attribute_category": data.get("cleanCodeAttributeCategory", None),
        }
        with _CLASS_LOCK:
            Rule.CACHE.put(self)

    @classmethod
    def get_object(cls, endpoint: Platform, key: str) -> Rule:
        """Returns a rule object from it key

        :param endpoint: The SonarQube reference
        :param key: The rule key
        :return: The Rule object corresponding to the input rule key
        :raises: ObjectNotFound if rule does not exist
        """
        if o := Rule.CACHE.get(key, endpoint.local_url):
            return o
        Rule.search_objects(endpoint=endpoint, params={"q": key})
        if o := Rule.CACHE.get(key, endpoint.local_url):
            return o
        raise exceptions.ObjectNotFound(key, f"Rule key '{key}' not found")

    @classmethod
    def get_external_rule(cls, endpoint: Platform, key: str) -> Rule:
        """Returns an external rule object from it key, that may not be listed by a search

        :param endpoint: The SonarQube reference
        :param key: The rule key
        :return: The Rule object corresponding to the input rule key
        :raises: ObjectNotFound if rule does not exist
        """
        if o := Rule.CACHE.get(key, endpoint.local_url):
            return o
        rule_data = json.loads(endpoint.get(Rule.API[c.READ], params={"key": key, "actives": "true"}).text)["rule"]
        return Rule(endpoint=endpoint, key=key, data=rule_data)

    @classmethod
    def create(cls, endpoint: Platform, key: str, **kwargs) -> Rule:
        """Creates a rule object

        :param endpoint: The SonarQube reference
        :param key: The rule key
        :param kwargs: Additional parameters to create the rule
        :return: The created rule object
        :raises: UnsupportedOperation if the rule creation is not supported on SonarQube Cloud
        :raises: SonarException if the rule creation fails
        """
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't create or extend rules on SonarQube Cloud")
        params = kwargs.copy()
        (_, params["customKey"]) = key.split(":")
        params["impacts"] = ";".join([f"{k}={v}" for k, v in params.get("impacts", {}).items()])
        log.debug("Creating rule key '%s'", key)
        params.pop("severity" if endpoint.is_mqr_mode() else "impacts", None)
        endpoint.post(cls.API[c.CREATE], params=params)
        created_rule = cls.get_object(endpoint=endpoint, key=key)
        created_rule.custom_desc = kwargs.get("markdownDescription", "NO DESCRIPTION")
        return created_rule

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> Rule:
        """Loads a rule object with a SonarQube API payload"""
        key = data["key"]
        if o := Rule.CACHE.get(key, endpoint.local_url):
            o.reload(data)
            return o
        return cls(key=key, endpoint=endpoint, data=data)

    @classmethod
    def instantiate(cls, endpoint: Platform, key: str, template_key: str, data: ObjectJsonRepr) -> Rule:
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't instantiate rules on SonarQube Cloud")
        try:
            rule = Rule.get_object(endpoint, key)
            log.info("Rule key '%s' already exists, instantiation skipped..., returning %s", key, rule)
            return rule
        except exceptions.ObjectNotFound:
            pass
        log.info("Instantiating rule key '%s' from template key '%s'", key, template_key)
        rule_params = ";".join(
            [f'{p["key"]}={str(p.get("value", "")).lower() if isinstance(p["value"], bool) else p.get("value", "")}' for p in data["params"]]
        )
        return Rule.create(
            key=key,
            endpoint=endpoint,
            templateKey=template_key,
            name=data.get("name", key),
            impacts={k.upper(): v.upper() for k, v in data.get("impacts", {}).items()} if "impacts" in data else None,
            severity=data.get("severity").upper() if "severity" in data else None,
            params=rule_params,
            markdownDescription=data.get("description", "NO DESCRIPTION"),
        )

    def __str__(self) -> str:
        return f"rule key '{self.key}'"

    def refresh(self, use_cache: bool = True) -> bool:
        """Refreshes a rule object from the platform

        :param use_cache: If True, will use the cache to avoid unnecessary calls
        :return: True if the rule was actually refreshed, False cache was used
        """
        if use_cache and "actives" in self.sq_json:
            return False

        try:
            data = json.loads(self.get(Rule.API[c.READ], params=self.api_params() | {"actives": "true"}).text)
        except exceptions.ObjectNotFound:
            Rule.CACHE.pop(self)
            raise
        self.sq_json.update(data["rule"])
        self.sq_json["actives"] = data["actives"].copy()
        return True

    def is_extended(self) -> bool:
        """Returns True if the rule has been extended with tags or a custom description, False otherwise"""
        return self.tags is not None or (not self.template_key and self.custom_desc is not None)

    def is_instantiated(self) -> bool:
        """Returns True if the rule is instantiated from a template, False otherwise"""
        return self.template_key is not None

    def to_json(self) -> ObjectJsonRepr:
        return util.remove_nones(self.sq_json | {"templateKey": self.template_key})

    def to_csv(self) -> list[str]:
        data = vars(self)
        tags = self.systags + (self.tags if self.tags else [])
        data["tags"] = ",".join(sorted(tags))
        data["ruleType"] = "STANDARD"
        if self.is_template:
            data["ruleType"] = "TEMPLATE"
        elif self.template_key:
            data["ruleType"] = "INSTANTIATED"
        if self.endpoint.version() >= c.MQR_INTRO_VERSION:
            data["legacySeverity"] = data.pop("severity", "")
            data["legacyType"] = data.pop("type", "")
            for qual in idefs.MQR_QUALITIES:
                data[qual.lower() + "Impact"] = self._impacts.get(qual, "")
            return [data[key] for key in CSV_EXPORT_FIELDS]
        else:
            return [data[key] for key in LEGACY_CSV_EXPORT_FIELDS]

    def export(self, full: bool = False) -> ObjectJsonRepr:
        """Returns the JSON corresponding to a rule export"""
        rule = self.to_json()
        d = {"severity": rule.get("severity", ""), "impacts": self.impacts(), "description": self.custom_desc}
        if len(rule.get("params", [])) > 0:
            params = util.sort_list_by_key(rule["params"], "key")
            d["params"] = {p["key"]: p for p in params} if full else {p["key"]: p.get("defaultValue", "") for p in params}
        mapping = {"isTemplate": "isTemplate", "tags": "tags", "lang": "language", "templateKey": "templateKey"}
        d |= {newkey: rule[oldkey] for oldkey, newkey in mapping.items() if oldkey in rule}
        if not d["isTemplate"]:
            d.pop("isTemplate", None)
        if full:
            d.update({f"_{k}": v for k, v in rule.items() if k not in ("severity", "params", "isTemplate", "tags", "mdNote", "lang")})
            d.pop("_key", None)
        return util.remove_nones(d)

    def set_tags(self, tags: list[str]) -> bool:
        """Sets rule custom tags"""
        log.info("Setting %s custom tags to '%s' ", str(self), str(tags))
        if ok := self.post(Rule.API[c.UPDATE], params=self.api_params() | {"tags": util.list_to_csv(tags)}).ok:
            self.tags = sorted(tags) if len(tags) > 0 else None
        return ok

    def reset_tags(self) -> bool:
        """Removes all custom tags from the rule"""
        log.debug("Removing custom tags from %s", str(self))
        return self.set_tags([])

    def set_description(self, description: str) -> bool:
        """Extends rule description"""
        if self.endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't extend rules description on SonarQube Cloud")
        log.info("Setting %s custom description to '%s'", str(self), description)
        if ok := self.post(Rule.API[c.UPDATE], params=self.api_params() | {"markdown_note": description}).ok:
            self.custom_desc = description if description != "" else None
        return ok

    def reset_description(self) -> bool:
        """Resets rule custom description"""
        return self.set_description("")

    def clean_code_attribute(self) -> dict[str, str]:
        """Returns the rule clean code attributes"""
        return self._clean_code_attribute

    def impacts(self, quality_profile_id: Optional[str] = None, substitute_with_default: bool = True) -> dict[str, str]:
        """Returns the rule clean code attributes"""
        found_qp = None
        if quality_profile_id:
            if "actives" not in self.sq_json:
                self.refresh()
            found_qp = next((qp for qp in self.sq_json.get("actives", []) if quality_profile_id and qp["qProfile"] == quality_profile_id), None)
        if not found_qp:
            return self._impacts if len(self._impacts) > 0 else {TYPE_TO_QUALITY[self.type]: self.severity}
        if self.endpoint.is_mqr_mode():
            qp_impacts = {imp["softwareQuality"]: imp["severity"] for imp in found_qp["impacts"]}
            default_impacts = self._impacts
        else:
            qp_impacts = {TYPE_TO_QUALITY[self.type]: self.severity}
            default_impacts = {TYPE_TO_QUALITY[self.type]: self.severity}

        if substitute_with_default:
            return {k: c.DEFAULT if qp_impacts[k] == default_impacts.get(k, qp_impacts[k]) else v for k, v in qp_impacts.items()}
        return qp_impacts

    def rule_severity(self, quality_profile_id: Optional[str] = None, substitute_with_default: bool = True) -> str:
        """Returns the severity, potentially customized in a QP"""
        found_qp = None
        if quality_profile_id:
            if "actives" not in self.sq_json:
                self.refresh()
            found_qp = next((qp for qp in self.sq_json.get("actives", []) if quality_profile_id and qp["qProfile"] == quality_profile_id), None)
        if not found_qp:
            return c.DEFAULT if substitute_with_default else self.severity
        return c.DEFAULT if substitute_with_default and found_qp["severity"] == self.severity else found_qp["severity"]

    def __get_quality_profile_data(self, quality_profile_id: str) -> Optional[dict[str, str]]:
        if not quality_profile_id:
            return None
        self.refresh()
        return next((qp for qp in self.sq_json.get("actives", []) if qp["qProfile"] == quality_profile_id), None)

    def is_prioritized_in_quality_profile(self, quality_profile_id: str) -> bool:
        """Returns True if the rule is a prioritized rule in a given quality profile, False otherwise"""
        if (found_qp := self.__get_quality_profile_data(quality_profile_id)) is None:
            return False
        return found_qp.get("prioritizedRule", False)

    def custom_parameters_in_quality_profile(self, quality_profile_id: str) -> Optional[dict[str, str]]:
        """Returns the rule custom params in the QP if any, else None"""
        if (found_qp := self.__get_quality_profile_data(quality_profile_id)) is None:
            return None
        return None if "params" not in found_qp or len(found_qp["params"]) == 0 else {p["key"]: p.get("value", "") for p in found_qp["params"]}

    def api_params(self, op: Optional[str] = None) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {c.READ: {"key": self.key}}
        return ops[op] if op and op in ops else ops[c.READ]


def get_facet(facet: str, endpoint: Platform) -> dict[str, str]:
    """Returns a facet as a count per item in the facet"""
    data = json.loads(endpoint.get(Rule.API[c.SEARCH], params={"ps": 1, "facets": facet}).text)
    return {f["val"]: f["count"] for f in data["facets"][0]["values"]}


def search(endpoint: Platform, params: dict[str, str]) -> dict[str, Rule]:
    """Searches rules with optional filters"""
    return Rule.search_objects(endpoint=endpoint, params=params, threads=4)


def search_keys(endpoint: Platform, **params) -> list[str]:
    """Searches rules with optional filters"""
    new_params = params.copy() if params else {}
    new_params["ps"] = 500
    new_params["p"], nbr_pages = 0, 1
    rule_list = []
    try:
        while new_params["p"] < nbr_pages:
            new_params["p"] += 1
            data = json.loads(endpoint.get(Rule.API[c.SEARCH], params=new_params).text)
            nbr_pages = sutil.nbr_pages(data)
            rule_list += [r[Rule.SEARCH_KEY_FIELD] for r in data[Rule.SEARCH_RETURN_FIELD]]
    except exceptions.SonarException:
        pass
    return rule_list


def count(endpoint: Platform, **params) -> int:
    """Count number of rules that correspond to certain filters"""
    return json.loads(endpoint.get(Rule.API[c.SEARCH], params={**params, "ps": 1}).text)["total"]


def get_list(endpoint: Platform, use_cache: bool = True, **params) -> dict[str, Rule]:
    """Returns a list of rules corresponding to certain search filters"""
    if use_cache and not params and len(Rule.CACHE.objects) > 1000:
        return Rule.CACHE.objects
    rule_list = {}
    lang_list = params.pop("languages", None)
    if not lang_list:
        lang_list = languages.get_list(endpoint).keys()
    if "include_external" in params:
        incl_ext = [str(params["include_external"]).lower()]
    else:
        incl_ext = ["false", "true"]
    for lang_key in lang_list:
        if not languages.exists(endpoint, lang_key):
            raise exceptions.ObjectNotFound(key=lang_key, message=f"Language '{lang_key}' does not exist")
    log.info("Getting rules for %d languages", len(lang_list))
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="RulesList") as executor:
        for lang_key in lang_list:
            futures += [executor.submit(search, endpoint, params | {"languages": lang_key, "include_external": inc}) for inc in incl_ext]
        for future in concurrent.futures.as_completed(futures):
            try:
                rule_list.update(future.result(timeout=30))
            except Exception as e:
                log.error(f"{str(e)} for {str(future)}.")
    log.info("Returning a list of %d rules", len(rule_list))
    return rule_list


def export(endpoint: Platform, export_settings: ConfigSettings, **kwargs) -> ObjectJsonRepr:
    """Returns a JSON export of all rules"""
    log.info("Exporting rules")
    full = export_settings.get("FULL_EXPORT", False)
    threads = 16 if endpoint.is_sonarcloud() else 8
    get_all_rules_details(endpoint=endpoint, threads=export_settings.get("threads", threads))

    all_rules = get_list(endpoint=endpoint, use_cache=False, include_external=False).items()
    rule_list = {}
    rule_list["instantiated"] = {k: rule.export(full) for k, rule in all_rules if rule.is_instantiated()}
    rule_list["extended"] = {k: rule.export(full) for k, rule in all_rules if rule.is_extended()}
    if not full:
        rule_list["extended"] = util.remove_nones(
            {
                k: {"tags": v.get("tags", None), "description": v.get("description", None)}
                for k, v in rule_list["extended"].items()
                if "tags" in v or "description" in v
            }
        )
    if full:
        rule_list["standard"] = {k: rule.export(full) for k, rule in all_rules if not rule.is_instantiated() and not rule.is_extended()}
    if export_settings.get("MODE", "") == "MIGRATION":
        rule_list["thirdParty"] = {r.key: r.export() for r in third_party(endpoint=endpoint)}

    for k in ("instantiated", "extended", "standard", "thirdParty"):
        if len(rule_list.get(k, {})) == 0:
            rule_list.pop(k, None)
    rule_list = rhelp.convert_rules_json(rule_list)
    if write_q := kwargs.get("write_q", None):
        write_q.put(rule_list)
        write_q.put(sutil.WRITE_END)
    return rule_list


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: KeyList = None) -> bool:
    """Imports a sonar-config configuration"""
    if not (rule_data := config_data.get("rules")):
        log.info("No customized rules (custom tags, extended description) to import")
        return True
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Can't import rules in SonarQube Cloud")
    get_list(endpoint=endpoint, use_cache=False)
    log.info("Importing extended rules (custom tags, extended description)")
    converted_data = util.list_to_dict(rule_data.get("extended", []), "key")
    for key, custom in converted_data.items():
        log.info("Importing rule key '%s' with customization %s", key, custom)
        try:
            rule = Rule.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            log.warning("Rule key '%s' does not exist, can't import it", key)
            continue
        if "description" in custom:
            rule.set_description(custom["description"])
        if "tags" in custom:
            rule.set_tags(util.csv_to_list(custom["tags"]))

    log.info("Importing custom rules (instantiated from rule templates)")
    converted_data = util.list_to_dict(rule_data.get("instantiated", []), "key")
    for key, instantiation_data in converted_data.items():
        log.info("Importing instantiated rule key '%s' with instantiation data %s", key, instantiation_data)
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
        except KeyError:
            log.warning("Template key information is mission in config JSON for instantiated rule '%s', rule creation skipped", key)
            continue
        Rule.instantiate(endpoint=endpoint, key=key, template_key=template_rule.key, data=instantiation_data)
    return True


def get_all_rules_details(endpoint: Platform, threads: int = 8) -> bool:
    """Collects all rules details

    :param Platform endpoint: The SonarQube Server or Cloud platform
    :param int threads: Number of threads to parallelize the process
    :return: Whether all rules collection succeeded
    """
    rule_list = get_list(endpoint=endpoint, include_external=False).values()
    ok = True
    if endpoint.is_sonarcloud():
        threads = max(threads, 20)
    log.info("Collecting rules details for %d rules with %d threads", len(rule_list), threads)
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="RuleDetails") as executor:
        futures = [executor.submit(Rule.refresh, rule, True) for rule in rule_list]
        i, nb_rules = 0, len(futures)
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result(timeout=10)
                i += 1
                if i % 100 == 0 or i == nb_rules:
                    log.info("Collected rules details for %d rules out of %d (%d%%)", i, nb_rules, int(100 * i / nb_rules))
            except Exception as e:
                log.error(f"{str(e)} for {str(future)}.")
                ok = False
    return ok


def convert_rule_list_for_yaml(rule_list: ObjectJsonRepr) -> list[ObjectJsonRepr]:
    """Converts a rule dict (key: data) to prepare for yaml by adding severity and key"""
    return util.dict_to_list(rule_list, "key", "severity")


def third_party(endpoint: Platform) -> list[Rule]:
    """Returns the list of rules coming from 3rd party plugins"""
    return [r for r in get_list(endpoint=endpoint).values() if r.repo and r.repo not in SONAR_REPOS and not r.repo.startswith("external_")]


def instantiated(endpoint: Platform) -> list[Rule]:
    """Returns the list of rules that are instantiated"""
    return [r for r in get_list(endpoint=endpoint).values() if r.template_key is not None]


def severities(endpoint: Platform, json_data: dict[str, any]) -> Optional[dict[str, str]]:
    """Returns the list of severities from a given rule JSON data"""
    if endpoint.is_mqr_mode():
        return {impact["softwareQuality"]: impact["severity"] for impact in json_data.get("impacts", [])}
    else:
        return json_data.get("severity", None)
