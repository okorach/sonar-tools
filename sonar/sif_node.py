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

    Node audit

"""

import datetime
from dateutil.relativedelta import relativedelta

import sonar.logging as log
import sonar.utilities as util
from sonar.util import types
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
from sonar import config

_RELEASE_DATE_6_7 = datetime.datetime(2017, 11, 8) + relativedelta(months=+6)
_RELEASE_DATE_7_9 = datetime.datetime(2019, 7, 1) + relativedelta(months=+6)
_RELEASE_DATE_8_9 = datetime.datetime(2021, 5, 4) + relativedelta(months=+6)
_RELEASE_DATE_9_9 = datetime.datetime(2023, 2, 1) + relativedelta(months=+6)

_CE_TASKS = "Compute Engine Tasks"
_WORKER_COUNT = "Worker Count"


def __audit_background_tasks(obj: object, obj_name: str) -> list[Problem]:
    """Audits the SIF for the health of background tasks stats, namely the failure rate

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param str obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    log.info("%s: Auditing CE background tasks", obj_name)
    problems = []
    ce_tasks = obj.json.get(_CE_TASKS)
    if ce_tasks is None:
        log.warning("%s: Can't find Compute Engine Tasks in SIF, audit on CE task is skipped", obj_name)
        return []
    ce_success = ce_tasks["Processed With Success"]
    ce_error = ce_tasks["Processed With Error"]
    failure_rate = 0
    if ce_success != 0 or ce_error != 0:
        failure_rate = ce_error / (ce_success + ce_error)
    if ce_error > 10 and failure_rate > 0.01:
        rule = get_rule(RuleId.BACKGROUND_TASKS_FAILURE_RATE_HIGH)
        if failure_rate > 0.1:
            rule = get_rule(RuleId.BACKGROUND_TASKS_FAILURE_RATE_VERY_HIGH)
        problems.append(Problem(rule, obj, int(failure_rate * 100)))
    else:
        log.info(
            "%s: Number of failed background tasks (%d), and failure rate %d%% is OK",
            obj_name,
            ce_error,
            int(failure_rate * 100),
        )
    ce_pending = ce_tasks["Pending"]
    if ce_pending > 100:
        rule = get_rule(RuleId.BACKGROUND_TASKS_PENDING_QUEUE_VERY_LONG)
        problems.append(Problem(rule, obj, ce_pending))
    elif ce_pending > 20 and ce_pending > (10 * ce_tasks[_WORKER_COUNT]):
        rule = get_rule(RuleId.BACKGROUND_TASKS_PENDING_QUEUE_LONG)
        problems.append(Problem(rule, obj, ce_pending))
    else:
        log.info("%s: Number of pending background tasks (%d) is OK", obj_name, ce_pending)
    return problems


def __audit_jvm(obj: object, obj_name: str, jvm_state: dict[str, str], heap_limits: tuple[int] = (1024, 4096)) -> list[Problem]:
    """Audits the SIF for the JVM head allocation used for a node (global SIF or App Node level)

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param str obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :param dict jvm_props: Web or CE JVM State section of the SIF (global SIF or App Node level)
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
            rule = get_rule(RuleId.CE_HEAP_TOO_LOW)
        else:
            rule = get_rule(RuleId.WEB_HEAP_TOO_LOW)
        limit = min_heap
    else:
        if "CE process" in obj_name:
            rule = get_rule(RuleId.CE_HEAP_TOO_HIGH)
        else:
            rule = get_rule(RuleId.WEB_HEAP_TOO_HIGH)
        limit = max_heap
    return [Problem(rule, obj, obj_name, heap, limit)]


def __audit_jvm_version(obj: object, obj_name: str, jvm_props: dict[str, str]) -> list[Problem]:
    """Audits the SIF for the JVM version used for a node (global SIF or App Node level)

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param str obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :param dict jvm_props: Web or CE JVM Properties section of the SIF (global SIF or App Node level)
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
    java_compat = config.get_java_compatibility()
    log.debug("Java compatibility matrix: %s", str(java_compat))
    if java_version not in java_compat:
        log.warning("%s: Java version %d not listed in compatibility matrix, skipping JVM version audit", obj_name, java_version)
        return []
    min_v, max_v = java_compat[java_version]
    sq_v_str = ".".join([str(i) for i in sq_version])
    if min_v <= sq_version <= max_v:
        log.info("%s: SonarQube %s running on a supported java version (java %d)", obj_name, sq_v_str, java_version)
        return []
    return [Problem(get_rule(RuleId.SETTING_WEB_WRONG_JAVA_VERSION), obj, obj_name, sq_v_str, java_version)]


def __audit_workers(obj: object, obj_name: str) -> list[Problem]:
    """Audits the SIF for number of CE workers configured (global SIF or App Node level)

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param str obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :param dict ce_data: CE sections of the SIF (global SIF or App Node level)
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    ed = obj.edition()
    if ed in ("community", "developer"):
        log.info("%s: %s edition, CE workers audit skipped...", obj_name, ed)
        return []
    try:
        ce_workers = obj.json[_CE_TASKS][_WORKER_COUNT]
    except KeyError:
        log.warning("%s: CE section missing from SIF, CE workers audit skipped...", obj_name)
        return []
    MAX_WORKERS = 4  # EE
    if ed == "datacenter":
        MAX_WORKERS = 6
    if ce_workers > MAX_WORKERS:
        return [Problem(get_rule(RuleId.TOO_MANY_CE_WORKERS), obj, ce_workers, MAX_WORKERS)]
    else:
        log.info(
            "%s: %d CE workers configured, correct compared to the max %d recommended",
            obj_name,
            ce_workers,
            MAX_WORKERS,
        )
    return []


def __audit_log_level(obj: object, obj_name: str, logging_data: dict[str, str]) -> list[Problem]:
    """Audits the SIF for the Web or CE process log level (global SIF or App Node level),
    and returns Problem if it is DEBUG or TRACE

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param str obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :param dict logging_data: Web or CE Logging section of the SIF (global SIF or App Node level)
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    log.info("%s: Auditing log level", obj_name)
    lvl = logging_data.get("Logs Level", None)
    if lvl is None:
        log.warning("%s: log level is missing, audit of log level is skipped...", obj_name)
        return []
    if lvl == "TRACE":
        return [Problem(get_rule(RuleId.LOGS_IN_TRACE_MODE), obj, obj_name)]
    if lvl == "DEBUG":
        return [Problem(get_rule(RuleId.LOGS_IN_DEBUG_MODE), obj, obj_name)]
    log.info("%s: Log level is '%s', this is fine", obj_name, lvl)
    return []


def audit_version(obj: object, obj_name: str) -> list[Problem]:
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
    log.debug("%s: version %s, start time = %s", obj_name, util.version_to_string(obj.version()), str(st_time))
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
    lta_str = util.version_to_string(current_lta[:2])
    if sq_version >= current_lta:
        log.info("%s: Version %s is correct wrt LTA (ex-LTS) %s", obj_name, util.version_to_string(obj.version()), lta_str)
        return []

    return [Problem(get_rule(RuleId.BELOW_LTA), "", util.version_to_string(obj.version()), lta_str)]


def audit_ce(obj: object, obj_name: str) -> list[Problem]:
    """Audits the CE section of a SIF (global SIF or App Node level),
    and returns list of Problem for each problem found

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param str obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    try:
        nb_workers = obj.json[_CE_TASKS][_WORKER_COUNT]
    except KeyError:
        nb_workers = 0

    heap_min = max(2048, 1024 * nb_workers)
    heap_max = max(4096, 2048 * nb_workers)
    return (
        __audit_background_tasks(obj, obj_name)
        + __audit_workers(obj, obj_name)
        + __audit_jvm(obj, obj_name, obj.json["Compute Engine JVM State"], (heap_min, heap_max))
        + __audit_log_level(obj, obj_name, obj.json["Compute Engine Logging"])
        + __audit_jvm_version(obj, obj_name, obj.json["Compute Engine JVM Properties"])
    )


def audit_web(obj: object, obj_name: str) -> list[Problem]:
    """Audits the Web section of a SIF (global SIF or App Node level),
    and returns list of Problem for each problem found

    :param obj: Object concerned by the audit (SIF or App Node)
    :type obj: Sif or AppNode
    :param str obj_name: String name of the object as it will appear in the audit warning, if any audit warning
    :return: List of problems found, or empty list
    :rtype: list[Problem]
    """
    (heap_min, heap_max) = (1024, 4096)
    if obj.edition() == "datacenter":
        (heap_min, heap_max) = (2048, 8192)
    return (
        audit_version(obj, obj_name)
        + __audit_jvm(obj, obj_name, obj.json["Web JVM State"], (heap_min, heap_max))
        + __audit_log_level(obj, obj_name, obj.json["Web Logging"])
        + __audit_jvm_version(obj, obj_name, obj.json["Web JVM Properties"])
    )


def audit_plugins(obj: object, obj_name: str, audit_settings: types.ConfigSettings) -> list[Problem]:
    """Audit for the presence of 3rd party plugins outside a white list"""
    if not audit_settings.get("audit.plugins", True):
        log.info("Audit of 3rd party plugins skipped...")
        return []
    if "Plugins" not in obj.json:
        log.info("Plugins entry not found for %s, audit of 3rd party plugins skipped...", obj_name)
        return []
    whitelist = util.csv_to_list(audit_settings.get("audit.plugins.whitelist", ""))
    log.info("Auditing 3rd part plugins with CSV whitelist '%s'", ", ".join(whitelist))
    problems = []
    for key, name in obj.json["Plugins"].items():
        if key not in whitelist:
            problems.append(Problem(get_rule(RuleId.CUSTOM_PLUGIN), obj, obj_name, key, name))
    return problems
