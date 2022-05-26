#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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

"""Abstraction of the SonarQube 'issue' concept"""

import datetime
import json
import re

import requests.utils

from sonar import env, projects, users, syncer
from sonar.findings import findings, changelog
import sonar.utilities as util

SEARCH_CRITERIAS = (
    "componentKeys",
    "types",
    "severities",
    "createdAfter",
    "createdBefore",
    "createdInLast",
    "createdAt",
    "branch",
    "pullRequest",
    "statuses",
    "tags",
    "inNewCodePeriod",
    "sinceLeakPeriod",
    "p",
    "page",
    "facets",
    "onComponentOnly",
    "s",
    "timeZone",
    "cwe",
    "owaspTop10",
    "owaspTop10-21",
    "sansTop25",
    "sonarsourceSecurity",
    "additionalFields",
    "asc",
    "assigned",
    "assignees",
    "author",
    "issues",
    "languages",
    "resolutions",
    "resolved",
    "rules",
    "scopes",
)

TYPES = ("BUG", "VULNERABILITY", "CODE_SMELL")
SEVERITIES = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")
STATUSES = ("OPEN", "CONFIRMED", "REOPENED", "RESOLVED", "CLOSED")
RESOLUTIONS = ("FALSE-POSITIVE", "WONTFIX", "FIXED", "REMOVED")

_TOO_MANY_ISSUES_MSG = "Too many issues, recursing..."
_ISSUES = {}


class TooManyIssuesError(Exception):
    """When a call to api/issues/search returns too many issues."""

    def __init__(self, nbr_issues, message):
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message


class Issue(findings.Finding):
    """SonarQube Issue."""

    SEARCH_API = "issues/search"
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000
    OPTIONS_SEARCH = [
        "additionalFields",
        "asc",
        "assigned",
        "assignees",
        "authors",
        "componentKeys",
        "createdAfter",
        "createdAt",
        "createdBefore",
        "createdInLast",
        "directories",
        "facetMode",
        "facets",
        "files",
        "branch",
        "fileUuids",
        "issues",
        "languages",
        "onComponentOnly",
        "p",
        "ps",
        "resolutions",
        "resolved",
        "rules",
        "s",
        "severities",
        "sinceLeakPeriod",
        "statuses",
        "tags",
        "types",
    ]

    def __init__(self, key, endpoint, data=None, from_export=False):
        super().__init__(key, endpoint, data, from_export)
        self._debt = None
        if data is not None:
            self.component = data.get("component", None)
        # util.logger.debug("Loaded issue: %s", util.json_dump(data))
        _ISSUES[self.uuid()] = self

    def __str__(self):
        return f"Issue key '{self.key}'"

    def __format__(self, format_spec=""):
        return (
            f"Key: {self.key} - Type: {self.type} - Severity: {self.severity}"
            f" - File/Line: {self.component}/{self.line} - Rule: {self.rule} - Project: {self.projectKey}"
        )

    def to_string(self):
        """Dumps the object in a string."""
        return util.json_dump(self._json)

    def url(self):
        branch = ""
        if self.branch is not None:
            branch = f"&branch={requests.utils.quote(self.branch)}"
        elif self.pull_request is not None:
            branch = f"pullRequest={requests.utils.quote(self.pull_request)}&"
        return f"{self.endpoint.url}/project/issues?id={self.projectKey}{branch}&issues={self.key}"

    def debt(self):
        if self._debt is not None:
            return self._debt
        if "debt" in self._json:
            kdays, days, hours, minutes = 0, 0, 0, 0
            debt = self._json["debt"]
            m = re.search(r"(\d+)kd", debt)
            if m:
                kdays = int(m.group(1))
            m = re.search(r"(\d+)d", debt)
            if m:
                days = int(m.group(1))
            m = re.search(r"(\d+)h", debt)
            if m:
                hours = int(m.group(1))
            m = re.search(r"(\d+)min", debt)
            if m:
                minutes = int(m.group(1))
            self._debt = ((kdays * 1000 + days) * 24 + hours) * 60 + minutes
        elif "effort" in self._json:
            self._debt = 0
            if self._json["effort"] != "null":
                self._debt = int(self._json["effort"])
        return self._debt

    def to_json(self):
        data = super().to_json()
        data["url"] = self.url()
        data["effort"] = self.debt()
        return data

    def read(self):
        resp = self.get(Issue.SEARCH_API, params={"issues": self.key, "additionalFields": "_all"})
        self._load(resp.issues[0])

    def changelog(self):
        if self._changelog is None:
            resp = self.get("issues/changelog", {"issue": self.key, "format": "json"})
            data = json.loads(resp.text)
            util.json_dump_debug(data["changelog"], f"{str(self)} Changelog = ")
            self._changelog = {}
            seq = 1
            for l in data["changelog"]:
                d = changelog.Changelog(l)
                if d.is_technical_change():
                    # Skip automatic changelog events generated by SonarSource itself
                    util.logger.debug("Changelog is a technical change: %s", str(d))
                    continue
                util.json_dump_debug(l, "Changelog item Changelog ADDED = ")
                seq += 1
                self._changelog[f"{d.date()}_{seq:03d}"] = d
        return self._changelog

    def get_all_events(self, event_type="changelog"):
        if event_type == "comments":
            events = self.comments()
            util.logger.debug("Issue %s has %d comments", self.key, len(events))
        else:
            events = self.changelog()
            util.logger.debug("Issue %s has %d changelog", self.key, len(events))
        bydate = {}
        for e in events:
            bydate[e["date"]] = e
        return bydate

    def comments(self):
        if "comments" not in self._json:
            self._comments = {}
        elif self._comments is None:
            self._comments = {}
            seq = 0
            for c in self._json["comments"]:
                seq += 1
                self._comments[f"{c['createdAt']}_{seq:03}"] = {
                    "date": c["createdAt"],
                    "event": "comment",
                    "value": c["markdown"],
                    "user": c["login"],
                    "userName": c["login"],
                }
        return self._comments

    def add_comment(self, comment, really=True):
        util.logger.debug("Adding comment %s to %s", comment, str(self))
        if really:
            return self.post("issues/add_comment", {"issue": self.key, "text": comment})
        else:
            return None

    def set_severity(self, severity):
        util.logger.debug(
            "Changing severity of issue %s from %s to %s",
            self.key,
            self.severity,
            severity,
        )
        return self.post("issues/set_severity", {"issue": self.key, "severity": severity})

    def assign(self, assignee):
        util.logger.debug("Assigning issue %s to %s", self.key, assignee)
        return self.post("issues/assign", {"issue": self.key, "assignee": assignee})

    def set_tags(self, tags):
        util.logger.debug("Setting tags %s to issue %s", tags, self.key)
        return self.post("issues/set_tags", {"issue": self.key, "tags": tags})

    def set_type(self, new_type):
        util.logger.debug("Changing type of issue %s from %s to %s", self.key, self.type, new_type)
        return self.post("issues/set_type", {"issue": self.key, "type": new_type})

    def is_wont_fix(self):
        return self.__has_been_marked_as_statuses(["WONTFIX"])

    def is_false_positive(self):
        return self.__has_been_marked_as_statuses(["FALSE-POSITIVE"])

    def __has_been_marked_as_statuses(self, statuses):
        for log in self.changelog():
            for diff in log["diffs"]:
                if diff["key"] != "resolution":
                    continue
                for status in statuses:
                    if diff["newValue"] == status:
                        return True
        return False

    def strictly_identical_to(self, another_finding, ignore_component=False):
        return super.strictly_identical_to(another_finding, ignore_component) and (self.debt() == another_finding.debt())

    def almost_identical_to(self, another_finding, ignore_component=False, **kwargs):
        return super.almost_identical_to(another_finding, ignore_component, **kwargs) and (
            self.debt() == another_finding.debt() or kwargs.get("ignore_debt", False)
        )

    def __do_transition(self, transition):
        return self.post("issues/do_transition", {"issue": self.key, "transition": transition})

    def reopen(self):
        util.logger.debug("Reopening %s", str(self))
        return self.__do_transition("reopen")

    def mark_as_false_positive(self):
        util.logger.debug("Marking %s as false positive", str(self))
        return self.__do_transition("falsepositive")

    def confirm(self):
        util.logger.debug("Confirming %s", str(self))
        return self.__do_transition("confirm")

    def unconfirm(self):
        util.logger.debug("Unconfirming %s", str(self))
        return self.__do_transition("unconfirm")

    def resolve_as_fixed(self):
        util.logger.debug("Marking %s as fixed", str(self))
        return self.__do_transition("resolve")

    def mark_as_wont_fix(self):
        util.logger.debug("Marking %s as won't fix", str(self))
        return self.__do_transition("wontfix")

    def close(self):
        util.logger.debug("Closing %s", str(self))
        return self.__do_transition("close")

    def mark_as_reviewed(self):
        if self.is_hotspot():
            util.logger.debug("Marking hotspot %s as reviewed", self.key)
            return self.__do_transition("resolveasreviewed")
        elif self.is_vulnerability():
            util.logger.debug(
                "Marking vulnerability %s as won't fix in replacement of 'reviewed'",
                self.key,
            )
            self.add_comment("Vulnerability marked as won't fix to replace hotspot 'reviewed' status")
            return self.__do_transition("wontfix")

        util.logger.debug(
            "Issue %s is neither a hotspot nor a vulnerability, cannot mark as reviewed",
            self.key,
        )
        return False

    def __apply_event(self, event, settings):
        util.logger.debug("Applying event %s", str(event))
        # origin = f"originally by *{event['userName']}* on original branch"
        (event_type, data) = event.changelog_type()
        if event_type == "SEVERITY":
            self.set_severity(data)
            # self.add_comment(f"Change of severity {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "TYPE":
            self.set_type(data)
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "REOPEN":
            if event.previous_state() == "CLOSED":
                util.logger.info("Reopen from closed issue won't be applied, issue was never closed")
            else:
                self.reopen()
            # self.add_comment(f"Issue re-open {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "FALSE-POSITIVE":
            self.mark_as_false_positive()
            # self.add_comment(f"False positive {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "WONT-FIX":
            self.mark_as_wont_fix()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "CONFIRM":
            self.confirm()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "UNCONFIRM":
            self.unconfirm()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "REVIEWED":
            self.mark_as_reviewed()
            # self.add_comment(f"Hotspot review {origin}")
        elif event_type == "ASSIGN":
            if settings[syncer.SYNC_ASSIGN]:
                u = users.get_login_from_name(data, endpoint=self.endpoint)
                if u is None:
                    u = settings[syncer.SYNC_SERVICE_ACCOUNTS][0]
                self.assign(u)
                # self.add_comment(f"Issue assigned {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "TAG":
            self.set_tags(data)
            # self.add_comment(f"Tag change {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "FIXED":
            self.resolve_as_fixed()
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "CLOSED":
            util.logger.info(
                "Changelog event is a CLOSE issue, it cannot be applied... %s",
                str(event),
            )
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "INTERNAL":
            util.logger.info("Changelog %s is internal, it will not be applied...", str(event))
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        else:
            util.logger.error("Event %s can't be applied", str(event))
            return False
        return True

    def apply_changelog(self, source_issue, settings):
        events = source_issue.changelog()
        if events is None or not events:
            util.logger.debug("Sibling %s has no changelog, no action taken", source_issue.key)
            return False

        change_nbr = 0
        start_change = len(self.changelog()) + 1
        util.logger.debug("Issue %s: Changelog = %s", str(self), str(self.changelog()))
        util.logger.info(
            "Applying changelog of issue %s to issue %s, from change %d",
            source_issue.key,
            self.key,
            start_change,
        )
        for key in sorted(events.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                util.logger.debug(
                    "Skipping change already applied in a previous sync: %s",
                    str(events[key]),
                )
                continue
            self.__apply_event(events[key], settings)

        comments = source_issue.comments()
        if len(self.comments()) == 0 and settings[syncer.SYNC_ADD_LINK]:
            util.logger.info("Target %s has 0 comments, adding sync link comment", str(self))
            start_change = 1
            self.add_comment(f"Automatically synchronized from [this original issue]({source_issue.url()})")
        else:
            start_change = len(self.comments())
            util.logger.info("Target %s already has %d comments", str(self), start_change)
        util.logger.info(
            "Applying comments of %s to %s, from comment %d",
            str(source_issue),
            str(self),
            start_change,
        )
        change_nbr = 0
        for key in sorted(comments.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                util.logger.debug(
                    "Skipping comment already applied in a previous sync: %s",
                    str(comments[key]),
                )
                continue
            # origin = f"originally by *{event['userName']}* on original branch"
            self.add_comment(comments[key]["value"])
        return True


# ------------------------------- Static methods --------------------------------------


def __search_all_by_directories(params, endpoint=None):
    new_params = params.copy()
    facets = _get_facets(
        new_params["componentKeys"],
        facets="directories",
        params=new_params,
        endpoint=endpoint,
    )
    issue_list = {}
    for d in facets["directories"]:
        util.logger.info("Search by directory %s", d["val"])
        new_params["directories"] = d["val"]
        issue_list.update(search(endpoint=endpoint, params=new_params, raise_error=False))
    util.logger.info("Search by directory ALL: %d issues found", len(issue_list))
    return issue_list


def __search_all_by_types(params, endpoint=None):
    issue_list = {}
    new_params = params.copy()
    for issue_type in ("BUG", "VULNERABILITY", "CODE_SMELL"):
        try:
            util.logger.info("Search by type %s", issue_type)
            new_params["types"] = issue_type
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            util.logger.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(__search_all_by_directories(params=new_params, endpoint=endpoint))
    util.logger.info("Search by type ALL: %d issues found", len(issue_list))
    return issue_list


def __search_all_by_severities(params, endpoint=None):
    issue_list = {}
    new_params = params.copy()
    for sev in ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"):
        try:
            util.logger.info("Search by severity %s", sev)
            new_params["severities"] = sev
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            util.logger.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(__search_all_by_types(params=new_params, endpoint=endpoint))
    util.logger.info("Search by severity ALL: %d issues found", len(issue_list))
    return issue_list


def __search_all_by_date(params, date_start=None, date_stop=None, endpoint=None):
    new_params = params.copy()
    if date_start is None:
        date_start = get_oldest_issue(endpoint=endpoint, params=new_params).replace(hour=0, minute=0, second=0, microsecond=0)
    if date_stop is None:
        date_stop = get_newest_issue(endpoint=endpoint, params=new_params).replace(hour=0, minute=0, second=0, microsecond=0)
    util.logger.info(
        "Search by date between [%s - %s]",
        util.date_to_string(date_start, False),
        util.date_to_string(date_stop, False),
    )
    issue_list = {}
    new_params.update({"createdAfter": date_start, "createdBefore": date_stop})
    try:
        issue_list = search(endpoint=endpoint, params=new_params)
    except TooManyIssuesError as e:
        util.logger.info("Too many issues (%d), splitting time window", e.nbr_issues)
        diff = (date_stop - date_start).days
        if diff == 0:
            util.logger.info(_TOO_MANY_ISSUES_MSG)
            issue_list = __search_all_by_severities(new_params, endpoint=endpoint)
        elif diff == 1:
            issue_list.update(
                __search_all_by_date(
                    new_params,
                    date_start=date_start,
                    date_stop=date_start,
                    endpoint=endpoint,
                )
            )
            issue_list.update(
                __search_all_by_date(
                    new_params,
                    date_start=date_stop,
                    date_stop=date_stop,
                    endpoint=endpoint,
                )
            )
        else:
            date_middle = date_start + datetime.timedelta(days=diff // 2)
            issue_list.update(
                __search_all_by_date(
                    new_params,
                    date_start=date_start,
                    date_stop=date_middle,
                    endpoint=endpoint,
                )
            )
            date_middle = date_middle + datetime.timedelta(days=1)
            issue_list.update(
                __search_all_by_date(
                    new_params,
                    date_start=date_middle,
                    date_stop=date_stop,
                    endpoint=endpoint,
                )
            )
    if date_start is not None and date_stop is not None:
        util.logger.debug(
            "Project %s has %d issues between %s and %s",
            new_params["componentKeys"],
            len(issue_list),
            util.date_to_string(date_start, False),
            util.date_to_string(date_stop, False),
        )
    return issue_list


def _search_all_by_project(project_key, params, endpoint=None):
    new_params = {} if params is None else params.copy()
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = util.csv_to_list(project_key)
    issue_list = {}
    for k in key_list:
        new_params["componentKeys"] = k
        try:
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            util.logger.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(__search_all_by_date(params=new_params, endpoint=endpoint))
    return issue_list


def search_by_project(project_key, endpoint, params=None, search_findings=False):
    if params is None:
        params = {}
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = util.csv_to_list(project_key)
    issue_list = {}
    for k in key_list:
        util.logger.debug("Issue search by project %s, with params %s", k, str(params))
        if endpoint.version() >= (9, 1, 0) and endpoint.edition() in ("enterprise", "datacenter") and search_findings:
            util.logger.info("Using new export findings to speed up issue export")
            issue_list.update(projects.Project(k, endpoint=endpoint).get_findings(params.get("branch", None), params.get("pullRequest", None)))
        else:
            issue_list.update(_search_all_by_project(k, params=params, endpoint=endpoint))
    util.logger.info(
        "Search by project %s params %s returned %d issues",
        project_key,
        str(params),
        len(issue_list),
    )
    return issue_list


def search_all(endpoint, params=None):
    new_params = {} if params is None else params.copy()
    util.logger.info("Issue search all with %s", str(params))
    issue_list = {}
    try:
        issue_list = search(endpoint=endpoint, params=params)
    except TooManyIssuesError:
        util.logger.info(_TOO_MANY_ISSUES_MSG)
        for k in projects.search(endpoint):
            issue_list.update(_search_all_by_project(k, params=new_params, endpoint=endpoint))
    return issue_list


def search(endpoint=None, params=None, raise_error=True):
    new_params = {} if params is None else params.copy()
    util.logger.debug("Search params = %s", str(new_params))
    if "ps" not in new_params:
        new_params["ps"] = Issue.MAX_PAGE_SIZE
    p = 1
    issue_list = {}
    while True:
        new_params["p"] = p
        resp = env.get(Issue.SEARCH_API, params=new_params, ctxt=endpoint)
        data = json.loads(resp.text)
        nbr_issues = data["paging"]["total"]
        nbr_pages = min(20, (nbr_issues + new_params["ps"] - 1) // new_params["ps"])
        util.logger.debug("Number of issues: %d - Page: %d/%d", nbr_issues, new_params["p"], nbr_pages)
        if nbr_issues > Issue.MAX_SEARCH and raise_error:
            raise TooManyIssuesError(
                nbr_issues,
                f"{nbr_issues} issues returned by api/{Issue.SEARCH_API}, this is more than the max {Issue.MAX_SEARCH} possible",
            )
        # TODO Add critical log when no raise error

        for i in data["issues"]:
            i["branch"] = new_params.get("branch", None)
            i["pullRequest"] = new_params.get("pullRequest", None)
            issue_list[i["key"]] = get_object(i["key"], endpoint=endpoint, data=i)

        if p >= nbr_pages:
            break
        p += 1
    return issue_list


def _get_facets(project_key, facets="directories", endpoint=None, params=None):
    new_params = {} if params is None else params.copy()
    new_params.update({"componentKeys": project_key, "facets": facets, "ps": 500})
    new_params = __get_issues_search_params(new_params)
    resp = env.get(Issue.SEARCH_API, params=new_params, ctxt=endpoint)
    data = json.loads(resp.text)
    util.json_dump_debug(data["facets"], "FACETS = ")
    l = {}
    facets_list = util.csv_to_list(facets)
    for f in data["facets"]:
        if f["property"] in facets_list:
            l[f["property"]] = f["values"]
    return l


def __get_one_issue_date(endpoint=None, asc_sort="false", params=None):
    """Returns the date of one issue found"""
    new_params = {} if params is None else params.copy()
    new_params["s"] = "CREATION_DATE"
    new_params["asc"] = asc_sort
    new_params["ps"] = 1
    issue_list = search(endpoint=endpoint, params=new_params, raise_error=False)
    if not issue_list:
        return None
    for _, i in issue_list.items():
        date = i.creation_date
        util.logger.debug("Date: %s Issue %s", str(date), str(i))
        break
    return date


def get_oldest_issue(endpoint=None, params=None):
    """Returns the oldest date of all issues found"""
    return __get_one_issue_date(endpoint=endpoint, asc_sort="true", params=params)


def get_newest_issue(endpoint=None, params=None):
    """Returns the newest date of all issues found"""
    return __get_one_issue_date(endpoint=endpoint, asc_sort="false", params=params)


def count(endpoint=None, **kwargs):
    """Returns number of issues of a search"""
    returned_data = search(endpoint=endpoint, params=kwargs.copy().update({"ps": 1}))
    util.logger.debug("Issue search %s would return %d issues", str(kwargs), returned_data["total"])
    return returned_data["total"]


def identical_attributes(o1, o2, key_list):
    for key in key_list:
        if o1[key] != o2[key]:
            return False
    return True


def __get_issues_search_params(params):
    outparams = {"additionalFields": "comments"}
    for key in params:
        if params[key] is not None and key in Issue.OPTIONS_SEARCH:
            outparams[key] = params[key]
    return outparams


def get_object(key, data=None, endpoint=None, from_export=False):
    if key not in _ISSUES:
        _ = Issue(key=key, data=data, endpoint=endpoint, from_export=from_export)
    return _ISSUES[key]


def get_search_criteria(params):
    """Returns the filtered list of params that are allowed for api/issue/search"""
    criterias = params.copy()
    if criterias.get("types", None) is not None:
        criterias["types"] = util.allowed_values_string(criterias["types"], TYPES)
    if criterias.get("severities", None) is not None:
        criterias["severities"] = util.allowed_values_string(criterias["severities"], SEVERITIES)
    if criterias.get("statuses", None) is not None:
        criterias["statuses"] = util.allowed_values_string(criterias["statuses"], STATUSES)
    if criterias.get("resolutions", None) is not None:
        criterias["resolutions"] = util.allowed_values_string(criterias["resolutions"], RESOLUTIONS)
    criterias = util.dict_subset(util.remove_nones(criterias), SEARCH_CRITERIAS)
    return criterias
