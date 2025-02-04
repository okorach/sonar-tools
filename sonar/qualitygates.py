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

    Abstraction of the SonarQube "quality gate" concept

"""

from __future__ import annotations
from typing import Union

from http import HTTPStatus
import json
from requests import RequestException

import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf
from sonar.util import types, cache, constants as c
from sonar import measures, exceptions, projects
import sonar.permissions.qualitygate_permissions as permissions
import sonar.utilities as util

from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem


__NEW_ISSUES_SHOULD_BE_ZERO = "Any numeric threshold on new issues should be 0 or should be removed from QG conditions"

GOOD_QG_CONDITIONS = {
    "new_reliability_rating": (1, 1, "Any rating other than A would let bugs slip through in new code"),
    "new_security_rating": (1, 1, "Any rating other than A would let vulnerabilities slip through in new code"),
    "new_maintainability_rating": (1, 1, "Expectation is that code smells density on new code is low enough to get A rating"),
    "new_coverage": (20, 90, "Coverage below 20% is a too low bar, above 90% is overkill"),
    "new_bugs": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_vulnerabilities": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_violations": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_blocker_issues": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_high_issues": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_software_quality_medium_issues": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_security_hotspots": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_blocker_violations": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_critical_violations": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_major_violations": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_duplicated_lines_density": (1, 5, "Duplication on new code of less than 1% is overkill, more than 5% is too relaxed"),
    "new_security_hotspots_reviewed": (100, 100, "All hotspots on new code must be reviewed, any other condition than 100% make little sense"),
    "reliability_rating": (4, 4, "Threshold on overall code should not be too strict or passing the QG will be often impossible"),
    "security_rating": (4, 4, "Threshold on overall code should not be too strict or passing the QG will be often impossible"),
}

_IMPORTABLE_PROPERTIES = ("isDefault", "isBuiltIn", "conditions", "permissions")


class QualityGate(sq.SqObject):
    """
    Abstraction of the Sonar Quality Gate concept
    """

    API = {
        c.CREATE: "qualitygates/create",
        c.GET: "qualitygates/show",
        c.DELETE: "qualitygates/destroy",
        c.LIST: "qualitygates/list",
        c.RENAME: "qualitygates/rename",
        "get_projects": "qualitygates/search",
    }
    CACHE = cache.Cache()

    def __init__(self, endpoint: pf.Platform, name: str, data: types.ApiPayload) -> None:
        """Constructor, don't use directly, use class methods instead"""
        super().__init__(endpoint=endpoint, key=name)
        self.name = name  #: Object name
        self.is_built_in = False  #: Whether the quality gate is built in
        self.is_default = False  #: Whether the quality gate is the default
        self._conditions = None  #: Quality gate conditions
        self._permissions = None  #: Quality gate permissions
        self._projects = None  #: Projects using this quality profile
        self.sq_json = data
        self.name = data.pop("name")
        self.key = data.pop("id", self.name)
        self.is_default = data.get("isDefault", False)
        self.is_built_in = data.get("isBuiltIn", False)
        self.conditions()
        self.permissions()
        QualityGate.CACHE.put(self)

    @classmethod
    def get_object(cls, endpoint: pf.Platform, name: str) -> QualityGate:
        """Reads a quality gate from SonarQube

        :param endpoint: Reference to the SonarQube platform
        :param name: Quality gate
        :return: the QualityGate object or None if not found
        """
        o = QualityGate.CACHE.get(name, endpoint.url)
        if o:
            return o
        data = search_by_name(endpoint, name)
        if not data:
            raise exceptions.ObjectNotFound(name, f"Quality gate '{name}' not found")
        return cls.load(endpoint, data)

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> QualityGate:
        """Creates a quality gate from returned API data
        :return: the QualityGate object
        """
        # SonarQube 10 compatibility: "id" field dropped, replaced by "name"
        o = QualityGate.CACHE.get(data["name"], endpoint.url)
        if not o:
            o = cls(endpoint, data["name"], data=data)
        log.debug("Loading 2 %s QG from %s", o.name, util.json_dump(data))
        o.sq_json = data
        o.is_default = data.get("isDefault", False)
        o.is_built_in = data.get("isBuiltIn", False)
        return o

    @classmethod
    def create(cls, endpoint: pf.Platform, name: str) -> Union[QualityGate, None]:
        """Creates an empty quality gate"""
        try:
            endpoint.post(QualityGate.API[c.CREATE], params={"name": name})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"creating quality gate '{name}'", catch_http_errors=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(name, e.response.text)
        return cls.get_object(endpoint, name)

    def __str__(self) -> str:
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"quality gate '{self.name}'"

    def url(self) -> str:
        """
        :return: The object permalink
        :rtype: str
        """
        return f"{self.endpoint.url}/quality_gates/show/{self.key}"

    def projects(self) -> dict[str, projects.Project]:
        """
        :raises ObjectNotFound: If Quality gate not found
        :return: The list of projects using this quality gate
        :rtype: dict {<projectKey>: <projectData>}
        """
        if self._projects is not None:
            return self._projects
        if self.endpoint.is_sonarcloud():
            params = {"gateId": self.key, "ps": 500}
        else:
            params = {"gateName": self.name, "ps": 500}
        page, nb_pages = 1, 1
        self._projects = {}
        while page <= nb_pages:
            params["p"] = page
            try:
                resp = self.get(QualityGate.API["get_projects"], params=params)
            except (ConnectionError, RequestException) as e:
                util.handle_error(e, f"getting projects of {str(self)}", catch_http_errors=(HTTPStatus.NOT_FOUND,))
                QualityGate.CACHE.pop(self)
                raise exceptions.ObjectNotFound(self.name, f"{str(self)} not found")
            data = json.loads(resp.text)
            for prj in data["results"]:
                key = prj["key"] if "key" in prj else prj["id"]
                self._projects[key] = projects.Project.get_object(self.endpoint, key)
            nb_pages = util.nbr_pages(data)
            page += 1
        return self._projects

    def conditions(self, encoded: bool = False) -> list[str]:
        """
        :param encoded: Whether to encode the conditions or not, defaults to False
        :type encoded: bool, optional
        :return: The quality gate conditions, encoded (for simplication) or not
        :rtype: list
        """
        if self._conditions is None:
            self._conditions = []
            data = json.loads(self.get(QualityGate.API[c.GET], params=self.api_params()).text)
            for cond in data.get("conditions", []):
                self._conditions.append(cond)
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
            self.post("qualitygates/delete_condition", params={"id": cond["id"]})
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
        if self.endpoint.is_sonarcloud():
            params = {"gateId": self.key}
        else:
            params = {"gateName": self.name}
        ok = True
        for cond in conditions_list:
            (params["metric"], params["op"], params["error"]) = _decode_condition(cond)
            ok = ok and self.post("qualitygates/create_condition", params=params).ok
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

    def set_permissions(self, permissions_list: types.ObjectJsonRepr) -> bool:
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
        if self.endpoint.is_sonarcloud():
            r = self.post("qualitygates/set_as_default", params={"id": self.key})
        else:
            r = self.post("qualitygates/set_as_default", params={"name": self.name})
        if r.ok:
            self.is_default = True
            # Turn off default for all other quality gates except the current one
            for qg in get_list(self.endpoint).values():
                if qg.name != self.name:
                    qg.is_default = False
        return r.ok

    def update(self, **data) -> bool:
        """Updates a quality gate
        :param dict data: Considered keys: "name", "conditions", "permissions"
        """
        if "name" in data and data["name"] != self.name:
            log.info("Renaming %s with %s", str(self), data["name"])
            self.post(QualityGate.API[c.RENAME], params={"id": self.key, "name": data["name"]})
            QualityGate.CACHE.pop(self)
            self.name = data["name"]
            self.key = data["name"]
            QualityGate.CACHE.put(self)
        ok = self.set_conditions(data.get("conditions", []))
        ok = ok and self.set_permissions(data.get("permissions", []))
        if data.get("isDefault", False):
            self.set_as_default()
        return ok

    def api_params(self, op: str = c.GET) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {c.GET: {"name": self.name}}
        return ops[op] if op in ops else ops[c.GET]

    def __audit_conditions(self) -> list[Problem]:
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

    def audit(self, audit_settings: types.ConfigSettings = None) -> list[Problem]:
        """Audits a quality gate, returns found problems"""
        my_name = str(self)
        log.debug("Auditing %s", my_name)
        problems = []
        if self.is_built_in:
            return problems
        max_cond = int(util.get_setting(audit_settings, "audit.qualitygates.maxConditions", 8))
        nb_conditions = len(self.conditions())
        log.debug("Auditing %s number of conditions (%d) is OK", my_name, nb_conditions)
        if nb_conditions == 0:
            problems.append(Problem(get_rule(RuleId.QG_NO_COND), self, my_name))
        elif nb_conditions > max_cond:
            problems.append(Problem(get_rule(RuleId.QG_TOO_MANY_COND), self, my_name, nb_conditions, max_cond))
        problems += self.__audit_conditions()
        if not self.is_default and len(self.projects()) == 0:
            problems.append(Problem(get_rule(RuleId.QG_NOT_USED), self, my_name))
        return problems

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
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


def audit(endpoint: pf.Platform = None, audit_settings: types.ConfigSettings = None, **kwargs) -> list[Problem]:
    """Audits Sonar platform quality gates, returns found problems"""
    if not audit_settings.get("audit.qualityGates", True):
        log.info("Auditing quality gates is disabled, audit skipped...")
        return []
    log.info("--- Auditing quality gates ---")
    problems = []
    quality_gates_list = get_list(endpoint)
    max_qg = util.get_setting(audit_settings, "audit.qualitygates.maxNumber", 5)
    nb_qg = len(quality_gates_list)
    log.debug("Auditing that there are no more than %s quality gates", str(max_qg))
    if nb_qg > max_qg:
        problems.append(Problem(get_rule(RuleId.QG_TOO_MANY_GATES), f"{endpoint.url}/quality_gates", nb_qg, 5))
    for qg in quality_gates_list.values():
        problems += qg.audit(audit_settings)
    if "write_q" in kwargs:
        kwargs["write_q"].put(problems)
    return problems


def get_list(endpoint: pf.Platform) -> dict[str, QualityGate]:
    """
    :return: The whole list of quality gates
    :rtype: dict {<name>: <QualityGate>}
    """
    log.info("Getting quality gates")
    data = json.loads(endpoint.get(QualityGate.API[c.LIST]).text)
    qg_list = {}
    for qg in data["qualitygates"]:
        qg_obj = QualityGate.CACHE.get(qg["name"], endpoint.url)
        if qg_obj is None:
            qg_obj = QualityGate(endpoint=endpoint, name=qg["name"], data=qg.copy())
        if endpoint.version() < (7, 9, 0) and "default" in data and data["default"] == qg["id"]:
            qg_obj.is_default = True
        else:
            qg_obj.is_default = qg.get("isDefault", False)
            qg_obj.is_built_in = qg.get("isBuiltIn", False)
        qg_list[qg_obj.name] = qg_obj
    return dict(sorted(qg_list.items()))


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports quality gates as JSON

    :param Platform endpoint: Reference to the Sonar platform
    :param ConfigSetting export_settings: Options to use for export
    :param KeyList key_list: Unused
    :return: Quality gates representations as JSON
    :rtype: ObjectJsonRepr
    """
    log.info("Exporting quality gates")
    qg_list = {k: qg.to_json(export_settings) for k, qg in get_list(endpoint).items()}
    write_q = kwargs.get("write_q", None)
    if write_q:
        write_q.put(qg_list)
        write_q.put(util.WRITE_END)
    return qg_list


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> bool:
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
    for name, data in config_data["qualityGates"].items():
        try:
            o = QualityGate.get_object(endpoint, name)
            log.debug("Found existing %s", str(o))
        except exceptions.ObjectNotFound:
            log.debug("QG %s not found, creating it", name)
            o = QualityGate.create(endpoint, name)
        ok = ok and o.update(**data)
    return ok


def count(endpoint: pf.Platform) -> int:
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :return: Number of quality gates
    :rtype: int
    """
    return len(get_list(endpoint))


def exists(endpoint: pf.Platform, gate_name: str) -> bool:
    """Returns whether a quality gate exists

    :param Platform endpoint: Reference to the SonarQube platform
    :param str gate_name: Quality gate name
    :return: Whether the quality gate exists
    :rtype: bool
    """
    try:
        _ = QualityGate.get_object(endpoint, gate_name)
        return True
    except exceptions.ObjectNotFound:
        return False


def _encode_conditions(conds: list[dict[str, str]]) -> list[str]:
    """Encode dict conditions in strings"""
    simple_conds = []
    for cond in conds:
        simple_conds.append(_encode_condition(cond))
    return simple_conds


def _encode_condition(cond: dict[str, str]) -> str:
    """Encode one dict conditions in a string"""
    metric, op, val = cond["metric"], cond["op"], cond["error"]
    if op == "GT":
        op = ">="
    elif op == "LT":
        op = "<="
    if metric.endswith("rating"):
        val = measures.get_rating_letter(val)
    return f"{metric} {op} {val}"


def _decode_condition(cond: str) -> tuple[str, str, str]:
    """Decodes a string condition in a tuple metric, op, value"""
    (metric, op, val) = cond.strip().split(" ")
    if op in (">", ">="):
        op = "GT"
    elif op in ("<", "<="):
        op = "LT"
    if metric.endswith("rating"):
        val = measures.get_rating_number(val)
    return (metric, op, val)


def search_by_name(endpoint: pf.Platform, name: str) -> dict[str, QualityGate]:
    """Searches quality gates matching name"""
    return util.search_by_name(endpoint, name, QualityGate.API[c.LIST], "qualitygates")


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    return util.dict_to_list(util.remove_nones(original_json), "name")
