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
import sonar.utilities as util

from sonar.audit import rules, types, severities
import sonar.audit.problem as pb

_RELEASE_DATE_6_7 = datetime.datetime(2017, 11, 8) + relativedelta(months=+6)
_RELEASE_DATE_7_9 = datetime.datetime(2019, 7, 1) + relativedelta(months=+6)
_RELEASE_DATE_8_9 = datetime.datetime(2021, 5, 4) + relativedelta(months=+6)

_CE_TASKS = "Compute Engine Tasks"
_WORKER_COUNT = "Worker Count"


def __audit_background_tasks(obj: object, obj_name: str, ce_data: dict[str, dict]) -> list[pb.Problem]:
    util.logger.info("%s: Auditing CE background tasks", obj_name)
    problems = []
    ce_tasks = ce_data.get(_CE_TASKS)
    if ce_tasks is None:
        util.logger.warning("%s: Can't find Compute Engine Tasks in SIF, audit on CE task is skipped", obj_name)
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
        util.logger.info(
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
        util.logger.info("%s: Number of pending background tasks (%d) is OK", obj_name, ce_pending)
    return problems


def __audit_jvm(obj: object, obj_name: str, jvm_state: dict[str, str], heap_limits: tuple[int] = (1024, 4096)) -> list[pb.Problem]:
    util.logger.info("%s: Auditing JVM RAM", obj_name)
    # On DCE we expect between 2 and 4 GB of RAM per App Node Web JVM
    (min_heap, max_heap) = heap_limits
    try:
        heap = jvm_state["Heap Max (MB)"]
    except KeyError:
        util.logger.warning("%s: Can't find JVM Heap in SIF, auditing this part is skipped", obj_name)
        return []
    if heap < min_heap or heap > max_heap:
        rule = rules.get_rule(rules.RuleId.WRONG_HEAP_ALLOC)
        return [pb.Problem(broken_rule=rule, msg=rule.msg.format(obj_name, heap, min_heap, max_heap), concerned_object=obj)]
    util.logger.info("%s: Heap of %d MB is within recommended range [%d-%d]", obj_name, heap, min_heap, max_heap)
    return []


def __audit_jvm_version(obj: object, obj_name: str, jvm_props: dict[str, str]) -> list[pb.Problem]:
    util.logger.info("%s: Auditing JVM version", obj_name)
    try:
        java_version = int(jvm_props["java.specification.version"])
    except KeyError:
        util.logger.warning("%s: Can't find Java version in SIF, auditing this part is skipped", obj_name)
        return []
    try:
        sq_version = obj.version()
    except KeyError:
        util.logger.warning("%s: Can't find SonarQube version in SIF, auditing this part is skipped", obj_name)
        return []
    if sq_version >= (9, 9, 0) and java_version != 17:
        rule = rules.get_rule(rules.RuleId.SETTING_WEB_WRONG_JAVA_VERSION)
        return [pb.Problem(broken_rule=rule, msg=rule.msg.format(obj_name, java_version), concerned_object=obj)]
    util.logger.info("%s: Running on the required java version (java %d)", obj_name, java_version)
    return []


def __audit_workers(obj: object, obj_name: str, ce_data: dict[str, str]) -> list[pb.Problem]:
    ed = obj.edition()
    if ed in ("community", "developer"):
        util.logger.info("%s: %s edition, CE workers audit skipped...", obj_name, ed)
        return []
    try:
        ce_workers = ce_data[_CE_TASKS][_WORKER_COUNT]
    except KeyError:
        util.logger.warning("%s: CE section missing from SIF, CE workers audit skipped...", obj_name)
        return []
    MAX_WORKERS = 4  # EE
    if ed == "datacenter":
        MAX_WORKERS = 6
    if ce_workers > MAX_WORKERS:
        rule = rules.get_rule(rules.RuleId.CE_TOO_MANY_WORKERS)
        return [pb.Problem(broken_rule=rule, msg=rule.msg.format(ce_workers, MAX_WORKERS), concerned_object=obj)]
    else:
        util.logger.info(
            "%s: %d CE workers configured, correct compared to the max %d recommended",
            obj_name,
            ce_workers,
            MAX_WORKERS,
        )
    return []


def __log_level(logging_section):
    return logging_section.get("Logs Level", None)


def __audit_log_level(obj: object, obj_name: str, logging_data: dict[str, str]):
    util.logger.info("%s: Auditing log level", obj_name)
    lvl = __log_level(logging_data)
    if lvl is None:
        util.logger.warning("%s: log level is missing, audit of log level is skipped...", obj_name)
        return []
    if lvl not in ("DEBUG", "TRACE"):
        util.logger.info("%s: Log level is '%s', all good...", obj_name, lvl)
        return []
    if lvl == "TRACE":
        return [
            pb.Problem(
                problem_type=types.Type.PERFORMANCE,
                severity=severities.Severity.CRITICAL,
                msg=f"Log level of {obj_name} set to TRACE, this does very negatively affect platform performance, reverting to INFO is required",
                concerned_object=obj,
            )
        ]
    if lvl == "DEBUG":
        return [
            pb.Problem(
                problem_type=types.Type.PERFORMANCE,
                severity=severities.Severity.HIGH,
                msg=f"Log level of {obj_name} is set to DEBUG, this may affect platform performance, reverting to INFO is recommended",
                concerned_object=obj,
            )
        ]
    util.logger.info("%s: Node log level is '%s', this is fine", obj_name, lvl)
    return []


def audit_version(obj: object, obj_name: str) -> list[pb.Problem]:
    sq_version = obj.version()
    if sq_version is None:
        util.logger.warning("%s: Version information is missing, audit on node vresion is skipped...")
        return []
    st_time = obj.start_time()
    if st_time > _RELEASE_DATE_8_9:
        current_lts = (8, 9, 0)

    elif st_time > _RELEASE_DATE_7_9:
        current_lts = (7, 9, 0)
    elif st_time > _RELEASE_DATE_6_7:
        current_lts = (6, 7, 0)
    else:
        current_lts = (5, 9, 0)
    lts_str = f"{current_lts[0]}.{current_lts[1]}"
    if sq_version >= current_lts:
        util.logger.info("%s: Version %s is correct wrt LTS %s", obj_name, obj.version(as_string=True), lts_str)
        return []

    rule = rules.get_rule(rules.RuleId.BELOW_LTS)
    return [pb.Problem(broken_rule=rule, msg=rule.msg.format(obj.version(as_string=True), lts_str))]


def audit_ce(obj: object, obj_name: str, node_data: dict[str, dict]):
    nb_workers = node_data[_CE_TASKS][_WORKER_COUNT]
    heap_min = max(2048, 1024 * nb_workers)
    heap_max = max(4096, 2048 * nb_workers)
    return (
        __audit_background_tasks(obj, obj_name, node_data)
        + __audit_workers(obj, obj_name, node_data)
        + __audit_jvm(obj, obj_name, node_data["Compute Engine JVM State"], (heap_min, heap_max))
        + __audit_log_level(obj, obj_name, node_data["Compute Engine Logging"])
        + __audit_jvm_version(obj, obj_name, node_data["Compute Engine JVM Properties"])
    )


def audit_web(obj: object, obj_name: str, node_data: dict[str, dict]):
    (heap_min, heap_max) = (1024, 4096)
    if obj.edition() == "datacenter":
        (heap_min, heap_max) = (2048, 8192)
    return (
        audit_version(obj, obj_name)
        + __audit_jvm(obj, obj_name, node_data["Web JVM State"], (heap_min, heap_max))
        + __audit_log_level(obj, obj_name, node_data["Web Logging"])
        + __audit_jvm_version(obj, obj_name, node_data["Web JVM Properties"])
    )
