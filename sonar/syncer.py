#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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

"""Findings syncer"""

import concurrent.futures
import traceback

from typing import Union

import sonar.logging as log
import sonar.utilities as util
from sonar.util import types
from sonar import findings
from sonar.projects import Project
from sonar.branches import Branch
from sonar import exceptions


SYNC_IGNORE_COMPONENTS = "ignore_components"
SYNC_ADD_LINK = "add_link"
SYNC_COMMENTS = "sync_comments"
SYNC_ASSIGN = "sync_assignments"
SYNC_SERVICE_ACCOUNT = "sync_service_account"
SYNC_TAG = "tag"

_SRC = "source"
_TGT = "target"
_KEY = "FindingKey"
_PROJECT = "Project"
_BRANCH = "Branch"
_PR = "PullRequest"
_URL = "FindingUrl"

_SYNC_MSG = "syncMessage"
_SYNC_MATCHES = "matches"
_SYNC_STATUS = "syncStatus"

SYNC_SINCE_DATE = "syncSinceDate"
SYNC_THREADS = "threads"

EXACT_MATCH = "nb_applies"
MULTIPLE_MATCHES = "nb_multiple_matches"
APPROX_MATCH = "nb_approx_match"
MODIFIED_MATCH = "nb_tgt_has_changelog"
NO_MATCH = "nb_no_match"


def __get_findings(findings_list: list[findings.Finding]) -> list[dict[str, str]]:
    """Returns a list of finding keys and their URLS"""
    return [{f"{_TGT}{_KEY}": f.key, f"{_TGT}{_URL}": f.url()} for f in findings_list]


def __issue_data(finding: findings.Finding, prefix: str) -> dict[str, str]:
    """Builds a dict of issue data for sync report"""
    data = {f"{prefix}{_KEY}": finding.key, f"{prefix}{_URL}": finding.url()}
    data |= {f"{prefix}{_PROJECT}": finding.projectKey, f"{prefix}{_BRANCH}": finding.branch, f"{prefix}{_PR}": finding.pull_request}
    return {k: v for k, v in data.items() if v is not None}


def __process_exact_sibling(finding: findings.Finding, sibling: findings.Finding, settings: types.ConfigSettings) -> dict[str, str]:
    """Returns data about an exact finding match"""
    finding_type = util.class_name(finding).lower()
    if finding.has_changelog() or finding.has_comments():
        if settings.get(SYNC_ADD_LINK, True):
            sibling.add_comment(f"Automatically synchronized from [this original {finding_type}]({finding.url()})")
        sibling.apply_changelog(finding, settings)
        if (tag := settings.get(SYNC_TAG, "")) != "":
            log.info("Adding TTATAG %s to %s", tag, sibling)
            try:
                sibling.add_tag(tag)
            except exceptions.UnsupportedOperation:
                # Setting tags on hotspots is currently not supported
                pass
        else:
            log.debug("No tag to add in synced finding")
        msg = f"Source {finding_type} changelog applied successfully"
    else:
        msg = f"Source {finding_type} has no changelog"
    return __issue_data(finding, _SRC) | __issue_data(sibling, _TGT) | {_SYNC_STATUS: "synchronized", _SYNC_MSG: msg}


def __process_no_match(finding: findings.Finding) -> dict[str, str]:
    """Returns data about no finding match"""
    return __issue_data(finding, _SRC) | {
        _SYNC_STATUS: "no match",
        _SYNC_MSG: f"Source {util.class_name(finding).lower()} has no match in target project",
    }


def __process_multiple_exact_siblings(finding: findings.Finding, siblings: list[findings.Finding]) -> dict[str, str]:
    """Returns data about multiple finding match"""
    log.info("Multiple matches for %s, cannot automatically apply changelog", str(finding))
    name = util.class_name(finding).lower()
    for sib in siblings:
        comment = ""
        i = 0
        for sib2 in siblings:
            if sib.key == sib2.key:
                continue
            i += 1
            comment += f"[{name} {i}]({sib2.url()}), "
        sib.add_comment(
            f"Sync did not happen due to multiple matches. [This original {name}]({finding.url()}) "
            f"corresponds to this {name},\nbut also to these other {name}s: {comment[:-2]}"
        )
    return __issue_data(finding, _SRC) | {
        _SYNC_STATUS: "unsynchronized",
        _SYNC_MSG: "Multiple matches",
        _SYNC_MATCHES: __get_findings(siblings),
    }


def __process_approx_siblings(finding: findings.Finding, siblings: list[findings.Finding]) -> dict[str, str]:
    """Returns data about unsync finding because of multiple approximate matches"""
    log.info("Found %d approximate matches for %s, cannot automatically apply changelog", len(siblings), str(finding))
    return __issue_data(finding, _SRC) | {
        _SYNC_STATUS: "unsynchronized",
        _SYNC_MSG: "Approximate matches only",
        _SYNC_MATCHES: __get_findings(siblings),
    }


def __process_modified_siblings(finding: findings.Finding, siblings: list[findings.Finding]) -> dict[str, str]:
    """Returns data about unsync finding because match already has a change log"""
    log.info("Found %d match(es) for %s, but they already have a changelog, cannot automatically apply changelog", len(siblings), str(finding))
    return (
        __issue_data(finding, _SRC)
        | __issue_data(siblings[0], _TGT)
        | {
            _SYNC_STATUS: "unsynchronized",
            _SYNC_MSG: f"Target {util.class_name(finding).lower()} already has a changelog",
        }
    )


def __sync_one_finding(
    src_finding: findings.Finding, tgt_findings: list[findings.Finding], settings: types.ConfigSettings
) -> tuple[int, dict[str, str]]:
    """Syncs one finding"""
    (exact_siblings, approx_siblings, modified_siblings) = src_finding.search_siblings(
        tgt_findings,
        sync_user=settings[SYNC_SERVICE_ACCOUNT],
        ignore_component=settings[SYNC_IGNORE_COMPONENTS],
    )
    if len(exact_siblings) == 1:
        code, report = EXACT_MATCH, __process_exact_sibling(src_finding, exact_siblings[0], settings)
    elif len(exact_siblings) > 1:
        code, report = MULTIPLE_MATCHES, __process_multiple_exact_siblings(src_finding, exact_siblings)
    elif approx_siblings:
        code, report = APPROX_MATCH, __process_approx_siblings(src_finding, approx_siblings)
    elif modified_siblings:
        code, report = MODIFIED_MATCH, __process_modified_siblings(src_finding, modified_siblings)
    else:
        code, report = NO_MATCH, __process_no_match(src_finding)
    log.debug("Syncing %s: result = %s", str(src_finding), code)
    return code, report


def __sync_curated_list(
    src_findings: list[findings.Finding], tgt_findings: list[findings.Finding], settings: types.ConfigSettings
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Syncs 2 list of findings"""
    counters = dict.fromkeys((EXACT_MATCH, APPROX_MATCH, MODIFIED_MATCH, MULTIPLE_MATCHES, NO_MATCH, "timeout", "exception"), 0)
    counters["nb_to_sync"] = len(src_findings)
    name = "finding" if len(src_findings) == 0 else util.class_name(src_findings[0]).lower()
    report = []
    log.debug("Curated list: %d %ss to sync, %d %ss in target", len(src_findings), name, len(tgt_findings), name)

    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.get(SYNC_THREADS, 8), thread_name_prefix="FindingSync") as executor:
        futures = [executor.submit(__sync_one_finding, finding, tgt_findings, settings) for finding in src_findings]
        for future in concurrent.futures.as_completed(futures):
            try:
                match_type, result = future.result(timeout=60)  # Retrieve result or raise an exception
                report.append(result)
                counters[match_type] += 1
            except TimeoutError:
                counters["timeout"] += 1
                log.error(f"Finding sync timed out after 60 seconds for {str(future)}, sync killed.")
            except Exception as e:
                counters["exception"] += 1
                log.error(f"Task raised an exception: {e}")
                traceback.print_exc()

    log.debug("Curated list sync results: %s", util.json_dump(counters))
    return (report, counters)


def sync_lists(
    src_findings: list[findings.Finding],
    tgt_findings: list[findings.Finding],
    src_object: object,
    tgt_object: object,
    sync_settings: types.ConfigSettings = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Syncs 2 list of findings and returns report and count of syncs"""
    # Mass collect changelogs with multithreading, that will be needed later
    min_date = sync_settings[SYNC_SINCE_DATE]
    findings.get_changelogs(issue_list=src_findings, added_after=min_date, threads=sync_settings[SYNC_THREADS])
    findings.get_changelogs(issue_list=tgt_findings, added_after=min_date, threads=sync_settings[SYNC_THREADS])

    interesting_src_findings = []
    counters = dict.fromkeys(("nb_to_sync", "nb_applies", "nb_approx_match", "nb_tgt_has_changelog", "nb_multiple_matches", "exception"), 0)
    log.info("source has %d finding candidates to sync, target has %d", len(src_findings), len(tgt_findings))
    if len(src_findings) == 0 or len(tgt_findings) == 0:
        log.info("source or target list of findings to sync empty, skipping...")
        return ([], counters)
    name = util.class_name(src_findings[0]).lower()
    sync_settings[SYNC_IGNORE_COMPONENTS] = src_object.project().key != tgt_object.project().key
    log.info("Syncing %d %ss from %s into %d %ss from %s", len(src_findings), name, str(src_object), len(tgt_findings), name, str(tgt_object))
    for finding in src_findings:
        if finding.is_closed():
            log.debug("%s is closed, so it will not be synchronized despite having a changelog", str(finding))
            continue
        if not (finding.has_changelog(added_after=min_date) or finding.has_comments()):
            log.debug("%s has no manual changelog or comments added after %s, skipped in sync", str(finding), str(min_date))
            continue

        modifiers = finding.modifiers().union(finding.commenters())
        syncer = sync_settings[SYNC_SERVICE_ACCOUNT]

        if len(modifiers) == 1 and list(modifiers)[0] == syncer:
            log.info(
                "%s has only been changed by %s, so it will not be synchronized despite having a changelog",
                str(finding),
                syncer,
            )
            continue
        interesting_src_findings.append(finding)

    log.info("Found %d %ss with manual changes in %s", len(interesting_src_findings), name, str(src_object))
    return __sync_curated_list(interesting_src_findings, tgt_findings, sync_settings)


def sync_objects(
    src_object: Union[Project, Branch], tgt_object: Union[Project, Branch], sync_settings: types.ConfigSettings = None
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Syncs findings from a source object into a target object"""
    log.info("Syncing %s and %s issues", str(src_object), str(tgt_object))
    (report, issue_counters) = sync_lists(
        list(src_object.get_issues().values()),
        list(tgt_object.get_issues().values()),
        src_object,
        tgt_object,
        sync_settings=sync_settings,
    )
    issue_counters = {f"issues_{k}": v for k, v in issue_counters.items()}
    log.info("Syncing %s and %s hotspots", str(src_object), str(tgt_object))
    (tmp_report, hotspot_counters) = sync_lists(
        list(src_object.get_hotspots().values()),
        list(tgt_object.get_hotspots().values()),
        src_object,
        tgt_object,
        sync_settings=sync_settings,
    )
    report += tmp_report
    hotspot_counters = {f"hotspots_{k}": v for k, v in hotspot_counters.items()}
    return report, issue_counters | hotspot_counters
