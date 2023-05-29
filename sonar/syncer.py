#
# sonar-tools
# Copyright (C) 2022-2023 Olivier Korach
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

import sonar.utilities as util


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


def __name(obj):
    return type(obj).__name__.lower()


def __get_findings(findings_list):
    find_list = []
    for finding in findings_list:
        find_list.append({SRC_KEY: finding.key, SRC_URL: finding.url()})
    return find_list


def __process_exact_sibling(finding, sibling, settings):
    if finding.has_changelog() or finding.has_comments():
        sibling.apply_changelog(finding, settings)
        msg = f"Source {__name(finding)} changelog applied successfully"
    else:
        msg = f"Source {__name(finding)} has no changelog"
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        SYNC_STATUS: "synchronized",
        SYNC_MSG: msg,
        TGT_KEY: sibling.key,
        TGT_URL: sibling.url(),
    }


def __process_no_match(finding):
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        SYNC_STATUS: "no match",
        SYNC_MSG: f"Source {__name(finding)} has no match in target project",
    }


def __process_multiple_exact_siblings(finding, siblings):
    util.logger.info("Multiple matches for %s, cannot automatically apply changelog", str(finding))
    name = __name(finding)
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


def __process_approx_siblings(finding, siblings):
    util.logger.info(
        "Found %d approximate siblings for %s, cannot automatically apply changelog",
        len(siblings),
        str(finding),
    )
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        SYNC_STATUS: "unsynchronized",
        SYNC_MSG: "Approximate matches only",
        SYNC_MATCHES: __get_findings(siblings),
    }


def __process_modified_siblings(finding, siblings):
    util.logger.info(
        "Found %d siblings for %s, but they already have a changelog, cannot automatically apply changelog",
        len(siblings),
        str(finding),
    )
    return {
        SRC_KEY: finding.key,
        SRC_URL: finding.url(),
        TGT_KEY: siblings[0].key,
        TGT_URL: siblings[0].url(),
        SYNC_STATUS: "unsynchronized",
        SYNC_MSG: f"Target {__name(finding)} already has a changelog",
    }


def __sync_findings_list(src_findings, tgt_findings, settings):
    counters = {
        "nb_to_sync": len(src_findings),
        "nb_applies": 0,
        "nb_approx_match": 0,
        "nb_tgt_has_changelog": 0,
        "nb_multiple_matches": 0,
    }
    report = []
    name = __name(list(src_findings.values())[0])
    util.logger.info(
        "%d %ss to sync, %d %ss in target",
        len(src_findings),
        name,
        len(tgt_findings),
        name,
    )
    for _, finding in src_findings.items():
        util.logger.debug("Searching sibling for %s", str(finding))
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
    util.json_dump_debug(counters, "COUNTERS")
    return (report, counters)


def sync_lists(src_findings, tgt_findings, src_object, tgt_object, sync_settings=None):
    interesting_src_findings = {}
    name = __name(list(src_findings.values())[0])
    util.logger.info(
        "Syncing %d %ss from %s into %d %ss from %s",
        len(src_findings),
        name,
        str(src_object),
        len(tgt_findings),
        name,
        str(tgt_object),
    )
    for key1, finding in src_findings.items():
        if not (finding.has_changelog() or finding.has_comments()):
            util.logger.debug("%s has no changelog or comments, skipped in sync", str(finding))
            continue
        if finding.is_closed():
            util.logger.info(
                "%s is closed, so it will not be synchronized despite having a changelog",
                str(finding),
            )
            continue
        modifiers = finding.modifiers().union(finding.commenters())
        # TODO - Manage more than 1 sync account - diff the 2 lists
        syncer = sync_settings[SYNC_SERVICE_ACCOUNTS][0]
        if sync_settings is None:
            sync_settings = {}
        if sync_settings.get(SYNC_SERVICE_ACCOUNTS, None) is None:
            sync_settings[SYNC_SERVICE_ACCOUNTS] = [syncer]
        if len(modifiers) == 1 and modifiers[0] == syncer:
            util.logger.info(
                "%s is has only been changed by %s, so it will not be synchronized despite having a changelog",
                str(finding),
                syncer,
            )
            continue
        interesting_src_findings[key1] = finding
    util.logger.info(
        "Found %d %ss with manual changes in %s",
        len(interesting_src_findings),
        name,
        str(src_object),
    )
    if len(interesting_src_findings) <= 0:
        util.logger.info("No %ss with manual changes in %s, skipping...", name, str(src_object))
        counters = {
            "nb_to_sync": 0,
            "nb_applies": 0,
            "nb_approx_match": 0,
            "nb_tgt_has_changelog": 0,
            "nb_multiple_matches": 0,
        }
        return ([], counters)
    return __sync_findings_list(interesting_src_findings, tgt_findings, sync_settings)
