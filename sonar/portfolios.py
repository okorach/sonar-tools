#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

import re
from typing import Optional, Union, Any, TYPE_CHECKING
import json
from http import HTTPStatus
from threading import Lock

import sonar.logging as log
import sonar.platform as pf
from sonar.util import cache
import sonar.util.constants as c

from sonar import aggregations, exceptions, applications, app_branches
from sonar.projects import Project

import sonar.permissions.permissions as perms
import sonar.permissions.portfolio_permissions as pperms
import sonar.sqobject as sq
import sonar.utilities as util
from sonar.audit import rules, problem
from sonar.portfolio_reference import PortfolioReference
from sonar.util import portfolio_helper as phelp

if TYPE_CHECKING:
    from sonar.util import types
    from sonar.branches import Branch

_CLASS_LOCK = Lock()

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
    "projectSelection",
    "applications",
    "portfolios",
    "subPortfolios",
    "projectsList",
)


class Portfolio(aggregations.Aggregation):
    """
    Abstraction of the Sonar portfolio concept
    """

    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "components"
    API = {
        c.CREATE: "views/create",
        c.GET: "views/show",
        c.UPDATE: "views/update",
        c.DELETE: "views/delete",
        c.SEARCH: "views/search",
        c.RECOMPUTE: "views/refresh",
    }
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000

    CACHE = cache.Cache()

    def __init__(self, endpoint: pf.Platform, key: str, name: Optional[str] = None) -> None:
        """Constructor, don't use - use class methods instead"""
        super().__init__(endpoint=endpoint, key=key)
        self.name: str = name if name is not None else key
        self._selection_mode: dict[str, Any] = {_SELECTION_MODE_NONE: True}  #: Portfolio project selection mode
        self._tags: list[str] = []  #: Portfolio tags when selection mode is TAGS
        self._description: Optional[str] = None  #: Portfolio description
        self._visibility: Optional[str] = None  #: Portfolio visibility
        self._applications: dict[str, Any] = {}  #: applications
        self._permissions: Optional[dict[str, list[str]]] = None  #: Permissions
        self._projects: Optional[dict[str, set[str]]] = None  #: Projects and branches in portfolio
        self.parent_portfolio: Optional[Portfolio] = None  #: Ref to parent portfolio object, if any
        self.root_portfolio: Optional[Portfolio] = None  #: Ref to root portfolio, if any
        self._sub_portfolios: dict[str, Portfolio] = {}  #: Subportfolios
        Portfolio.CACHE.put(self)
        log.debug("Created portfolio object name '%s'", name)

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str) -> Portfolio:
        """Gets a portfolio object from its key"""
        check_supported(endpoint)
        log.debug("Getting portfolio object key '%s'", key)
        o = Portfolio.CACHE.get(key, endpoint.local_url)
        if o:
            log.debug("%s is in cache", str(o))
            return o
        log.debug("Portfolio key '%s' not in cache, searching it", key)
        data = search_by_key(endpoint, key)
        if data is None:
            log.debug("Search for portfolio '%s' FAIL", key)
            raise exceptions.ObjectNotFound(key, f"Portfolio key '{key}' not found")
        log.debug("Search for portfolio '%s' SUCCESS", key)
        return Portfolio.load(endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint: pf.Platform, key: str, name: Optional[str] = None, **kwargs) -> Portfolio:
        """Creates a portfolio object"""
        check_supported(endpoint)
        if exists(endpoint=endpoint, key=key):
            raise exceptions.ObjectAlreadyExists(key=key, message=f"Portfolio '{key}' already exists")
        parent_key = kwargs["parent"].key if "parent" in kwargs else None
        if not name:
            name = key
        log.debug("Creating portfolio name '%s', key '%s', parent = %s", name, key, str(parent_key))
        params = {"name": name, "key": key, "parent": parent_key}
        for p in "description", "visibility":
            params[p] = kwargs.get(p, None)
        endpoint.post(Portfolio.API[c.CREATE], params=params)
        o = cls(endpoint=endpoint, name=name, key=key)
        if parent_key:
            parent_p = Portfolio.get_object(endpoint, parent_key)
            o.parent_portfolio = parent_p
            o.root_portfolio = parent_p.root_portfolio
        else:
            o.parent_portfolio = None
            o.root_portfolio = o
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
        return (
            f"subportfolio '{self.key}'"
            if self.sq_json and self.sq_json.get("qualifier", _PORTFOLIO_QUALIFIER) == _SUBPORTFOLIO_QUALIFIER
            else f"portfolio '{self.key}'"
        )

    def reload(self, data: types.ApiPayload) -> None:
        """Reloads a portfolio with returned API data"""
        super().reload(data)
        if "originalKey" not in data and data["qualifier"] == _PORTFOLIO_QUALIFIER:
            self.parent_portfolio = None
            self.root_portfolio = self
        self.load_selection_mode()
        self.reload_sub_portfolios()

    def reload_sub_portfolios(self) -> None:
        if "subViews" not in self.sq_json:
            return
        self._sub_portfolios = {}
        for data in self.sq_json["subViews"]:
            if data["qualifier"] in ("VW", "SVW"):
                self.load_sub_portfolio(data.copy())

    def load_selection_mode(self) -> None:
        """Loads the portfolio selection mode"""
        mode = self.sq_json.get(_API_SELECTION_MODE_FIELD, None)
        if mode is None:
            return
        branch = self.sq_json.get("branch", c.DEFAULT_BRANCH)
        if mode == _SELECTION_MODE_MANUAL:
            self._selection_mode = {mode: {}}
            for projdata in self.sq_json.get("selectedProjects", {}):
                branch_list = projdata.get("selectedBranches", [c.DEFAULT_BRANCH])
                self._selection_mode[mode].update({projdata["projectKey"]: set(branch_list)})
        elif mode == _SELECTION_MODE_REGEXP:
            self._selection_mode = {mode: self.sq_json["regexp"], "branch": branch}
        elif mode == _SELECTION_MODE_TAGS:
            self._selection_mode = {mode: self.sq_json["tags"], "branch": branch}
        elif mode == _SELECTION_MODE_REST:
            self._selection_mode = {mode: True, "branch": branch}
        else:
            self._selection_mode = {mode: True}

    def refresh(self) -> None:
        """Refreshes a portfolio data from the Sonar instance"""
        log.debug("Updating details for %s root key %s", str(self), self.root_portfolio)
        if not self.is_toplevel():
            self.root_portfolio.refresh()
            return
        data = json.loads(self.get(Portfolio.API[c.GET], params={"key": self.key}).text)
        if not self.is_sub_portfolio():
            self.reload(data)
        self.root_portfolio.reload_sub_portfolios()
        self.applications()

    def url(self) -> str:
        """Returns the object permalink"""
        return f"{self.base_url(local=False)}/portfolio?id={self.key}"

    def projects(self) -> Optional[dict[str, str]]:
        """Returns list of projects and their branches if selection mode is manual, or the list of projects for other modes"""
        if not self._selection_mode or _SELECTION_MODE_MANUAL not in self._selection_mode:
            if self._projects is None:
                data = json.loads(self.get("api/views/projects_status", params={"portfolio": self.key}).text)
                self._projects = {p["refKey"]: {c.DEFAULT_BRANCH} for p in data["projects"]}
            return self._projects
        return self._selection_mode[_SELECTION_MODE_MANUAL]

    def components(self) -> list[Union[Project, Branch]]:
        """Returns the list of components objects (projects/branches) in the portfolio"""
        log.debug("Collecting portfolio components from %s", util.json_dump(self.sq_json))
        new_comps = []
        for p_key, p_branches in self.projects().items():
            proj = Project.get_object(self.endpoint, p_key)
            for br in p_branches:
                # If br is DEFAULT_BRANCH, next() will find nothing and we'll append the project itself
                new_comps.append(next((b for b in proj.branches().values() if b.name == br), proj))
        return new_comps

    def applications(self) -> Optional[dict[str, str]]:
        log.debug("Collecting portfolios applications from %s", util.json_dump(self.sq_json))
        if "subViews" not in self.sq_json:
            self._applications = {}
            return self._applications
        apps = [data for data in self.sq_json["subViews"] if data["qualifier"] == "APP"]
        for app_data in apps:
            app_o = applications.Application.get_object(self.endpoint, app_data["originalKey"])
            for branch in app_data["selectedBranches"]:
                if app_branches.ApplicationBranch.get_object(app=app_o, branch_name=branch).is_main():
                    app_data["selectedBranches"].remove(branch)
                    app_data["selectedBranches"].insert(0, c.DEFAULT_BRANCH)
            self._applications[app_data["originalKey"]] = app_data["selectedBranches"]
        return self._applications

    def sub_portfolios(self, full: bool = False) -> dict[str, Portfolio]:
        """Returns the list of sub portfolios as dict"""
        self.refresh()
        # self._sub_portfolios = _sub_portfolios(self.sq_json, self.endpoint.version(), full=full)
        self.reload_sub_portfolios()
        return self._sub_portfolios

    def add_reference_subportfolio(self, reference: Portfolio) -> object:
        ref = PortfolioReference.create(parent=self, reference=reference)
        if self.endpoint.version() >= (9, 3, 0):
            self.post("views/add_portfolio", params={"portfolio": self.key, "reference": reference.key}, mute=(HTTPStatus.BAD_REQUEST,))
        else:
            self.post("views/add_local_view", params={"key": self.key, "ref_key": reference.key}, mute=(HTTPStatus.BAD_REQUEST,))
        self._sub_portfolios.update({reference.key: ref})
        return ref

    def add_standard_subportfolio(self, key: str, name: str, **kwargs) -> Portfolio:
        """Adds a subportfolio"""
        subp = Portfolio.create(endpoint=self.endpoint, key=key, name=name, parent=self, **kwargs)
        if self.endpoint.version() < (9, 3, 0):
            self.post("views/add_sub_view", params={"key": self.key, "name": name, "subKey": key}, mute=(HTTPStatus.BAD_REQUEST,))
        self._sub_portfolios.update({subp.key: subp})
        return subp

    def load_sub_portfolio(self, data: types.ApiPayload) -> Portfolio:
        """Loads an existing a subportfolio"""
        if data["qualifier"] == _PORTFOLIO_QUALIFIER:
            # Reference portfolios
            key = data["originalKey"]
            ref = Portfolio.get_object(endpoint=self.endpoint, key=key)
            subp = PortfolioReference.load(reference=ref, parent=self)
        else:
            # Standard subportfolios
            key = data["key"]
            log.info("Loading std subp %s", key)
            try:
                subp = Portfolio.get_object(endpoint=self.endpoint, key=key)
                subp.reload(data)
            except exceptions.ObjectNotFound:
                subp = Portfolio.load(endpoint=self.endpoint, data=data)
            key = subp.key
            subp.parent_portfolio = self
            subp.root_portfolio = self.root_portfolio
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
        for cmp in data["components"]:
            comp_list[cmp["key"]] = cmp
        return comp_list

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

    def audit(self, audit_settings: types.ConfigSettings, **kwargs) -> list[problem.Problem]:
        """Audits a portfolio"""
        log.info("Auditing %s", str(self))
        problems = (
            super().audit(audit_settings)
            + self._audit_empty(audit_settings)
            + self._audit_singleton(audit_settings)
            + self._audit_bg_task(audit_settings)
        )
        if not self.is_sub_portfolio():
            problems += self.permissions().audit(audit_settings)
            problems += self.audit_visibility(audit_settings)
        "write_q" in kwargs and kwargs["write_q"].put(problems)
        return problems

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Returns the portfolio representation as JSON"""
        self.refresh()
        json_data: types.ObjectJsonRepr = {"key": self.key, "name": self.name}
        if self._description:
            json_data["description"] = self._description
        subportfolios = self.sub_portfolios()
        if not self.is_sub_portfolio():
            json_data["visibility"] = self._visibility
            if pf_perms := self.permissions().export(export_settings=export_settings):
                json_data["permissions"] = util.perms_to_list(pf_perms)
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
        return util.remove_nones(util.filter_export(self.to_json(export_settings), _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False)))

    def permissions(self) -> pperms.PortfolioPermissions:
        """Returns a portfolio permissions (if toplevel) or None if sub-portfolio"""
        if self._permissions is None and not self.is_sub_portfolio():
            # No permissions for sub portfolios
            self._permissions = pperms.PortfolioPermissions(self)
        return self._permissions

    def set_permissions(self, portfolio_perms: list[types.PermissionDef]) -> None:
        """Sets a portfolio permissions described as JSON"""
        if not self.is_sub_portfolio():
            # No permissions for SVW
            self.permissions().set(portfolio_perms)

    def selection_mode(self) -> dict[str, str]:
        """Returns a portfolio selection mode"""
        if self._selection_mode is None:
            # FIXME: If portfolio is a subportfolio you must reload with sub-JSON
            self.reload(json.loads(self.get(Portfolio.API[c.GET], params={"key": self.root_portfolio.key}).text))
        return {k.lower(): v for k, v in self._selection_mode.items()}

    def has_project(self, key: str) -> bool:
        return _SELECTION_MODE_MANUAL in self._selection_mode and key in self._selection_mode[_SELECTION_MODE_MANUAL]

    def has_project_branch(self, key: str, branch: str) -> bool:
        return self.has_project(key) and branch in self._selection_mode[_SELECTION_MODE_MANUAL][key]

    def add_projects(self, projects: set[str]) -> Portfolio:
        """Adds projects main branch to a portfolio"""
        self.set_manual_mode()
        for key in projects:
            try:
                self.post("views/add_project", params={"key": self.key, "project": key}, mute=(HTTPStatus.BAD_REQUEST,))
                self._selection_mode[_SELECTION_MODE_MANUAL][key] = {c.DEFAULT_BRANCH}
            except exceptions.ObjectNotFound:
                Portfolio.CACHE.pop(self)
                raise
        return self

    def add_project_branches(self, project_key: str, branches: set[str]) -> Portfolio:
        """Adds projects branches to a portfolio"""
        log.debug("Adding all project branches %s to %s", str(branches), str(self))
        for branch in branches:
            if branch == c.DEFAULT_BRANCH:
                continue
            self.add_project_branch(project_key, branch)
        return self

    def add_project_branch(self, project_key: str, branch: str) -> bool:
        r = self.post("views/add_project_branch", params={"key": self.key, "project": project_key, "branch": branch})
        if project_key in self._selection_mode[_SELECTION_MODE_MANUAL]:
            self._selection_mode[_SELECTION_MODE_MANUAL][project_key].discard(c.DEFAULT_BRANCH)
            self._selection_mode[_SELECTION_MODE_MANUAL][project_key].add(branch)
        else:
            self._selection_mode[_SELECTION_MODE_MANUAL][project_key] = {branch}
        return r.ok

    def set_manual_mode(self) -> Portfolio:
        """Sets a portfolio to manual mode"""
        if not self._selection_mode or _SELECTION_MODE_MANUAL not in self._selection_mode:
            self.post("views/set_manual_mode", params={"portfolio": self.key})
            self._selection_mode = {_SELECTION_MODE_MANUAL: {}}
        return self

    def set_tags_mode(self, tags: list[str], branch: Optional[str] = None) -> Portfolio:
        """Sets a portfolio to tags mode"""
        self.post("views/set_tags_mode", params={"portfolio": self.key, "tags": util.list_to_csv(tags), "branch": branch})
        self._selection_mode = {_SELECTION_MODE_TAGS: tags, "branch": branch or c.DEFAULT_BRANCH}
        return self

    def set_regexp_mode(self, regexp: str, branch: Optional[str] = None) -> Portfolio:
        """Sets a portfolio to regexp mode"""
        self.post("views/set_regexp_mode", params={"portfolio": self.key, "regexp": regexp, "branch": branch})
        self._selection_mode = {_SELECTION_MODE_REGEXP: regexp, "branch": branch or c.DEFAULT_BRANCH}
        return self

    def set_remaining_projects_mode(self, branch: Optional[str] = None) -> Portfolio:
        """Sets a portfolio to remaining projects mode"""
        self.post("views/set_remaining_projects_mode", params={"portfolio": self.key, "branch": branch})
        self._selection_mode = {"rest": True, "branch": branch or c.DEFAULT_BRANCH}
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

    def set_selection_mode(self, data: dict[str, Any]) -> Portfolio:
        """Sets a portfolio selection mode"""
        params = data
        log.info("Setting %s selection mode params %s", str(self), str(params))
        branch = params.get("branch")
        if _SELECTION_MODE_MANUAL.lower() in params:
            self.set_manual_mode()
            projs_data = {p["key"]: p.get("branches", [c.DEFAULT_BRANCH]) for p in params[_SELECTION_MODE_MANUAL.lower()]}
            self.add_projects(set(projs_data.keys()))
            for p, b in projs_data.items():
                self.add_project_branches(p, b)
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
            self.post(Portfolio.API[c.UPDATE], params={"key": self.key, "name": self.name, "description": desc})
            self._description = desc
        return self

    def set_name(self, name: str) -> Portfolio:
        if name:
            self.post(Portfolio.API[c.UPDATE], params={"key": self.key, "name": name})
            self.name = name
        return self

    def add_application(self, app_key: str) -> bool:
        self.add_application_branch(app_key=app_key, branch=c.DEFAULT_BRANCH)

    def add_application_branch(self, app_key: str, branch: str = c.DEFAULT_BRANCH) -> bool:
        app = applications.Application.get_object(self.endpoint, app_key)
        if branch == c.DEFAULT_BRANCH:
            log.info("%s: Adding %s default branch", str(self), str(app))
            self.post("views/add_application", params={"portfolio": self.key, "application": app_key}, mute=(HTTPStatus.BAD_REQUEST,))
        else:
            app_branch = app_branches.ApplicationBranch.get_object(app=app, branch_name=branch)
            log.info("%s: Adding %s", str(self), str(app_branch))
            params = {"key": self.key, "application": app_key, "branch": branch}
            self.post("views/add_application_branch", params=params, mute=(HTTPStatus.BAD_REQUEST,))
        if app_key not in self._applications:
            self._applications[app_key] = []
        self._applications[app_key].append(branch)
        return True

    def add_subportfolio(self, key: str, name: Optional[str] = None, by_ref: bool = False) -> Portfolio:
        """Adds a subportfolio to a portfolio, defined by key, name and by reference option"""

        log.info("Adding sub-portfolios to %s", str(self))
        if self.is_parent_of(key):
            log.warning("Portfolio '%s' is already subportfolio of %s", key, str(self))
            return self._sub_portfolios[key]
        if by_ref:
            subp = self.add_reference_subportfolio(Portfolio.get_object(self.endpoint, key))
        else:
            subp = self.add_standard_subportfolio(key=key, name=name)
        subp.parent_portfolio = self
        subp.root_portfolio = self.root_portfolio
        return subp

    def is_sub_portfolio(self) -> bool:
        """Returns whether the portfolio is a subportfolio"""
        log.debug("%s ROOT = %s JSON = %s", str(self), str(self.root_portfolio), util.json_dump(self.sq_json))
        return self.root_portfolio is not self

    def is_toplevel(self) -> bool:
        """Returns whether the portfolio is top level"""
        return not self.is_sub_portfolio()

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
        params = self.root_portfolio.api_params() if self.root_portfolio else self.api_params()
        return self.post(Portfolio.API[c.RECOMPUTE], params=params).ok

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
                proj_key_list += [comp["refKey"] for comp in data["components"]]
            except exceptions.SonarException:
                break
            nbr_pages = util.nbr_pages(data)
            log.debug("Number of projects: %d - Page: %d/%d", nbr_projects, page, nbr_pages)
            if nbr_projects > Portfolio.MAX_SEARCH:
                log.warning("Can't collect more than %d projects from %s", Portfolio.MAX_SEARCH, str(self))
            if page >= nbr_pages or page >= Portfolio.MAX_SEARCH / Portfolio.MAX_PAGE_SIZE:
                break
        log.debug("%s projects list = %s", str(self), str(proj_key_list))
        return proj_key_list

    def update(self, data: dict[str, Any], recurse: bool) -> None:
        """Updates a portfolio with sonar-config JSON data, if recurse is true, this recurses in sub portfolios"""
        if "byReference" in data and data["byReference"]:
            log.debug("Skipping setting portfolio details, it's a reference")
            return

        log.debug("Updating details of %s with %s", str(self), str(data))
        self.set_description(data.get("description", None))
        self.set_name(data.get("name", None))
        self.set_visibility(data.get("visibility", None))
        if "permissions" in data:
            self.set_permissions(data["permissions"])
        log.debug("1.Setting root of %s is %s", str(self), str(self.root_portfolio))
        if "projectSelection" in data:
            self.set_selection_mode(data["projectSelection"])
        if "applications" in data:
            for app_key, branches in {a["key"]: a.get("branches", [c.DEFAULT_BRANCH]) for a in data["applications"]}.items():
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
        if not data.get("portfolios"):
            return
        subportfolios_json = util.list_to_dict(data["portfolios"], "key")
        for key, subp_data in subportfolios_json.items():
            log.info("Processing subportfolio %s", key)
            if subp_data.get("byReference", False):
                o_subp = Portfolio.get_object(self.endpoint, key)
                if o_subp.key not in key_list:
                    try:
                        self.add_subportfolio(o_subp.key, name=o_subp.name, by_ref=True)
                    except exceptions.SonarException as e:
                        # If the exception is that the portfolio already references, just pass
                        if "already references" not in e.message:
                            raise
            else:
                try:
                    o_subp = Portfolio.get_object(self.endpoint, key)
                except exceptions.ObjectNotFound:
                    o_subp = self.add_subportfolio(key=key, name=subp_data["name"], by_ref=False)
                o_subp.update(data=subp_data, recurse=True)

    def api_params(self, op: Optional[str] = None) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {c.READ: {"key": self.key}}
        return ops[op] if op and op in ops else ops[c.READ]


def count(endpoint: pf.Platform) -> int:
    """Counts number of portfolios"""
    return aggregations.count(api=Portfolio.API[c.SEARCH], endpoint=endpoint)


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
            return dict(sorted(search(endpoint=endpoint).items()))
        return {key: Portfolio.get_object(endpoint, key) for key in sorted(key_list)}


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, Portfolio]:
    """Search all portfolios of a platform and returns as dict"""
    check_supported(endpoint)
    return sq.search_objects(endpoint=endpoint, object_class=Portfolio, params=params)


def check_supported(endpoint: pf.Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("No API yet to export portfolios on SonarQube Cloud")
    if endpoint.edition() not in (c.SC, c.EE, c.DCE):
        raise exceptions.UnsupportedOperation(f"No portfolios in {endpoint.edition()} edition")


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings, **kwargs) -> list[object]:
    """Audits all portfolios"""
    check_supported(endpoint)
    if not audit_settings.get("audit.portfolios", True):
        log.debug("Auditing portfolios is disabled, skipping...")
        return []
    log.info("--- Auditing portfolios ---")
    problems = []
    key_regexp = kwargs.get("key_list", None) or ".*"
    for p in [o for o in get_list(endpoint).values() if not key_regexp or re.match(key_regexp, o.key)]:
        problems += p.audit(audit_settings, **kwargs)
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
    return Portfolio.get_object(endpoint, key).delete()


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> bool:
    """Imports portfolio configuration described in a JSON"""
    if "portfolios" not in config_data:
        log.info("No portfolios to import")
        return False
    check_supported(endpoint)

    log.info("Importing portfolios - pass 1: Create all toplevel portfolios")
    search(endpoint=endpoint)
    # First pass to create all top level porfolios that may be referenced
    new_key_list = util.csv_to_list(key_list)
    for data in config_data["portfolios"]:
        key = data["key"]
        if new_key_list and key not in new_key_list:
            continue
        log.info("Importing portfolio key '%s'", key)
        try:
            o = Portfolio.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            log.info("Portfolio not found, creating it")
            newdata = data.copy()
            key, name = newdata.pop("key"), newdata.pop("name")
            o = Portfolio.create(endpoint=endpoint, name=name, key=key, **newdata)
            o.parent_portfolio = None
            o.root_portfolio = o

    # Second pass to define hierarchies
    log.info("Importing portfolios - pass 2: Creating sub-portfolios")
    for data in config_data["portfolios"]:
        key = data["key"]
        if new_key_list and key not in new_key_list:
            continue
        try:
            o = Portfolio.get_object(endpoint, key)
            o.update(data=data, recurse=True)
        except exceptions.SonarException as e:
            log.error(e.message)
    return True


def search_by_name(endpoint: pf.Platform, name: str) -> types.ApiPayload:
    """Searches portfolio by name and, if found, returns data as JSON"""
    return util.search_by_name(endpoint, name, Portfolio.API[c.SEARCH], "components")


def search_by_key(endpoint: pf.Platform, key: str) -> types.ApiPayload:
    """Searches portfolio by key and, if found, returns data as JSON"""
    return util.search_by_key(endpoint, key, Portfolio.API[c.SEARCH], "components")


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports portfolios as JSON

    :param Platform endpoint: Reference to the SonarQube platform
    :param ConfigSetting export_settings: Options to use for export
    :return: Dict of portfolio settings
    :rtype: ObjectJsonRepr
    """
    write_q = kwargs.get("write_q", None)
    key_regexp = kwargs.get("key_list", ".*")
    check_supported(endpoint)

    log.info("Exporting portfolios")
    portfolio_list = {k: v for k, v in get_list(endpoint=endpoint).items() if not key_regexp or re.match(key_regexp, k)}
    nb_portfolios = len(portfolio_list)
    i = 0
    exported_portfolios = {}
    for k, p in portfolio_list.items():
        try:
            if not p.is_sub_portfolio():
                exp = p.export(export_settings)
                if write_q:
                    write_q.put(phelp.convert_portfolio_json(exp))
                else:
                    exp.pop("key")
                    exported_portfolios[k] = exp
            else:
                log.debug("Skipping export of %s, it's a standard sub-portfolio", str(p))
        except exceptions.SonarException:
            exported_portfolios[k] = {}
        i += 1
        if i % 10 == 0 or i == nb_portfolios:
            log.info("Exported %d/%d portfolios (%d%%)", i, nb_portfolios, (i * 100) // nb_portfolios)
    write_q and write_q.put(util.WRITE_END)
    return dict(sorted(exported_portfolios.items()))


def recompute(endpoint: pf.Platform) -> None:
    """Triggers recomputation of all portfolios"""
    endpoint.post(Portfolio.API["REFRESH"])


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
        o.parent_portfolio = o_parent
        o.root_portfolio = o_parent.root_portfolio
        nbr_creations += __create_portfolio_hierarchy(endpoint, subp, parent_key=key)
    return nbr_creations
