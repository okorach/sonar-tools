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
"""Abstraction of the SonarQube "hotspot" concept"""

import json
import re
import requests.utils
import sonar.utilities as util
from sonar import syncer, users
from sonar.projects import projects
from sonar.findings import findings, changelog

SEARCH_CRITERIAS = (
    "branch",
    "cwe",
    "files",
    "hotspots",
    "onlyMine",
    "owaspTop10",
    "owaspTop10-2021",
    "p",
    "ps",
    "projectKey",
    "pullRequest",
    "resolution",
    "sansTop25",
    "sinceLeakPeriod",
    "sonarsourceSecurity",
    "status",
)

TYPES = ("SECURITY_HOTSPOT",)
RESOLUTIONS = ("SAFE", "ACKNOWLEDGED", "FIXED")
STATUSES = ("TO_REVIEW", "REVIEWED")
SEVERITIES = ()

_OBJECTS = {}


class TooManyHotspotsError(Exception):
    def __init__(self, nbr_issues, message):
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message


class Hotspot(findings.Finding):
    def __init__(self, key, endpoint, data=None, from_export=False):
        super().__init__(key, endpoint, data, from_export)
        self.vulnerabilityProbability = None  #:
        self.category = data["securityCategory"]  #:
        self.vulnerabilityProbability = data["vulnerabilityProbability"]  #:
        self.securityCategory = None  #:
        self.type = "SECURITY_HOTSPOT"
        self.__details = None

        # FIXME: Ugly hack to fix how hotspot branches are managed
        m = re.match(r"^(.*):BRANCH:(.*)$", self.projectKey)
        if m:
            self.projectKey = m.group(1)
            self.branch = m.group(2)
        m = re.match(r"^(.*):PULL_REQUEST:(.*)$", self.projectKey)
        if m:
            self.projectKey = m.group(1)
            self.branch = m.group(2)
        _OBJECTS[self.uuid()] = self
        if self.rule is None and self.refresh():
            self.rule = self.__details["rule"]["key"]

    def __str__(self):
        """
        :return: String representation of the hotspot
        :rtype: str
        """
        return f"Hotspot key '{self.key}'"

    def url(self):
        """
        :return: Permalink URL to the hotspot in the SonarQube platform
        :rtype: str
        """
        branch = ""
        if self.branch is not None:
            branch = f"branch={requests.utils.quote(self.branch)}&"
        elif self.pull_request is not None:
            branch = f"pullRequest={requests.utils.quote(self.pull_request)}&"
        return f"{self.endpoint.url}/security_hotspots?{branch}id={self.projectKey}&hotspots={self.key}"

    def to_json(self):
        """
        :return: JSON representation of the hotspot
        :rtype: dict
        """
        data = super().to_json()
        data["url"] = self.url()
        return data

    def refresh(self):
        """Refreshes and reads hotspots details in SonarQube
        :return: The hotspot details
        :rtype: Whether ther operation succeeded
        """
        resp = self.get("hotspots/show", {"hotspot": self.key})
        if resp.ok:
            self.__details = json.loads(resp.text)
        return resp.ok

    def __mark_as(self, resolution, comment=None):
        params = {"hotspot": self.key, "status": "REVIEWED", "resolution": resolution}
        if comment is not None:
            params["comment"] = comment
        return self.post("hotspots/change_status", params=params).ok

    def mark_as_safe(self):
        """Marks a hotspot as safe

        :return: Whether the operation succeeded
        :rtype: bool
        """
        return self.__mark_as("SAFE")

    def mark_as_fixed(self):
        """Marks a hotspot as fixed

        :return: Whether the operation succeeded
        :rtype: bool
        """
        return self.__mark_as("FIXED")

    def mark_as_acknowledged(self):
        """Marks a hotspot as acknowledged

        :return: Whether the operation succeeded
        :rtype: bool
        """
        if self.endpoint.version() < (9, 4, 0):
            util.logger.warning("Platform version is < 9.4, can't acknowledge %s", str(self))
            return False
        return self.__mark_as("ACKNOWLEDGED")

    def mark_as_to_review(self):
        """Marks a hotspot as to review

        :return: Whether the operation succeeded
        :rtype: bool
        """
        return self.post("hotspots/change_status", params={"hotspot": self.key, "status": "TO_REVIEW"}).ok

    def reopen(self):
        """Reopens a hotspot as to review

        :return: Whether the operation succeeded
        :rtype: bool
        """
        return self.mark_as_to_review()

    def add_comment(self, comment):
        """Adds a comment to a hotspot

        :param comment: Comment to add, in markdown format
        :type comment: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        params = {"hotspot": self.key, "comment": comment}
        return self.post("hotspots/add_comment", params=params).ok

    def assign(self, assignee, comment=None):
        """Assigns a hotspot (and optionally comment)

        :param assignee: User login to assign the hotspot
        :type assignee: str
        :param comment: Comment to add, in markdown format, defaults to None
        :type comment: str, optional
        :return: Whether the operation succeeded
        :rtype: bool
        """
        params = {"hotspot": self.key, "assignee": assignee}
        if comment is not None:
            params["comment"] = comment
        return self.post("hotspots/assign", params=params)

    def __apply_event(self, event, settings):
        util.logger.debug("Applying event %s", str(event))
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
            # self.add_comment(f"Hotspot marked as acknowledged {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "ASSIGN":
            if settings[syncer.SYNC_ASSIGN]:
                u = users.get_login_from_name(data, endpoint=self.endpoint)
                if u is None:
                    u = settings[syncer.SYNC_SERVICE_ACCOUNTS][0]
                self.assign(u)
                # self.add_comment(f"Hotspot assigned assigned {origin}", settings[SYNC_ADD_COMMENTS])

        elif event_type == "INTERNAL":
            util.logger.info("Changelog %s is internal, it will not be applied...", str(event))
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        else:
            util.logger.error("Event %s can't be applied", str(event))
            return False
        return True

    def apply_changelog(self, source_hotspot, settings):
        """
        :meta private:
        """
        events = source_hotspot.changelog()
        if events is None or not events:
            util.logger.debug("Sibling %s has no changelog, no action taken", str(source_hotspot))
            return False

        change_nbr = 0
        start_change = len(self.changelog()) + 1
        util.logger.debug("Applying changelog of %s to %s, from change %d", str(source_hotspot), str(self), start_change)
        for key in sorted(events.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                util.logger.debug("Skipping change already applied in a previous sync: %s", str(events[key]))
                continue
            self.__apply_event(events[key], settings)

        comments = source_hotspot.comments()
        if len(self.comments()) == 0 and settings[syncer.SYNC_ADD_LINK]:
            util.logger.info("Target %s has 0 comments, adding sync link comment", str(self))
            start_change = 1
            self.add_comment(f"Automatically synchronized from [this original issue]({source_hotspot.url()})")
        else:
            start_change = len(self.comments())
            util.logger.info("Target %s already has %d comments", str(self), start_change)
        util.logger.info(
            "Applying comments of %s to %s, from comment %d",
            str(source_hotspot),
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

    def changelog(self):
        """
        :return: The hotspot changelog
        :rtype: dict
        """
        if self._changelog is not None:
            return self._changelog
        if not self.__details:
            self.refresh()
        util.json_dump_debug(self.__details, f"{str(self)} Details = ")
        self._changelog = {}
        seq = 1
        for l in self.__details["changelog"]:
            d = changelog.Changelog(l)
            if d.is_technical_change():
                # Skip automatic changelog events generated by SonarSource itself
                util.logger.debug("Changelog is a technical change: %s", str(d))
                continue
            util.json_dump_debug(l, "Changelog item Changelog ADDED = ")
            seq += 1
            self._changelog[f"{d.date()}_{seq:03d}"] = d
        return self._changelog

    def comments(self):
        """
        :return: The hotspot comments
        :rtype: dict
        """
        if self._comments is not None:
            return self._comments
        if not self.__details:
            self.refresh()
        self._comments = {}
        seq = 0
        for c in self.__details["comment"]:
            seq += 1
            self._comments[f"{c['createdAt']}_{seq:03d}"] = {
                "date": c["createdAt"],
                "event": "comment",
                "value": c["markdown"],
                "user": c["login"],
                "userName": c["login"],
                "commentKey": c["key"],
            }
        return self._comments


def search_by_project(project_key, endpoint=None, params=None):
    """Searches hotspots of a project

    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param project_key: Project key
    :type project_key: str
    :param params: Search filters to narrow down the search, defaults to None
    :type params: dict
    :return: List of found hotspots
    :rtype: dict{<key>: <Hotspot>}
    """
    new_params = {} if params is None else params.copy()
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = util.csv_to_list(project_key)
    hotspots = {}
    for k in key_list:
        new_params["projectKey"] = k
        project_hotspots = search(endpoint=endpoint, params=new_params)
        util.logger.debug("Project '%s' has %d hotspots", k, len(project_hotspots))
        hotspots.update(project_hotspots)
    return hotspots


def search(endpoint, page=None, params=None):
    """Searches hotspots

    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param project_key: Project key
    :type project_key: str
    :param params: Search filters to narrow down the search, defaults to None
    :type params: dict
    :return: List of found hotspots
    :rtype: dict{<key>: <Hotspot>}
    """
    hotspots_list = {}
    new_params = {} if params is None else params.copy()
    r_list = util.csv_to_list(params.get("resolution", None))
    s_list = util.csv_to_list(params.get("status", None))
    if len(r_list) > 1:
        for r in r_list:
            new_params["resolution"] = r
            hotspots_list.update(search(endpoint, params=new_params))
        return hotspots_list
    elif len(s_list) > 1:
        for s in s_list:
            new_params["status"] = s
            hotspots_list.update(search(endpoint, params=new_params))
        return hotspots_list

    new_params["ps"] = 500
    p = 1
    while True:
        if page is None:
            new_params["p"] = p
        else:
            new_params["p"] = page
        resp = endpoint.get("hotspots/search", params=new_params)
        data = json.loads(resp.text)
        nbr_hotspots = data["paging"]["total"]
        nbr_pages = (nbr_hotspots + 499) // 500
        util.logger.debug(
            "Number of issues: %d - Page: %d/%d",
            nbr_hotspots,
            new_params["p"],
            nbr_pages,
        )
        if page is None and nbr_hotspots > 10000:
            raise TooManyHotspotsError(
                nbr_hotspots,
                f"{nbr_hotspots} hotpots returned by api/hotspots/search, " "this is more than the max 10000 possible",
            )

        for i in data["hotspots"]:
            if "branch" in params:
                i["branch"] = params["branch"]
            if "pullRequest" in params:
                i["pullRequest"] = params["pullRequest"]
            hotspots_list[i["key"]] = get_object(i["key"], endpoint=endpoint, data=i)
        if page is not None or p >= nbr_pages:
            break
        p += 1
    return hotspots_list


def get_object(key, data=None, endpoint=None, from_export=False):
    if key not in _OBJECTS:
        _ = Hotspot(key=key, data=data, endpoint=endpoint, from_export=from_export)
    return _OBJECTS[key]


def get_search_criteria(params):
    """Returns the filtered list of params that are allowed for api/issue/search"""
    criterias = {} if params is None else params.copy()
    for old, new in {
        "resolutions": "resolution",
        "componentsKey": "projectKey",
        "statuses": "status",
    }.items():
        if old in params:
            criterias[new] = params[old]
    if criterias.get("status", None) is not None:
        criterias["status"] = util.allowed_values_string(criterias["status"], STATUSES)
    if criterias.get("resolution", None) is not None:
        criterias["resolution"] = util.allowed_values_string(criterias["resolution"], RESOLUTIONS)
        util.logger.error("hotspot 'status' criteria incompatible with 'resolution' criteria, ignoring 'status'")
        criterias["status"] = "REVIEWED"
    return util.dict_subset(util.remove_nones(criterias), SEARCH_CRITERIAS)
