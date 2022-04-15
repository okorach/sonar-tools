#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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


SYNC_IGNORE_COMPONENTS = 'ignore_components'
SYNC_ADD_LINK = 'add_link'
SYNC_ADD_COMMENTS = 'add_comments'
SYNC_COMMENTS = 'sync_comments'
SYNC_ASSIGN = 'sync_assignments'
SYNC_SERVICE_ACCOUNTS = 'sync_service_accounts'

SRC_KEY = 'sourceIssueKey'
SRC_URL = 'sourceIssueUrl'
SYNC_MSG = 'syncMessage'
SYNC_MATCHES = 'matches'
TGT_KEY = 'targetIssueKey'
TGT_URL = 'targetIssueUrl'
SYNC_STATUS = 'syncStatus'


def __get_issues(issue_list):
    iss_list = []
    for issue in issue_list:
        iss_list.append({SRC_KEY: issue.key, SRC_URL: issue.url()})
    return iss_list


def __process_exact_sibling(issue, sibling, settings):
    if sibling.has_changelog_or_comments():
        issue.apply_changelog(sibling, settings)
        msg = 'Source issue changelog applied successfully'
    else:
        msg = 'Source issue has no changelog'
    return {
        SRC_KEY: issue.key,
        SRC_URL: issue.url(),
        SYNC_STATUS: 'synchronized',
        SYNC_MSG: msg,
        TGT_KEY: sibling.key,
        TGT_URL: sibling.url()
    }


def __process_no_match(issue):
    return {
        SRC_KEY: issue.key,
        SRC_URL: issue.url(),
        SYNC_STATUS: 'no match',
        SYNC_MSG: 'Source issue has no match in target project'
    }


def __process_multiple_exact_siblings(issue, siblings):
    util.logger.info('Multiple matches for %s, cannot automatically apply changelog', str(issue))
    for sib in siblings:
        comment = ''
        i = 0
        for sib2 in siblings:
            if sib.key == sib2.key:
                continue
            i += 1
            comment += f"[issue {i}]({sib2.url()}), "
        sib.add_comment(f"Sync did not happen due to multiple matches. [This original issue]({issue.url()}) "
                        f"corresponds to this issue,\nbut also to these other issues: {comment[:-2]}")
    return {
        SRC_KEY: issue.key,
        SRC_URL: issue.url(),
        SYNC_STATUS: 'unsynchronized',
        SYNC_MSG: 'Multiple matches',
        SYNC_MATCHES: __get_issues(siblings)
    }


def __process_approx_siblings(issue, siblings):
    util.logger.info('Found %d approximate siblings for issue %s, cannot automatically apply changelog',
                     len(siblings), str(issue))
    return {
        SRC_KEY: issue.key,
        SRC_URL: issue.url(),
        SYNC_STATUS: 'unsynchronized',
        SYNC_MSG: 'Approximate matches only',
        SYNC_MATCHES: __get_issues(siblings)
    }


def __process_modified_siblings(issue, siblings):
    util.logger.info(
        'Found %d siblings for issue %s, but they already have a changelog, cannot automatically apply changelog',
        len(siblings), str(issue))
    return {
        SRC_KEY: issue.key,
        SRC_URL: issue.url(),
        TGT_KEY: siblings[0].key,
        TGT_URL: siblings[0].url(),
        SYNC_STATUS: 'unsynchronized',
        SYNC_MSG: 'Target issue already has a changelog',
        SYNC_MATCHES: __get_issues(siblings)
    }

def __sync_issues_list(src_issues, tgt_issues, settings):
    counters = {'nb_to_sync': len(src_issues), 'nb_applies': 0, 'nb_approx_match': 0,
                'nb_tgt_has_changelog': 0, 'nb_multiple_matches': 0}
    report = []

    util.logger.info("%d issues to sync, %d issues in target", len(src_issues), len(tgt_issues))
    for _, issue in src_issues.items():
        util.logger.debug('Searching sibling for issue %s', str(issue))
        (exact_siblings, approx_siblings, modified_siblings) = issue.search_siblings(
            tgt_issues, allowed_users=settings[SYNC_SERVICE_ACCOUNTS],
            ignore_component=settings[SYNC_IGNORE_COMPONENTS])
        if len(exact_siblings) == 1:
            report.append(__process_exact_sibling(exact_siblings[0], issue, settings))
            counters['nb_applies'] += 1
        elif len(exact_siblings) > 1:
            report.append(__process_multiple_exact_siblings(issue, exact_siblings))
            counters['nb_multiple_matches'] += 1
        elif approx_siblings:
            report.append(__process_approx_siblings(issue, approx_siblings))
            counters['nb_approx_match'] += 1
        elif modified_siblings:
            counters['nb_tgt_has_changelog'] += 1
            report.append(__process_modified_siblings(issue, modified_siblings))
        else:   # No match
            report.append(__process_no_match(issue))
    counters['nb_no_match'] = counters['nb_to_sync'] - (
        counters['nb_applies'] + counters['nb_tgt_has_changelog'] +
        counters['nb_multiple_matches'] + counters['nb_approx_match']
    )
    util.json_dump_debug(counters, "COUNTERS")
    return (report, counters)


def sync_lists(src_issues, tgt_issues, src_object, tgt_object, sync_settings=None):
    interesting_src_issues = {}
    util.logger.info("Syncing %d issues from %s into %d issues from %s", len(src_issues), str(src_object), len(tgt_issues), str(tgt_object))
    for key1, issue in src_issues.items():
        if not issue.has_changelog_or_comments():
            util.logger.debug("%s has no changelog or comments, skipped in sync", str(issue))
            continue
        if issue.is_closed():
            util.logger.info("%s is closed, so it will not be synchronized despite having a changelog", str(issue))
            continue
        modifiers = issue.modifiers_and_commenters()
        # TODO - Manage more than 1 sync account - diff the 2 lists
        syncer = sync_settings[SYNC_SERVICE_ACCOUNTS][0]
        if sync_settings is None:
            sync_settings = {}
        if sync_settings.get(SYNC_SERVICE_ACCOUNTS, None) is None:
            sync_settings[SYNC_SERVICE_ACCOUNTS] = [syncer]
        if len(modifiers) == 1 and modifiers[0] == syncer:
            util.logger.info("%s is has only been changed by %s, so it will not be synchronized despite having a changelog",
                str(issue), syncer)
            continue
        interesting_src_issues[key1] = issue
    util.logger.info("Found %d issues with manual changes in %s", len(interesting_src_issues), str(src_object))
    if len(interesting_src_issues) <= 0:
        util.logger.info("No issues with manual changes in %s, skipping...", str(src_object))
        counters = {'nb_to_sync': 0, 'nb_applies': 0, 'nb_approx_match': 0,
            'nb_tgt_has_changelog': 0, 'nb_multiple_matches': 0}
        return ([], counters)
    return __sync_issues_list(interesting_src_issues, tgt_issues, sync_settings)
