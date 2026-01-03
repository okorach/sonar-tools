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
from typing import Optional, Any, TYPE_CHECKING

import json
from datetime import datetime
from copy import deepcopy
import traceback
import concurrent.futures

from threading import Lock
import requests.utils

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache, constants as c
from sonar.util import qualityprofile_helper as qphelp
from sonar import exceptions
from sonar import rules, languages
import sonar.permissions.qualityprofile_permissions as permissions
import sonar.util.misc as util
import sonar.utilities as sutil

from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
from sonar.api.manager import ApiOperation as op
from sonar.api.manager import ApiManager as Api

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr, KeyList, ConfigSettings

_IMPORTABLE_PROPERTIES = ("name", "language", "parentName", "isBuiltIn", "isDefault", "rules", "permissions", "prioritizedRules")

_CLASS_LOCK = Lock()


class QualityProfile(SqObject):
    """
    Abstraction of the SonarQube "quality profile" concept
    Objects of this class must be created with one of the 3 available class methods. Don't use __init__
    """

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "profiles"

    def __init__(self, endpoint: Platform, key: str, data: ApiPayload = None) -> None:
        """Do not use, use class methods to create objects"""
        super().__init__(endpoint=endpoint, key=key)

        self.name = data["name"]  #: Quality profile name
        self.language = data["language"]  #: Quality profile language
        self.is_default = data["isDefault"]  #: Quality profile is default
        self.is_built_in = data["isBuiltIn"]  #: Quality profile is built-in - read-only
        self.sq_json = data
        self._permissions: Optional[object] = None
        self._rules: Optional[dict[str, rules.Rule]] = None
        self.__last_use: Optional[datetime] = None
        self.__last_update: Optional[datetime] = None

        # self._rules = self.rules()
        self.nbr_rules = int(data["activeRuleCount"])  #: Number of rules in the quality profile
        self.nbr_deprecated_rules = int(data["activeDeprecatedRuleCount"])  #: Number of deprecated rules in the quality profile

        (self._projects, self._projects_lock) = (None, Lock())
        self.project_count = data.get("projectCount", None)  #: Number of projects using this quality profile
        self.parent_name = data.get("parentName", None)  #: Name of parent profile, or None if none

        self.__last_use = sutil.string_to_date(data.get("lastUsed", None))
        self.__last_update = sutil.string_to_date(data.get("rulesUpdatedAt", None))

        log.debug("Created %s", str(self))
        QualityProfile.CACHE.put(self)

    def __str__(self) -> str:
        """String formatting of the object"""
        return f"quality profile '{self.name}' of language '{self.language}'"

    def __hash__(self) -> int:
        return hash((self.name, self.language, self.base_url()))

    @classmethod
    def get_object(cls, endpoint: Platform, name: str, language: str) -> QualityProfile:
        """Returns a quality profile from its name and language

        :param endpoint: Reference to the SonarQube platform
        :param name: Quality profile name
        :param language: Quality profile language

        :return: The quality profile object, of None if not found
        """
        get_list(endpoint)
        if o := cls.CACHE.get(name, language, endpoint.local_url):
            return o
        raise exceptions.ObjectNotFound(name, message=f"Quality Profile '{language}:{name}' not found")

    @classmethod
    def read(cls, endpoint: Platform, name: str, language: str) -> Optional[QualityProfile]:
        """Creates a QualityProfile object corresponding to quality profile with same name and language in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Quality profile name
        :param str language: Quality profile language
        :return: The quality profile object
        :rtype: QualityProfile or None if not found
        """
        if not languages.Language.exists(endpoint=endpoint, language=language):
            log.error("Language '%s' does not exist, quality profile creation aborted", language)
            return None
        log.debug("Reading quality profile '%s' of language '%s'", name, language)
        o = QualityProfile.CACHE.get(name, language, endpoint.local_url)
        if o:
            return o
        api, _, _, _ = Api(cls, op.LIST, endpoint).get_all()
        data = sutil.search_by_name(endpoint, name, api, QualityProfile.SEARCH_RETURN_FIELD, extra_params={"language": language})
        return cls(key=data["key"], endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint: Platform, name: str, language: str) -> Optional[QualityProfile]:
        """Creates a new quality profile in SonarQube and returns the corresponding QualityProfile object

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Quality profile name
        :param str description: Quality profile language
        :return: The quality profile object
        :rtype: QualityProfile or None if creation failed
        """
        if not languages.Language.exists(endpoint=endpoint, language=language):
            log.error("Language '%s' does not exist, quality profile creation aborted")
            return None
        log.debug("Creating quality profile '%s' of language '%s'", name, language)
        api, _, params, _ = Api(cls, op.CREATE, endpoint).get_all(name=name, language=language)
        endpoint.post(api, params=params)
        return cls.read(endpoint=endpoint, name=name, language=language)

    @classmethod
    def clone(cls, endpoint: Platform, name: str, language: str, original_qp_name: str) -> Optional[QualityProfile]:
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
        api, _, params, _ = Api(cls, op.COPY, endpoint).get_all(toName=name, fromKey=original_qp.key)
        endpoint.post(api, params=params)
        return cls.read(endpoint=endpoint, name=name, language=language)

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> None:
        """Creates a QualityProfile object from the result of a SonarQube API quality profile search data

        :param Platform endpoint: Reference to the SonarQube platform
        :param dict data: The JSON data corresponding to the quality profile
        :type data: dict
        :return: The quality profile object
        :rtype: QualityProfile
        """
        log.debug("Loading quality profile '%s' of language '%s'", data["name"], data["language"])
        return cls(endpoint=endpoint, key=data["key"], data=data)

    @classmethod
    def api_for(cls, operation: op, endpoint: Platform) -> str:
        """Returns the API to use for a particular operation"""
        api, _, _, _ = Api(cls, operation, endpoint).get_all()
        return api

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
            api, _, params, _ = Api(self, op.CHANGE_PARENT).get_all(
                qualityProfile=self.name, language=self.language, parentQualityProfile=parent_name
            )
            r = self.post(api, params=params)
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
        api, _, params, _ = Api(self, op.SET_DEFAULT).get_all(qualityProfile=self.name, language=self.language)
        r = self.post(api, params=params)
        if r.ok:
            self.is_default = True
            # Turn off default for all other profiles except the current profile
            for qp in get_list(self.endpoint).values():
                if qp.language == self.language and qp.key != self.key:
                    qp.is_default = False
        return r.ok

    def delete(self) -> bool:
        """Deletes the quality profile

        :return: Whether the deletion was successful
        :rtype: bool
        """
        return self.delete_object(**self.api_params(op.DELETE))

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
        self._rules = {k: rules.Rule.get_object(self.endpoint, k) for k in rule_key_list}
        return self._rules

    def activate_rule(
        self, rule_key: str, impacts: Optional[dict[str, str]] = None, severity: Optional[str] = None, prioritized: bool = False, **params
    ) -> bool:
        """Activates a rule in the quality profile

        :param rule_key: Rule key to activate
        :param impacts: Impacts of the rule in the quality profile, defaults to the rule default impacts
        :param severity: Severity of the rule in the quality profiles, defaults to the rule default severity
        :param prioritized: Whether the rule is prioritized, defaults to False
        :param params: List of parameters associated to the rules, defaults to None
        :return: Whether the activation succeeded
        :rtype: bool
        """
        log.debug("Activating rule %s in %s", rule_key, str(self))
        api_params = {"key": self.key, "rule": rule_key, "prioritizedRule": prioritized}
        if not self.endpoint.is_mqr_mode():
            api_params["severity"] = severity
        elif impacts:
            api_params = {"key": self.key, "rule": rule_key, "impacts": ";".join([f"{k.upper()}={v.upper()}" for k, v in impacts.items()])}
        if len(params) > 0:
            str_params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
            api_params["params"] = ";".join([f"{k}={v}" for k, v in str_params.items()])
        try:
            api, _, _, _ = Api(self, op.ACTIVATE_RULE).get_all()
            ok = self.post(api, params=api_params).ok
        except exceptions.SonarException:
            return False
        self._rules = self._rules or {}
        self._rules[rule_key] = rules.Rule.get_object(self.endpoint, rule_key)
        return ok

    def deactivate_rule(self, rule_key: str) -> bool:
        """Deactivates a rule in the quality profile

        :param str rule_key: Rule key to deactivate
        :return: Whether the deactivation succeeded
        :rtype: bool
        """
        log.debug("Deactivating rule %s in %s", rule_key, str(self))
        try:
            api, _, params, _ = Api(self, op.DEACTIVATE_RULE).get_all(key=self.key, rule=rule_key)
            return self.post(api, params=params).ok
        except exceptions.SonarException:
            return False

    def deactivate_rules(self, ruleset: list[str]) -> bool:
        """Deactivates a list of rules in the quality profile
        :return: Whether the deactivation of all rules was successful
        :rtype: bool
        """
        ok = True
        for r_key in ruleset:
            ok = self.deactivate_rule(rule_key=r_key) and ok
        self.rules(use_cache=False)
        return ok

    def activate_rules(self, ruleset: list[dict[str, Any]]) -> bool:
        """Activates a list of rules in the quality profile
        :return: Whether the activation of all rules was successful
        :rtype: bool
        """
        ok = True
        ruleset_d = util.list_to_dict(ruleset, "key", keep_in_values=True)
        log.info("%s: Activating rules %s", self, util.json_dump(ruleset_d))
        for r_key, r_data in ruleset_d.items():
            sev = r_data.get("severity").upper() if "severity" in r_data else None
            impacts = {k.upper(): v.upper() for k, v in r_data.get("impacts", {}).items()} if "impacts" in r_data else None
            rule_params = {p["key"]: p["value"] for p in r_data["params"]} if "params" in r_data else {}
            ok = ok and self.activate_rule(rule_key=r_key, impacts=impacts, severity=sev, prioritized=r_data.get("prioritized", False), **rule_params)
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
        ruleset_d = util.list_to_dict(ruleset, "key", keep_in_values=True)
        log.debug("%s: Setting rules %s", self, util.json_dump(ruleset_d))
        keys_to_activate = list(set(ruleset_d.keys()) - set(current_rules))
        keys_to_activate += [
            r["key"]
            for r in ruleset_d.values()
            if any(r.get(k) for k in ("prioritized", "params", "severity", "impacts")) and r["key"] not in keys_to_activate
        ]
        rules_to_activate = [ruleset_d[k] for k in keys_to_activate]
        rules_to_deactivate = list(set(current_rules) - set(ruleset_d.keys()))
        log.info("set_rules: Activating %d rules and deactivating %d rules", len(rules_to_activate), len(rules_to_deactivate))
        ok = self.activate_rules(rules_to_activate)
        ok = ok and self.deactivate_rules(rules_to_deactivate)
        return ok

    def update(self, data: ObjectJsonRepr) -> QualityProfile:
        """Updates a QP with data coming from sonar-config"""
        if self.is_built_in or data.get("isBuiltIn", False):
            log.debug("Not updating built-in %s", self)
        else:
            log.debug("Updating %s with %s", self, data)
            if "name" in data and data["name"] != self.name:
                log.info("Renaming %s with %s", self, data["name"])
                api, _, params, _ = Api(self, op.RENAME).get_all(id=self.key, name=data["name"])
                self.post(api, params=params)
                QualityProfile.CACHE.pop(self)
                self.name = data["name"]
                QualityProfile.CACHE.put(self)
            log.debug("Updating %s setting parent to %s", self, data.get(qphelp.KEY_PARENT))
            if parent_key := data.pop(qphelp.KEY_PARENT, None):
                self.set_parent(parent_key)
                parent_qp = get_object(self.endpoint, parent_key, self.language)
                log.info("%s activating parent rules %s", self, list(parent_qp.rules().keys()))
                self.activate_rules([{"key": k} for k in parent_qp.rules()])
            self.activate_rules(data.get("rules", []) + data.get("addedRules", []) + data.get("modifiedRules", []))
            self.deactivate_rules(data.get("removedRules", []))
            self.set_permissions(data.get("permissions", []))
            self.is_built_in = data.get("isBuiltIn", False)
        if data.get("isDefault", False):
            self.set_as_default()
        if not data.get(qphelp.KEY_CHILDREN):
            log.debug("%s has no children, end of update", self)
            return self
        log.debug("%s has children, updating children", self)
        children_data = util.list_to_dict(data[qphelp.KEY_CHILDREN], "name", keep_in_values=True)
        for child_name, child_data in children_data.items():
            try:
                child_qp = get_object(self.endpoint, child_name, self.language)
            except exceptions.ObjectNotFound:
                child_qp = QualityProfile.create(self.endpoint, child_name, self.language)
            try:
                child_qp.update(child_data | {qphelp.KEY_PARENT: self.name})
            except Exception as e:
                traceback.print_exc()
                log.error("Child quality Profile import error: %s", e)
                continue
        return self

    def to_json(self, export_settings: ConfigSettings) -> ObjectJsonRepr:
        """
        :param export_settings: Settings for export, such as whether to export all rules or only the active ones
        :return: the quality profile properties as JSON dict
        """
        json_data = self.sq_json.copy()
        json_data.update({"name": self.name, "language": self.language, "parentName": self.parent_name})
        full: bool = export_settings.get("FULL_EXPORT", False)
        if not self.is_default:
            json_data.pop("isDefault", None)
        if not self.is_built_in:
            json_data.pop("isBuiltIn", None)
            json_data["rules"] = []
            for rule in self.rules().values():
                data = {
                    k: v
                    for k, v in rule.export(full).items()
                    if k not in ("isTemplate", "templateKey", "language", "tags", "severity", "severities", "impacts")
                }
                if "params" in data:
                    if rule.is_instantiated():
                        data.pop("params")
                    else:
                        data["params"] = dict(sorted(data["params"].items()))
                if self.rule_is_prioritized(rule.key):
                    data["prioritized"] = True
                if self.rule_has_custom_severity(rule.key):
                    data["severity"] = self.rule_severity(rule.key, substitute_with_default=True)
                if self.rule_has_custom_impacts(rule.key):
                    data["impacts"] = {k: v for k, v in self.rule_impacts(rule.key, substitute_with_default=True).items() if v != c.DEFAULT}
                json_data["rules"].append({"key": rule.key, **data})
        json_data["permissions"] = self.permissions().export(export_settings)
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))

    def compare(self, another_qp: QualityProfile) -> dict[str, str]:
        """Compares 2 quality profiles rulesets
        :param QualityProfile another_qp: The second quality profile to compare with self
        :return: dict result of the compare ("inLeft", "inRight", "same", "modified")
        """
        api, _, params, _ = Api(self, op.COMPARE).get_all(leftKey=self.key, rightKey=another_qp.key)
        data = json.loads(self.get(api, params=params).text)
        for r in data["inLeft"] + data["same"] + data["inRight"] + data["modified"]:
            for k in ("name", "pluginKey", "pluginName", "languageKey", "languageName"):
                r.pop(k, None)
        return data

    def api_params(self, operation: Optional[op] = None) -> ApiParams:
        operations = {
            op.GET: {"qualityProfile": self.name, "language": self.language},
            op.LIST: {"q": self.name, "language": self.language},
            op.DELETE: {"qualityProfile": self.name, "language": self.language},
        }
        return operations[operation] if operation and operation in operations else operations[op.GET]

    def rule_impacts(self, rule_key: str, substitute_with_default: bool = True) -> dict[str, str]:
        """Returns the impacts of a rule in the quality profile

        :param str rule_key: The rule key to get severities for
        :return: The impacts of the rule in the quality profile
        """
        return rules.Rule.get_object(self.endpoint, rule_key).impacts(self.key, substitute_with_default=substitute_with_default)

    def rule_severity(self, rule_key: str, substitute_with_default: bool = True) -> str:
        """Returns the severity of a rule in the quality profile

        :param str rule_key: The rule key to get severities for
        :return: The severity
        """
        return rules.Rule.get_object(self.endpoint, rule_key).rule_severity(self.key, substitute_with_default=substitute_with_default)

    def __process_rules_diff(self, rule_set: dict[str, str]) -> list[dict[str, str]]:
        diff_rules = {}
        for rule in rule_set:
            r_key = rule["key"]
            o_rule = rules.Rule.get_object(self.endpoint, r_key)
            diff_rules[r_key] = {}
            if self.rule_has_custom_severity(r_key):
                diff_rules[r_key]["severity"] = self.rule_severity(r_key, substitute_with_default=True)
            if self.rule_has_custom_impacts(r_key):
                diff_rules[r_key]["impacts"] = {k: v for k, v in self.rule_impacts(r_key, substitute_with_default=True).items() if v != c.DEFAULT}
            if self.rule_is_prioritized(r_key):
                diff_rules[r_key]["prioritized"] = True
            if (params := self.rule_custom_params(r_key)) is not None and not o_rule.is_instantiated():
                diff_rules[r_key]["params"] = params.copy()
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
            diff_rules["addedRules"] = util.sort_list_by_key(self.__process_rules_diff(compare_result["inLeft"]), "key")
        if len(compare_result["modified"]) > 0:
            diff_rules["modifiedRules"] = util.sort_list_by_key(self.__process_rules_diff(compare_result["modified"]), "key")
        if len(compare_result["inRight"]) > 0:
            diff_rules["removedRules"] = sorted(r["key"] for r in compare_result["inRight"])
        elif self.endpoint.version() >= (10, 3, 0):
            diff_rules["removedRules"] = []
        return diff_rules

    def projects(self) -> KeyList:
        """Returns the list of projects keys using this quality profile
        :return: List of projects using explicitly this QP
        :rtype: List[project_key]
        """

        with self._projects_lock:
            if self._projects is None:
                self._projects = []
                page = 1
                more = True
                while more:
                    api, _, params, ret = Api(self, op.GET_PROJECTS).get_all(key=self.key, ps=500, p=page)
                    data = json.loads(self.get(api, params=params).text)
                    log.debug("Got QP %s data = %s", self.key, str(data))
                    self._projects += [p["key"] for p in data[ret]]
                    page += 1
                    if self.endpoint.version() >= (10, 0, 0):
                        more = sutil.nbr_pages(data) >= page
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

    def rule_has_custom_impacts(self, rule_key: str) -> bool:
        """Checks whether the rule has custom impacts in the quality profile

        :param str rule_key: The rule key to check
        :return: Whether the rule has a some custom impacts in the quality profile
        """
        if self.endpoint.is_sonarcloud():
            return False
        rule = rules.Rule.get_object(self.endpoint, rule_key)
        impacts = rule.impacts(quality_profile_id=self.key, substitute_with_default=True)
        has_custom = any(sev != c.DEFAULT for sev in impacts.values())
        log.debug(
            "Checking if rule %s has custom impacts in %s: %s - result %s",
            rule_key,
            str(self),
            str(impacts),
            has_custom,
        )
        return has_custom

    def rule_has_custom_severity(self, rule_key: str) -> bool:
        """Checks whether the rule has custom impacts in the quality profile

        :param str rule_key: The rule key to check
        :return: Whether the rule has a some custom severity in the quality profile
        """
        if self.endpoint.is_sonarcloud():
            return False
        rule = rules.Rule.get_object(self.endpoint, rule_key)
        sev = rule.rule_severity(quality_profile_id=self.key, substitute_with_default=True)
        log.debug(
            "Checking if rule %s has custom impacts in %s: %s - result %s",
            rule_key,
            str(self),
            sev,
            sev != c.DEFAULT,
        )
        return sev != c.DEFAULT

    def rule_is_prioritized(self, rule_key: str) -> bool:
        """Checks whether the rule is prioritized in the quality profile

        :param str rule_key: The rule key to check
        :return: Whether the rule is prioritized in the quality profile
        """
        return rules.Rule.get_object(self.endpoint, rule_key).is_prioritized_in_quality_profile(self.key)

    def rule_custom_params(self, rule_key: str) -> Optional[dict[str, str]]:
        """Returns the rule custom params in the quality profile if any, None otherwise

        :param str rule_key: The rule key to check
        """
        return rules.Rule.get_object(self.endpoint, rule_key).custom_parameters_in_quality_profile(self.key)

    def permissions(self) -> permissions.QualityProfilePermissions:
        """
        :return: The list of users and groups that can edit the quality profile
        """
        if self._permissions is None:
            self._permissions = permissions.QualityProfilePermissions(self)
        return self._permissions

    def set_permissions(self, perms: ObjectJsonRepr) -> bool:
        """Sets the list of users and groups that can can edit the quality profile
        :params perms: Dict of permissions to set ({"users": <users comma separated>, "groups": <groups comma separated>})
        :return: Whether the operation was successful
        """
        return self.permissions().set(perms)

    def audit_too_few_rules(self, audit_settings: ConfigSettings = None) -> list[Problem]:
        """Audits a quality profile that woudl have too few rules

        :param dict audit_settings: Options of what to audit and thresholds to raise problems
        :return: A problem if the quality profile has too few rules, None otherwise
        """
        if self.is_built_in:
            return []
        total_rules = rules.count(endpoint=self.endpoint, languages=self.language)
        if self.nbr_rules < int(total_rules * audit_settings.get("audit.qualityProfiles.minNumberOfRules", 0.5)):
            return [Problem(get_rule(RuleId.QP_TOO_FEW_RULES), self, str(self), self.nbr_rules, total_rules)]
        return []

    def audit_not_used(self, audit_settings: ConfigSettings = None) -> list[Problem]:
        """Audits whether a QP is used, raise problem if not used, or last use date is more than 60 days"""
        age = util.age(self.last_use(), rounded=True)
        if self.project_count == 0 or age is None:
            return [Problem(get_rule(RuleId.QP_NOT_USED), self, str(self))]
        elif age > audit_settings.get("audit.qualityProfiles.maxUnusedAge", 60):
            rule = get_rule(RuleId.QP_LAST_USED_DATE)
            return [Problem(rule, self, str(self), age)]
        return []

    def audit_last_change_date(self, audit_settings: ConfigSettings = None) -> list[Problem]:
        """Audits if a QP is changed sufficiently frequently, raise problem if not"""
        if (age := util.age(self.last_update(), rounded=True)) > audit_settings.get("audit.qualityProfiles.maxLastChangeAge", 180):
            return [Problem(get_rule(RuleId.QP_LAST_CHANGE_DATE), self, str(self), age)]
        return []

    def audit_deprecated_rules(self, audit_settings: ConfigSettings = None) -> list[Problem]:
        """Audits a quality profile for deprecated rules"""
        if audit_settings.get("audit.qualityProfiles.checkDeprecatedRules", True):
            max_deprecated_rules = 0
            if (parent_qp := self.built_in_parent()) is not None:
                max_deprecated_rules = parent_qp.nbr_deprecated_rules
            if self.nbr_deprecated_rules > max_deprecated_rules:
                return [Problem(get_rule(RuleId.QP_USE_DEPRECATED_RULES), self, str(self), self.nbr_deprecated_rules)]
        return []

    def audit(self, audit_settings: ConfigSettings = None) -> list[Problem]:
        """Audits a quality profile and return list of problems found

        :param dict audit_settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        """
        log.info("Auditing %s", str(self))
        if self.is_built_in:
            log.info("%s is built-in, skipping audit", str(self))
            return []

        log.debug("Auditing %s (key '%s')", str(self), self.key)
        problems = self.audit_last_change_date(audit_settings)
        problems += self.audit_too_few_rules(audit_settings)
        problems += self.audit_not_used(audit_settings)
        problems += self.audit_deprecated_rules(audit_settings)
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


def search(endpoint: Platform, params: ApiParams = None) -> dict[str, QualityProfile]:
    """Searches projects in SonarQube

    param Platform endpoint: Reference to the SonarQube platform
    :param dict params: list of parameters to filter quality profiles to search
    :return: list of quality profiles
    :rtype: dict{key: QualityProfile}
    """
    return QualityProfile.get_paginated(endpoint=endpoint, params=params)


def get_list(endpoint: Platform, use_cache: bool = True) -> dict[str, QualityProfile]:
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


def __audit_duplicates(qp_list: dict[str, QualityProfile], audit_settings: ConfigSettings = None) -> list[Problem]:
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


def __audit_nbr_of_qp(qp_list: dict[str, QualityProfile], audit_settings: ConfigSettings = None) -> list[Problem]:
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


def audit(endpoint: Platform, audit_settings: ConfigSettings = None, **kwargs) -> list[Problem]:
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


def hierarchize_language(qp_list: dict[str, str], endpoint: Platform, language: str) -> ObjectJsonRepr:
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
            if qphelp.KEY_CHILDREN not in parent_qp:
                parent_qp[qphelp.KEY_CHILDREN] = {}
            this_qp = QualityProfile.get_object(endpoint=endpoint, name=qp_name, language=language)
            qp_json_data |= this_qp.diff(QualityProfile.get_object(endpoint=endpoint, name=parent_qp_name, language=language))
            qp_json_data.pop("rules", None)
            parent_qp[qphelp.KEY_CHILDREN][qp_name] = qp_json_data
            to_remove.append(qp_name)
    for qp_name in to_remove:
        hierarchy.pop(qp_name)
    return hierarchy


def hierarchize(qp_list: ObjectJsonRepr, endpoint: Platform) -> ObjectJsonRepr:
    """Organize a flat list of QP in hierarchical (inheritance) fashion

    :param qp_list: List of quality profiles
    :type qp_list: {<language>: {<qp_name>: <qd_data>}}
    :return: Same list with child profiles nested in their parent
    :rtype: {<language>: {<qp_name>: {"children": <qp_list>; <qp_data>}}}
    """
    log.info("Organizing quality profiles in hierarchy")
    return {lang: hierarchize_language(lang_qp_list, endpoint=endpoint, language=lang) for lang, lang_qp_list in qp_list.items()}


def export(endpoint: Platform, export_settings: ConfigSettings, **kwargs) -> ObjectJsonRepr:
    """Exports all or a list of quality profiles configuration as dict

    :param ConfigSettings export_settings: Export parameters
    :return: Dict of quality profiles JSON representation
    """
    log.info("Exporting quality profiles")
    rules.get_all_rules_details(endpoint=endpoint, threads=export_settings.get("threads", 8))
    qp_list = {}
    for qp in get_list(endpoint=endpoint).values():
        log.debug("Exporting %s", str(qp))
        json_data = qp.to_json(export_settings=export_settings)
        lang = json_data.pop("language")
        name = json_data.pop("name")
        if lang not in qp_list:
            qp_list[lang] = {}
        qp_list[lang][name] = json_data
    qp_list = hierarchize(qp_list, endpoint=endpoint)
    qp_list = qphelp.convert_qps_json(qp_list)
    if write_q := kwargs.get("write_q", None):
        write_q.put(qp_list)
        write_q.put(sutil.WRITE_END)
    # return dict(sorted(qp_list.items()))
    return qp_list


def import_qp(endpoint: Platform, name: str, lang: str, qp_data: ObjectJsonRepr) -> bool:
    """Function for multithreaded QP import"""
    try:
        o = get_object(endpoint=endpoint, name=name, language=lang)
    except exceptions.ObjectNotFound:
        log.info("Quality profile '%s' of language '%s' does not exist, creating it", name, lang)
        o = QualityProfile.create(endpoint=endpoint, name=name, language=lang)
    log.info("Importing %s", o)
    o.update(qp_data)
    log.info("Imported %s", o)
    return True


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: KeyList = None) -> bool:
    """Imports a configuration in SonarQube

    :param Platform endpoint: reference to the SonarQube platform
    :param dict config_data: the configuration to import
    :return: Whether the operation succeeded
    """
    config_data = deepcopy(config_data)
    if not (qps_data := config_data.get("qualityProfiles", None)):
        log.info("No quality profiles to import")
        return False
    log.info("Importing quality profiles")
    get_list(endpoint=endpoint)

    qps_data = util.list_to_dict(qps_data, "language", keep_in_values=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="QPImport") as executor:
        futures, futures_map = [], {}
        for lang, lang_data in qps_data.items():
            lang_data = util.list_to_dict(lang_data["profiles"], "name", keep_in_values=True)
            if not languages.Language.exists(endpoint=endpoint, language=lang):
                log.warning("Language '%s' does not exist, quality profiles import skipped for this language", lang)
                continue
            for name, qps_data in lang_data.items():
                futures.append(future := executor.submit(import_qp, endpoint, name, lang, qps_data))
                futures_map[future] = f"quality profile '{name}' of language '{lang}'"
        for future in concurrent.futures.as_completed(futures):
            qp = futures_map[future]
            try:
                _ = future.result(timeout=60)
            except TimeoutError:
                log.error(f"Importing {qp} timed out after 60 seconds for {str(future)}.")
            except Exception as e:
                log.error(f"Exception {str(e)} when importing {qp} or its chilren.")
    return True
