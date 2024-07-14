#
# sonar-tools
# Copyright (C) 2024 Olivier Korach
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

""" Abstraction of Sonar Application Branch """

from __future__ import annotations

import json
from http import HTTPStatus
from requests.exceptions import HTTPError
from requests.utils import quote

import sonar.logging as log
from sonar.components import Component, KEY_SEPARATOR

from sonar.applications import Application as App
from sonar.branches import Branch

from sonar import exceptions, projects
import sonar.sqobject as sq

_OBJECTS = {}

APIS = {
    "search": "api/components/search_projects",
    "get": "api/applications/show",
    "create": "api/applications/create_branch",
    "delete": "api/applications/delete_branch",
    "update": "api/applications/update_branch",
}

_NOT_SUPPORTED = "Applications not supported in community edition"


class ApplicationBranch(Component):
    """
    Abstraction of the SonarQube "application branch" concept
    """

    def __init__(self, app: App, name: str, project_branches: list[Branch], is_main: bool = False) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint=app.endpoint, key=f"{app.key} BRANCH {name}")
        self.concerned_object = app
        self.name = name
        self.is_main = is_main
        self._project_branches = project_branches
        self._last_analysis = None
        log.debug("Created object %s with uuid %s id %x", str(self), self.uuid(), id(self))
        _OBJECTS[self.uuid()] = self

    @classmethod
    def get_object(cls, app: App, branch_name: str) -> ApplicationBranch:
        """Gets an Application object from SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        if app.endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        uu = uuid(app.key, branch_name, app.endpoint.url)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        app.refresh()
        uu = uuid(app.key, branch_name, app.endpoint.url)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        raise exceptions.ObjectNotFound(app.key, f"app.Application key '{app.key}' branch {branch_name} not found")

    @classmethod
    def create(cls, app: App, name: str, project_branches: list[Branch]) -> ApplicationBranch:
        """Creates an ApplicationBranch object in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :param str name: Application name
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectAlreadyExists: If key already exist for another Application
        :return: The created Application object
        :rtype: Application
        """
        if app.endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        params = {"application": app.key, "branch": name, "project": [], "projectBranch": []}
        for branch in project_branches:
            params["project"].append(branch.concerned_object.key)
            br_name = "" if branch.is_main() else branch.name
            params["projectBranch"].append(br_name)
        try:
            app.endpoint.post(APIS["create"], params=params)
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.BAD_REQUEST:
                raise exceptions.ObjectAlreadyExists(f"app.App {app.key} branch '{name}", e.response.text)
        return ApplicationBranch(app=app, name=name, project_branches=project_branches)

    @classmethod
    def load(cls, app: App, branch_data: dict[str, str]) -> ApplicationBranch:
        project_branches = []
        for proj_data in branch_data["projects"]:
            proj = projects.Project.get_object(app.endpoint, proj_data["key"])
            project_branches.append(Branch.get_object(concerned_object=proj, branch_name=proj_data["branch"]))
        return ApplicationBranch(app=app, name=branch_data["branch"], project_branches=project_branches, is_main=branch_data.get("isMain", False))

    def __str__(self) -> str:
        return f"application '{self.concerned_object.key}' branch '{self.name}'"

    def projects_branches(self) -> list[Branch]:
        """
        :return: The list of project branches included in the application branch
        :rtype: list[Branch]
        """
        return self._project_branches

    def delete(self) -> bool:
        """Deletes an ApplicationBranch

        :return: Whether the delete succeeded
        :rtype: bool
        """
        if self.is_main:
            log.warning("Can't delete main %s, simply delete the application for that", str(self))
            return False
        return sq.delete_object(self, APIS["delete"], self.search_params(), _OBJECTS)

    def reload(self, data: dict[str, str]) -> None:
        """Reloads an App Branch from JSON data coming from Sonar"""
        super().reload(data)
        self.name = data.get("branch", "")

    def export(self) -> dict[str, str]:
        """Exports an application branch

        :param full: Whether to do a full export including settings that can't be set, defaults to False
        :type full: bool, optional
        """
        log.info("Exporting %s", str(self))
        jsondata = {"projects": {b.concerned_object.key: b.name for b in self._project_branches}}
        if self.is_main:
            jsondata["isMain"] = True
        return jsondata

    def update(self, name: str, project_branches: list[Branch]) -> bool:
        """Updates an ApplicationBranch name and project branches

        :param str name: New application branch name
        :param list[Branch] project_branches: New application project branches
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :return: whether the operation succeeded
        """
        if not name and not project_branches:
            return False
        params = self.search_params()
        params["name"] = name
        for branch in project_branches:
            params["project"].append(branch.concerned_object.key)
            br_name = "" if branch.is_main() else branch.name
            params["projectBranch"].append(br_name)
        try:
            ok = self.endpoint.post(APIS["update"], params=params).ok
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(str(self), e.response.text)
        self.name = name
        self._project_branches = project_branches
        return ok

    def update_name(self, new_name: str) -> bool:
        """Updates an Application Branch name

        :param str name: New application branch name
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :return: whether the operation succeeded
        """
        return self.update(name=new_name, project_branches=self._project_branches)

    def update_project_branches(self, new_project_branches: list[Branch]) -> bool:
        """Updates an Application list of project branches

        :param list[Branch] project_branches: New application project branches
        :raises ObjectNotFound: If ApplicationBranch not found in SonarQube
        :return: whether the operation succeeded
        """
        return self.update(name=self.name, project_branches=new_project_branches)

    def search_params(self) -> dict[str, str]:
        """Return params used to search/create/delete for that object"""
        return {"application": self.concerned_object.key, "branch": self.name}

    def uuid(self) -> str:
        """Returns the object UUID"""
        return uuid(self.concerned_object.key, self.name, self.endpoint.url)

    def component_data(self) -> dict[str, str]:
        """Returns key data"""
        return {
            "key": self.concerned_object.key,
            "name": self.concerned_object.name,
            "type": type(self.concerned_object).__name__.upper(),
            "branch": self.name,
            "url": self.url(),
        }

    def url(self) -> str:
        """Returns the URL of the Application Branch"""
        return f"{self.endpoint.url}/dashboard?id={self.concerned_object.key}&branch={quote(self.name)}"


def uuid(app_key: str, branch_name: str, url: str) -> str:
    """Returns the UUID of an object of that class"""
    return f"{app_key}{KEY_SEPARATOR}{branch_name}@{url}"


def list_from(app: App, data: dict[str, str]) -> dict[str, ApplicationBranch]:
    """Returns a dict of application branches form the pure App JSON"""
    if not data or "branches" not in data:
        return {}
    branch_list = {}
    for br in data["branches"]:
        branch_data = json.loads(app.endpoint.get(APIS["get"], params={"application": app.key, "branch": br["name"]}).text)["application"]
        branch_list[branch_data["branch"]] = ApplicationBranch.load(app, branch_data)
    return branch_list
