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

from __future__ import annotations

import json
from http import HTTPStatus
from threading import Lock
from requests.exceptions import HTTPError

import sonar.logging as log
from sonar.platform import Platform as SonarCnx
from sonar.components import Component

from sonar.applications import Application as App
from sonar.branches import Branch

from sonar import exceptions, projects
import sonar.sqobject as sq

_OBJECTS = {}
_CLASS_LOCK = Lock()

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
        super().__init__(key=f"{app.key} BRANCH {name}", endpoint=app.endpoint)
        self.concerned_object = app
        self.name = name
        self.is_main = is_main
        self._project_branches = project_branches
        self._last_analysis = None
        log.debug("Created object %s with uuid %s id %x", str(self), self.uuid(), id(self))
        _OBJECTS[self.uuid()] = self

    @classmethod
    def get_object(cls, endpoint: SonarCnx, app: App, branch_name: str, project_branches: list[Branch]) -> ApplicationBranch:
        """Gets an Application object from SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        if endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        uu = uuid(app.key, branch_name, endpoint.url)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        app.refresh()
        uu = uuid(app.key, branch_name, endpoint.url)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        raise exceptions.ObjectNotFound(app.key, f"Application key '{app.key}' not found")

    @classmethod
    def create(cls, endpoint: SonarCnx, app: App, name: str, project_branches: list[Branch]) -> ApplicationBranch:
        """Creates an ApplicationBranch object in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :param str name: Application name
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectAlreadyExists: If key already exist for another Application
        :return: The created Application object
        :rtype: Application
        """
        if endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        params = {"application": app.key, "branch": name, "project": [], "projectBranch": []}
        for branch in project_branches:
            params["project"].append(branch.concerned_object.key)
            br_name = "" if branch.is_main() else branch.name
            params["projectBranch"].append(br_name)
        try:
            endpoint.post(APIS["create"], params=params)
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.BAD_REQUEST:
                raise exceptions.ObjectAlreadyExists(f"App {app.key} branch '{name}", e.response.text)
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
        :rtype: list[branches.Branch]
        """
        return self._project_branches

    def delete(self) -> None:
        """Deletes an ApplicationBranch

        :param params: Params for delete, typically None
        :type params: dict, optional
        :param exit_on_error: When to fail fast and exit if the HTTP status code is not 2XX, defaults to True
        :type exit_on_error: bool, optional
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: Whether the delete succeeded
        :rtype: bool
        """
        return sq.delete_object(self, APIS["delete"], self.search_params(), _OBJECTS)

    def export(self) -> dict[str, str]:
        """Exports an application branch

        :param full: Whether to do a full export including settings that can't be set, defaults to False
        :type full: bool, optional
        """
        log.info("Exporting %s", str(self))
        return {self.name: {b.concerned_object.key: b.name for b in self._project_branches}}

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
        """Return params used to search/create/delete for that object

        :meta private:
        """
        return {"application": self.concerned_object.key, "branch": self.name}

    def uuid(self) -> str:
        """Returns the object UUID"""
        return uuid(self.concerned_object.key, self.name, self.endpoint.url)


def uuid(app_key: str, branch_name: str, url: str) -> str:
    """Returns the UUID of an object of that class"""
    return f"{app_key} BRANCH {branch_name}@{url}"


def list_from(app: App, data: dict[str, str]) -> dict[str, ApplicationBranch]:
    """Returns a dict of application branches"""
    branch_list = {}
    log.info("Building APP Br from %s", data["branches"])
    for br in data["branches"]:
        branch_data = json.loads(app.endpoint.get(APIS["get"], params={"application": app.key, "branch": br["name"]}).text)["application"]
        branch_list[branch_data["branch"]] = ApplicationBranch.load(app, branch_data)
    return branch_list
