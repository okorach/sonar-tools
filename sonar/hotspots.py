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
"""Abstraction of the SonarQube "hotspot" concept"""

from __future__ import annotations

import json
import re
from typing import Optional
from http import HTTPStatus
from requests import RequestException
import requests.utils

import sonar.logging as log
import sonar.platform as pf

import sonar.utilities as util
from sonar.util import types, cache, constants as c

from sonar import syncer, users
from sonar import findings, rules, changelog, projects

PROJECT_FILTER = "project"
PROJECT_FILTER_OLD = "projectKey"

SEARCH_CRITERIAS = (
    "branch",
    "cwe",
    "files",
    "hotspots",
    "inNewCodePeriod",
    "onlyMine",
    "owaspAsvs-4.0",
    "owaspAsvsLevel",
    "owaspTop10",
    "owaspTop10-2021",
    "p",
    "pciDss-3.2",
    "pciDss-4.0",
    PROJECT_FILTER,
    PROJECT_FILTER_OLD,
    "ps",
    "pullRequest",
    "resolution",
    "sinceLeakPeriod",
    "resolution",
    "sonarsourceSecurity",
    "status",
)

TYPES = ("SECURITY_HOTSPOT",)
RESOLUTIONS = ("SAFE", "ACKNOWLEDGED", "FIXED")
STATUSES = ("TO_REVIEW", "REVIEWED")
SEVERITIES = ()

# Filters for search of hotspots are different than for issues :-(
_FILTERS_HOTSPOTS_REMAPPING = {"resolutions": "resolution", "statuses": "status", "componentsKey": PROJECT_FILTER, "components": PROJECT_FILTER}


class TooManyHotspotsError(Exception):
    """Too many hotspots found during a search"""

    def __init__(self, nbr_issues: int, message: str) -> None:
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message


class Hotspot(findings.Finding):
    """Abstraction of the Sonar hotspot concept"""

    CACHE = cache.Cache()
    API = {c.GET: "hotspots/show", c.SEARCH: "hotspots/search"}
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000

    def __init__(self, endpoint: pf.Platform, key: str, data: types.ApiPayload = None, from_export: bool = False) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key, data=data, from_export=from_export)
        self.type = "SECURITY_HOTSPOT"
        self.__details = None
        Hotspot.CACHE.put(self)
        self.refresh()

    def __str__(self) -> str:
        """
        :return: String representation of the object
        """
        return f"Hotspot key '{self.key}'"

    def url(self) -> str:
        """
        :return: Permalink URL to the hotspot in the SonarQube platform
        """
        branch = ""
        if self.branch is not None:
            branch = f"branch={requests.utils.quote(self.branch)}&"
        elif self.pull_request is not None:
            branch = f"pullRequest={requests.utils.quote(self.pull_request)}&"
        return f"{self.base_url(local=False)}/security_hotspots?{branch}id={self.projectKey}&hotspots={self.key}"

    def to_json(self, without_time: bool = False) -> types.ObjectJsonRepr:
        """
        :return: JSON representation of the hotspot
        :rtype: dict
        """
        data = super().to_json(without_time)
        if self.endpoint.is_mqr_mode():
            data["impacts"]["SECURITY"] += "(HOTSPOT)"
        return data

    def _load(self, data: types.ApiPayload, from_export: bool = False) -> None:
        """Loads the hotspot details from the provided data (coming from api/hotspots/search)"""
        super()._load(data, from_export)
        if not self.rule:
            self.rule = data.get("ruleKey", None)
        self.severity = data.get("vulnerabilityProbability", "UNDEFINED")
        self.impacts = {"SECURITY": self.severity}

    def refresh(self) -> bool:
        """Refreshes and reads hotspots details in SonarQube
        :return: Whether there operation succeeded
        """
        try:
            resp = self.get(Hotspot.API[c.GET], {"hotspot": self.key})
            if resp.ok:
                d = json.loads(resp.text)
                self.__details = d
                if self.file is None and "path" in d["component"]:
                    self.file = d["component"]["path"]
                self.branch, self.pull_request = self.get_branch_and_pr(d["project"])
                self.severity = d["rule"].get("vulnerabilityProbability", "UNDEFINED")
                self.impacts = {"SECURITY": self.severity}
                if not self.rule:
                    self.rule = d["rule"]["key"]
                self.assignee = d.get("assignee", None)
            return resp.ok
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, "refreshing hotspot", catch_all=True)
            return False

    def __mark_as(self, resolution: Optional[str], comment: Optional[str] = None, status: str = "REVIEWED") -> bool:
        try:
            params = util.remove_nones({"hotspot": self.key, "status": status, "resolution": resolution, "commemt": comment})
            r = self.post("hotspots/change_status", params=params)
        except (ConnectionError, requests.RequestException) as e:
            util.handle_error(e, f"marking hotspot as {status}/{resolution}", catch_all=True)
            return False
        self.refresh()
        return r.ok

    def mark_as_safe(self) -> bool:
        """Marks a hotspot as safe

        :return: Whether the operation succeeded
        """
        return self.__mark_as(resolution="SAFE")

    def mark_as_fixed(self) -> bool:
        """Marks a hotspot as fixed

        :return: Whether the operation succeeded
        """
        return self.__mark_as(resolution="FIXED")

    def mark_as_acknowledged(self) -> bool:
        """Marks a hotspot as acknowledged

        :return: Whether the operation succeeded
        """
        if self.endpoint.version() < (9, 4, 0) and not self.endpoint.is_sonarcloud():
            log.warning("Can't acknowledge %s, this is not supported by SonarQube Server < 9.4", str(self))
            return False
        elif self.endpoint.is_sonarcloud():
            log.warning("Can't acknowledge %s, this is not supported by SonarQube Cloud", str(self))
            return False
        return self.__mark_as(resolution="ACKNOWLEDGED")

    def mark_as_to_review(self) -> bool:
        """Marks a hotspot as to review

        :return: Whether the operation succeeded
        """
        return self.__mark_as(status="TO_REVIEW", resolution=None)

    def reopen(self) -> bool:
        """Reopens a hotspot as to review

        :return: Whether the operation succeeded
        """
        return self.mark_as_to_review()

    def add_comment(self, comment: str) -> bool:
        """Adds a comment to a hotspot

        :param str comment: Comment to add, in markdown format
        :return: Whether the operation succeeded
        """
        try:
            return self.post("hotspots/add_comment", params={"hotspot": self.key, "comment": comment}).ok
        except (ConnectionError, requests.RequestException) as e:
            util.handle_error(e, "adding comment to hotspot", catch_all=True)
            return False

    def assign(self, assignee: Optional[str], comment: Optional[str] = None) -> bool:
        """Assigns a hotspot (and optionally comment)

        :param str assignee: User login to assign the hotspot, None to unassign
        :param str comment: Optional comment to add
        :return: Whether the operation succeeded
        """
        try:
            if assignee is None:
                log.debug("Unassigning %s", str(self))
            else:
                log.debug("Assigning %s to '%s'", str(self), str(assignee))
            r = self.post("hotspots/assign", util.remove_nones({"hotspot": self.key, "assignee": assignee, "comment": comment}))
            if r.ok:
                self.assignee = assignee
        except (ConnectionError, requests.RequestException) as e:
            util.handle_error(e, "assigning/unassigning hotspot", catch_all=True)
            return False
        return r.ok

    def unassign(self, comment: Optional[str] = None) -> bool:
        """Unassigns a hotspot (and optionally comment)

        :return: Whether the operation succeeded
        """
        return self.assign(assignee=None, comment=comment)

    def __apply_event(self, event: object, settings: types.ConfigSettings) -> bool:
        """Applies a changelog event (transition, comment, assign) to the hotspot"""
        log.debug("Applying event %s", str(event))
        # origin = f"originally by *{event['userName']}* on original branch"
        (event_type, data) = event.changelog_type()
        if event_type == "HOTSPOT_SAFE":
            self.mark_as_safe()
            # self.add_comment(f"Hotspot review safe {origin}")
        elif event_type == "HOTSPOT_FIXED":
            self.mark_as_fixed()
            # self.add_comment(f"Hotspot marked as fixed {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "HOTSPOT_TO_REVIEW":
            self.mark_as_to_review()
            # self.add_comment(f"Hotspot marked as fixed {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "HOTSPOT_ACKNOWLEDGED":
            self.mark_as_acknowledged()
            if self.endpoint.is_sonarcloud():
                self.add_comment("Original hotspot status was changed to ACKNOWLEDGED, but this status is not supported in SonarQube Cloud")
            # self.add_comment(f"Hotspot marked as acknowledged {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "ASSIGN":
            if settings[syncer.SYNC_ASSIGN]:
                u = users.get_login_from_name(endpoint=self.endpoint, name=data)
                if u is None:
                    u = settings[syncer.SYNC_SERVICE_ACCOUNT]
                self.assign(u)
                # self.add_comment(f"Hotspot assigned assigned {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "UNASSIGN":
            self.unassign()
        elif event_type == "INTERNAL":
            log.info("Changelog %s is internal, it will not be applied...", str(event))
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        else:
            log.error("Event %s can't be applied", str(event))
            return False
        return True

    def apply_changelog(self, source_hotspot: Hotspot, settings: types.ConfigSettings) -> bool:
        """
        :meta private:
        """
        events = source_hotspot.changelog()
        if events is None or not events:
            log.debug("Sibling %s has no changelog, no action taken", str(source_hotspot))
            return False

        change_nbr = 0
        # FIXME: There can be a glitch if there are non manual changes in the changelog
        start_change = len(self.changelog()) + 1
        log.debug("Applying changelog of %s to %s, from change %d", str(source_hotspot), str(self), start_change)
        for key in sorted(events.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                log.debug("Skipping change already applied in a previous sync: %s", str(events[key]))
                continue
            self.__apply_event(events[key], settings)

        comments = source_hotspot.comments()
        if len(self.comments()) == 0 and settings[syncer.SYNC_ADD_LINK]:
            log.info("Target %s has 0 comments, adding sync link comment", str(self))
            start_change = 1
            self.add_comment(f"Automatically synchronized from [this original hotspot]({source_hotspot.url()})")
        else:
            start_change = len(self.comments())
            log.info("Target %s already has %d comments", str(self), start_change)
        log.info("Applying comments of %s to %s, from comment %d", str(source_hotspot), str(self), start_change)
        change_nbr = 0
        for key in sorted(comments.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                log.debug("Skipping comment already applied in a previous sync: %s", str(comments[key]))
                continue
            # origin = f"originally by *{event['userName']}* on original branch"
            self.add_comment(comments[key]["value"])
        return True

    def changelog(self, manual_only: bool = True) -> dict[str, changelog.Changelog]:
        """
        :return: The hotspot changelog
        """
        if self._changelog is not None:
            return self._changelog
        if not self.__details:
            self.refresh()
        self._changelog = {}
        seq = 1
        for l in self.__details["changelog"]:
            d = changelog.Changelog(l, self)
            if d.is_technical_change():
                # Skip automatic changelog events generated by SonarSource itself
                log.debug("%s: Changelog is a technical change: %s", str(self), str(l))
                continue
            if manual_only and not d.is_manual_change():
                # Skip automatic changelog events generated by SonarSource itself
                log.debug("%s: Changelog is an automatic change: %s", str(self), str(l))
                continue
            log.debug("%s: Changelog added %s", str(self), str(l))
            seq += 1
            self._changelog[f"{d.date()}_{seq:03d}"] = d
        return self._changelog

    def comments(self) -> dict[str, str]:
        """
        :return: The hotspot comments
        """
        if self._comments is not None:
            return self._comments
        if not self.__details:
            self.refresh()
        self._comments = {}
        seq = 0
        for cmt in self.__details["comment"]:
            seq += 1
            self._comments[f"{cmt['createdAt']}_{seq:03d}"] = {
                "date": cmt["createdAt"],
                "event": "comment",
                "value": cmt["markdown"],
                "user": cmt["login"],
                "userName": cmt["login"],
                "commentKey": cmt["key"],
            }
        return self._comments


def search_by_project(endpoint: pf.Platform, project_key: str, filters: types.ApiParams = None) -> dict[str, Hotspot]:
    """Searches hotspots of a project

    :param Platform endpoint: Reference to the SonarQube platform
    :param str project_key: Project key
    :param dict params: Search filters to narrow down the search, defaults to None
    :return: List of found hotspots
    :rtype: dict{<key>: <Hotspot>}
    """
    key_list = util.csv_to_list(project_key)
    hotspots = {}
    for k in key_list:
        filters[component_filter(endpoint)] = k
        project_hotspots = search(endpoint=endpoint, filters=filters)
        log.info("Project '%s' has %d hotspots corresponding to filters", k, len(project_hotspots))
        hotspots.update(project_hotspots)
    return post_search_filter(hotspots, filters=filters)


def component_filter(endpoint: pf.Platform) -> str:
    """Returns the string to filter by porject in api/hotspots/search"""
    if endpoint.version() >= c.NEW_ISSUE_SEARCH_INTRO_VERSION:
        return PROJECT_FILTER
    else:
        return PROJECT_FILTER_OLD


def search(endpoint: pf.Platform, filters: types.ApiParams = None) -> dict[str, Hotspot]:
    """Searches hotspots

    :param Platform endpoint: Reference to the SonarQube platform
    :param ApiParams filters: Search filters to narrow down the search, defaults to None
    :return: List of found hotspots
    :rtype: dict{<key>: <Hotspot>}
    """
    hotspots_list = {}
    new_params = sanitize_search_filters(endpoint=endpoint, params=filters)
    log.debug("Search hotspots with params %s", str(new_params))
    ps = Hotspot.MAX_PAGE_SIZE if "ps" not in new_params else new_params["ps"]
    split_filters = split_search_filters(new_params)
    log.debug("Split search filters = %s", split_filters)
    for inline_filters in split_filters:
        p, nbr_pages = 1, 1
        inline_filters["ps"] = ps
        log.debug("Searching hotspots with sanitized filters %s", str(inline_filters))
        while p <= nbr_pages:
            inline_filters["p"] = p
            try:
                data = json.loads(endpoint.get(Hotspot.API[c.SEARCH], params=inline_filters, mute=(HTTPStatus.NOT_FOUND,)).text)
                nbr_hotspots = util.nbr_total_elements(data)
            except (ConnectionError, RequestException) as e:
                util.handle_error(e, "searching hotspots", catch_all=True)
                nbr_hotspots = 0
                return {}
            nbr_pages = util.nbr_pages(data)
            log.debug("Number of hotspots: %d - Page: %d/%d", nbr_hotspots, p, nbr_pages)
            if nbr_hotspots > Hotspot.MAX_SEARCH:
                raise TooManyHotspotsError(
                    nbr_hotspots,
                    f"{nbr_hotspots} hotpots returned by api/{Hotspot.API[c.SEARCH]}, this is more than the max {Hotspot.MAX_SEARCH} possible",
                )

            for enrichment in "branch", "pullRequest":
                if enrichment in inline_filters:
                    data["hotspots"] = [{**ele, enrichment: inline_filters[enrichment]} for _, ele in enumerate(data["hotspots"])]
            hotspots_list |= {i["key"]: get_object(endpoint=endpoint, key=i["key"], data=i) for i in data["hotspots"]}
            p += 1
    return post_search_filter(hotspots_list, filters)


def get_object(endpoint: pf.Platform, key: str, data: dict[str] = None, from_export: bool = False) -> Hotspot:
    """Returns a hotspot from its key"""
    o = Hotspot.CACHE.get(key, endpoint.local_url)
    if not o:
        o = Hotspot(key=key, data=data, endpoint=endpoint, from_export=from_export)
    return o


def sanitize_search_filters(endpoint: pf.Platform, params: types.ApiParams) -> types.ApiParams:
    """Returns the filtered list of params that are allowed for api/hotspots/search"""
    log.debug("Sanitizing hotspot search criteria %s", str(params))
    if params is None:
        return {}
    criterias = util.remove_nones(params.copy())
    criterias = util.dict_remap(criterias, _FILTERS_HOTSPOTS_REMAPPING)
    if "status" in criterias:
        criterias["status"] = util.allowed_values_string(criterias["status"], STATUSES)
    if "resolution" in criterias:
        criterias["resolution"] = util.allowed_values_string(criterias["resolution"], RESOLUTIONS)
        criterias["status"] = "REVIEWED"
    if endpoint.version() <= c.NEW_ISSUE_SEARCH_INTRO_VERSION:
        criterias = util.dict_remap(original_dict=criterias, remapping={PROJECT_FILTER: PROJECT_FILTER_OLD})
    else:
        criterias = util.dict_remap(original_dict=criterias, remapping={PROJECT_FILTER_OLD: PROJECT_FILTER})
    criterias = util.dict_subset(criterias, SEARCH_CRITERIAS)
    log.debug("Sanitized hotspot search criteria %s", str(criterias))
    return criterias


def __split_filter(params: types.ApiParams, criteria: str) -> list[types.ApiParams]:
    """Creates a list of filters from a single one that has values that requires multiple hotspot searches"""
    if (crits := params.pop(criteria, None)) is None:
        return [params]
    return [{**params, criteria: crit} for crit in util.csv_to_list(crits)]


def split_search_filters(params: types.ApiParams) -> list[types.ApiParams]:
    """Split search filters for which you can only pass 1 value at a time in api/hotspots/search"""
    list_2d = [__split_filter(f, "status") for f in __split_filter(params, "resolution")]
    return [crit2 for crit1 in list_2d for crit2 in crit1]


def post_search_filter(hotspots_dict: dict[str, Hotspot], filters: types.ApiParams) -> dict[str, Hotspot]:
    """Filters a dict of hotspots with provided filters"""
    log.debug("Post filtering findings with %s - Starting with %d hotspots", str(filters), len(hotspots_dict))
    filtered_findings = hotspots_dict.copy()
    if "severities" in filters:
        filtered_findings = {k: v for k, v in filtered_findings.items() if v.severity in filters["severities"]}
        log.debug("%d hotspots remaining after filtering by severities %s", len(filtered_findings), str(filters["severities"]))
    if "createdAfter" in filters:
        min_date = util.string_to_date(filters["createdAfter"])
        filtered_findings = {k: v for k, v in filtered_findings.items() if v.creation_date >= min_date}
        log.debug("%d hotspots remaining after filtering by createdAfter %s", len(filtered_findings), str(filters["createdAfter"]))
    if "createdBefore" in filters:
        max_date = util.string_to_date(filters["createdBefore"])
        filtered_findings = {k: v for k, v in filtered_findings.items() if v.creation_date <= max_date}
        log.debug("%d hotspots remaining after filtering by createdBefore %s", len(filtered_findings), str(filters["createdBefore"]))
    if "languages" in filters:
        filtered_findings = {
            k: v for k, v in filtered_findings.items() if rules.get_object(endpoint=v.endpoint, key=v.rule).language in filters["languages"]
        }
        log.debug("%d hotspots remaining after filtering by languages %s", len(filtered_findings), str(filters["languages"]))
    log.debug("%d hotspots remaining after post search filtering", len(filtered_findings))
    return filtered_findings


def count(endpoint: pf.Platform, **kwargs) -> int:
    """Returns number of hotspots of a search"""
    params = {} if not kwargs else kwargs.copy()
    params["ps"] = 1
    params = sanitize_search_filters(endpoint, params)
    nbr_hotspots = util.nbr_total_elements(json.loads(endpoint.get(Hotspot.API[c.SEARCH], params=params, mute=(HTTPStatus.NOT_FOUND,)).text))
    log.debug("Hotspot counts with filters %s returned %d hotspots", str(kwargs), nbr_hotspots)
    return nbr_hotspots
