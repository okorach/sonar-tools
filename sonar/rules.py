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
"""

    Abstraction of the SonarQube "rule" concept

"""
from __future__ import annotations
import json
import concurrent.futures
from threading import Lock
from typing import Optional
from http import HTTPStatus
from requests import RequestException

import sonar.logging as log
import sonar.sqobject as sq
from sonar.util import types, cache, constants as c, issue_defs as idefs
from sonar import platform, utilities, exceptions, languages

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


class Rule(sq.SqObject):
    """
    Abstraction of the Sonar Rule concept
    """

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "rules"

    API = {c.CREATE: "rules/create", c.READ: "rules/show", c.UPDATE: "rules/update", c.DELETE: "rules/delete", c.LIST: "rules/search"}

    def __init__(self, endpoint: platform.Platform, key: str, data: types.ApiPayload) -> None:
        super().__init__(endpoint=endpoint, key=key)
        log.debug("Creating rule object '%s'", key)  # utilities.json_dump(data))
        self.sq_json = data.copy()
        self.severity = data.get("severity", None)
        self.repo = data.get("repo", None)
        self.type = data.get("type", None)
        if "impacts" in data:
            self._impacts = {imp["softwareQuality"]: imp["severity"] for imp in data["impacts"]}
        else:
            if self.type in idefs.STD_TYPES:
                self._impacts = {TYPE_TO_QUALITY[self.type]: self.severity}

        self.tags = None if len(data.get("tags", [])) == 0 else data["tags"]
        self.systags = data.get("sysTags", [])
        self.name = data.get("name", None)
        self.language = data.get("lang", None)
        if not self.language:
            log.debug("Guessing rule '%s' language from repo '%s'", self.key, str(data.get("repo", "")))
            self.language = EXTERNAL_REPOS.get(data.get("repo", ""), "UNKNOWN")
        self.custom_desc = data.get("mdNote", None)
        self.created_at = data["createdAt"]
        self.is_template = data.get("isTemplate", False)
        self.template_key = data.get("templateKey", None)
        self._clean_code_attribute = {
            "attribute": data.get("cleanCodeAttribute", None),
            "attribute_category": data.get("cleanCodeAttributeCategory", None),
        }
        with _CLASS_LOCK:
            Rule.CACHE.put(self)

    @classmethod
    def get_object(cls, endpoint: platform.Platform, key: str) -> Rule:
        """Returns a rule object from the cache or from the platform itself"""
        o = Rule.CACHE.get(key, endpoint.local_url)
        if o:
            return o
        try:
            r = endpoint.get(Rule.API[c.READ], params={"key": key, "actives": "true"})
        except (ConnectionError, RequestException) as e:
            utilities.handle_error(e, f"getting rule {key}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            raise exceptions.ObjectNotFound(key=key, message=f"Rule key '{key}' does not exist")
        return Rule(endpoint=endpoint, key=key, data=json.loads(r.text)["rule"])

    @classmethod
    def create(cls, endpoint: platform.Platform, key: str, **kwargs) -> Optional[Rule]:
        """Creates a rule object"""
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't create or extend rules on SonarQube Cloud")
        params = kwargs.copy()
        (_, params["customKey"]) = key.split(":")
        log.debug("Creating rule key '%s'", key)
        if not endpoint.post(cls.API[c.CREATE], params=params).ok:
            return None
        return cls.get_object(endpoint=endpoint, key=key)

    @classmethod
    def load(cls, endpoint: platform.Platform, key: str, data: types.ApiPayload) -> Rule:
        """Loads a rule object"""
        o = Rule.CACHE.get(key, endpoint.local_url)
        if o:
            o.sq_json.update(data)
            return o
        return cls(key=key, endpoint=endpoint, data=data)

    @classmethod
    def instantiate(cls, endpoint: platform.Platform, key: str, template_key: str, data: types.ObjectJsonRepr) -> Rule:
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Can't instantiate rules on SonarQube Cloud")
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
            severity=data.get("severity", "MEDIUM"),
            params=rule_params,
            markdownDescription=data.get("description", "NO DESCRIPTION"),
        )

    def __str__(self) -> str:
        return f"rule key '{self.key}'"

    def refresh(self, use_cache: bool = True) -> bool:
        """Refreshes a rule object from the platform
        :param use_cache: If True, will use the cache to avoid unnecessary calls
        :return: True if the rule was actually refreshed, False cache was used"""
        if use_cache and "actives" in self.sq_json:
            return False

        try:
            data = json.loads(self.get(Rule.API[c.READ], params={"key": self.key, "actives": "true"}).text)
        except (ConnectionError, RequestException) as e:
            utilities.handle_error(e, f"Reading {self}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            Rule.CACHE.pop(self)
            raise exceptions.ObjectNotFound(key=self.key, message=f"{self} does not exist")
        self.sq_json.update(data["rule"])
        self.sq_json["actives"] = data["actives"].copy()
        return True

    def to_json(self) -> types.ObjectJsonRepr:
        return self.sq_json

    def to_csv(self) -> list[str]:
        data = vars(self)
        tags = self.systags
        if self.tags:
            tags += self.tags
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
            data = [data[key] for key in CSV_EXPORT_FIELDS]
        else:
            data = [data[key] for key in LEGACY_CSV_EXPORT_FIELDS]
        return data

    def export(self, full: bool = False) -> types.ObjectJsonRepr:
        """Returns the JSON corresponding to a rule export"""
        rule = self.to_json()
        if self.endpoint.is_mqr_mode():
            d = {"severities": {impact["softwareQuality"]: impact["severity"] for impact in self.sq_json.get("impacts", [])}}
        else:
            d = {"severity": rule.get("severity", "")}
        if len(rule.get("params", {})) > 0:
            d["params"] = rule["params"] if full else {p["key"]: p.get("defaultValue", "") for p in rule["params"]}
        mapping = {"isTemplate": "isTemplate", "tags": "tags", "mdNote": "description", "lang": "language"}
        for oldkey, newkey in mapping.items():
            if oldkey in rule and rule[oldkey] is not None:
                d[newkey] = rule[oldkey]
        if full:
            d.update({f"_{k}": v for k, v in rule.items() if k not in ("severity", "params", "isTemplate", "tags", "mdNote", "lang")})
            d.pop("_key", None)
        return d

    def set_tags(self, tags: list[str]) -> bool:
        """Sets rule custom tags"""
        log.debug("Settings custom tags of %s to '%s' ", str(self), str(tags))
        ok = self.post(Rule.API[c.UPDATE], params={"key": self.key, "tags": utilities.list_to_csv(tags)}).ok
        if ok:
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
        log.debug("Settings custom description of %s to '%s'", str(self), description)
        ok = self.post(Rule.API[c.UPDATE], params={"key": self.key, "markdown_note": description}).ok
        if ok:
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
            self.refresh()
            found_qp = next((qp for qp in self.sq_json.get("actives", []) if quality_profile_id and qp["qProfile"] == quality_profile_id), None)
        if not found_qp:
            return self._impacts if self.endpoint.is_mqr_mode() else {TYPE_TO_QUALITY[self.type]: self.severity}
        if self.endpoint.is_mqr_mode():
            qp_impacts = {imp["softwareQuality"]: imp["severity"] for imp in found_qp["impacts"]}
            default_impacts = self._impacts
        else:
            qp_impacts = {TYPE_TO_QUALITY[self.type]: self.severity}
            default_impacts = {TYPE_TO_QUALITY[self.type]: self.severity}

        if substitute_with_default:
            return {k: c.DEFAULT if qp_impacts[k] == default_impacts.get(k, qp_impacts[k]) else v for k, v in qp_impacts.items()}
        else:
            return qp_impacts

    def is_prioritized_in_quality_profile(self, quality_profile_id: str) -> bool:
        """Returns True if the rule is a prioritized rule in a given quality profile, False otherwise"""
        found_qp = None
        if quality_profile_id:
            self.refresh()
            found_qp = next((qp for qp in self.sq_json.get("actives", []) if qp["qProfile"] == quality_profile_id), None)
        if not found_qp:
            return False
        return found_qp.get("prioritizedRule", False)

    def api_params(self, op: Optional[str] = None) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {c.READ: {"key": self.key}}
        return ops[op] if op and op in ops else ops[c.READ]


def get_facet(facet: str, endpoint: platform.Platform) -> dict[str, str]:
    """Returns a facet as a count per item in the facet"""
    data = json.loads(endpoint.get(Rule.API[c.SEARCH], params={"ps": 1, "facets": facet}).text)
    return {f["val"]: f["count"] for f in data["facets"][0]["values"]}


def search(endpoint: platform.Platform, params) -> dict[str, Rule]:
    """Searches rules with optional filters"""
    return sq.search_objects(endpoint=endpoint, object_class=Rule, params=params, threads=4)


def search_keys(endpoint: platform.Platform, **params) -> list[str]:
    """Searches rules with optional filters"""
    new_params = params.copy() if params else {}
    new_params["ps"] = 500
    new_params["p"], nbr_pages = 0, 1
    rule_list = []
    try:
        while new_params["p"] < nbr_pages:
            new_params["p"] += 1
            data = json.loads(endpoint.get(Rule.API[c.SEARCH], params=new_params).text)
            nbr_pages = utilities.nbr_pages(data)
            rule_list += [r[Rule.SEARCH_KEY_FIELD] for r in data[Rule.SEARCH_RETURN_FIELD]]
    except (ConnectionError, RequestException) as e:
        utilities.handle_error(e, "searching rules", catch_all=True)
    return rule_list


def count(endpoint: platform.Platform, **params) -> int:
    """Count number of rules that correspond to certain filters"""
    return json.loads(endpoint.get(Rule.API[c.SEARCH], params={**params, "ps": 1}).text)["total"]


def get_list(endpoint: platform.Platform, use_cache: bool = True, **params) -> dict[str, Rule]:
    """Returns a list of rules corresponding to certain search filters"""
    if not use_cache or params or len(Rule.CACHE.objects) < 1000:
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
    return Rule.CACHE.objects


def get_object(endpoint: platform.Platform, key: str) -> Optional[Rule]:
    """Returns a Rule object from its key
    :return: The Rule object corresponding to the input rule key, or None if not found
    :param str key: The rule key
    :rtype: Rule or None
    """
    try:
        return Rule.get_object(key=key, endpoint=endpoint)
    except exceptions.ObjectNotFound:
        return None


def export(endpoint: platform.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Returns a JSON export of all rules"""
    log.info("Exporting rules")
    full = export_settings.get("FULL_EXPORT", False)
    rule_list, other_rules, instantiated_rules, extended_rules = {}, {}, {}, {}
    for rule_key, rule in get_list(endpoint=endpoint, use_cache=False, include_external=False).items():
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

    if write_q := kwargs.get("write_q", None):
        write_q.put(rule_list)
        write_q.put(utilities.WRITE_END)
    return rule_list


def import_config(endpoint: platform.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> bool:
    """Imports a sonar-config configuration"""
    if "rules" not in config_data:
        log.info("No customized rules (custom tags, extended description) to import")
        return True
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Can't import rules in SonarQube Cloud")
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


def get_all_rules_details(endpoint: platform.Platform, threads: int = 8) -> bool:
    """Collects all rules details

    :param Platform endpoint: The SonarQube Server or Cloud platform
    :param int threads: Number of threads to parallelize the process
    :return: Whether all rules collection succeeded
    """
    rule_list = get_list(endpoint=endpoint, include_external=False).values()
    ok = True
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="RuleDetails") as executor:
        futures = [executor.submit(Rule.refresh, rule, True) for rule in rule_list]
        i, nb_rules = 0, len(futures)
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result(timeout=1)
                i += 1
                if i % 100 == 0 or i == nb_rules:
                    log.info("Collected rules details for %d rules out of %d (%d%%)", i, nb_rules, int(100 * i / nb_rules))
            except Exception as e:
                log.error(f"{str(e)} for {str(future)}.")
                ok = False
    return ok


def convert_for_export(rule: types.ObjectJsonRepr, qp_lang: str, with_template_key: bool = True, full: bool = False) -> types.ObjectJsonRepr:
    """Converts rule data for export"""
    d = {"severity": rule.get("severity", "")}
    if len(rule.get("params", {})) > 0:
        d["params"] = rule["params"] if full else {p["key"]: p.get("defaultValue", "") for p in rule["params"]}
    if rule["isTemplate"]:
        d["isTemplate"] = True
    if "tags" in rule and len(rule["tags"]) > 0:
        d["tags"] = rule["tags"]
    if rule.get("mdNote", None) is not None:
        d["description"] = rule["mdNote"]
    if with_template_key and "templateKey" in rule:
        d["templateKey"] = rule["templateKey"]
    if "lang" in rule and rule["lang"] != qp_lang:
        d["language"] = rule["lang"]
    if full:
        d.update({f"_{k}": v for k, v in rule.items() if k not in ("severity", "params", "isTemplate", "tags", "mdNote", "templateKey", "lang")})
        d.pop("_key", None)
    return d


def convert_rule_list_for_yaml(rule_list: types.ObjectJsonRepr) -> list[types.ObjectJsonRepr]:
    """Converts a rule dict (key: data) to prepare for yaml by adding severity and key"""
    return utilities.dict_to_list(rule_list, "key", "severity")


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    clean_json = utilities.remove_nones(original_json)
    return {category: convert_rule_list_for_yaml(clean_json[category]) for category in ("instantiated", "extended") if category in clean_json}


def third_party(endpoint: platform.Platform) -> list[Rule]:
    """Returns the list of rules coming from 3rd party plugins"""
    return [r for r in get_list(endpoint=endpoint).values() if r.repo and r.repo not in SONAR_REPOS and not r.repo.startswith("external_")]


def instantiated(endpoint: platform.Platform) -> list[Rule]:
    """Returns the list of rules that are instantiated"""
    return [r for r in get_list(endpoint=endpoint).values() if r.template_key is not None]


def severities(endpoint: platform.Platform, json_data: dict[str, any]) -> Optional[dict[str, str]]:
    """Returns the list of severities from a given rule JSON data"""
    if endpoint.is_mqr_mode():
        return {impact["softwareQuality"]: impact["severity"] for impact in json_data.get("impacts", [])}
    else:
        return json_data.get("severity", None)
