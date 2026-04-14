#
# sonar-tools
# Copyright (C) 2022-2026 Olivier Korach
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

from __future__ import annotations
from typing import Union, TYPE_CHECKING

import concurrent.futures
import traceback

import sonar.logging as log
import sonar.util.misc as util
from sonar import findings
from sonar.projects import Project
from sonar.branches import Branch
from sonar import exceptions

if TYPE_CHECKING:
    from sonar.util.types import ConfigSettings


SYNC_IGNORE_COMPONENTS = "ignore_components"
SYNC_ADD_LINK = "add_link"
SYNC_COMMENTS = "sync_comments"
SYNC_ASSIGN = "sync_assignments"
SYNC_SERVICE_ACCOUNT = "sync_service_account"
SYNC_TAG = "tag"
SYNC_BIDIRECTIONAL = "bidirectional"

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

_SYNC_COMMENT_PREFIXES = (
    "Automatically synchronized from [this original",
    "Automatic bidirectional sync",
)


def __is_sync_comment(text: str) -> bool:
    """Returns whether a comment is an auto-generated sync link comment."""
    return any(text.startswith(prefix) for prefix in _SYNC_COMMENT_PREFIXES)


def __delete_sync_comments(finding: findings.Finding) -> None:
    """Deletes all previous auto-generated sync link comments from a finding."""
    for cmt in finding.comments().values():
        if __is_sync_comment(cmt.get("value", "")) and "commentKey" in cmt:
            finding.delete_comment(cmt["commentKey"])


def __get_findings(findings_list: list[findings.Finding]) -> list[dict[str, str]]:
    """Returns a list of finding keys and their URLS"""
    return [{f"{_TGT}{_KEY}": f.key, f"{_TGT}{_URL}": f.url()} for f in findings_list]


def __issue_data(finding: findings.Finding, prefix: str) -> dict[str, str]:
    """Builds a dict of issue data for sync report"""
    data = {f"{prefix}{_KEY}": finding.key, f"{prefix}{_URL}": finding.url()}
    data |= {f"{prefix}{_PROJECT}": finding.projectKey, f"{prefix}{_BRANCH}": finding.branch, f"{prefix}{_PR}": finding.pull_request}
    return {k: v for k, v in data.items() if v is not None}


def __process_exact_sibling(finding: findings.Finding, sibling: findings.Finding, settings: ConfigSettings) -> dict[str, str]:
    """Returns data about an exact finding match"""
    finding_type = util.class_name(finding).lower()
    last_target_change = sibling.last_changelog_date()
    if finding.has_changelog(after=last_target_change) or finding.has_comments(after=last_target_change):
        count = sibling.apply_changelog(finding, settings)
        if settings.get(SYNC_ADD_LINK, True):
            __delete_sync_comments(finding)
            __delete_sync_comments(sibling)
            sibling.add_comment(f"Automatically synchronized from [this original {finding_type}]({finding.url()})")
        try:
            tags = finding.get_tags()
            if (tag := settings.get(SYNC_TAG, "")) != "":
                tags += [tag]
            else:
                log.debug("No tag to add in synced finding")
            if len(tags) > 0:
                sibling.set_tags(tags)
        except exceptions.UnsupportedOperation:
            # Setting tags on hotspots is currently not supported
            pass
        msg = f"Source {finding_type} changelog applied successfully ({count} changes)"
    elif last_target_change:
        msg = f"Source {finding_type} has no changelog more recent than target last changelog {last_target_change}"
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


def __sync_one_finding(src_finding: findings.Finding, tgt_findings: list[findings.Finding], settings: ConfigSettings) -> tuple[int, dict[str, str]]:
    """Syncs one finding"""
    (exact_siblings, approx_siblings, modified_siblings) = src_finding.search_siblings(
        tgt_findings,
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
    src_findings: list[findings.Finding], tgt_findings: list[findings.Finding], settings: ConfigSettings
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
                log.error(f"Finding sync timed out after 60 seconds for {future!s}, sync killed.")
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
    sync_settings: ConfigSettings = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Syncs 2 list of findings and returns report and count of syncs"""
    # Mass collect changelogs with multithreading, that will be needed later

    log.info("Removing closed issues from the source issues to sync")
    total_findings = len(src_findings)
    src_findings = [f for f in src_findings if not f.is_closed()]
    log.info("Removed %d closed issues from the sync, %d left to sync", total_findings - len(src_findings), len(src_findings))

    min_date = sync_settings[SYNC_SINCE_DATE]
    findings.get_changelogs(issue_list=src_findings, added_after=min_date, threads=sync_settings[SYNC_THREADS])
    findings.get_changelogs(issue_list=tgt_findings, added_after=min_date, threads=sync_settings[SYNC_THREADS])

    log.info("Removing issues with no changelogs%s and no comments from the source issues to sync", f" after {min_date}" if min_date else "")
    total_findings = len(src_findings)
    src_findings = [f for f in src_findings if f.has_changelog(after=min_date) or f.has_comments(after=min_date)]
    log.info("Removed %d issues from the sync, %d left to sync", total_findings - len(src_findings), len(src_findings))

    interesting_src_findings = []
    counters = dict.fromkeys(("nb_to_sync", "nb_applies", "nb_approx_match", "nb_tgt_has_changelog", "nb_multiple_matches", "exception"), 0)
    log.info("source has %d finding candidates to sync, target has %d", len(src_findings), len(tgt_findings))
    if len(src_findings) == 0 or len(tgt_findings) == 0:
        log.info("source or target list of findings to sync empty, skipping...")
        return ([], counters)

    log.info("Removing issues with only changes from the sync service account from the source issues to sync")
    syncer = sync_settings[SYNC_SERVICE_ACCOUNT]
    for finding in src_findings:
        modifiers = finding.modifiers().union(finding.commenters())
        if len(modifiers) == 1 and list(modifiers)[0] == syncer:
            log.info("%s has only been changed by %s, so it will not be synchronized despite having a changelog", finding, syncer)
            continue
        interesting_src_findings.append(finding)

    log.info(
        "Found %d %ss with manual changes left to sync in %s",
        len(interesting_src_findings),
        util.class_name(src_findings[0]).lower(),
        str(src_object),
    )
    sync_settings[SYNC_IGNORE_COMPONENTS] = src_object.project().key != tgt_object.project().key
    return __sync_curated_list(interesting_src_findings, tgt_findings, sync_settings)


# --- Bidirectional sync functions ---


def __build_pair_mapping(
    driving_findings: list[findings.Finding],
    all_src_findings: list[findings.Finding],
    all_tgt_findings: list[findings.Finding],
    ignore_component: bool,
) -> tuple[list[tuple[findings.Finding, findings.Finding]], list[dict[str, str]], dict[str, int]]:
    """Builds finding pairs for bidirectional sync.

    Each driving finding is matched against the full pool on the opposite side.
    Single-threaded because it mutates the available pools.
    """
    available_src = list(all_src_findings)
    available_tgt = list(all_tgt_findings)
    src_keys = {f.key for f in all_src_findings}
    pairs = []
    report = []
    # Only count non-match outcomes here; EXACT_MATCH is counted later when pairs are actually synced
    counters = dict.fromkeys((APPROX_MATCH, MULTIPLE_MATCHES, NO_MATCH, "nb_skipped"), 0)
    already_paired = set()

    for finding in driving_findings:
        if finding.key in already_paired:
            counters["nb_skipped"] += 1
            continue
        # Determine which pool to search: if the driving finding comes from src, search tgt, and vice versa
        search_pool = available_tgt if finding.key in src_keys else available_src

        (exact_matches, approx_matches) = finding.search_siblings_bidirectional(search_pool, ignore_component=ignore_component)
        if len(exact_matches) == 1:
            match = exact_matches[0]
            pairs.append((finding, match))
            already_paired.add(finding.key)
            already_paired.add(match.key)
            if match in available_src:
                available_src.remove(match)
            if match in available_tgt:
                available_tgt.remove(match)
            if finding in available_src:
                available_src.remove(finding)
            if finding in available_tgt:
                available_tgt.remove(finding)
        elif len(exact_matches) > 1:
            report.append(__process_multiple_exact_siblings(finding, exact_matches))
            counters[MULTIPLE_MATCHES] += 1
        elif approx_matches:
            report.append(__process_approx_siblings(finding, approx_matches))
            counters[APPROX_MATCH] += 1
        else:
            report.append(__process_no_match(finding))
            counters[NO_MATCH] += 1

    return pairs, report, counters


def __sync_comments_bidirectional(finding_a: findings.Finding, finding_b: findings.Finding, service_account: str) -> int:
    """Syncs comments bidirectionally between two findings using content-based dedup.

    Returns the number of comments added.
    """
    count = 0
    comments_a = finding_a.comments()
    comments_b = finding_b.comments()

    # Collect ALL comment text values on each side (including service account copies)
    # so that previously-synced comments are recognized as duplicates
    all_values_a = {cmt.get("value", "") for cmt in comments_a.values()}
    all_values_b = {cmt.get("value", "") for cmt in comments_b.values()}

    # Add comments from A that are missing on B (skip auto-generated and service account comments)
    for cmt in comments_a.values():
        if __is_sync_comment(cmt.get("value", "")):
            continue
        if cmt.get("user") == service_account:
            continue
        if cmt["value"] not in all_values_b:
            finding_b.add_comment(cmt["value"])
            count += 1

    # Add comments from B that are missing on A (skip auto-generated and service account comments)
    for cmt in comments_b.values():
        if __is_sync_comment(cmt.get("value", "")):
            continue
        if cmt.get("user") == service_account:
            continue
        if cmt["value"] not in all_values_a:
            finding_a.add_comment(cmt["value"])
            count += 1

    return count


def __sync_tags_bidirectional(finding_a: findings.Finding, finding_b: findings.Finding, sync_tag: str) -> None:
    """Syncs tags bidirectionally by computing the union of both sides' tags."""
    try:
        tags_a = set(finding_a.get_tags())
        tags_b = set(finding_b.get_tags())
        merged = tags_a | tags_b
        if sync_tag:
            merged.add(sync_tag)
        merged_list = sorted(merged)
        if set(merged_list) != tags_a:
            finding_a.set_tags(merged_list)
        if set(merged_list) != tags_b:
            finding_b.set_tags(merged_list)
    except exceptions.UnsupportedOperation:
        # Setting tags on hotspots is currently not supported
        pass


def __sync_one_pair_bidirectional(finding_a: findings.Finding, finding_b: findings.Finding, settings: ConfigSettings) -> tuple[str, dict[str, str]]:
    """Syncs one pair of findings bidirectionally.
    Changelog: most-recent-wins direction. Comments: merge. Tags: union."""
    finding_type = util.class_name(finding_a).lower()
    service_account = settings.get(SYNC_SERVICE_ACCOUNT, "")

    # Determine changelog direction: the side with the more recent last_changelog_date is the "source"
    date_a = finding_a.last_changelog_date()
    date_b = finding_b.last_changelog_date()
    changelog_count = 0
    if date_a is not None and (date_b is None or date_a > date_b):
        # A is newer, apply A's changelog to B
        changelog_count = finding_b.apply_changelog(finding_a, settings)
        sync_direction = "A->B"
    elif date_b is not None and (date_a is None or date_b > date_a):
        # B is newer, apply B's changelog to A
        changelog_count = finding_a.apply_changelog(finding_b, settings)
        sync_direction = "B->A"
    else:
        sync_direction = "none"

    # Comments: bidirectional merge
    comment_count = __sync_comments_bidirectional(finding_a, finding_b, service_account)

    # Tags: set union
    __sync_tags_bidirectional(finding_a, finding_b, settings.get(SYNC_TAG, ""))

    # Delete old sync link comments and add a fresh one as the last comment
    if settings.get(SYNC_ADD_LINK, True) and (changelog_count > 0 or comment_count > 0):
        __delete_sync_comments(finding_a)
        __delete_sync_comments(finding_b)
        if sync_direction == "A->B":
            finding_a.add_comment(f"Automatic bidirectional sync (as source) with [this {finding_type}]({finding_b.url()})")
            finding_b.add_comment(f"Automatic bidirectional sync (as target) with [this {finding_type}]({finding_a.url()})")
        elif sync_direction == "B->A":
            finding_a.add_comment(f"Automatic bidirectional sync (as target) with [this {finding_type}]({finding_b.url()})")
            finding_b.add_comment(f"Automatic bidirectional sync (as source) with [this {finding_type}]({finding_a.url()})")
        else:
            finding_a.add_comment(f"Automatic bidirectional sync with [this {finding_type}]({finding_b.url()})")
            finding_b.add_comment(f"Automatic bidirectional sync with [this {finding_type}]({finding_a.url()})")

    msg = f"Bidirectional sync: {changelog_count} changelog changes ({sync_direction}), {comment_count} comments merged"
    report = (
        __issue_data(finding_a, _SRC)
        | __issue_data(finding_b, _TGT)
        | {
            _SYNC_STATUS: "synchronized",
            _SYNC_MSG: msg,
            "syncDirection": sync_direction,
        }
    )
    return EXACT_MATCH, report


def __sync_curated_list_bidirectional(
    pairs: list[tuple[findings.Finding, findings.Finding]], settings: ConfigSettings
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Syncs a list of finding pairs bidirectionally using thread pool."""
    counters = dict.fromkeys((EXACT_MATCH, "timeout", "exception"), 0)
    report = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.get(SYNC_THREADS, 8), thread_name_prefix="BiDirSync") as executor:
        futures = [executor.submit(__sync_one_pair_bidirectional, a, b, settings) for a, b in pairs]
        for future in concurrent.futures.as_completed(futures):
            try:
                match_type, result = future.result(timeout=60)
                report.append(result)
                counters[match_type] += 1
            except TimeoutError:
                counters["timeout"] += 1
                log.error("Bidirectional finding sync timed out after 60 seconds for %s, sync killed.", str(future))
            except Exception as e:
                counters["exception"] += 1
                log.error("Bidirectional sync task raised an exception: %s", e)
                traceback.print_exc()

    log.debug("Bidirectional curated list sync results: %s", util.json_dump(counters))
    return report, counters


def __filter_service_account_only(finding_list: list[findings.Finding], service_account: str) -> list[findings.Finding]:
    """Filters out findings that have only been modified by the service account."""
    interesting = []
    for finding in finding_list:
        modifiers = finding.modifiers().union(finding.commenters())
        if len(modifiers) == 1 and list(modifiers)[0] == service_account:
            log.info("%s has only been changed by %s, so it will not be synchronized despite having a changelog", finding, service_account)
            continue
        interesting.append(finding)
    return interesting


def sync_lists_bidirectional(
    src_findings: list[findings.Finding],
    tgt_findings: list[findings.Finding],
    src_object: object,
    tgt_object: object,
    sync_settings: ConfigSettings = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Syncs 2 lists of findings bidirectionally and returns report and count of syncs"""
    # Remove closed issues from BOTH sides
    log.info("Removing closed issues from both sides for bidirectional sync")
    total_src = len(src_findings)
    src_findings = [f for f in src_findings if not f.is_closed()]
    log.info("Removed %d closed source issues, %d left", total_src - len(src_findings), len(src_findings))

    total_tgt = len(tgt_findings)
    tgt_findings = [f for f in tgt_findings if not f.is_closed()]
    log.info("Removed %d closed target issues, %d left", total_tgt - len(tgt_findings), len(tgt_findings))

    # Mass collect changelogs for both sides
    min_date = sync_settings[SYNC_SINCE_DATE]
    findings.get_changelogs(issue_list=src_findings, added_after=min_date, threads=sync_settings[SYNC_THREADS])
    findings.get_changelogs(issue_list=tgt_findings, added_after=min_date, threads=sync_settings[SYNC_THREADS])

    # Identify findings with changes on either side - these drive the sync
    interesting_src = [f for f in src_findings if f.has_changelog(after=min_date) or f.has_comments(after=min_date)]
    interesting_tgt = [f for f in tgt_findings if f.has_changelog(after=min_date) or f.has_comments(after=min_date)]
    log.info("Found %d source and %d target findings with changes", len(interesting_src), len(interesting_tgt))

    # Collect all findings that have changes on either side (deduped)
    interesting_keys = {f.key for f in interesting_src} | {f.key for f in interesting_tgt}
    if len(interesting_keys) == 0:
        log.info("No findings with changes on either side, skipping bidirectional sync...")
        counters = dict.fromkeys(("nb_to_sync", EXACT_MATCH, APPROX_MATCH, MULTIPLE_MATCHES, NO_MATCH, "timeout", "exception"), 0)
        return [], counters

    # Filter service-account-only changes from the driving set
    service_account = sync_settings[SYNC_SERVICE_ACCOUNT]
    interesting_src = __filter_service_account_only(interesting_src, service_account)
    interesting_tgt = __filter_service_account_only(interesting_tgt, service_account)

    # Build a combined driving set: findings with changes, deduped by key
    driving_findings = list(interesting_src)
    driving_keys = {f.key for f in driving_findings}
    for f in interesting_tgt:
        if f.key not in driving_keys:
            driving_findings.append(f)
            driving_keys.add(f.key)

    counters = dict.fromkeys(("nb_to_sync", EXACT_MATCH, APPROX_MATCH, MULTIPLE_MATCHES, NO_MATCH, "timeout", "exception"), 0)
    log.info("Bidirectional sync: %d findings with manual changes to sync", len(driving_findings))
    if len(driving_findings) == 0:
        return [], counters

    ignore_components = src_object.project().key != tgt_object.project().key
    sync_settings[SYNC_IGNORE_COMPONENTS] = ignore_components

    # Match driving findings against the FULL pool of non-closed findings on the other side
    # A finding from src with changes must be able to find its match in tgt even if the tgt copy has no changelog
    log.info(
        "Building bidirectional pair mapping from %d driving findings against %d src + %d tgt findings",
        len(driving_findings),
        len(src_findings),
        len(tgt_findings),
    )
    pairs, pair_report, pair_counters = __build_pair_mapping(driving_findings, src_findings, tgt_findings, ignore_components)
    nb_skipped = pair_counters.pop("nb_skipped", 0)
    counters.update(pair_counters)
    counters["nb_to_sync"] = len(driving_findings) - nb_skipped

    log.info("Built %d pairs for bidirectional sync", len(pairs))
    sync_report, sync_counters = __sync_curated_list_bidirectional(pairs, sync_settings)

    # Merge counters
    for k, v in sync_counters.items():
        counters[k] = counters.get(k, 0) + v

    return pair_report + sync_report, counters


def sync_objects(
    src_object: Union[Project, Branch], tgt_object: Union[Project, Branch], sync_settings: ConfigSettings = None
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Syncs findings from a source object into a target object"""
    sync_func = sync_lists_bidirectional if sync_settings.get(SYNC_BIDIRECTIONAL, False) else sync_lists
    log.info(
        "Syncing %s and %s issues (%s)",
        str(src_object),
        str(tgt_object),
        "bidirectional" if sync_settings.get(SYNC_BIDIRECTIONAL) else "unidirectional",
    )
    (report, issue_counters) = sync_func(
        list(src_object.get_issues().values()),
        list(tgt_object.get_issues().values()),
        src_object,
        tgt_object,
        sync_settings=sync_settings,
    )
    issue_counters = {f"issues_{k}": v for k, v in issue_counters.items()}
    log.info(
        "Syncing %s and %s hotspots (%s)",
        str(src_object),
        str(tgt_object),
        "bidirectional" if sync_settings.get(SYNC_BIDIRECTIONAL) else "unidirectional",
    )
    (tmp_report, hotspot_counters) = sync_func(
        list(src_object.get_hotspots().values()),
        list(tgt_object.get_hotspots().values()),
        src_object,
        tgt_object,
        sync_settings=sync_settings,
    )
    report += tmp_report
    hotspot_counters = {f"hotspots_{k}": v for k, v in hotspot_counters.items()}
    return report, issue_counters | hotspot_counters
