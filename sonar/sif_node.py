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

    Node audit

"""

import datetime
from dateutil.relativedelta import relativedelta

import sonar.logging as log
from sonar.audit import rules
import sonar.audit.problem as pb

_RELEASE_DATE_6_7 = datetime.datetime(2017, 11, 8) + relativedelta(months=+6)
_RELEASE_DATE_7_9 = datetime.datetime(2019, 7, 1) + relativedelta(months=+6)
_RELEASE_DATE_8_9 = datetime.datetime(2021, 5, 4) + relativedelta(months=+6)
_RELEASE_DATE_9_9 = datetime.datetime(2023, 2, 1) + relativedelta(months=+6)

_CE_TASKS = "Compute Engine Tasks"
_WORKER_COUNT = "Worker Count"


def __audit_background_tasks(obj: object, obj_name: str, ce_data: dict[str, str]) -> list[pb.Problem]:
    """Audits the SIF for the health of background tasks stats, namely the failure rate

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :type obj_name: str
    :param ce_data: CE section of the SIF (global or for a given DCE app node)
    :type obj_name: dict
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    log.info("%s: Auditing CE background tasks", obj_name)
    problems = []
    ce_tasks = ce_data.get(_CE_TASKS)
    if ce_tasks is None:
        log.warning("%s: Can't find Compute Engine Tasks in SIF, audit on CE task is skipped", obj_name)
        return []
    ce_success = ce_tasks["Processed With Success"]
    ce_error = ce_tasks["Processed With Error"]
    failure_rate = 0
    if ce_success != 0 or ce_error != 0:
        failure_rate = ce_error / (ce_success + ce_error)
    if ce_error > 10 and failure_rate > 0.01:
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_FAILURE_RATE_HIGH)
        if failure_rate > 0.1:
            rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_FAILURE_RATE_VERY_HIGH)
        problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(int(failure_rate * 100)), concerned_object=obj))
    else:
        log.info(
            "%s: Number of failed background tasks (%d), and failure rate %d%% is OK",
            obj_name,
            ce_error,
            int(failure_rate * 100),
        )
    ce_pending = ce_tasks["Pending"]
    if ce_pending > 100:
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_VERY_LONG)
        problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(ce_pending), concerned_object=obj))
    elif ce_pending > 20 and ce_pending > (10 * ce_tasks[_WORKER_COUNT]):
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_LONG)
        problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(ce_pending), concerned_object=obj))
    else:
        log.info("%s: Number of pending background tasks (%d) is OK", obj_name, ce_pending)
    return problems


def __audit_jvm(obj: object, obj_name: str, jvm_state: dict[str, str], heap_limits: tuple[int] = (1024, 4096)) -> list[pb.Problem]:
    """Audits the SIF for the JVM head allocation used for a node (global SIF or App Node level)

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :type obj_name: str
    :param jvm_props: Web or CE JVM State section of the SIF (global SIF or App Node level)
    :type obj_name: dict
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    log.info("%s: Auditing JVM RAM", obj_name)
    # On DCE we expect between 2 and 4 GB of RAM per App Node Web JVM
    (min_heap, max_heap) = heap_limits
    try:
        heap = jvm_state["Heap Max (MB)"]
    except KeyError:
        log.warning("%s: Can't find JVM Heap in SIF, auditing this part is skipped", obj_name)
        return []
    if min_heap <= heap <= max_heap:
        log.info("%s: Heap of %d MB is within recommended range [%d-%d]", obj_name, heap, min_heap, max_heap)
        return []

    if heap < min_heap:
        if "CE process" in obj_name:
            rule = rules.get_rule(rules.RuleId.CE_HEAP_TOO_LOW)
        else:
            rule = rules.get_rule(rules.RuleId.WEB_HEAP_TOO_LOW)
        limit = min_heap
    else:
        if "CE process" in obj_name:
            rule = rules.get_rule(rules.RuleId.CE_HEAP_TOO_HIGH)
        else:
            rule = rules.get_rule(rules.RuleId.WEB_HEAP_TOO_HIGH)
        limit = max_heap
    return [pb.Problem(broken_rule=rule, msg=rule.msg.format(obj_name, heap, limit), concerned_object=obj)]


def __audit_jvm_version(obj: object, obj_name: str, jvm_props: dict[str, str]) -> list[pb.Problem]:
    """Audits the SIF for the JVM version used for a node (global SIF or App Node level)

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :type obj_name: str
    :param jvm_props: Web or CE JVM Properties section of the SIF (global SIF or App Node level)
    :type obj_name: dict
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    log.info("%s: Auditing JVM version", obj_name)
    try:
        str_v = jvm_props["java.specification.version"]
        if str_v.startswith("1."):
            str_v = str_v.split(".")[-1]
        java_version = int(str_v)
    except KeyError:
        log.warning("%s: Can't find Java version in SIF, auditing this part is skipped", obj_name)
        return []
    try:
        sq_version = obj.version()
    except KeyError:
        log.warning("%s: Can't find SonarQube version in SIF, auditing this part is skipped", obj_name)
        return []
    sq_v_str = ".".join([str(i) for i in sq_version])
    if (java_version == 17 and sq_version >= (9, 6, 0)) or (
        java_version == 11 and (7, 9, 0) <= sq_version <= (9, 8, 0) or (java_version == 8 and (7, 9, 0) <= sq_version < (8, 9, 0))
    ):
        log.info("%s: SonarQube %s running on a supported java version (java %d)", obj_name, sq_v_str, java_version)
        return []
    rule = rules.get_rule(rules.RuleId.SETTING_WEB_WRONG_JAVA_VERSION)
    return [pb.Problem(broken_rule=rule, msg=rule.msg.format(obj_name, sq_v_str, java_version), concerned_object=obj)]


def __audit_workers(obj: object, obj_name: str, ce_data: dict[str, str]) -> list[pb.Problem]:
    """Audits the SIF for number of CE workers configured (global SIF or App Node level)

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :type obj_name: str
    :param ce_data: CE sections of the SIF (global SIF or App Node level)
    :type obj_name: dict
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    ed = obj.edition()
    if ed in ("community", "developer"):
        log.info("%s: %s edition, CE workers audit skipped...", obj_name, ed)
        return []
    try:
        ce_workers = ce_data[_CE_TASKS][_WORKER_COUNT]
    except KeyError:
        log.warning("%s: CE section missing from SIF, CE workers audit skipped...", obj_name)
        return []
    MAX_WORKERS = 4  # EE
    if ed == "datacenter":
        MAX_WORKERS = 6
    if ce_workers > MAX_WORKERS:
        rule = rules.get_rule(rules.RuleId.TOO_MANY_CE_WORKERS)
        return [pb.Problem(broken_rule=rule, msg=rule.msg.format(ce_workers, MAX_WORKERS), concerned_object=obj)]
    else:
        log.info(
            "%s: %d CE workers configured, correct compared to the max %d recommended",
            obj_name,
            ce_workers,
            MAX_WORKERS,
        )
    return []


def __audit_log_level(obj: object, obj_name: str, logging_data: dict[str, str]) -> list[pb.Problem]:
    """Audits the SIF for the Web or CE process log level (global SIF or App Node level),
    and returns Problem if it is DEBUG or TRACE

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :type obj_name: str
    :param logging_data: Web or CE Logging section of the SIF (global SIF or App Node level)
    :type obj_name: dict
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    log.info("%s: Auditing log level", obj_name)
    lvl = logging_data.get("Logs Level", None)
    if lvl is None:
        log.warning("%s: log level is missing, audit of log level is skipped...", obj_name)
        return []
    if lvl == "TRACE":
        rule = rules.get_rule(rules.RuleId.LOGS_IN_TRACE_MODE)
        return [pb.Problem(broken_rule=rule, msg=rule.msg.format(obj_name), concerned_object=obj)]
    if lvl == "DEBUG":
        rule = rules.get_rule(rules.RuleId.LOGS_IN_DEBUG_MODE)
        return [pb.Problem(broken_rule=rule, msg=rule.msg.format(obj_name), concerned_object=obj)]
    log.info("%s: Log level is '%s', this is fine", obj_name, lvl)
    return []


def audit_version(obj: object, obj_name: str) -> list[pb.Problem]:
    """Audits the SIF for SonarQube version (global SIF or App Node level),
    and returns Problem if it is below LTA (ex-LTS)

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :type obj_name: str
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    sq_version = obj.version()
    if sq_version is None:
        log.warning("%s: Version information is missing, audit on node version is skipped...", obj_name)
        return []
    st_time = obj.start_time()
    log.debug("%s: version %s, start time = %s", obj_name, obj.version(as_string=True), str(st_time))
    if st_time > _RELEASE_DATE_9_9:
        current_lta = (9, 9, 0)
    elif st_time > _RELEASE_DATE_8_9:
        current_lta = (8, 9, 0)
    elif st_time > _RELEASE_DATE_7_9:
        current_lta = (7, 9, 0)
    elif st_time > _RELEASE_DATE_6_7:
        current_lta = (6, 7, 0)
    else:
        current_lta = (5, 9, 0)
    lta_str = f"{current_lta[0]}.{current_lta[1]}"
    if sq_version >= current_lta:
        log.info("%s: Version %s is correct wrt LTA (ex-LTS) %s", obj_name, obj.version(as_string=True), lta_str)
        return []

    rule = rules.get_rule(rules.RuleId.BELOW_LTA)
    return [pb.Problem(broken_rule=rule, msg=rule.msg.format(obj.version(as_string=True), lta_str))]


def audit_ce(obj: object, obj_name: str, node_data: dict[str, dict]) -> list[pb.Problem]:
    """Audits the CE section of a SIF (global SIF or App Node level),
    and returns list of Problem for each problem found

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :type obj_name: str
    :param node_data: Global SIF or one Application node section a DCE SIF
    :type node_data: dict
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    try:
        nb_workers = node_data[_CE_TASKS][_WORKER_COUNT]
    except KeyError:
        nb_workers = 0

    heap_min = max(2048, 1024 * nb_workers)
    heap_max = max(4096, 2048 * nb_workers)
    return (
        __audit_background_tasks(obj, obj_name, node_data)
        + __audit_workers(obj, obj_name, node_data)
        + __audit_jvm(obj, obj_name, node_data["Compute Engine JVM State"], (heap_min, heap_max))
        + __audit_log_level(obj, obj_name, node_data["Compute Engine Logging"])
        + __audit_jvm_version(obj, obj_name, node_data["Compute Engine JVM Properties"])
    )


def audit_web(obj: object, obj_name: str, node_data: dict[str, dict]) -> list[pb.Problem]:
    """Audits the Web section of a SIF (global SIF or App Node level),
    and returns list of Problem for each problem found

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :type obj_name: str
    :param node_data: Global SIF or one Application node section a DCE SIF
    :type node_data: dict
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    (heap_min, heap_max) = (1024, 4096)
    if obj.edition() == "datacenter":
        (heap_min, heap_max) = (2048, 8192)
    return (
        audit_version(obj, obj_name)
        + __audit_jvm(obj, obj_name, node_data["Web JVM State"], (heap_min, heap_max))
        + __audit_log_level(obj, obj_name, node_data["Web Logging"])
        + __audit_jvm_version(obj, obj_name, node_data["Web JVM Properties"])
    )
