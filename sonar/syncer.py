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

import sonar.logging as log
import sonar.utilities as util
from sonar.util import types
from sonar import findings


SYNC_IGNORE_COMPONENTS = "ignore_components"
SYNC_ADD_LINK = "add_link"
SYNC_ADD_COMMENTS = "add_comments"
SYNC_COMMENTS = "sync_comments"
SYNC_ASSIGN = "sync_assignments"
SYNC_SERVICE_ACCOUNTS = "sync_service_accounts"

SRC_KEY = "sourceFindingKey"
SRC_URL = "sourceFindingUrl"
SYNC_MSG = "syncMessage"
SYNC_MATCHES = "matches"
TGT_KEY = "targetFindingKey"
TGT_URL = "targetFindingUrl"
SYNC_STATUS = "syncStatus"
SYNC_SINCE_DATE = "syncSinceDate"
SYNC_THREADS = "threads"


def __get_findings(findings_list: list[findings.Finding]) -> list[dict[str, str]]:
    """Returns a list of finding keys and their URLS"""
    return [{SRC_KEY: f.key, SRC_URL: f.url()} for f in findings_list]


def __process_exact_sibling(finding: findings.Finding, sibling: findings.Finding, settings: types.ConfigSettings) -> dict[str, str]:
    """Returns data about an exact finding match"""
    if finding.has_changelog() or finding.has_comments():
        sibling.apply_changelog(finding, settings)
        msg = f"Source {util.class_name(finding).lower()} changelog applied successfully"
    else:
        msg = f"Source {util.class_name(finding).lower()} has no changelog"
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        SYNC_STATUS: "synchronized",
        SYNC_MSG: msg,
        TGT_KEY: sibling.key,
        TGT_URL: sibling.url(),
    }


def __process_no_match(finding: findings.Finding) -> dict[str, str]:
    """Returns data about no finding match"""
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        SYNC_STATUS: "no match",
        SYNC_MSG: f"Source {util.class_name(finding).lower()} has no match in target project",
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
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        SYNC_STATUS: "unsynchronized",
        SYNC_MSG: "Multiple matches",
        SYNC_MATCHES: __get_findings(siblings),
    }


def __process_approx_siblings(finding: findings.Finding, siblings: list[findings.Finding]) -> dict[str, str]:
    """Returns data about unsync finding because of multiple approximate matches"""
    log.info("Found %d approximate matches for %s, cannot automatically apply changelog", len(siblings), str(finding))
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        SYNC_STATUS: "unsynchronized",
        SYNC_MSG: "Approximate matches only",
        SYNC_MATCHES: __get_findings(siblings),
    }


def __process_modified_siblings(finding: findings.Finding, siblings: list[findings.Finding]) -> dict[str, str]:
    """Returns data about unsync finding because match already has a change log"""
    log.info("Found %d match(es) for %s, but they already have a changelog, cannot automatically apply changelog", len(siblings), str(finding))
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        TGT_KEY: siblings[0].key,
        TGT_URL: siblings[0].url(),
        SYNC_STATUS: "unsynchronized",
        SYNC_MSG: f"Target {util.class_name(finding).lower()} already has a changelog",
    }


def __sync_curated_list(
    src_findings: list[findings.Finding], tgt_findings: list[findings.Finding], settings: types.ConfigSettings
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Syncs 2 list of findings"""
    counters = {k: 0 for k in ("nb_applies", "nb_approx_match", "nb_tgt_has_changelog", "nb_multiple_matches")}
    counters["nb_to_sync"] = len(src_findings)
    name = "finding" if len(src_findings) == 0 else util.class_name(src_findings[0]).lower()
    report = []
    log.info("%d %ss to sync, %d %ss in target", len(src_findings), name, len(tgt_findings), name)
    for finding in src_findings:
        log.debug("Searching sibling for %s", str(finding))
        (exact_siblings, approx_siblings, modified_siblings) = finding.search_siblings(
            tgt_findings,
            allowed_users=settings[SYNC_SERVICE_ACCOUNTS],
            ignore_component=settings[SYNC_IGNORE_COMPONENTS],
        )
        if len(exact_siblings) == 1:
            report.append(__process_exact_sibling(finding, exact_siblings[0], settings))
            counters["nb_applies"] += 1
        elif len(exact_siblings) > 1:
            report.append(__process_multiple_exact_siblings(finding, exact_siblings))
            counters["nb_multiple_matches"] += 1
        elif approx_siblings:
            report.append(__process_approx_siblings(finding, approx_siblings))
            counters["nb_approx_match"] += 1
        elif modified_siblings:
            counters["nb_tgt_has_changelog"] += 1
            report.append(__process_modified_siblings(finding, modified_siblings))
        else:  # No match
            report.append(__process_no_match(finding))
    counters["nb_no_match"] = counters["nb_to_sync"] - (
        counters["nb_applies"] + counters["nb_tgt_has_changelog"] + counters["nb_multiple_matches"] + counters["nb_approx_match"]
    )
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
    counters = {k: 0 for k in ("nb_to_sync", "nb_applies", "nb_approx_match", "nb_tgt_has_changelog", "nb_multiple_matches")}
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
        # TODO - Manage more than 1 sync account - diff the 2 lists
        syncer = sync_settings[SYNC_SERVICE_ACCOUNTS][0]
        if sync_settings is None:
            sync_settings = {}
        if sync_settings.get(SYNC_SERVICE_ACCOUNTS, None) is None:
            sync_settings[SYNC_SERVICE_ACCOUNTS] = [syncer]

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
