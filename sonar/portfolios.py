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

    Abstraction of the SonarQube "portfolio" concept

"""

from __future__ import annotations
from queue import Queue
from typing import Union, Optional
import json
import datetime
from http import HTTPStatus
from threading import Lock
from requests import HTTPError, RequestException

import sonar.logging as log
import sonar.platform as pf
from sonar.util import types

from sonar import aggregations, exceptions, settings, applications, app_branches
import sonar.permissions.permissions as perms
import sonar.permissions.portfolio_permissions as pperms
import sonar.sqobject as sq
import sonar.utilities as util
from sonar.audit import rules, problem

from sonar.portfolio_reference import PortfolioReference

_CLASS_LOCK = Lock()

_CREATE_API = "views/create"
_GET_API = "views/show"

_PORTFOLIO_QUALIFIER = "VW"
_SUBPORTFOLIO_QUALIFIER = "SVW"

_SELECTION_MODE_MANUAL = "MANUAL"
_SELECTION_MODE_REGEXP = "REGEXP"
_SELECTION_MODE_TAGS = "TAGS"
_SELECTION_MODE_REST = "REST"
_SELECTION_MODE_NONE = "NONE"

SELECTION_MODES = (_SELECTION_MODE_MANUAL, _SELECTION_MODE_REGEXP, _SELECTION_MODE_TAGS, _SELECTION_MODE_REST, _SELECTION_MODE_NONE)

_API_SELECTION_MODE_FIELD = "selectionMode"
_API_SELECTION_BRANCH_FIELD = "projectSelectionBranch"
_API_SELECTION_REGEXP_FIELD = "projectSelectionRegexp"
_API_SELECTION_TAGS_FIELD = "projectSelectionTags"

_IMPORTABLE_PROPERTIES = (
    "key",
    "name",
    "description",
    "visibility",
    "permissions",
    "projects",
    "projectsList",
    "portfolios",
    "subPortfolios",
    "applications",
)


class Portfolio(aggregations.Aggregation):
    """
    Abstraction of the Sonar portfolio concept
    """

    SEARCH_API = "views/search"
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "components"
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000

    _OBJECTS = {}

    def __init__(self, endpoint: pf.Platform, name: str, key: str = None) -> None:
        """Constructor, don't use - use class methods instead"""
        if not key:
            key = name.replace(" ", "_")
        super().__init__(endpoint=endpoint, key=key)
        self.name = name
        self._selection_mode = {_SELECTION_MODE_NONE: True}  #: Portfolio project selection mode
        self._tags = []  #: Portfolio tags when selection mode is TAGS
        self._description = None  #: Portfolio description
        self._visibility = None  #: Portfolio visibility
        self._sub_portfolios = {}  #: Subportfolios
        self._applications = {}  #: applications
        self._permissions = None  #: Permissions
        self.is_sub_portfolio = None
        self.parent = None  #: Ref to parent portfolio object, if any
        self._root_portfolio = None  #: Ref to root portfolio, if any
        Portfolio._OBJECTS[self.uuid()] = self
        log.debug("Created portfolio object name '%s'", name)

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str) -> Portfolio:
        """Gets a portfolio object from its key"""
        check_supported(endpoint)
        log.debug("Getting portfolio object key '%s'", key)
        uid = sq.uuid(key, endpoint.url)
        if uid in Portfolio._OBJECTS:
            return Portfolio._OBJECTS[uid]
        data = search_by_key(endpoint, key)
        if data is None:
            raise exceptions.ObjectNotFound(key, f"Portfolio key '{key}' not found")
        return Portfolio.load(endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint: pf.Platform, key: str, name: str, **kwargs) -> Portfolio:
        """Creates a portfolio object"""
        check_supported(endpoint)
        if exists(endpoint=endpoint, key=key):
            raise exceptions.ObjectAlreadyExists(key=key, message=f"Portfolio '{key}' already exists")
        parent_key = kwargs["parent"].key if "parent" in kwargs else None
        log.debug("Creating portfolio name '%s', key '%s', parent = %s", name, key, str(parent_key))
        params = {"name": name, "key": key, "parent": parent_key}
        for p in "description", "visibility":
            params[p] = kwargs.get(p, None)
        endpoint.post(_CREATE_API, params=params)
        o = cls(endpoint=endpoint, name=name, key=key)
        if parent_key:
            o.load_parent(Portfolio.get_object(endpoint, parent_key))
        # TODO - Allow on the fly selection mode
        return o

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> Portfolio:
        """Creates and load a Portfolio object with returned API data"""
        log.debug("Loading portfolio '%s' with data %s", data["name"], util.json_dump(data))
        o = cls(endpoint=endpoint, name=data["name"], key=data["key"])
        o.reload(data)
        return o

    def __str__(self) -> str:
        """Returns string representation of object"""
        return f"subportfolio '{self.key}'" if self.is_sub_portfolio else f"portfolio '{self.key}'"

    def reload(self, data: types.ApiPayload) -> None:
        """Reloads a portfolio with returned API data"""
        log.debug("Reloading %s with %s", str(self), util.json_dump(data))
        super().reload(data)
        self.name = data.get("name", self.name)
        self.is_sub_portfolio = self._json.get("qualifier", _PORTFOLIO_QUALIFIER) == _SUBPORTFOLIO_QUALIFIER
        self._visibility = self._json.get("visibility", self._visibility)
        self.load_selection_mode()
        self.reload_sub_portfolios()

    def reload_sub_portfolios(self) -> None:
        if "subViews" not in self._json:
            return
        self._sub_portfolios = {}
        for data in self._json["subViews"]:
            if data["qualifier"] in ("VW", "SVW"):
                self.load_sub_portfolio(data.copy())

    def load_selection_mode(self) -> None:
        """Loads the portfolio selection mode"""
        mode = self._json.get(_API_SELECTION_MODE_FIELD, None)
        if mode is None:
            return
        branch = self._json.get("branch", settings.DEFAULT_BRANCH)
        if mode == _SELECTION_MODE_MANUAL:
            self._selection_mode = {mode: {}}
            for projdata in self._json.get("selectedProjects", {}):
                branch_list = projdata.get("selectedBranches", [settings.DEFAULT_BRANCH])
                self._selection_mode[mode].update({projdata["projectKey"]: branch_list})
        elif mode == _SELECTION_MODE_REGEXP:
            self._selection_mode = {mode: self._json["regexp"], "branch": branch}
        elif mode == _SELECTION_MODE_TAGS:
            self._selection_mode = {mode: self._json["tags"], "branch": branch}
        elif mode == _SELECTION_MODE_REST:
            self._selection_mode = {mode: True, "branch": branch}
        else:
            self._selection_mode = {mode: True}

    def refresh(self) -> None:
        """Refreshes a portfolio data from the Sonar instance"""
        log.debug("Updating details for %s root key %s", str(self), self._root_portfolio)
        data = json.loads(self.get(_GET_API, params={"key": self.root_portfolio().key}).text)
        if not self.is_sub_portfolio:
            self.reload(data)
        self.root_portfolio().reload_sub_portfolios()
        self.applications()

    def last_analysis(self) -> datetime.datetime:
        """Returns the portfolio last computation date"""
        if self._last_analysis is None:
            super().refresh()
        return self._last_analysis

    def load_parent(self, parent_portfolio: Portfolio) -> None:
        """Sets the parent portfolio of a subportfolio"""
        self.parent = parent_portfolio
        self._root_portfolio = self.root_portfolio()
        log.debug("%s: Parent = %s, Root = %s", str(self), str(self.parent), str(self._root_portfolio))

    def url(self) -> str:
        """Returns the object permalink"""
        return f"{self.endpoint.url}/portfolio?id={self.key}"

    def root_portfolio(self) -> Portfolio:
        """Returns the root portfolio of a portfolio in a hierarchy"""
        if self.parent is None or self.parent.key == self.key:
            log.debug("Found root for %s, parent = %s", self.key, str(self.parent))
            self._root_portfolio = self
        else:
            log.debug("recursing root for %s, parent = %s", self.key, str(self.parent))
            self._root_portfolio = self.parent.root_portfolio()
        return self._root_portfolio

    def projects(self) -> Optional[dict[str, str]]:
        """Returns list of projects and their branches if selection mode is manual, None otherwise"""
        if not self._selection_mode or _SELECTION_MODE_MANUAL not in self._selection_mode:
            log.debug("%s: Not manual mode, no projects", str(self))
            return None
        return self._selection_mode[_SELECTION_MODE_MANUAL]

    def applications(self) -> Optional[dict[str, str]]:
        log.debug("Collecting portfolios applications")
        apps = [data for data in self._json["subViews"] if data["qualifier"] == "APP"]
        for app_data in apps:
            app_o = applications.Application.get_object(self.endpoint, app_data["originalKey"])
            for branch in app_data["selectedBranches"]:
                if app_branches.ApplicationBranch.get_object(app=app_o, branch_name=branch).is_main():
                    app_data["selectedBranches"].remove(branch)
                    app_data["selectedBranches"].insert(0, settings.DEFAULT_BRANCH)
            self._applications[app_data["originalKey"]] = app_data["selectedBranches"]
        return self._applications

    def sub_portfolios(self, full: bool = False) -> dict[str, Portfolio]:
        """Returns the list of sub portfolios as dict"""
        self.refresh()
        # self._sub_portfolios = _sub_portfolios(self._json, self.endpoint.version(), full=full)
        self.reload_sub_portfolios()
        return self._sub_portfolios

    def add_reference_subportfolio(self, reference: Portfolio) -> object:
        ref = PortfolioReference.create(parent=self, reference=reference)
        try:
            if self.endpoint.version() >= (9, 3, 0):
                self.post("views/add_portfolio", params={"portfolio": self.key, "reference": reference.key}, mute=(HTTPStatus.BAD_REQUEST,))
            else:
                self.post("views/add_local_view", params={"key": self.key, "ref_key": reference.key}, mute=(HTTPStatus.BAD_REQUEST,))
        except (ConnectionError, RequestException) as e:
            if not isinstance(e, HTTPError) or e.response.status_code != HTTPStatus.BAD_REQUEST:
                log.error("%s while adding reference subportfolio to %s", util.error_msg(e), str(self))
                raise
        self._sub_portfolios.update({reference.key: ref})
        return ref

    def add_standard_subportfolio(self, key: str, name: str, **kwargs) -> Portfolio:
        """Adds a subportfolio"""
        subp = Portfolio.create(endpoint=self.endpoint, key=key, name=name, parent=self, **kwargs)
        try:
            if self.endpoint.version() < (9, 3, 0):
                self.post("views/add_sub_view", params={"key": self.key, "name": name, "subKey": key}, mute=(HTTPStatus.BAD_REQUEST,))
        except (ConnectionError, RequestException) as e:
            if not isinstance(e, HTTPError) or e.response.status_code != HTTPStatus.BAD_REQUEST:
                log.error("%s while adding standard subportfolio to %s", util.error_msg(e), str(self))
                raise
        self._sub_portfolios.update({subp.key: subp})
        return subp

    def load_sub_portfolio(self, data: types.ApiPayload) -> Portfolio:
        """Loads an existing a subportfolio"""
        if data["qualifier"] == _PORTFOLIO_QUALIFIER:
            key = data["originalKey"]
            ref = Portfolio.get_object(endpoint=self.endpoint, key=key)
            subp = PortfolioReference.load(reference=ref, parent=self)
        else:
            subp = Portfolio.load(endpoint=self.endpoint, data=data)
            key = subp.key
            subp.parent = self
            subp.reload_sub_portfolios()
        self._sub_portfolios.update({key: subp})
        return subp

    def get_components(self) -> types.ApiPayload:
        """Returns subcomponents of a Portfolio"""
        data = json.loads(
            self.get(
                "measures/component_tree",
                params={
                    "component": self.key,
                    "metricKeys": "ncloc",
                    "strategy": "children",
                    "ps": Portfolio.MAX_PAGE_SIZE,
                },
            ).text
        )
        comp_list = {}
        for c in data["components"]:
            comp_list[c["key"]] = c
        return comp_list

    def delete(self) -> bool:
        """Deletes a portfolio, returns whether the operation succeeded"""
        return sq.delete_object(self, "views/delete", {"key": self.key}, Portfolio._OBJECTS)

    def _audit_empty(self, audit_settings: types.ConfigSettings) -> list[problem.Problem]:
        """Audits if a portfolio is empty (no projects)"""
        if not audit_settings.get("audit.portfolios.empty", True):
            log.debug("Auditing empty portfolios is disabled, skipping...")
            return []
        return self._audit_empty_aggregation(broken_rule=rules.RuleId.PORTFOLIO_EMPTY)

    def _audit_singleton(self, audit_settings: types.ConfigSettings) -> list[problem.Problem]:
        """Audits if a portfolio contains a single project"""
        if not audit_settings.get("audit.portfolios.singleton", True):
            log.debug("Auditing singleton portfolios is disabled, skipping...")
            return []
        return self._audit_singleton_aggregation(broken_rule=rules.RuleId.PORTFOLIO_SINGLETON)

    def audit(self, audit_settings: types.ConfigSettings) -> list[problem.Problem]:
        """Audits a portfolio"""
        log.info("Auditing %s", str(self))
        return (
            super().audit(audit_settings)
            + self._audit_empty(audit_settings)
            + self._audit_singleton(audit_settings)
            + self._audit_bg_task(audit_settings)
        )

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Returns the portfolio representation as JSON"""
        self.refresh()
        json_data = {"key": self.key, "name": self.name}
        if self._description:
            json_data["description"] = self._description
        subportfolios = self.sub_portfolios()
        if not self.is_sub_portfolio:
            json_data["visibility"] = self._visibility
            json_data["permissions"] = self.permissions().export(export_settings=export_settings)
        json_data["tags"] = self._tags
        if subportfolios:
            json_data["portfolios"] = {}
            for s in subportfolios.values():
                subp_json = s.to_json(export_settings)
                subp_key = subp_json.pop("key")
                json_data["portfolios"][subp_key] = subp_json
        mode = self.selection_mode().copy()
        if mode:
            if "none" not in mode or export_settings.get("MODE", "") == "MIGRATION":
                json_data["projects"] = mode
            if export_settings.get("MODE", "") == "MIGRATION":
                json_data["projects"]["keys"] = self.get_project_list()
        json_data["applications"] = self._applications

        return json_data

    def export(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Exports a portfolio (for sonar-config)"""
        log.info("Exporting %s", str(self))
        return util.remove_nones(util.filter_export(self.to_json(export_settings), _IMPORTABLE_PROPERTIES, export_settings["FULL_EXPORT"]))

    def permissions(self) -> pperms.PortfolioPermissions:
        """Returns a portfolio permissions (if toplevel) or None if sub-portfolio"""
        if self._permissions is None and not self.is_sub_portfolio:
            # No permissions for sub portfolios
            self._permissions = pperms.PortfolioPermissions(self)
        return self._permissions

    def set_permissions(self, portfolio_perms: dict[str, str]) -> None:
        """Sets a portfolio permissions described as JSON"""
        if not self.is_sub_portfolio:
            # No permissions for SVW
            self.permissions().set(portfolio_perms)

    def selection_mode(self) -> dict[str, str]:
        """Returns a portfolio selection mode"""
        if self._selection_mode is None:
            # FIXME: If portfolio is a subportfolio you must reload with sub-JSON
            self.reload(json.loads(self.get(_GET_API, params={"key": self.root_portfolio().key}).text))
        return {k.lower(): v for k, v in self._selection_mode.items()}

    def has_project(self, key: str) -> bool:
        return _SELECTION_MODE_MANUAL in self._selection_mode and key in self._selection_mode[_SELECTION_MODE_MANUAL]

    def has_project_branch(self, key: str, branch: str) -> bool:
        return self.has_project(key) and branch == self._selection_mode[_SELECTION_MODE_MANUAL][key]

    def add_projects(self, project_list: list[Union[str, object]]) -> Portfolio:
        """Adds projects main branch to a portfolio"""
        if not project_list or len(project_list) == 0:
            return self
        self.set_manual_mode()
        branch_dict = {}
        for p in project_list:
            key = p if isinstance(p, str) else p.key
            branch_dict[key] = None
        return self.add_project_branches(branch_dict)

    def add_project_branches(self, branch_dict: dict[str, Union[str, object]]) -> Portfolio:
        """Adds projects branches to a portfolio"""
        if not branch_dict:
            return self
        self.set_manual_mode()
        proj_dict = {}
        for proj, branch in branch_dict.items():
            key = proj if isinstance(proj, str) else proj.key
            try:
                if not self.has_project(key):
                    self.post("views/add_project", params={"key": self.key, "project": key}, mute=(HTTPStatus.BAD_REQUEST,))
                    self._selection_mode[_SELECTION_MODE_MANUAL][key] = settings.DEFAULT_BRANCH
                if not self.has_project_branch(key, branch):
                    self.post("views/add_project_branch", params={"key": self.key, "project": key, "branch": branch}, mute=(HTTPStatus.BAD_REQUEST,))
                    self._selection_mode[_SELECTION_MODE_MANUAL][key] = branch
                proj_dict[key] = branch
                self._selection_mode[_SELECTION_MODE_MANUAL] = proj_dict
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(self.key, f"Project '{key}' or branch '{branch}' not found, can't be added to {str(self)}")
                if e.response.status_code == HTTPStatus.BAD_REQUEST:
                    log.error("%s while adding project branches to %s", util.error_msg(e), str(self))
                    raise
            except (ConnectionError, RequestException) as e:
                log.error("%s while adding project branches to %s", util.error_msg(e), str(self))
                raise
        return self

    def set_manual_mode(self) -> Portfolio:
        """Sets a portfolio to manual mode"""
        if not self._selection_mode or _SELECTION_MODE_MANUAL not in self._selection_mode:
            self.post("views/set_manual_mode", params={"portfolio": self.key})
            self._selection_mode = {_SELECTION_MODE_MANUAL: {}}
        return self

    def set_tags_mode(self, tags: list[str], branch: Optional[str] = None) -> Portfolio:
        """Sets a portfolio to tags mode"""
        if branch is None:
            branch = settings.DEFAULT_BRANCH
        self.post("views/set_tags_mode", params={"portfolio": self.key, "tags": util.list_to_csv(tags), "branch": get_api_branch(branch)})
        self._selection_mode = {_SELECTION_MODE_TAGS: tags, "branch": branch}
        return self

    def set_regexp_mode(self, regexp: str, branch: Optional[str] = None) -> Portfolio:
        """Sets a portfolio to regexp mode"""
        if branch is None:
            branch = settings.DEFAULT_BRANCH
        self.post("views/set_regexp_mode", params={"portfolio": self.key, "regexp": regexp, "branch": get_api_branch(branch)})
        self._selection_mode = {_SELECTION_MODE_REGEXP: regexp, "branch": branch}
        return self

    def set_remaining_projects_mode(self, branch: Optional[str] = None) -> Portfolio:
        """Sets a portfolio to remaining projects mode"""
        if branch is None:
            branch = settings.DEFAULT_BRANCH
        self.post("views/set_remaining_projects_mode", params={"portfolio": self.key, "branch": get_api_branch(branch)})
        self._selection_mode = {"rest": True, "branch": branch}
        return self

    def set_none_mode(self) -> Portfolio:
        """Sets a portfolio to none mode"""
        # Hack: API change between 9.0 and 9.1
        mode = self._selection_mode
        if not mode or len(mode) > 0:
            if self.endpoint.version() < (9, 1, 0):
                self.post("views/mode", params={"key": self.key, _API_SELECTION_MODE_FIELD: "NONE"})
            else:
                self.post("views/set_none_mode", params={"portfolio": self.key})
            self._selection_mode = {}
        return self

    def set_selection_mode(self, data: dict[str, str]) -> Portfolio:
        """Sets a portfolio selection mode"""
        params = data.get("projects", {})
        log.info("Setting %s selection mode params %s", str(self), str(params))
        branch = params.get("branch", None)
        if _SELECTION_MODE_MANUAL.lower() in params:
            self.set_manual_mode().add_projects(params[_SELECTION_MODE_MANUAL.lower()])
        elif _SELECTION_MODE_TAGS.lower() in params:
            self.set_tags_mode(params[_SELECTION_MODE_TAGS.lower()], branch)
        elif _SELECTION_MODE_REGEXP.lower() in params:
            self.set_regexp_mode(params[_SELECTION_MODE_REGEXP.lower()], branch)
        elif _SELECTION_MODE_REST.lower() in params:
            self.set_remaining_projects_mode(branch)
        else:
            self.set_none_mode()
        return self

    def set_description(self, desc: str) -> Portfolio:
        if desc:
            self.post("views/update", params={"key": self.key, "name": self.name, "description": desc})
            self._description = desc
        return self

    def set_name(self, name: str) -> Portfolio:
        if name:
            self.post("views/update", params={"key": self.key, "name": name})
            self.name = name
        return self

    def add_application(self, app_key: str) -> bool:
        self.add_application_branch(app_key=app_key, branch=settings.DEFAULT_BRANCH)

    def add_application_branch(self, app_key: str, branch: str = settings.DEFAULT_BRANCH) -> bool:
        app = applications.Application.get_object(self.endpoint, app_key)
        try:
            if branch == settings.DEFAULT_BRANCH:
                log.info("%s: Adding %s default branch", str(self), str(app))
                self.post("views/add_application", params={"portfolio": self.key, "application": app_key}, mute=(HTTPStatus.BAD_REQUEST,))
            else:
                app_branch = app_branches.ApplicationBranch.get_object(app=app, branch_name=branch)
                log.info("%s: Adding %s", str(self), str(app_branch))
                params = {"key": self.key, "application": app_key, "branch": branch}
                self.post("views/add_application_branch", params=params, mute=(HTTPStatus.BAD_REQUEST,))
        except (ConnectionError, RequestException) as e:
            if not isinstance(e, HTTPError) or e.response.status_code != HTTPStatus.BAD_REQUEST:
                log.error("%s while adding application branch to %s", util.error_msg(e), str(self))
                raise
            log.warning(util.error_msg(e))
        if app_key not in self._applications:
            self._applications[app_key] = []
        self._applications[app_key].append(branch)
        return True

    def add_subportfolio(self, key: str, name: str = None, by_ref: bool = False) -> object:
        """Adds a subportfolio to a portfolio, defined by key, name and by reference option"""
        # if not exists(key, self.endpoint):
        #    log.warning("Can't add in %s the subportfolio key '%s' by reference, it does not exists", str(self), key)
        #    return False

        log.info("Adding sub-portfolios to %s", str(self))
        if self.is_parent_of(key):
            log.warning("Portfolio '%s' is already subportfolio of %s", key, str(self))
            return self._sub_portfolios[key]
        if by_ref:
            subp = self.add_reference_subportfolio(Portfolio.get_object(self.endpoint, key))
        else:
            subp = self.add_standard_subportfolio(key=key, name=name)
        return subp

    def is_toplevel(self) -> bool:
        return self.is_sub_portfolio is None or not self.is_sub_portfolio

    def is_parent_of(self, key: str) -> bool:
        """Returns whether a portfolio is parent of another subportfolio (given by key)"""
        return key in self._sub_portfolios

    def is_subporfolio_of(self, key: str) -> bool:
        """Returns whether a portfolio is already a subportfolio of another portfolio (given by key)"""
        try:
            parent = Portfolio.get_object(endpoint=self.endpoint, key=key)
        except exceptions.ObjectNotFound:
            return False
        return parent.is_parent_of(self.key)

    def recompute(self) -> bool:
        """Triggers portfolio recomputation, return whether operation REQUEST succeeded"""
        log.debug("Recomputing %s", str(self))
        key = self._root_portfolio.key if self._root_portfolio else self.key
        return self.post("views/refresh", params={"key": key}).ok

    def get_project_list(self) -> list[str]:
        log.debug("Search %s projects list", str(self))
        proj_key_list = []
        page = 0
        params = {"component": self.key, "ps": Portfolio.MAX_PAGE_SIZE, "qualifiers": "TRK", "strategy": "leaves", "metricKeys": "ncloc"}
        while True:
            page += 1
            params["p"] = page
            try:
                data = json.loads(self.get("api/measures/component_tree", params=params).text)
                nbr_projects = util.nbr_total_elements(data)
                proj_key_list += [c["refKey"] for c in data["components"]]
            except (ConnectionError, RequestException) as e:
                log.error("%s while collecting projects from %s, stopping collection", util.error_msg(e), str(self))
                break
            nbr_pages = util.nbr_pages(data)
            log.debug("Number of projects: %d - Page: %d/%d", nbr_projects, page, nbr_pages)
            if nbr_projects > Portfolio.MAX_SEARCH:
                log.warning("Can't collect more than %d projects from %s", Portfolio.MAX_SEARCH, str(self))
            if page >= nbr_pages or page >= Portfolio.MAX_SEARCH / Portfolio.MAX_PAGE_SIZE:
                break
        log.debug("%s projects list = %s", str(self), str(proj_key_list))
        return proj_key_list

    def update(self, data: dict[str, str], recurse: bool) -> None:
        """Updates a portfolio with sonar-config JSON data, if recurse is true, this recurses in sub portfolios"""
        log.debug("Updating %s with %s", str(self), util.json_dump(data))
        if "byReference" in data and data["byReference"]:
            log.debug("Skipping setting portfolio details, it's a reference")
            return

        log.debug("Updating details of %s with %s", str(self), str(data))
        self.set_description(data.get("description", None))
        self.set_name(data.get("name", None))
        self.set_visibility(data.get("visibility", None))
        if "permissions" in data:
            self.set_permissions(perms.decode_full(data["permissions"]))
        self._root_portfolio = self.root_portfolio()
        log.debug("1.Setting root of %s is %s", str(self), str(self._root_portfolio))
        self.set_selection_mode(data)
        for app_key, branches in data.get("applications", {}).items():
            for branch in util.csv_to_list(branches):
                self.add_application_branch(app_key=app_key, branch=branch)
        if not recurse:
            return

        log.info("Updating %s subportfolios", str(self))
        subps = self.sub_portfolios(full=True)
        get_list(endpoint=self.endpoint)
        key_list = []
        if subps:
            key_list = list(subps.keys())
        subportfolios_json = data.get("portfolios", data.get("subPortfolios", {}))
        for key, subp_data in subportfolios_json.items():
            log.info("Processing subportfolio %s", key)
            if subp_data.get("byReference", False):
                o_subp = Portfolio.get_object(self.endpoint, key)
                if o_subp.key not in key_list:
                    self.add_subportfolio(o_subp.key, name=o_subp.name, by_ref=True)
            else:
                try:
                    o_subp = Portfolio.get_object(self.endpoint, key)
                except exceptions.ObjectNotFound:
                    o_subp = self.add_subportfolio(key=key, name=subp_data["name"], by_ref=False)
                o_subp.load_parent(self)
                o_subp.update(data=subp_data, recurse=True)

    def search_params(self) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        return {"portfolio": self.key}


def count(endpoint: pf.Platform) -> int:
    """Counts number of portfolios"""
    return aggregations.count(api=Portfolio.SEARCH_API, endpoint=endpoint)


def get_list(endpoint: pf.Platform, key_list: types.KeyList = None, use_cache: bool = True) -> dict[str, Portfolio]:
    """
    :return: List of Portfolios (all of them if key_list is None or empty)
    :param KeyList key_list: List of portfolios keys to get, if None or empty all portfolios are returned
    :param bool use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :rtype: dict{<branchName>: <Branch>}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            log.debug("Listing portfolios")
            object_list = search(endpoint=endpoint)
            return object_list
        object_list = {}
        for key in util.csv_to_list(key_list):
            object_list[key] = Portfolio.get_object(endpoint, key)
    return object_list


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, Portfolio]:
    """Search all portfolios of a platform and returns as dict"""
    check_supported(endpoint)
    return sq.search_objects(endpoint=endpoint, object_class=Portfolio, params=params)


def check_supported(endpoint: pf.Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    errmsg = ""
    if endpoint.edition() not in ("enterprise", "datacenter"):
        errmsg = f"No portfolios in {endpoint.edition()} edition"
    if endpoint.is_sonarcloud():
        errmsg = "No portfolios in SonarCloud"
    if errmsg != "":
        log.warning(errmsg)
        raise exceptions.UnsupportedOperation(errmsg)


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings, key_list: list[str, str] = None) -> list[object]:
    """Audits all portfolios"""
    if not audit_settings.get("audit.portfolios", True):
        log.debug("Auditing portfolios is disabled, skipping...")
        return []
    log.info("--- Auditing portfolios ---")
    problems = []
    for p in get_list(endpoint=endpoint, key_list=key_list).values():
        problems += p.audit(audit_settings)
    return problems


def exists(endpoint: pf.Platform, key: str) -> bool:
    """Tells whether a portfolio with a given key exists"""
    try:
        Portfolio.get_object(endpoint, key)
        return True
    except exceptions.ObjectNotFound:
        return False


def delete(endpoint: pf.Platform, key: str) -> bool:
    """Deletes a portfolio by its key"""
    try:
        p = Portfolio.get_object(endpoint, key)
        p.delete()
        return True
    except exceptions.ObjectNotFound:
        return False


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> None:
    """Imports portfolio configuration described in a JSON"""
    if "portfolios" not in config_data:
        log.info("No portfolios to import")
        return
    check_supported(endpoint)

    log.info("Importing portfolios - pass 1: Create all top level portfolios")
    search(endpoint=endpoint)
    # First pass to create all top level porfolios that may be referenced
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["portfolios"].items():
        if new_key_list and key not in new_key_list:
            continue
        log.info("Importing portfolio key '%s'", key)
        try:
            o = Portfolio.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            log.info("Portfolio not found, creating it")
            newdata = data.copy()
            name = newdata.pop("name")
            o = Portfolio.create(endpoint=endpoint, name=name, key=key, **newdata)

    # Second pass to define hierarchies
    log.info("Importing portfolios - pass 2: Creating sub-portfolios")
    for key, data in config_data["portfolios"].items():
        if new_key_list and key not in new_key_list:
            continue
        try:
            o = Portfolio.get_object(endpoint, key)
            o.update(data=data, recurse=True)
        except exceptions.ObjectNotFound as e:
            log.error(e.message)


def search_by_name(endpoint: pf.Platform, name: str) -> types.ApiPayload:
    """Searches portfolio by name and, if found, returns data as JSON"""
    return util.search_by_name(endpoint, name, Portfolio.SEARCH_API, "components")


def search_by_key(endpoint: pf.Platform, key: str) -> types.ApiPayload:
    """Searches portfolio by key and, if found, returns data as JSON"""
    return util.search_by_key(endpoint, key, Portfolio.SEARCH_API, "components")


def export(
    endpoint: pf.Platform, export_settings: types.ConfigSettings, key_list: Optional[types.KeyList] = None, write_q: Optional[Queue] = None
) -> types.ObjectJsonRepr:
    """Exports portfolios as JSON

    :param Platform endpoint: Reference to the SonarQube platform
    :param ConfigSetting export_settings: Options to use for export
    :param KeyList key_list: list of portfoliios keys to export as csv or list, defaults to all if None
    :return: Dict of portfolio settings
    :rtype: ObjectJsonRepr
    """
    check_supported(endpoint)

    log.info("Exporting portfolios")
    if key_list:
        nb_portfolios = len(key_list)
    else:
        nb_portfolios = count(endpoint=endpoint)
    i = 0
    exported_portfolios = {}
    for k, p in sorted(get_list(endpoint=endpoint, key_list=key_list).items()):
        try:
            if not p.is_sub_portfolio:
                exp = p.export(export_settings)
                if write_q:
                    write_q.put(exp)
                else:
                    exp.pop("key")
                    exported_portfolios[k] = exp
            else:
                log.debug("Skipping export of %s, it's a standard sub-portfolio", str(p))
        except (ConnectionError, RequestException) as e:
            log.error("%s while exporting %s, export will be empty for this portfolio", util.error_msg(e), str(p))
            exported_portfolios[k] = {}
        i += 1
        if i % 10 == 0 or i == nb_portfolios:
            log.info("Exported %d/%d portfolios (%d%%)", i, nb_portfolios, (i * 100) // nb_portfolios)
    if write_q:
        write_q.put(None)
    return exported_portfolios


def recompute(endpoint: pf.Platform) -> None:
    """Triggers recomputation of all portfolios"""
    endpoint.post("views/refresh")


def _find_sub_portfolio(key: str, data: types.ApiPayload) -> types.ApiPayload:
    """Finds a subportfolio in a JSON hierarchy"""
    for subp in data.get("subViews", []):
        if subp["key"] == key:
            return subp
        child = _find_sub_portfolio(key, subp)
        if child is not None:
            return child
    return {}


def __create_portfolio_hierarchy(endpoint: pf.Platform, data: types.ApiPayload, parent_key: str) -> int:
    """Creates the hierarchy of portfolios that are new defined by reference"""
    nbr_creations = 0
    o_parent = Portfolio.get_object(endpoint, parent_key)
    subportfolios_json = data.get("portfolios", data.get("subPortfolios", {}))
    for key, subp in subportfolios_json.items():
        if subp.get("byReference", False):
            continue
        try:
            o = Portfolio.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            newdata = subp.copy()
            name = newdata.pop("name")
            log.debug("Object not found, creating portfolio name '%s'", name)
            o = Portfolio.create(endpoint, name, key=key, parent=o_parent.key, **newdata)
            o.reload(subp)
            nbr_creations += 1
        o.load_parent(o_parent)
        nbr_creations += __create_portfolio_hierarchy(endpoint, subp, parent_key=key)
    return nbr_creations


def get_api_branch(branch: str) -> str:
    """Returns the value to pass to the API for the branch parameter"""
    return branch if branch != settings.DEFAULT_BRANCH else None


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    new_json = util.dict_to_list(original_json, "key")
    for p_json in new_json:
        try:
            p_json["projects"] = [{"key": k, "branch": br} for k, br in p_json["projects"]["manual"].items()]
        except KeyError:
            pass
        if "portfolios" in p_json:
            p_json["portfolios"] = convert_for_yaml(p_json["portfolios"])
        if "applications" in p_json:
            p_json["applications"] = [{"key": k, "branches": br} for k, br in p_json["applications"].items()]
        if "permissions" in p_json:
            p_json["permissions"] = perms.convert_for_yaml(p_json["permissions"])
    return new_json
