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

    Abstraction of the SonarQube "quality gate" concept

"""

from __future__ import annotations

from typing import Union

from http import HTTPStatus
import json
from requests.exceptions import HTTPError

import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf

from sonar import measures, exceptions, projects
import sonar.permissions.qualitygate_permissions as permissions
import sonar.utilities as util

from sonar.audit import rules
import sonar.audit.problem as pb


_OBJECTS = {}

#: Quality gates APIs
APIS = {
    "create": "qualitygates/create",
    "list": "qualitygates/list",
    "rename": "qualitygates/rename",
    "details": "qualitygates/show",
    "get_projects": "qualitygates/search",
}

__NEW_ISSUES_SHOULD_BE_ZERO = "Any numeric threshold on new issues should be 0 or should be removed from QG conditions"

GOOD_QG_CONDITIONS = {
    "new_reliability_rating": (1, 1, "Any rating other than A would let bugs slip through in new code"),
    "new_security_rating": (1, 1, "Any rating other than A would let vulnerabilities slip through in new code"),
    "new_maintainability_rating": (1, 1, "Expectation is that code smells density on new code is low enough to get A rating"),
    "new_coverage": (20, 90, "Coverage below 20% is a too low bar, above 90% is overkill"),
    "new_bugs": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
    "new_vulnerabilities": (0, 0, __NEW_ISSUES_SHOULD_BE_ZERO),
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

    def __init__(self, endpoint: pf.Platform, name: str, data: dict[str, str]) -> None:
        """Constructor, don't use directly, use class methods instead"""
        super().__init__(endpoint=endpoint, key=name)
        self.name = name  #: Object name
        self.is_built_in = False  #: Whether the quality gate is built in
        self.is_default = False  #: Whether the quality gate is the default
        self._conditions = None  #: Quality gate conditions
        self._permissions = None  #: Quality gate permissions
        self._projects = None  #: Projects using this quality profile
        self._json = data
        self.name = data.pop("name")
        self.key = data.pop("id", self.name)
        self.is_default = data.get("isDefault", False)
        self.is_built_in = data.get("isBuiltIn", False)
        self.conditions()
        self.permissions()
        _OBJECTS[self.uuid()] = self

    @classmethod
    def get_object(cls, endpoint: pf.Platform, name: str) -> QualityGate:
        """Reads a quality gate from SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Quality gate
        :return: the QualityGate object or None if not found
        :rtype: QualityGate or None
        """
        uid = sq.uuid(name, endpoint.url)
        if uid in _OBJECTS:
            return _OBJECTS[uid]
        data = search_by_name(endpoint, name)
        if not data:
            raise exceptions.ObjectNotFound(name, f"Quality gate '{name}' not found")
        return cls.load(endpoint, data)

    @classmethod
    def load(cls, endpoint: pf.Platform, data: dict[str, str]) -> QualityGate:
        """Creates a quality gate from returned API data
        :return: the QualityGate object
        :rtype: QualityGate or None
        """
        # SonarQube 10 compatibility: "id" field dropped, replaced by "name"
        o = _OBJECTS.get(sq.uuid(data["name"], endpoint.url), None)
        if not o:
            o = cls(data["name"], endpoint, data=data)
        o._json = data
        return o

    @classmethod
    def create(cls, endpoint: pf.Platform, name: str) -> Union[QualityGate, None]:
        """Creates an empty quality gate"""
        r = endpoint.post(APIS["create"], params={"name": name})
        if not r.ok:
            return None
        return cls.get_object(endpoint, name)

    def __str__(self) -> str:
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"quality gate '{self.name}'"

    def uuid(self) -> str:
        """Returns the UUID of a quality gate"""
        return sq.uuid(self.name, self.endpoint.url)

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
        params = {"gateName": self.name, "ps": 500}
        page, nb_pages = 1, 1
        self._projects = {}
        while page <= nb_pages:
            params["p"] = page
            try:
                resp = self.get(APIS["get_projects"], params=params)
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(self.name, f"{str(self)} not found")
            data = json.loads(resp.text)
            for prj in data["results"]:
                log.info("Proj = %s", str(prj))
                key = prj["key"] if "key" in prj else prj["id"]
                self._projects[key] = projects.Project.get_object(self.endpoint, key)
            nb_pages = util.nbr_pages(data)
            page += 1
        return self._projects

    def count_projects(self) -> int:
        """
        :return: The number of projects using this quality gate
        :rtype: int
        """
        return len(self.projects())

    def conditions(self, encoded: bool = False) -> list[str]:
        """
        :param encoded: Whether to encode the conditions or not, defaults to False
        :type encoded: bool, optional
        :return: The quality gate conditions, encoded (for simplication) or not
        :rtype: list
        """
        if self._conditions is None:
            self._conditions = []
            data = json.loads(self.get(APIS["details"], params={"name": self.name}).text)
            for c in data.get("conditions", []):
                self._conditions.append(c)
        if encoded:
            return _encode_conditions(self._conditions)
        return self._conditions

    def clear_conditions(self) -> None:
        """Clears all quality gate conditions, if quality gate is not built-in
        :return: Nothing
        """
        if self.is_built_in:
            log.debug("Can't clear conditions of built-in %s", str(self))
        else:
            log.debug("Clearing conditions of %s", str(self))
            for c in self.conditions():
                self.post("qualitygates/delete_condition", params={"id": c["id"]})
            self._conditions = None

    def set_conditions(self, conditions_list: list[str]) -> bool:
        """Sets quality gate conditions (overriding any previous conditions) as encoded in sonar-config
        :param conditions_list: List of conditions, encoded
        :type conditions_list: dict
        :return: Whether the operation succeeded
        :rtype: bool
        """
        if not conditions_list or len(conditions_list) == 0:
            return True
        if self.is_built_in:
            log.debug("Can't set conditions of built-in %s", str(self))
            return False
        self.clear_conditions()
        log.debug("Setting conditions of %s", str(self))
        params = {"gateName": self.name}
        ok = True
        for cond in conditions_list:
            (params["metric"], params["op"], params["error"]) = _decode_condition(cond)
            ok = ok and self.post("qualitygates/create_condition", params=params).ok
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

    def set_permissions(self, permissions_list: dict[str, str]) -> QualityGate:
        """Sets quality gate permissions
        :param permissions_list:
        :type permissions_list: dict {"users": [<userlist>], "groups": [<grouplist>]}
        :return: Whether the operation succeeded
        :rtype: bool
        """
        return self.permissions().set(permissions_list)

    def set_as_default(self) -> bool:
        """Sets the quality gate as the default
        :return: Whether setting as default quality gate was successful
        :rtype: bool
        """
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
            self.post(APIS["rename"], params={"id": self.key, "name": data["name"]})
            _OBJECTS.pop(self.uuid(), None)
            self.name = data["name"]
            _OBJECTS[self.uuid()] = self
        ok = self.set_conditions(data.get("conditions", []))
        ok = ok and self.set_permissions(data.get("permissions", []))
        if data.get("isDefault", False):
            self.set_as_default()
        return ok

    def __audit_conditions(self) -> list[pb.Problem]:
        problems = []
        for c in self.conditions():
            m = c["metric"]
            if m not in GOOD_QG_CONDITIONS:
                rule = rules.get_rule(rules.RuleId.QG_WRONG_METRIC)
                msg = rule.msg.format(str(self), m)
                problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=self))
                continue
            val = int(c["error"])
            (mini, maxi, precise_msg) = GOOD_QG_CONDITIONS[m]
            log.info("Condition on metric '%s': Check that %d in range [%d - %d]", m, val, mini, maxi)
            if val < mini or val > maxi:
                rule = rules.get_rule(rules.RuleId.QG_WRONG_THRESHOLD)
                msg = rule.msg.format(str(self), str(val), str(m), str(mini), str(maxi), precise_msg)
                problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=self))
        return problems

    def audit(self, audit_settings: dict[str, str] = None) -> list[pb.Problem]:
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
            rule = rules.get_rule(rules.RuleId.QG_NO_COND)
            msg = rule.msg.format(my_name)
            problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=self))
        elif nb_conditions > max_cond:
            rule = rules.get_rule(rules.RuleId.QG_TOO_MANY_COND)
            msg = rule.msg.format(my_name, nb_conditions, max_cond)
            problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=self))
        problems += self.__audit_conditions()
        log.debug("Auditing that %s has some assigned projects", my_name)
        if not self.is_default and len(self.projects()) == 0:
            rule = rules.get_rule(rules.RuleId.QG_NOT_USED)
            msg = rule.msg.format(my_name)
            problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=self))
        return problems

    def to_json(self, export_settings: dict[str, str]) -> dict[str, str]:
        """Returns JSON representation of object"""
        json_data = self._json
        full = export_settings.get("FULL_EXPORT", False)
        if not self.is_default and not full:
            json_data.pop("isDefault")
        if self.is_built_in:
            if full:
                json_data["_conditions"] = self.conditions(encoded=True)
        else:
            if not full:
                json_data.pop("isBuiltIn")
            json_data["conditions"] = self.conditions(encoded=True)
            json_data["permissions"] = self.permissions().export(export_settings=export_settings)
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))


def audit(endpoint: pf.Platform = None, audit_settings: dict[str, str] = None) -> list[pb.Problem]:
    """Audits Sonar platform quality gates, returns found problems"""
    log.info("--- Auditing quality gates ---")
    problems = []
    quality_gates_list = get_list(endpoint)
    max_qg = util.get_setting(audit_settings, "audit.qualitygates.maxNumber", 5)
    nb_qg = len(quality_gates_list)
    log.debug("Auditing that there are no more than %s quality gates", str(max_qg))
    if nb_qg > max_qg:
        rule = rules.get_rule(rules.RuleId.QG_TOO_MANY_GATES)
        problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(nb_qg, 5), concerned_object=f"{endpoint.url}/quality_gates"))
    for qg in quality_gates_list.values():
        problems += qg.audit(audit_settings)
    return problems


def get_list(endpoint: pf.Platform) -> dict[str, QualityGate]:
    """
    :return: The whole list of quality gates
    :rtype: dict {<name>: <QualityGate>}
    """
    log.info("Getting quality gates")
    data = json.loads(endpoint.get(APIS["list"]).text)
    qg_list = {}
    for qg in data["qualitygates"]:
        log.debug("Getting QG %s", str(qg))
        qg_obj = QualityGate(endpoint=endpoint, name=qg["name"], data=qg)
        if endpoint.version() < (7, 9, 0) and "default" in data and data["default"] == qg["id"]:
            qg_obj.is_default = True
        qg_list[qg_obj.name] = qg_obj
    return qg_list


def export(endpoint: pf.Platform, export_settings: dict[str, str]) -> dict[str, str]:
    """
    :return: The list of quality gates in their JSON representation
    :rtype: dict
    """
    log.info("Exporting quality gates")
    return {k: qg.to_json(export_settings) for k, qg in get_list(endpoint).items()}


def import_config(endpoint: pf.Platform, config_data: dict[str, str]) -> bool:
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
        except exceptions.ObjectNotFound:
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
    for c in conds:
        simple_conds.append(_encode_condition(c))
    return simple_conds


def _encode_condition(c: dict[str, str]) -> str:
    """Encode one dict conditions in a string"""
    metric, op, val = c["metric"], c["op"], c["error"]
    if op == "GT":
        op = ">="
    elif op == "LT":
        op = "<="
    if metric.endswith("rating"):
        val = measures.get_rating_letter(val)
    return f"{metric} {op} {val}"


def _decode_condition(c: str) -> tuple[str, str, str]:
    """Decodes a string condition in a tuple metric, op, value"""
    (metric, op, val) = c.strip().split(" ")
    if op in (">", ">="):
        op = "GT"
    elif op in ("<", "<="):
        op = "LT"
    if metric.endswith("rating"):
        val = measures.get_rating_number(val)
    return (metric, op, val)


def search_by_name(endpoint: pf.Platform, name: str) -> dict[str, QualityGate]:
    """Searches quality gates matching name"""
    return util.search_by_name(endpoint, name, APIS["list"], "qualitygates")
