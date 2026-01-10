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
"""Abstraction of the SonarQube "hotspot" concept"""

from __future__ import annotations
from typing import Optional, Any, Union, TYPE_CHECKING

import json
from datetime import datetime
from copy import deepcopy

import requests.utils

import sonar.logging as log
import sonar.util.misc as util
from sonar.util import cache, constants as c

from sonar import users
from sonar import findings, rules, changelog
from sonar import exceptions
import sonar.util.issue_defs as idefs
import sonar.utilities as sutil
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from sonar.issues import Issue
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr, ConfigSettings
    from sonar.projects import Project

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

TYPES = (idefs.TYPE_HOTSPOT,)
RESOLUTIONS = ("SAFE", "ACKNOWLEDGED", "FIXED")
STATUSES = ("TO_REVIEW", "REVIEWED")
SEVERITIES = ()

# Filters for search of hotspots are different than for issues :-(
_FILTERS_HOTSPOTS_REMAPPING = {"resolutions": "resolution", "statuses": "status", "componentsKey": PROJECT_FILTER, "components": PROJECT_FILTER}


class TooManyHotspotsError(Exception):
    """Too many hotspots found during a search"""

    def __init__(self, nbr_issues: int, message: str) -> None:
        """Exception constructor"""
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message


class Hotspot(findings.Finding):
    """Abstraction of the Sonar hotspot concept"""

    CACHE = cache.Cache()
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000

    def __init__(self, endpoint: Platform, key: str, data: ApiPayload, from_export: bool = False) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key, data=data, from_export=from_export)
        self.type = idefs.TYPE_HOTSPOT
        self.__details: ApiPayload = data
        Hotspot.CACHE.put(self)
        self.refresh()

    def __str__(self) -> str:
        """Returns the string representation of the object"""
        return f"Hotspot key '{self.key}'"

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> Hotspot:
        """Loads a hotspot from the API payload"""
        o: Optional[Hotspot] = Hotspot.CACHE.get(data["key"], endpoint.local_url)
        if not o:
            o = Hotspot(endpoint=endpoint, key=data["key"], data=data)
        o.reload(data)
        return o

    @classmethod
    def search(cls, endpoint: Platform, **search_params: Any) -> dict[str, Hotspot]:
        """Searches hotspots

        :param endpoint: Reference to the SonarQube platform
        :param search_params: Search filters to narrow down the search
        :return: Dict of found hotspots indexed by hotspot key
        """
        log.debug("Searching hotspots with params %s", search_params)
        split_filters = split_search_filters(cls.sanitize_search_params(endpoint=endpoint, **search_params))
        log.debug("Split search filters = %s", split_filters)
        hotspots_list: dict[str, Hotspot] = {}
        for inline_filters in split_filters:
            hotspots_list |= cls.get_paginated(endpoint=endpoint, params=inline_filters)
        # Add Branch and Pull Request info to hotspots (which is not returned in the API payload)
        hotspots_list = cls.add_branch_and_pr(hotspots_list, **search_params)
        # Filter results based on creation date, severities, languages
        hotspots_list = cls.post_search_filters(hotspots_list, **search_params)
        log.debug("Searching hotspots with params = %s returned %d hotspots", search_params, len(hotspots_list))
        return hotspots_list

    @classmethod
    def search_by_project(cls, endpoint: Platform, project: Union[str, Project], **search_params: Any) -> dict[str, Hotspot]:
        """Searches hotspots of a project

        :param endpoint: Reference to the SonarQube platform
        :param project: Project key or Project object
        :param search_params: Search filters to narrow down the search
        :return: Dict of found hotspots
        """
        if not isinstance(project, str):
            project = project.key
        hotspots = cls.search(endpoint=endpoint, **(search_params | {"project": project}))
        log.info("Project '%s' has %d hotspots corresponding to filters", project, len(hotspots))
        return hotspots

    def reload(self, data: ApiPayload, from_export: bool = False) -> None:
        """Loads the hotspot details from the provided data (coming from api/hotspots/search)"""
        super().reload(data, from_export)
        if not self.rule:
            self.rule = data.get("ruleKey", None)
        self.severity = data.get("vulnerabilityProbability", "UNDEFINED")
        self.impacts = {idefs.QUALITY_SECURITY: self.severity}

    def refresh(self) -> Hotspot:
        """Refreshes and reads hotspots details in SonarQube, returns self"""
        api, _, params, _ = self.endpoint.api.get_details(self, Oper.GET, hotspot=self.key)
        self.__details = d = json.loads(self.get(api, params=params).text)
        if self.file is None and "path" in d["component"]:
            self.file = d["component"]["path"]
        self.branch, self.pull_request = self.get_branch_and_pr(d["project"])
        self.severity = d["rule"].get("vulnerabilityProbability", "UNDEFINED")
        self.impacts = {idefs.QUALITY_SECURITY: self.severity}
        if not self.rule:
            self.rule = d["rule"]["key"]
        self.assignee = d.get("assignee", None)
        return self

    def url(self) -> str:
        """Returns the permalink URL to the hotspot in the SonarQube platform"""
        branch = ""
        if self.branch is not None:
            branch = f"branch={requests.utils.quote(self.branch)}&"
        elif self.pull_request is not None:
            branch = f"pullRequest={requests.utils.quote(self.pull_request)}&"
        return f"{self.base_url(local=False)}/security_hotspots?{branch}id={self.projectKey}&hotspots={self.key}"

    def to_json(self, without_time: bool = False) -> ObjectJsonRepr:
        """Returns the JSON representation of the hotspot"""
        data = super().to_json(without_time)
        if self.endpoint.is_mqr_mode():
            data["impacts"][idefs.QUALITY_SECURITY] += f"({idefs.TYPE_HOTSPOT})"
        return data

    def __mark_as(self, resolution: Optional[str], comment: Optional[str] = None, status: str = "REVIEWED") -> bool:
        """Marks a hotspot with a particular resolution and status

        :return: Whether the operation succeeded
        """
        try:
            params = {"hotspot": self.key, "status": status, "resolution": resolution, "comment": comment}
            api, _, api_params, _ = self.endpoint.api.get_details(self, Oper.CHANGE_STATUS, **params)
            ok = self.post(api, params=api_params).ok
            self.refresh()
        except exceptions.SonarException:
            return False
        else:
            return ok

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
        if self.endpoint.is_sonarcloud():
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

        :param comment: Comment to add, in markdown format
        :return: Whether the operation succeeded
        """
        try:
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.ADD_COMMENT, hotspot=self.key, comment=comment)
            return self.post(api, params=params).ok
        except exceptions.SonarException:
            return False

    def __apply_event(self, event: object, settings: ConfigSettings) -> bool:
        """Applies a changelog event (transition, comment, assign) to the hotspot"""
        from sonar import syncer

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
                u = users.get_login_from_name(endpoint=self.endpoint, name=data) or settings[syncer.SYNC_SERVICE_ACCOUNT]
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

    def apply_changelog(self, source_hotspot: Hotspot, settings: ConfigSettings) -> int:
        """Applies a changelog and comments from a source to a target hotspot

        :param source_hotspot: The source hotspot to take changes from
        :return: Number of changes applied
        """
        counter = 0
        last_target_change = self.last_changelog_date()
        events = source_hotspot.changelog(after=last_target_change)
        msg = "Source %s has no changelog added after target %s last change (%s), no %s applied"
        if len(events) == 0:
            log.info(msg, source_hotspot, self, last_target_change, "changelog")
        else:
            log.info("Applying %d changelogs of %s to %s, from %s", len(events), source_hotspot, self, last_target_change)
            for key in sorted(events.keys()):
                self.__apply_event(events[key], settings)
                counter += 1

        last_target_change = self.last_comment_date()
        events = source_hotspot.comments(after=last_target_change)
        if len(events) == 0:
            log.info(msg, source_hotspot, self, last_target_change, "comment")
        else:
            log.info("Applying %d comments of %s to %s, from %s", len(events), source_hotspot, self, last_target_change)
            for key in sorted(events.keys()):
                self.add_comment(events[key]["value"])
                counter += 1
        return counter

    def changelog(self, after: Optional[datetime] = None, manual_only: bool = True) -> dict[str, changelog.Changelog]:
        """Returns the changelog of a hotspot

        :param after: If set, only changes after that date are returned
        :param manual_only: Whether the only manual changes should be returned or all changes
        :return: The hotspot changelog
        :rtype: dict{"<date>_<sequence_nbr>": Changelog}
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
            self._changelog[f"{d.date_str()}_{seq:03d}"] = d
        if after is not None:
            return {k: v for k, v in self._changelog.items() if v.date_time() > after}
        return self._changelog

    def comments(self, after: Optional[datetime] = None) -> dict[str, str]:
        """
        :param after: If set will only return comments after this date, else all
        :return: The hotspot comments
        :rtype: dict{"<date>_<sequence_nbr>": <comment>}
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
                "date": util.to_datetime(cmt["createdAt"]),
                "event": "comment",
                "value": cmt["markdown"],
                "user": cmt["login"],
                "userName": cmt["login"],
                "commentKey": cmt["key"],
            }
        if after is not None:
            return {k: v for k, v in self._comments.items() if v["date"] and v["date"] > util.add_tz(after)}
        return self._comments

    @classmethod
    def sanitize_search_params(cls, endpoint: Platform, **search_params: Any) -> ApiParams:
        """Returns the sanitized list of params that are allowed for api/hotspots/search"""
        log.debug("Sanitizing hotspot search criteria %s", search_params)
        params = deepcopy(search_params)
        if params == {}:
            return params
        comp_filter = PROJECT_FILTER if endpoint.version() >= c.NEW_ISSUE_SEARCH_INTRO_VERSION else PROJECT_FILTER_OLD
        if params.get(PROJECT_FILTER_OLD) and not params.get(comp_filter):
            params[comp_filter] = params.pop(PROJECT_FILTER_OLD)
        elif params.get(PROJECT_FILTER) and not params.get(comp_filter):
            params[comp_filter] = params.pop(PROJECT_FILTER)
        criterias = util.remove_nones(params)
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
        criterias = util.dict_subset(criterias, *SEARCH_CRITERIAS)
        log.debug("Sanitized hotspot search criteria %s", str(criterias))
        return criterias

    @staticmethod
    def post_search_filters(findings: dict[str, Union[Issue, Hotspot]], **filters: Any) -> dict[str, Union[Issue, Hotspot]]:
        """Filters a dict of hotspots with provided filters"""
        log.debug("Post filtering findings with %s - Starting with %d hotspots", str(filters), len(findings))
        filtered_findings = findings.copy()
        if "severities" in filters:
            filtered_findings = {k: v for k, v in filtered_findings.items() if v.severity in filters["severities"]}
            log.debug("%d hotspots remaining after filtering by severities %s", len(filtered_findings), filters["severities"])
        if "createdAfter" in filters:
            min_date = sutil.string_to_date(filters["createdAfter"])
            filtered_findings = {k: v for k, v in filtered_findings.items() if v.creation_date >= min_date}
            log.debug("%d hotspots remaining after filtering by createdAfter %s", len(filtered_findings), filters["createdAfter"])
        if "createdBefore" in filters:
            max_date = sutil.string_to_date(filters["createdBefore"])
            filtered_findings = {k: v for k, v in filtered_findings.items() if v.creation_date <= max_date}
            log.debug("%d hotspots remaining after filtering by createdBefore %s", len(filtered_findings), filters["createdBefore"])
        if "languages" in filters:
            filtered_findings = {
                k: v for k, v in filtered_findings.items() if rules.Rule.get_object(endpoint=v.endpoint, key=v.rule).language in filters["languages"]
            }
            log.debug("%d hotspots remaining after filtering by languages %s", len(filtered_findings), filters["languages"])
        log.debug("%d hotspots remaining after post search filtering", len(filtered_findings))
        return filtered_findings


def __split_filter(params: ApiParams, criteria: str) -> list[ApiParams]:
    """Creates a list of filters from a single one that has values that requires multiple hotspot searches"""
    if (crits := params.pop(criteria, None)) is None:
        return [params]
    return [{**params, criteria: crit} for crit in util.csv_to_list(crits)]


def split_search_filters(params: ApiParams) -> list[ApiParams]:
    """Split search filters for which you can only pass 1 value at a time in api/hotspots/search"""
    list_2d = [__split_filter(f, "status") for f in __split_filter(params, "resolution")]
    return [crit2 for crit1 in list_2d for crit2 in crit1]
