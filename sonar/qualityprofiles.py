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

"""Abstraction of the SonarQube Quality Profile concept"""
from __future__ import annotations
from typing import Optional
import json
from datetime import datetime
from http import HTTPStatus
import concurrent.futures

from queue import Queue
from threading import Thread, Lock
from requests import RequestException
import requests.utils

import sonar.logging as log
import sonar.platform as pf
from sonar.util import types, cache, constants as c
from sonar import exceptions
from sonar import rules, languages
import sonar.permissions.qualityprofile_permissions as permissions
import sonar.sqobject as sq
import sonar.utilities as util

from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem

_KEY_PARENT = "parent"
_CHILDREN_KEY = "children"

_IMPORTABLE_PROPERTIES = ("name", "language", "parentName", "isBuiltIn", "isDefault", "rules", "permissions", "prioritizedRules")

_CLASS_LOCK = Lock()


class QualityProfile(sq.SqObject):
    """
    Abstraction of the SonarQube "quality profile" concept
    Objects of this class must be created with one of the 3 available class methods. Don't use __init__
    """

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "profiles"
    API = {
        c.CREATE: "qualityprofiles/create",
        c.GET: "qualityprofiles/search",
        c.DELETE: "qualityprofiles/delete",
        c.LIST: "qualityprofiles/search",
        c.RENAME: "qualityprofiles/rename",
    }

    def __init__(self, endpoint: pf.Platform, key: str, data: types.ApiPayload = None) -> None:
        """Do not use, use class methods to create objects"""
        super().__init__(endpoint=endpoint, key=key)

        self.name = data["name"]  #: Quality profile name
        self.language = data["language"]  #: Quality profile language
        self.is_default = data["isDefault"]  #: Quality profile is default
        self.is_built_in = data["isBuiltIn"]  #: Quality profile is built-in - read-only
        self.sq_json = data
        self._permissions = None
        self._rules = None
        self.__last_use = None
        self.__last_update = None

        # self._rules = self.rules()
        self.nbr_rules = int(data["activeRuleCount"])  #: Number of rules in the quality profile
        self.nbr_deprecated_rules = int(data["activeDeprecatedRuleCount"])  #: Number of deprecated rules in the quality profile

        (self._projects, self._projects_lock) = (None, Lock())
        self.project_count = data.get("projectCount", None)  #: Number of projects using this quality profile
        self.parent_name = data.get("parentName", None)  #: Name of parent profile, or None if none

        self.__last_use = util.string_to_date(data.get("lastUsed", None))
        self.__last_update = util.string_to_date(data.get("rulesUpdatedAt", None))

        log.debug("Created %s", str(self))
        QualityProfile.CACHE.put(self)

    @classmethod
    def read(cls, endpoint: pf.Platform, name: str, language: str) -> Optional[QualityProfile]:
        """Creates a QualityProfile object corresponding to quality profile with same name and language in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Quality profile name
        :param str language: Quality profile language
        :return: The quality profile object
        :rtype: QualityProfile or None if not found
        """
        if not languages.exists(endpoint=endpoint, language=language):
            log.error("Language '%s' does not exist, quality profile creation aborted", language)
            return None
        log.debug("Reading quality profile '%s' of language '%s'", name, language)
        o = QualityProfile.CACHE.get(name, language, endpoint.local_url)
        if o:
            return o
        data = util.search_by_name(
            endpoint, name, QualityProfile.API[c.LIST], QualityProfile.SEARCH_RETURN_FIELD, extra_params={"language": language}
        )
        return cls(key=data["key"], endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint: pf.Platform, name: str, language: str) -> Optional[QualityProfile]:
        """Creates a new quality profile in SonarQube and returns the corresponding QualityProfile object

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Quality profile name
        :param str description: Quality profile language
        :return: The quality profile object
        :rtype: QualityProfile or None if creation failed
        """
        if not languages.exists(endpoint=endpoint, language=language):
            log.error("Language '%s' does not exist, quality profile creation aborted")
            return None
        log.debug("Creating quality profile '%s' of language '%s'", name, language)
        try:
            endpoint.post(QualityProfile.API[c.CREATE], params={"name": name, "language": language})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"creating quality profile '{language}:{name}'", catch_http_statuses=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(f"{language}:{name}", e.response.text)
        return cls.read(endpoint=endpoint, name=name, language=language)

    @classmethod
    def clone(cls, endpoint: pf.Platform, name: str, language: str, original_qp_name: str) -> Optional[QualityProfile]:
        """Creates a new quality profile in SonarQube with rules copied from original_key

        :param endpoint: Reference to the SonarQube platform
        :param name: Quality profile name
        :param language: Quality profile language
        :param original_qp_name: Original quality profile name
        :return: The cloned quality profile object
        """
        log.info("Cloning quality profile name '%s' into quality profile name '%s'", original_qp_name, name)
        l = [qp for qp in get_list(endpoint, use_cache=False).values() if qp.name == original_qp_name and qp.language == language]
        if len(l) != 1:
            raise exceptions.ObjectNotFound(f"{language}:{original_qp_name}", f"Quality profile {language}:{original_qp_name} not found")
        original_qp = l[0]
        log.debug("Found QP to clone: %s", str(original_qp))
        try:
            endpoint.post("qualityprofiles/copy", params={"toName": name, "fromKey": original_qp.key})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"cloning {str(original_qp)} into name '{name}'", catch_http_statuses=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(f"{language}:{name}", e.response.text)
        return cls.read(endpoint=endpoint, name=name, language=language)

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> None:
        """Creates a QualityProfile object from the result of a SonarQube API quality profile search data

        :param Platform endpoint: Reference to the SonarQube platform
        :param dict data: The JSON data corresponding to the quality profile
        :type data: dict
        :return: The quality profile object
        :rtype: QualityProfile
        """
        log.debug("Loading quality profile '%s' of language '%s'", data["name"], data["language"])
        return cls(endpoint=endpoint, key=data["key"], data=data)

    def __str__(self) -> str:
        """String formatting of the object"""
        return f"quality profile '{self.name}' of language '{self.language}'"

    def __hash__(self) -> int:
        return hash((self.name, self.language, self.base_url()))

    def url(self) -> str:
        """
        :return: the SonarQube permalink URL to the quality profile
        :rtype: str
        """
        return f"{self.base_url(local=False)}/profiles/show?language={self.language}&name={requests.utils.quote(self.name)}"

    def last_use(self) -> datetime:
        """
        :return: When the quality profile was last used
        :rtype: datetime or None if never
        """
        return self.__last_use

    def last_update(self) -> datetime:
        """
        :return: When the quality profile was last updated
        :rtype: datetime or None
        """
        return self.__last_update

    def set_parent(self, parent_name: str) -> bool:
        """Sets the parent quality profile of the current profile

        :param str parent_name: Name of the parent quality profile
        :return: Whether setting the parent was successful or not
        :rtype: bool
        """
        log.info("Setting parent %s to %s", str(parent_name), self.parent_name)
        if parent_name is None:
            return False
        if get_object(endpoint=self.endpoint, name=parent_name, language=self.language) is None:
            log.warning("Can't set parent name '%s' to %s, parent not found", str(parent_name), str(self))
            return False
        if parent_name == self.name:
            log.error("Can't set %s as parent of itself", str(self))
            return False
        elif self.parent_name is None or self.parent_name != parent_name:
            r = self.post("qualityprofiles/change_parent", params={**self.api_params(c.GET), "parentQualityProfile": parent_name})
            self.parent_name = parent_name
            self.rules(use_cache=False)
            return r.ok
        else:
            log.debug("Won't set parent of %s. It's the same as currently", str(self))
            return True

    def set_as_default(self) -> bool:
        """Sets the quality profile as the default for the language
        :return: Whether setting as default quality profile was successful
        :rtype: bool
        """
        r = self.post("qualityprofiles/set_default", params=self.api_params(c.GET))
        if r.ok:
            self.is_default = True
            # Turn off default for all other profiles except the current profile
            for qp in get_list(self.endpoint).values():
                if qp.language == self.language and qp.key != self.key:
                    qp.is_default = False
        return r.ok

    def is_child(self) -> bool:
        """
        :return: Whether the quality profile has a parent
        :rtype: bool
        """
        return self.parent_name is not None

    def inherits_from_built_in(self) -> bool:
        """
        :return: Whether the quality profile inherits from a built-in profile (following parents of parents)
        :rtype: bool
        """
        return self.built_in_parent() is not None

    def built_in_parent(self) -> Optional[QualityProfile]:
        """
        :return: The built-in parent profile of the profile, or None
        :rtype: QualityProfile or None if profile does not inherit from a built-in profile
        """
        self.is_built_in = self.sq_json.get("isBuiltIn", False)
        if self.is_built_in:
            return self
        if self.parent_name is None:
            return None
        return get_object(endpoint=self.endpoint, name=self.parent_name, language=self.language).built_in_parent()

    def rules(self, use_cache: bool = False) -> dict[str, rules.Rule]:
        """
        :return: The list of rules active in the quality profile
        :rtype: dict{<rule_key>: <rule_data>}
        """
        if self._rules is not None and use_cache:
            # Assume nobody changed QP during execution
            return self._rules
        rule_key_list = rules.search_keys(self.endpoint, activation="true", qprofile=self.key, s="key", languages=self.language)
        self._rules = {k: rules.get_object(self.endpoint, k) for k in rule_key_list}
        return self._rules

    def activate_rule(self, rule_key: str, severity: Optional[str] = None, **params) -> bool:
        """Activates a rule in the quality profile

        :param str rule_key: Rule key to activate
        :param str severity: Severity of the rule in the quality profiles, defaults to the rule default severity
        :param params: List of parameters associated to the rules, defaults to None
        :return: Whether the activation succeeded
        :rtype: bool
        """
        log.debug("Activating rule %s in %s", rule_key, str(self))
        api_params = {"key": self.key, "rule": rule_key, "severity": severity}
        if len(params) > 0:
            api_params["params"] = ";".join([f"{k}={v}" for k, v in params.items()])
        try:
            r = self.post("qualityprofiles/activate_rule", params=api_params)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"activating rule {rule_key} in {str(self)}", catch_all=True)
            return False
        if self._rules is None:
            self._rules = {}
        self._rules[rule_key] = rules.get_object(self.endpoint, rule_key)
        return r.ok

    def deactivate_rule(self, rule_key: str) -> bool:
        """Deactivates a rule in the quality profile

        :param str rule_key: Rule key to deactivate
        :return: Whether the deactivation succeeded
        :rtype: bool
        """
        log.debug("Deactivating rule %s in %s", rule_key, str(self))
        try:
            r = self.post("qualityprofiles/deactivate_rule", params={"key": self.key, "rule": rule_key})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"deactivating rule {rule_key} in {str(self)}", catch_all=True)
            return False
        return r.ok

    def deactivate_rules(self, ruleset: list[str]) -> bool:
        """Deactivates a list of rules in the quality profile
        :return: Whether the deactivation of all rules was successful
        :rtype: bool
        """
        ok = True
        for r_key in ruleset:
            ok = ok and self.deactivate_rule(rule_key=r_key)
        self.rules(use_cache=False)
        return ok

    def activate_rules(self, ruleset: list[dict[str, str]]) -> bool:
        """Activates a list of rules in the quality profile
        :return: Whether the activation of all rules was successful
        :rtype: bool
        """
        ok = True
        ruleset_d = {r["key"]: r for r in ruleset}
        log.info("%s: Activating rules %s", self, util.json_dump(ruleset_d))
        for r_key, r_data in ruleset_d.items():
            sev = r_data if isinstance(r_data, str) else r_data.get("severity", None)
            if "params" in r_data:
                ok = ok and self.activate_rule(rule_key=r_key, severity=sev, **r_data["params"])
            else:
                ok = ok and self.activate_rule(rule_key=r_key, severity=sev)
        self.rules(use_cache=False)
        return ok

    def set_rules(self, ruleset: list[dict[str, str]]) -> bool:
        """Sets the quality profile with a set of rules. If the quality profile current has rules
        not in the ruleset these rules are deactivated
        :return: Whether the quality profile was set with all the given rules
        :rtype: bool
        """
        if not ruleset:
            return False
        current_rules = list(self.rules(use_cache=False).keys())
        ruleset_d = {r["key"]: r for r in ruleset}
        log.info("%s: Setting rules %s", self, util.json_dump(ruleset_d))
        keys_to_activate = util.difference(list(ruleset_d.keys()), current_rules)
        rules_to_activate = [ruleset_d[k] for k in keys_to_activate]
        rules_to_deactivate = util.difference(current_rules, list(ruleset_d.keys()))
        log.info("set_rules: Activating %d rules and deactivating %d rules", len(rules_to_activate), len(rules_to_deactivate))
        ok = self.activate_rules(rules_to_activate)
        ok = ok and self.deactivate_rules(rules_to_deactivate)
        return ok

    def update(self, data: types.ObjectJsonRepr) -> QualityProfile:
        """Updates a QP with data coming from sonar-config"""
        if self.is_built_in:
            log.debug("Not updating built-in %s", str(self))
        else:
            log.debug("Updating %s with %s", str(self), str(data))
            if "name" in data and data["name"] != self.name:
                log.info("Renaming %s with %s", str(self), data["name"])
                self.post(QualityProfile.API[c.RENAME], params={"id": self.key, "name": data["name"]})
                QualityProfile.CACHE.pop(self)
                self.name = data["name"]
                QualityProfile.CACHE.put(self)
            self.set_parent(data.pop(_KEY_PARENT, None))
            self.set_rules(data.get("rules", []) + data.get("addedRules", []))
            self.activate_rules(data.get("modifiedRules", []))
            self.set_permissions(data.get("permissions", []))
            self.is_built_in = data.get("isBuiltIn", False)
            if data.get("isDefault", False):
                self.set_as_default()

        for child_name, child_data in data.get(_CHILDREN_KEY, {}).items():
            try:
                child_qp = get_object(self.endpoint, child_name, self.language)
            except exceptions.ObjectNotFound:
                child_qp = QualityProfile.create(self.endpoint, child_name, self.language)
            child_qp.update(child_data | {_KEY_PARENT: self.name})
        return self

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """
        :param export_settings: Settings for export, such as whether to export all rules or only the active ones
        :return: the quality profile properties as JSON dict
        """
        json_data = self.sq_json.copy()
        json_data.update({"name": self.name, "language": self.language, "parentName": self.parent_name})
        full = export_settings.get("FULL_EXPORT", False)
        if not self.is_default:
            json_data.pop("isDefault", None)
        if not self.is_built_in:
            json_data.pop("isBuiltIn", None)
            json_data["rules"] = []
            for rule in self.rules().values():
                data = {k: v for k, v in rule.export(full).items() if k not in ("isTemplate", "templateKey", "language", "tags", "severities")}
                if self.rule_is_prioritized(rule.key):
                    data["prioritized"] = True
                if self.rule_has_custom_severities(rule.key):
                    data["severities"] = self.rule_impacts(rule.key, substitute_with_default=True)
                json_data["rules"].append({"key": rule.key, **data})
        json_data["permissions"] = self.permissions().export(export_settings)
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))

    def compare(self, another_qp: QualityProfile) -> dict[str, str]:
        """Compares 2 quality profiles rulesets
        :param QualityProfile another_qp: The second quality profile to compare with self
        :return: dict result of the compare ("inLeft", "inRight", "same", "modified")
        """
        data = json.loads(self.get("qualityprofiles/compare", params={"leftKey": self.key, "rightKey": another_qp.key}).text)
        for r in data["inLeft"] + data["same"] + data["inRight"] + data["modified"]:
            for k in ("name", "pluginKey", "pluginName", "languageKey", "languageName"):
                r.pop(k, None)
        return data

    def api_params(self, op: str = c.GET) -> types.ApiParams:
        operations = {
            c.GET: {"qualityProfile": self.name, "language": self.language},
            c.LIST: {"q": self.name, "language": self.language},
            c.DELETE: {"qualityProfile": self.name, "language": self.language},
        }
        return operations[op] if op in operations else operations[c.GET]

    def rule_impacts(self, rule_key: str, substitute_with_default: bool = True) -> dict[str, str]:
        """Returns the severities of a rule in the quality profile

        :param str rule_key: The rule key to get severities for
        :return: The severities of the rule in the quality profile
        :rtype: dict[str, str]
        """
        return rules.get_object(self.endpoint, rule_key).impacts(self.key, substitute_with_default=substitute_with_default)

    def __process_rules_diff(self, rule_set: dict[str:str]) -> dict[str:str]:
        diff_rules = {}
        for rule in rule_set:
            r_key = rule["key"]
            diff_rules[r_key] = {}
            if self.rule_has_custom_severities(r_key):
                diff_rules[r_key]["severities"] = self.rule_impacts(r_key, substitute_with_default=True)
            if self.rule_is_prioritized(r_key):
                diff_rules[r_key]["prioritized"] = True
            rule_params = rule["left"].get("params", {}) if "left" in rule else rule.get("params", {})
            if len(rule_params) > 0:
                diff_rules[r_key]["params"] = rule_params
        return [{"key": k, **v} for k, v in diff_rules.items()]

    def diff(self, another_qp: QualityProfile) -> dict[str:str]:
        """Returns the list of rules added or modified in self compared to another_qp (for inheritance)
        :param another_qp: The second quality profile to diff
        :type another_qp: QualityProfile
        :return: dict result of the diff ("inLeft", "modified")
        :rtype: dict
        """
        log.debug("Comparing %s and %s", str(self), str(another_qp))
        compare_result = self.compare(another_qp)
        diff_rules = {"addedRules": {}, "modifiedRules": {}}
        if len(compare_result["inLeft"]) > 0:
            diff_rules["addedRules"] = self.__process_rules_diff(compare_result["inLeft"])
        if len(compare_result["modified"]) > 0:
            diff_rules["modifiedRules"] = self.__process_rules_diff(compare_result["modified"])
        if len(compare_result["inRight"]) > 0:
            diff_rules["removedRules"] = {r["key"]: True for r in compare_result["inRight"]}
        elif self.endpoint.version() >= (10, 3, 0):
            diff_rules["removedRules"] = {}
        return diff_rules

    def projects(self) -> types.KeyList:
        """Returns the list of projects keys using this quality profile
        :return: List of projects using explicitly this QP
        :rtype: List[project_key]
        """

        with self._projects_lock:
            if self._projects is None:
                self._projects = []
                params = {"key": self.key, "ps": 500}
                page = 1
                more = True
                while more:
                    params["p"] = page
                    data = json.loads(self.get("qualityprofiles/projects", params=params).text)
                    log.debug("Got QP %s data = %s", self.key, str(data))
                    self._projects += [p["key"] for p in data["results"]]
                    page += 1
                    if self.endpoint.version() >= (10, 0, 0):
                        more = util.nbr_pages(data) >= page
                    else:
                        more = data["more"]

                log.debug("Projects for %s = '%s'", str(self), ", ".join(self._projects))
        return self._projects

    def used_by_project(self, project: object) -> bool:
        """
        :param Project project: The project
        :return: Whether the quality profile is used by the project
        :rtype: bool
        """
        return project.key in self.projects()

    def rule_has_custom_severities(self, rule_key: str) -> bool:
        """Checks whether the rule has a custom severity in the quality profile

        :param str rule_key: The rule key to check
        :return: Whether the rule has a some custom severities in the quality profile
        """
        if self.endpoint.is_sonarcloud():
            return False
        rule = rules.Rule.get_object(self.endpoint, rule_key)
        log.debug(
            "Checking if rule %s has custom severities in %s: %s - result %s",
            rule_key,
            str(self),
            str(rule.impacts(quality_profile_id=self.key, substitute_with_default=True)),
            any(sev != c.DEFAULT for sev in rule.impacts(quality_profile_id=self.key, substitute_with_default=True).values()),
        )
        return any(sev != c.DEFAULT for sev in rule.impacts(quality_profile_id=self.key, substitute_with_default=True).values())

    def rule_is_prioritized(self, rule_key: str) -> bool:
        """Checks whether the rule is prioritized in the quality profile

        :param str rule_key: The rule key to check
        :return: Whether the rule is prioritized in the quality profile
        """
        return rules.Rule.get_object(self.endpoint, rule_key).is_prioritized_in_quality_profile(self.key)

    def permissions(self) -> permissions.QualityProfilePermissions:
        """
        :return: The list of users and groups that can edit the quality profile
        """
        if self._permissions is None:
            self._permissions = permissions.QualityProfilePermissions(self)
        return self._permissions

    def set_permissions(self, perms: types.ObjectJsonRepr) -> bool:
        """Sets the list of users and groups that can can edit the quality profile
        :params perms: Dict of permissions to set ({"users": <users comma separated>, "groups": <groups comma separated>})
        :return: Whether the operation was successful
        """
        return self.permissions().set(perms)

    def audit(self, audit_settings: types.ConfigSettings = None) -> list[Problem]:
        """Audits a quality profile and return list of problems found

        :param dict audit_settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        """
        log.info("Auditing %s", str(self))
        if self.is_built_in:
            log.info("%s is built-in, skipping audit", str(self))
            return []

        log.debug("Auditing %s (key '%s')", str(self), self.key)
        problems = []
        age = util.age(self.last_update(), rounded=True)
        if age > audit_settings.get("audit.qualityProfiles.maxLastChangeAge", 180):
            problems.append(Problem(get_rule(RuleId.QP_LAST_CHANGE_DATE), self, str(self), age))

        total_rules = rules.count(endpoint=self.endpoint, languages=self.language)
        if self.nbr_rules < int(total_rules * audit_settings.get("audit.qualityProfiles.minNumberOfRules", 0.5)):
            problems.append(Problem(get_rule(RuleId.QP_TOO_FEW_RULES), self, str(self), self.nbr_rules, total_rules))

        age = util.age(self.last_use(), rounded=True)
        if self.project_count == 0 or age is None:
            problems.append(Problem(get_rule(RuleId.QP_NOT_USED), self, str(self)))
        elif age > audit_settings.get("audit.qualityProfiles.maxUnusedAge", 60):
            rule = get_rule(RuleId.QP_LAST_USED_DATE)
            problems.append(Problem(rule, self, str(self), age))
        if audit_settings.get("audit.qualityProfiles.checkDeprecatedRules", True):
            max_deprecated_rules = 0
            parent_qp = self.built_in_parent()
            if parent_qp is not None:
                max_deprecated_rules = parent_qp.nbr_deprecated_rules
            if self.nbr_deprecated_rules > max_deprecated_rules:
                problems.append(Problem(get_rule(RuleId.QP_USE_DEPRECATED_RULES), self, str(self), self.nbr_deprecated_rules))
        problems += self.permissions().audit(audit_settings)
        return problems

    def is_identical_to(self, another_qp: QualityProfile) -> bool:
        """Checks whether the quality profile is identical to another quality profile

        :param QualityProfile another_qp: The other quality profile to compare with
        :return: Whether the quality profiles are identical
        :rtype: bool
        """
        data = self.compare(another_qp)
        return all(data.get(k, []) == [] for k in ("inLeft", "inRight", "modified"))


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, QualityProfile]:
    """Searches projects in SonarQube

    param Platform endpoint: Reference to the SonarQube platform
    :param dict params: list of parameters to filter quality profiles to search
    :return: list of quality profiles
    :rtype: dict{key: QualityProfile}
    """
    return sq.search_objects(endpoint=endpoint, object_class=QualityProfile, params=params)


def get_list(endpoint: pf.Platform, use_cache: bool = True) -> dict[str, QualityProfile]:
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :param bool use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :return: the list of all quality profiles
    :rtype: dict{key: QualityProfile}
    """

    with _CLASS_LOCK:
        if len(QualityProfile.CACHE) == 0 or not use_cache:
            QualityProfile.CACHE.clear()
            search(endpoint=endpoint)
    return QualityProfile.CACHE.objects


def __audit_duplicate(qp1: QualityProfile, qp2: QualityProfile) -> list[Problem]:
    if qp2.is_identical_to(qp1):
        return [Problem(get_rule(RuleId.QP_DUPLICATES), qp1, qp1.name, qp2.name, qp1.language)]
    return []


def __audit_duplicates(qp_list: dict[str, QualityProfile], audit_settings: types.ConfigSettings = None) -> list[Problem]:
    """Audits for duplicate quality profiles
    :param qp_list: dict of QP indexed with their key
    :param audit_settings: Audit settings to use
    """
    if not audit_settings.get("audit.qualityProfiles.duplicates", True):
        return []
    log.info("Auditing for duplicate quality profiles")
    problems = []
    langs = {qp.language for qp in qp_list.values()}
    pairs = set()
    for lang in sorted(langs):
        lang_qp_list = {k: qp for k, qp in qp_list.items() if qp.language == lang}
        pairs |= {(key1, key2) if key1 < key2 else (key2, key1) for key1 in lang_qp_list.keys() for key2 in lang_qp_list.keys() if key1 != key2}

    threads = audit_settings.get("threads", 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="QPDuplication") as executor:
        futures = [executor.submit(__audit_duplicate, qp_list[key1], qp_list[key2]) for (key1, key2) in pairs]
        for future in concurrent.futures.as_completed(futures):
            try:
                problems += future.result(timeout=30)
            except Exception as e:
                log.error(f"{str(e)} for {str(future)}.")
    return problems


def __audit_nbr_of_qp(qp_list: dict[str, QualityProfile], audit_settings: types.ConfigSettings = None) -> list[Problem]:
    """Audits for duplicate quality profiles"""
    if (max_qp := audit_settings.get("audit.qualityProfiles.maxPerLanguage", 5)) == 0:
        log.info("Auditing for number of quality profiles per disabled, skipping...")
        return []
    log.info("Auditing for number of quality profiles per language, max %d", max_qp)
    langs = {}
    problems = []
    for qp in qp_list.values():
        endpoint = qp.endpoint
        langs[qp.language] = langs.get(qp.language, 0) + 1
    for lang, nb_qp in langs.items():
        if nb_qp > max_qp:
            rule = get_rule(RuleId.QP_TOO_MANY_QP)
            problems.append(Problem(rule, f"{endpoint.external_url}/profiles?language={lang}", nb_qp, lang, max_qp))
    return problems


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings = None, **kwargs) -> list[Problem]:
    """Audits all quality profiles and return list of problems found

    :param endpoint: reference to the SonarQube platform
    :param audit_settings: Configuration of audit
    :return: list of problems found
    """
    if not audit_settings.get("audit.qualityProfiles", True):
        log.info("Auditing quality profiles is disabled, audit skipped...")
        return []
    log.info("--- Auditing quality profiles ---")
    rules.get_list(endpoint=endpoint)
    problems = []
    qp_list = search(endpoint=endpoint)
    for qp in qp_list.values():
        problems += qp.audit(audit_settings)
    problems += __audit_nbr_of_qp(qp_list=qp_list, audit_settings=audit_settings)
    problems += __audit_duplicates(qp_list=qp_list, audit_settings=audit_settings)
    "write_q" in kwargs and kwargs["write_q"].put(problems)
    return problems


def hierarchize_language(qp_list: dict[str, str], endpoint: pf.Platform, language: str) -> types.ObjectJsonRepr:
    """Organizes a flat list of quality profiles in inheritance hierarchy"""
    log.debug("Organizing QP list %s in hierarchy", str(qp_list.keys()))
    hierarchy = qp_list.copy()
    to_remove = []
    for qp_name, qp_json_data in hierarchy.items():
        if "parentName" in qp_json_data:
            if qp_json_data["parentName"] not in hierarchy:
                log.critical("Can't find parent %s in quality profiles", qp_json_data["parentName"])
                continue
            parent_qp_name = qp_json_data.pop("parentName")
            parent_qp = hierarchy[parent_qp_name]
            if _CHILDREN_KEY not in parent_qp:
                parent_qp[_CHILDREN_KEY] = {}
            this_qp = get_object(endpoint=endpoint, name=qp_name, language=language)
            qp_json_data |= this_qp.diff(get_object(endpoint=endpoint, name=parent_qp_name, language=language))
            qp_json_data.pop("rules", None)
            parent_qp[_CHILDREN_KEY][qp_name] = qp_json_data
            to_remove.append(qp_name)
    for qp_name in to_remove:
        hierarchy.pop(qp_name)
    return hierarchy


def hierarchize(qp_list: types.ObjectJsonRepr, endpoint: pf.Platform) -> types.ObjectJsonRepr:
    """Organize a flat list of QP in hierarchical (inheritance) fashion

    :param qp_list: List of quality profiles
    :type qp_list: {<language>: {<qp_name>: <qd_data>}}
    :return: Same list with child profiles nested in their parent
    :rtype: {<language>: {<qp_name>: {"children": <qp_list>; <qp_data>}}}
    """
    log.info("Organizing quality profiles in hierarchy")
    return {lang: hierarchize_language(lang_qp_list, endpoint=endpoint, language=lang) for lang, lang_qp_list in qp_list.items()}


def flatten_language(language: str, qp_list: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Converts a hierarchical list of QP of a given language into a flat list"""
    flat_list = {}
    for qp_name, qp_data in qp_list.copy().items():
        if _CHILDREN_KEY in qp_data:
            children = flatten_language(language, qp_data[_CHILDREN_KEY])
            for child in children.values():
                if "parent" not in child:
                    child["parent"] = f"{language}:{qp_name}"
            qp_data.pop(_CHILDREN_KEY)
            flat_list.update(children)
        flat_list[f"{language}:{qp_name}"] = qp_data
    return flat_list


def flatten(qp_list: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Organize a hierarchical list of QP in a flat list"""
    flat_list = {}
    for lang, lang_qp_list in qp_list.items():
        flat_list.update(flatten_language(lang, lang_qp_list))
    return flat_list


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports all or a list of quality profiles configuration as dict

    :param ConfigSettings export_settings: Export parameters
    :return: Dict of quality profiles JSON representation
    """
    log.info("Exporting quality profiles")
    rules.get_all_rules_details(endpoint=endpoint, threads=export_settings.get("threads", 8))
    qp_list = {}
    for qp in get_list(endpoint=endpoint).values():
        log.info("Exporting %s", str(qp))
        json_data = qp.to_json(export_settings=export_settings)
        lang = json_data.pop("language")
        name = json_data.pop("name")
        if lang not in qp_list:
            qp_list[lang] = {}
        qp_list[lang][name] = json_data
    qp_list = hierarchize(qp_list, endpoint=endpoint)
    if write_q := kwargs.get("write_q", None):
        write_q.put(qp_list)
        write_q.put(util.WRITE_END)
    return dict(sorted(qp_list.items()))


def get_object(endpoint: pf.Platform, name: str, language: str) -> Optional[QualityProfile]:
    """Returns a quality profile Object from its name and language

    :param endpoint: Reference to the SonarQube platform
    :param name: Quality profile name
    :param language: Quality profile language

    :return: The quality profile object, of None if not found
    """
    get_list(endpoint)
    o = QualityProfile.CACHE.get(name, language, endpoint.local_url)
    if not o:
        raise exceptions.ObjectNotFound(name, message=f"Quality Profile '{language}:{name}' not found")
    return o


def import_qp(endpoint: pf.Platform, name: str, lang: str, qp_data: types.ObjectJsonRepr) -> bool:
    """Function for multithreaded QP import"""
    try:
        o = get_object(endpoint=endpoint, name=name, language=lang)
    except exceptions.ObjectNotFound:
        log.info("Quality profile '%s' of language '%s' does not exist, creating it", name, lang)
        try:
            # Statistically a new QP is close to Sonar way so better start with the Sonar way ruleset and
            # add/remove a few rules, than adding all rules from 0
            o = QualityProfile.clone(endpoint=endpoint, name=name, language=lang, original_qp_name="Sonar way")
        except Exception:
            o = QualityProfile.create(endpoint=endpoint, name=name, language=lang)
    log.info("Importing %s", o)
    o.update(qp_data)
    log.info("Imported %s", o)


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> bool:
    """Imports a configuration in SonarQube

    :param Platform endpoint: reference to the SonarQube platform
    :param dict config_data: the configuration to import
    :return: Whether the operation succeeded
    """
    threads = 8
    if "qualityProfiles" not in config_data:
        log.info("No quality profiles to import")
        return False
    log.info("Importing quality profiles")
    get_list(endpoint=endpoint)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="QPImport") as executor:
        futures, futures_map = [], {}
        for lang, lang_data in config_data["qualityProfiles"].items():
            if not languages.exists(endpoint=endpoint, language=lang):
                log.warning("Language '%s' does not exist, quality profiles import skipped for this language", lang)
                continue
            for name, qp_data in lang_data.items():
                futures.append(future := executor.submit(import_qp, endpoint, name, lang, qp_data))
                futures_map[future] = f"quality profile '{name}' of language '{lang}'"
        for future in concurrent.futures.as_completed(futures):
            qp = futures_map[future]
            try:
                _ = future.result(timeout=60)
            except TimeoutError as e:
                log.error(f"Importing {qp} timed out after 60 seconds for {str(future)}.")
            except Exception as e:
                log.error(f"Exception {str(e)} when importing {qp} or its chilren.")
    return True


def exists(endpoint: pf.Platform, name: str, language: str) -> bool:
    """
    :param Platform endpoint: reference to the SonarQube platform
    :param str name: Quality profile name
    :param str language: Quality profile language
    :return: whether the project exists
    :rtype: bool
    """
    try:
        get_object(endpoint=endpoint, name=name, language=language)
        return True
    except exceptions.ObjectNotFound:
        return False


def convert_one_qp_yaml(qp: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Converts a QP in a modified version more suitable for YAML export"""

    if _CHILDREN_KEY in qp:
        qp[_CHILDREN_KEY] = {k: convert_one_qp_yaml(q) for k, q in qp[_CHILDREN_KEY].items()}
        qp[_CHILDREN_KEY] = util.dict_to_list(qp[_CHILDREN_KEY], "name")
    return qp


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    new_json = {}
    for lang, qp_list in util.remove_nones(original_json).items():
        new_json[lang] = {"profiles": util.dict_to_list(qp_list, "name")}
    new_json = util.dict_to_list(new_json, "language")
    for lang in new_json:
        lang["profiles"] = [convert_one_qp_yaml(qp) for qp in lang["profiles"]]
    return new_json
