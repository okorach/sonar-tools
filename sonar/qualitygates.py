#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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

"""Abstraction of the SonarQube "quality gate" concept"""

from __future__ import annotations
from typing import Optional, Any, TYPE_CHECKING

import json

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache
from sonar import measures, exceptions
from sonar import projects
import sonar.permissions.qualitygate_permissions as permissions
import sonar.util.misc as util
import sonar.utilities as sutil

from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
from sonar.util import common_json_helper
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr, KeyList, ConfigSettings

__MAX_ISSUES_SHOULD_BE_ZERO = "Any numeric threshold on number of issues should be 0 or should be removed from QG conditions"
__THRESHOLD_ON_OVERALL_CODE = "Threshold on overall code should not be too strict or passing the QG will often be impossible"
__RATING_A = "Any rating other than A would let vulnerabilities slip through in new code"
__SCA_THRESHOLD = "SCA severity threshold on overall code should not be too low"

SCA_HIGH = 19

GOOD_QG_CONDITIONS = {
    "new_reliability_rating": (1, 1, __RATING_A),
    "new_reliability_rating_with_aica": (1, 1, __RATING_A),
    "new_software_quality_reliability_rating": (1, 1, __RATING_A),
    "new_software_quality_maintainability_rating": (1, 1, __RATING_A),
    "new_software_quality_security_rating": (1, 1, __RATING_A),
    "new_security_rating": (1, 1, __RATING_A),
    "new_security_rating_with_aica": (1, 1, __RATING_A),
    "new_maintainability_rating": (1, 1, "Expectation is that code smells density on new code is low enough to get A rating"),
    "new_coverage": (20, 90, "Coverage below 20% is a too low bar, above 90% is overkill"),
    "new_duplicated_lines_density": (1, 5, "Duplication on new code of less than 1% is overkill, more than 5% is too relaxed"),
    "new_vulnerabilities": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_bugs": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_code_smells": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_security_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_reliability_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_maintainability_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_violations": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_blocker_violations": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_critical_violations": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_major_violations": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_minor_violations": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_security_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_reliability_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_maintainability_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_blocker_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_high_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_medium_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_low_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_maintainability_debt_ratio": (1.0, 20.0, "Maintainability debt ratio should be between 1% and 20% to be acceptable"),
    "new_security_hotspots": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "new_security_hotspots_reviewed": (100, 100, "All hotspots on new code must be reviewed, any other condition than 100% make little sense"),
    "security_rating": (4, 4, __THRESHOLD_ON_OVERALL_CODE),
    "reliability_rating": (4, 4, __THRESHOLD_ON_OVERALL_CODE),
    "software_quality_security_rating": (3, 4, __THRESHOLD_ON_OVERALL_CODE),
    "software_quality_reliability_rating": (3, 4, __THRESHOLD_ON_OVERALL_CODE),
    "sca_severity_any_issue": (SCA_HIGH, SCA_HIGH, __SCA_THRESHOLD),
    "sca_rating_any_issue": (3, 5, __SCA_THRESHOLD),
    "sca_severity_licensing": (SCA_HIGH, SCA_HIGH, __SCA_THRESHOLD),
    "sca_severity_vulnerability": (SCA_HIGH, SCA_HIGH, __SCA_THRESHOLD),
    "new_sca_severity_licensing": (0, 1000, ""),
    "new_sca_severity_any_issue": (0, 1000, ""),
    "new_sca_severity_vulnerability": (0, 1000, ""),
    "blocker_violations": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "critical_violations": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "software_quality_blocker_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "software_quality_high_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
    "prioritized_rule_issues": (0, 0, __MAX_ISSUES_SHOULD_BE_ZERO),
}

_IMPORTABLE_PROPERTIES = ("name", "isDefault", "isBuiltIn", "conditions", "permissions")


class QualityGate(SqObject):
    """Abstraction of the SonarQube Quality Gate concept"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, name: str, data: ApiPayload) -> None:
        """Constructor, don't use directly, use class methods instead"""
        super().__init__(endpoint=endpoint, key=name)
        self.name = name  #: Object name
        # Override key with id if present
        self.key = data.get("id", self.name)
        log.debug("Loading %s with data %s", self, util.json_dump(data))
        self.is_built_in = False  #: Whether the quality gate is built in
        self.is_default = False  #: Whether the quality gate is the default
        self._conditions: Optional[dict[str, str]] = None  #: Quality gate conditions
        self._permissions: Optional[object] = None  #: Quality gate permissions
        self._projects: Optional[dict[str, projects.Project]] = None  #: projects.Projects using this quality profile
        self.sq_json = data
        self.name = data.get("name", self.name)
        self.is_default = data.get("isDefault", False)
        self.is_built_in = data.get("isBuiltIn", False)
        self.qg_id = data.get("id")
        self.conditions()
        self.permissions()
        log.debug("Created %s with uuid %d id %x", str(self), hash(self), id(self))
        self.__class__.CACHE.put(self)

    def __str__(self) -> str:
        """Returns the string formatting of the object"""
        return f"quality gate '{self.name}'"

    def __hash__(self) -> int:
        """Default UUID for SQ objects"""
        return hash((self.name,))

    def hash_payload(data: ApiPayload) -> tuple[Any, ...]:
        """Returns the hash items for a given object search payload"""
        return (data["name"],)

    def hash_object(self) -> tuple[Any, ...]:
        """Returns the hash elements for a given object"""
        return (self.name,)

    @classmethod
    def get_object(cls, endpoint: Platform, name: str) -> QualityGate:
        """Reads a quality gate from SonarQube

        :param endpoint: Reference to the SonarQube platform
        :param name: Quality gate
        :return: the QualityGate object or None if not found
        """
        o: Optional[QualityGate] = cls.CACHE.get(endpoint.local_url, name)
        if o:
            return o
        if data := search_by_name(endpoint, name):
            return cls.load(endpoint, data)
        raise exceptions.ObjectNotFound(name, f"Quality gate '{name}' not found")

    @classmethod
    def create(cls, endpoint: Platform, name: str) -> QualityGate:
        """Creates an empty quality gate"""
        api, _, params, _ = endpoint.api.get_details(cls, Oper.CREATE, name=name)
        endpoint.post(api, params=params)
        return cls.get_object(endpoint, name)

    @classmethod
    def search(cls, endpoint: Platform, use_cache: bool = False, **search_params: Any) -> dict[str, QualityGate]:
        """Returns the whole list of quality gates

        :param Platform endpoint: Reference to the SonarQube platform
        :param bool use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :param search_params: Search parameters (None, see api/qualitygates/search parameters)
        :return: Dict of quality gates indexed by name
        """
        log.info("Searching quality gates with params %s", search_params)
        if use_cache and len(search_params) == 0 and len(cls.CACHE.from_platform(endpoint)) > 0:
            log.debug("Returning cached quality gates")
            return {qg.name: qg for qg in cls.CACHE.from_platform(endpoint).values()}
        api, _, params, ret = endpoint.api.get_details(cls, Oper.SEARCH, **search_params)
        dataset = json.loads(endpoint.get(api, params=params).text)[ret]
        return {qg["name"]: cls.load(endpoint, qg) for qg in dataset}

    def reload(self, data: ApiPayload) -> QualityGate:
        """Reloads the quality gate from the given data"""
        super().reload(data)
        self.is_default = data.get("isDefault", False)
        self.is_built_in = data.get("isBuiltIn", False)
        return self

    def url(self) -> str:
        """Returns the object permalink"""
        return f"{self.base_url(local=False)}/quality_gates/show/{self.key}"

    def delete(self) -> bool:
        """Deletes a quality gate, returns whether the operation succeeded"""
        return self.delete_object(id=self.qg_id, name=self.name)

    def projects(self) -> dict[str, projects.Project]:
        """
        :raises ObjectNotFound: If Quality gate not found
        :return: The list of projects using this quality gate
        """
        if self._projects is not None:
            return self._projects
        page, nb_pages = 1, 1
        self._projects = {}
        max_ps = self.endpoint.api.max_page_size(self, Oper.GET_PROJECTS)
        p_field = self.endpoint.api.page_field(self, Oper.GET_PROJECTS)
        params = {"ps": max_ps} | {"gateId": self.key} if self.endpoint.is_sonarcloud() else {"gateName": self.name}
        api, _, params, return_field = self.endpoint.api.get_details(self, Oper.GET_PROJECTS, **params)
        while page <= nb_pages:
            params[p_field] = page
            try:
                resp = self.get(api, params=params)
            except exceptions.ObjectNotFound:
                self.__class__.CACHE.pop(self)
                raise
            data = json.loads(resp.text)
            for prj in data[return_field]:
                key = prj["key"] if "key" in prj else prj["id"]
                self._projects[key] = projects.Project.get_object(self.endpoint, key)
            nb_pages = sutil.nbr_pages(data)
            page += 1
        return self._projects

    def conditions(self, encoded: bool = False) -> list[str]:
        """
        :param encoded: Whether to encode the conditions or not, optional, defaults to False
        :return: The quality gate conditions, encoded (for simplication) or not
        """
        if self._conditions is None:
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.GET, name=self.name)
            data = json.loads(self.get(api, params=params).text)
            log.debug("Loading %s with conditions %s", self, util.json_dump(data))
            self._conditions = list(data.get("conditions", []))
        if encoded:
            return _encode_conditions(self._conditions)
        return self._conditions

    def clear_conditions(self) -> bool:
        """Clears all quality gate conditions, if quality gate is not built-in
        :return: Nothing
        """
        if self.is_built_in:
            log.debug("Can't clear conditions of built-in %s", str(self))
            return False
        log.debug("Clearing conditions of %s", str(self))
        for cond in self.conditions():
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.DELETE_CONDITION, id=cond["id"])
            self.post(api, params=params)
        self._conditions = []
        return True

    def set_conditions(self, conditions_list: list[str]) -> bool:
        """Sets quality gate conditions (overriding any previous conditions) as encoded in sonar-config
        :param list[str] conditions_list: List of conditions, encoded
        :return: Whether the operation succeeded
        """
        if not conditions_list or len(conditions_list) == 0:
            return True
        if self.is_built_in:
            log.debug("Can't set conditions of built-in %s", str(self))
            return False
        self.clear_conditions()
        log.debug("Setting conditions of %s", str(self))
        base_params = {"gateId": self.key, "gateName": self.name}
        ok = True
        for cond in conditions_list:
            (metric, op, error) = _decode_condition(cond)
            params = base_params | {"metric": metric, "op": op, "error": error}
            try:
                api, _, api_params, _ = self.endpoint.api.get_details(self, Oper.CREATE_CONDITION, **params)
                ok = ok and self.post(api, params=api_params).ok
            except exceptions.SonarException:
                ok = False
        self._conditions = None
        self.conditions()
        return ok

    def permissions(self) -> permissions.QualityGatePermissions:
        """
        :return: The quality gate permissions
        :rtype: QualityGatePermissions
        """
        if self._permissions is None:
            self._permissions = permissions.QualityGatePermissions(self)
        return self._permissions

    def set_permissions(self, permissions_list: ObjectJsonRepr) -> bool:
        """Sets quality gate permissions
        :param permissions_list:
        :type permissions_list: dict {"users": [<userlist>], "groups": [<grouplist>]}
        :return: Whether the operation succeeded
        """
        return self.permissions().set(permissions_list)

    def copy(self, new_qg_name: str) -> QualityGate:
        """Copies the QG into another one with name new_qg_name"""
        data = json.loads(self.post("qualitygates/copy", params={"sourceName": self.name, "name": new_qg_name}).text)
        return QualityGate(self.endpoint, name=new_qg_name, data=data)

    def set_as_default(self) -> bool:
        """Sets the quality gate as the default
        :return: Whether setting as default quality gate was successful
        :rtype: bool
        """
        params = {"id": self.key} if self.endpoint.is_sonarcloud() else {"name": self.name}
        try:
            ok = self.post("qualitygates/set_as_default", params=params).ok
            # Turn off default for all other quality gates except the current one
            for qg in QualityGate.search(self.endpoint).values():
                qg.is_default = qg.name == self.name
        except exceptions.SonarException:
            return False
        else:
            return ok

    def update(self, **data: Any) -> bool:
        """Updates a quality gate
        :param dict data: Considered keys: "name", "conditions", "permissions"
        """
        log.debug("Updating %s with data %s", str(self), util.json_dump(data))
        if self.is_built_in:
            log.debug("Can't update built-in %s", str(self))
            return True
        if "name" in data and data["name"] != self.name:
            log.info("Renaming %s with %s", self, data["name"])
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.RENAME, id=self.qg_id, name=data["name"])
            self.post(api, params=params)
            self.__class__.CACHE.pop(self)
            self.key = self.name = data["name"]
            self.__class__.CACHE.put(self)
        ok = self.set_conditions(data.get("conditions", []))
        ok = self.set_permissions(data.get("permissions", [])) and ok
        if data.get("isDefault", False):
            ok = self.set_as_default() and ok
        return ok

    def is_identical_to(self, other_qg: QualityGate) -> bool:
        """Checks whether the quality gate is identical to another one
        :param other_qg: The other quality gate to compare with
        :return: True if identical, False otherwise
        """
        return sorted(self.conditions(encoded=True)) == sorted(other_qg.conditions(encoded=True))

    def api_params(self, operation: Oper = Oper.GET) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {Oper.GET: {"name": self.name}}
        return ops[operation] if operation in ops else ops[Oper.GET]

    def audit_conditions(self) -> list[Problem]:
        problems = []
        for cond in self.conditions():
            m = cond["metric"]
            if m not in GOOD_QG_CONDITIONS:
                problems.append(Problem(get_rule(RuleId.QG_WRONG_METRIC), self, str(self), m))
                continue
            val = int(cond["error"])
            (mini, maxi, precise_msg) = GOOD_QG_CONDITIONS[m]
            log.info("Condition on metric '%s': Check that %d in range [%d - %d]", m, val, mini, maxi)
            if val < mini or val > maxi:
                rule = get_rule(RuleId.QG_WRONG_THRESHOLD)
                problems.append(Problem(rule, self, str(self), val, m, mini, maxi, precise_msg))
        return problems

    def audit(self, audit_settings: ConfigSettings = None) -> list[Problem]:
        """Audits a quality gate, returns found problems"""
        my_name = str(self)
        log.debug("Auditing %s", my_name)
        if self.is_built_in:
            return []
        problems = []
        audit_settings = audit_settings or {}
        max_cond = int(sutil.get_setting(audit_settings, "audit.qualitygates.maxConditions", 8))
        nb_conditions = len(self.conditions())
        log.debug("Auditing %s number of conditions (%d) is OK", my_name, nb_conditions)
        if nb_conditions == 0:
            problems.append(Problem(get_rule(RuleId.QG_NO_COND), self, my_name))
        elif nb_conditions > max_cond:
            problems.append(Problem(get_rule(RuleId.QG_TOO_MANY_COND), self, my_name, nb_conditions, max_cond))
        problems += self.audit_conditions()
        problems += self.permissions().audit(audit_settings)
        if not self.is_default and len(self.projects()) == 0:
            problems.append(Problem(get_rule(RuleId.QG_NOT_USED), self, my_name))
        return problems

    def to_json(self, export_settings: ConfigSettings) -> ObjectJsonRepr:
        """Returns JSON representation of object"""
        json_data = self.sq_json
        full = export_settings.get("FULL_EXPORT", False)
        if not self.is_default and not full:
            json_data.pop("isDefault", None)
        if self.is_built_in:
            if full:
                json_data["_conditions"] = self.conditions(encoded=True)
        else:
            if not full:
                json_data.pop("isBuiltIn", None)
            json_data["conditions"] = self.conditions(encoded=True)
            json_data["permissions"] = self.permissions().export(export_settings=export_settings)
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))


def __audit_duplicates(qg_list: dict[str, QualityGate], audit_settings: ConfigSettings = None) -> list[Problem]:
    """Audits for duplicate quality gates
    :param qg_list: dict of QP indexed with their key
    :param audit_settings: Audit settings to use
    """
    if not audit_settings.get("audit.qualityGates.duplicates", True):
        return []
    problems = []
    pairs = {(key1, key2) if key1 < key2 else (key2, key1) for key1 in qg_list.keys() for key2 in qg_list.keys() if key1 != key2}
    for key1, key2 in pairs:
        qg1, qg2 = qg_list[key1], qg_list[key2]
        log.debug("Comparing %s and %s", qg1, qg2)
        if qg2.is_identical_to(qg1):
            problems.append(Problem(get_rule(RuleId.QG_DUPLICATES), f"{qg1.endpoint.external_url}/quality_gates", qg1.name, qg2.name))
    return problems


def audit(endpoint: Platform, audit_settings: Optional[ConfigSettings] = None, **kwargs: Any) -> list[Problem]:
    """Audits Sonar platform quality gates, returns found problems"""
    audit_settings = audit_settings or {}
    if not audit_settings.get("audit.qualityGates", True):
        log.info("Auditing quality gates is disabled, audit skipped...")
        return []
    log.info("--- Auditing quality gates ---")
    problems = []
    all_qg = QualityGate.search(endpoint)
    custom_qg = {k: qg for k, qg in all_qg.items() if not qg.is_built_in}
    max_qg = sutil.get_setting(audit_settings, "audit.qualitygates.maxNumber", 5)
    log.debug("Auditing that there are no more than %d quality gates", max_qg)
    if (nb_qg := len(custom_qg)) > max_qg:
        problems.append(Problem(get_rule(RuleId.QG_TOO_MANY_GATES), f"{endpoint.external_url}/quality_gates", nb_qg, max_qg))
    for qg in custom_qg.values():
        problems += qg.audit(audit_settings | {"audit.permissions.zeroPermissions": False})
    problems += __audit_duplicates(custom_qg, audit_settings)
    "write_q" in kwargs and kwargs["write_q"].put(problems)
    return problems


def export(endpoint: Platform, export_settings: ConfigSettings, **kwargs: Any) -> ObjectJsonRepr:
    """Exports quality gates as JSON

    :param Platform endpoint: Reference to the Sonar platform
    :param ConfigSetting export_settings: Options to use for export
    :return: Quality gates representations as JSON
    """
    log.info("Exporting quality gates")
    qg_list = [util.clean_data(qg.to_json(export_settings), remove_none=True, remove_empty=True) for qg in QualityGate.search(endpoint).values()]
    write_q = kwargs.get("write_q", None)
    if write_q:
        write_q.put(qg_list)
        write_q.put(sutil.WRITE_END)
    return qg_list


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: KeyList = None) -> bool:
    """Imports quality gates in a SonarQube platform, fom sonar-config data
    Quality gates already existing are updates with the provided configuration

    :param Platform endpoint: Reference to the SonarQube platform
    :param dict config_data: JSON representation of quality gates (as per export format)
    :return: Whether the import succeeded
    :rtype: bool
    """
    if "qualityGates" not in config_data:
        log.info("No quality gates to import")
        return True
    log.info("Importing quality gates")
    ok = True
    converted_data = util.list_to_dict(config_data["qualityGates"], "name")
    for name, data in converted_data.items():
        try:
            o: QualityGate = QualityGate.get_object(endpoint, name)
            log.debug("Found existing %s", str(o))
        except exceptions.ObjectNotFound:
            log.debug("QG %s not found, creating it", name)
            o = QualityGate.create(endpoint, name)
        log.debug("Importing %s with %s", str(o), util.json_dump(data))
        ok = o.update(**data) and ok
    return ok


def count(endpoint: Platform) -> int:
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :return: Number of quality gates
    :rtype: int
    """
    return len(QualityGate.search(endpoint))


def _encode_conditions(conds: list[dict[str, str]]) -> list[str]:
    """Encode dict conditions in strings"""
    simple_conds = []
    for cond in conds:
        simple_conds.append(_encode_condition(cond))
    return simple_conds


_PERCENTAGE_METRICS = ("density", "ratio", "percent", "security_hotspots_reviewed", "coverage")


def _encode_condition(cond: dict[str, str]) -> str:
    """Encode one dict conditions in a string"""
    metric, oper, val = cond["metric"], cond["op"], cond["error"]
    if oper == "GT":
        oper = ">="
    elif oper == "LT":
        oper = "<="
    if "rating" in metric:
        val = measures.get_rating_letter(val)
    elif metric.startswith("sca_severity") and f"{val}" == f"{SCA_HIGH}":
        val = "High"
    if any(d in metric for d in _PERCENTAGE_METRICS):
        val = f"{val}%"
    return f"{metric} {oper} {val}"


def _decode_condition(cond: str) -> tuple[str, str, str]:
    """Decodes a string condition in a tuple metric, op, value"""
    (metric, oper, val) = cond.strip().split(" ")
    if oper in (">", ">="):
        oper = "GT"
    elif oper in ("<", "<="):
        oper = "LT"
    if "rating" in metric:
        val = measures.get_rating_number(val)
    elif metric.startswith("sca_severity") and val == "High":
        val = 19
    if any(d in metric for d in _PERCENTAGE_METRICS) and val.endswith("%"):
        val = val[:-1]
    return (metric, oper, val)


def search_by_name(endpoint: Platform, name: str) -> Optional[dict[str, Any]]:
    """Searches quality gates matching name"""
    api, _, _, ret = endpoint.api.get_details(QualityGate, Oper.SEARCH)
    return sutil.search_by_name(endpoint, name, api, ret)


def convert_qgs_json(old_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Converts the sonar-config quality gates old JSON report format to the new one"""
    old_json = common_json_helper.convert_common_fields(old_json, with_permissions=False)
    for qg in [q for q in old_json.values() if "permissions" in q]:
        for ptype in [p for p in ("users", "groups") if p in qg["permissions"]]:
            qg["permissions"][ptype] = util.csv_to_list(qg["permissions"][ptype])
    return util.dict_to_list(old_json, "name")
