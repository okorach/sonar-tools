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

"""Abstraction of the SonarQube User concept"""
from __future__ import annotations
from typing import Union, Optional
import datetime as dt
import json

from http import HTTPStatus
from requests import RequestException

import sonar.logging as log
from sonar import platform as pf
from sonar.util import types, cache
import sonar.util.constants as c

from sonar import groups, sqobject, tokens, exceptions
import sonar.utilities as util
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem


_GROUPS_API_SC = "users/groups"

SETTABLE_PROPERTIES = ("login", "name", "scmAccounts", "email", "groups", "local")
USER_API = "v2/users-management/users"


class User(sqobject.SqObject):
    """
    Abstraction of the SonarQube "user" concept
    Objects of this class must be created with one of the 3 available class constructor methods. Don't use __init__
    """

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "login"
    SEARCH_RETURN_FIELD = "users"

    API = {
        c.CREATE: USER_API,
        c.UPDATE: USER_API,
        c.DELETE: USER_API,
        c.SEARCH: USER_API,
        "GROUP_MEMBERSHIPS": "v2/authorizations/group-memberships",
        "UPDATE_LOGIN": USER_API,
    }
    API_V1 = {
        c.CREATE: "users/create",
        c.UPDATE: "users/update",
        c.DELETE: "users/deactivate",
        c.SEARCH: "users/search",
        "UPDATE_LOGIN": "users/update_login",
    }
    API_SC = {
        c.SEARCH: "organizations/search_members",
    }

    def __init__(self, endpoint: pf.Platform, login: str, data: types.ApiPayload) -> None:
        """Do not use to create users, use on of the constructor class methods"""
        super().__init__(endpoint=endpoint, key=login)
        self.login = login  #: User login (str)
        self.id = None  #: SonarQube 10+ User Id (str)
        self.name = None  #: User name (str)
        self._groups = None  #: User groups (list)
        self.scm_accounts = None  #: User SCM accounts (list)
        self.email = None  #: User email (str)
        self.is_local = None  #: Whether user is local (bool) - read-only
        self.last_login = None  #: User last login (datetime) - read-only
        self.nb_tokens = None  #: Nbr of tokens (int) - read-only
        self.__tokens = None
        self.__load(data)
        log.debug("Created %s id '%s'", str(self), str(self.id))
        User.CACHE.put(self)

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> User:
        """Creates a user object from the result of a SonarQube API user search data

        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Platform
        :param data: The JSON data corresponding to the group
        :type data: dict
        :return: The user object
        :rtype: User or None
        """
        log.debug("Loading user '%s'", data["login"])
        return cls(login=data["login"], endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint: pf.Platform, login: str, name: str, is_local: bool = True, password: str = None) -> User:
        """Creates a new user in SonarQube and returns the corresponding User object

        :param Platform endpoint: Reference to the SonarQube platform
        :param str login: User login
        :param name: User name, defaults to login
        :type name: str, optional
        :param is_local: Whether the user is local, defaults to True
        :type is_local: bool, optional
        :param password: The password if user is local, defaults to login
        :type password: str, optional
        :return: The user object
        :rtype: User or None
        """
        log.debug("Creating user '%s' name '%s'", login, name)
        params = {"login": login, "local": str(is_local).lower(), "name": name}
        if is_local:
            params["password"] = password if password else login
        try:
            endpoint.post(User.api_for(c.CREATE, endpoint), params=params)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"creating user '{login}'", catch_http_errors=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(login, util.sonar_error(e.response))
        return cls.get_object(endpoint=endpoint, login=login)

    @classmethod
    def get_object(cls, endpoint: pf.Platform, login: str) -> User:
        """Creates a User object corresponding to the user with same login in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str login: User login
        :raises ObjectNotFound: if login not found
        :return: The user object
        :rtype: User
        """
        o = User.CACHE.get(login, endpoint.url)
        if o:
            return o
        log.debug("Getting user '%s'", login)
        for k, o in search(endpoint, params={"q": login}).items():
            if k == login:
                return o
        raise exceptions.ObjectNotFound(login, f"User '{login}' not found")

    @classmethod
    def get_object_by_id(cls, endpoint: pf.Platform, id: str) -> User:
        """Searches a user by its (API v2) id in SonarQube

        :param endpoint: Reference to the SonarQube platform
        :param id: User id
        :raises ObjectNotFound: if id not found
        :raises UnsuppoertedOperation: If SonarQube version < 10.4
        :return: The user object
        :rtype: User
        """
        if endpoint.version() < (10, 4, 0):
            raise exceptions.UnsupportedOperation("Get by ID is an APIv2 features, staring from SonarQube 10.4")
        log.debug("Getting user id '%s'", id)
        try:
            data = json.loads(endpoint.get(f"/api/v2/users-management/users/{id}", mute=()).text)
            return cls.load(endpoint, data)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"getting user id '{id}'", catch_http_errors=(HTTPStatus.NOT_FOUND,))
            raise exceptions.ObjectNotFound(id, f"User id '{id}' not found")

    @classmethod
    def api_for(cls, op: str, endpoint: object) -> Optional[str]:
        """Returns the API for a given operation depedning on the SonarQube version"""
        if endpoint.is_sonarcloud():
            api_to_use = User.API_SC
        elif endpoint.version() < (10, 4, 0):
            api_to_use = User.API_V1
        else:
            api_to_use = User.API
        return api_to_use[op] if op in api_to_use else api_to_use[c.LIST]

    def __str__(self) -> str:
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"user '{self.login}'"

    def __load(self, data: types.ApiPayload) -> None:
        self.name = data["name"]  #: User name
        self.scm_accounts = list(set(util.csv_to_list(data.pop("scmAccounts", None))))  #: User SCM accounts
        self.email = data.get("email", None)  #: User email
        self.is_local = data.get("local", False)  #: User is local - read-only
        self.last_login = None  #: User last login - read-only
        self.nb_tokens = None
        if self.endpoint.version() < (10, 4, 0):
            self.last_login = util.string_to_date(data.get("lastConnectionDate", None))
            self.nb_tokens = data.get("tokenCount", None)  #: Nbr of tokens - read-only
        else:
            dt1 = util.string_to_date(data.get("sonarQubeLastConnectionDate", None))
            dt2 = util.string_to_date(data.get("sonarLintLastConnectionDate", None))
            if not dt1:
                self.last_login = dt2
            elif not dt2:
                self.last_login = dt1
            else:
                self.last_login = max(dt1, dt2)
            self.id = data["id"]
        self.__tokens = None
        self._groups = self.groups(data)
        self.sq_json = data

    def groups(self, data: types.ApiPayload = None, **kwargs) -> types.KeyList:
        """Returns the list of groups of a user"""
        log.info("Getting %s groups = %s", str(self), str(self._groups))
        if self._groups is not None and kwargs.get(c.USE_CACHE, True):
            return self._groups
        if self.endpoint.is_sonarcloud():
            data = json.loads(self.get(_GROUPS_API_SC, self.api_params(c.GET)).text)["groups"]
            self._groups = [g["name"] for g in data]
        elif self.endpoint.version() < (10, 4, 0):
            if data is None:
                data = self.sq_json
            self._groups = data.get("groups", [])
            if "sonar-users" not in self._groups:
                self._groups.append("sonar-users")
            log.debug("Updated %s groups = %s", str(self), str(self._groups))
        else:
            data = json.loads(self.get(User.API["GROUP_MEMBERSHIPS"], {"userId": self.id, "pageSize": 500}).text)["groupMemberships"]
            log.debug("Groups = %s", str(data))
            self._groups = [groups.get_object_from_id(self.endpoint, g["groupId"]).name for g in data]
        self._groups = sorted(self._groups)
        return self._groups

    def refresh(self) -> User:
        """Refreshes a User object from SonarQube data

        :return:  The user itself
        """
        data = json.loads(self.get(User.api_for(c.SEARCH, self.endpoint), params={"q": self.login}).text)
        for d in data["users"]:
            if d["login"] == self.login:
                self.__load(d)
                break
        self.groups(use_cache=False)
        return self

    def url(self) -> str:
        """
        :return: the SonarQube permalink to the user, actually the global users page only
                 since this is as close as we can get to the precise user definition
        :rtype: str
        """
        return f"{self.endpoint.url}/admin/users"

    def tokens(self, **kwargs) -> list[tokens.UserToken]:
        """
        :return: The list of tokens of the user
        :rtype: list[Token]
        """
        if self.__tokens is None or not kwargs.get(c.USE_CACHE, True):
            self.__tokens = tokens.search(self.endpoint, self.login)
        return self.__tokens

    def update(self, **kwargs) -> User:
        """Updates a user with name, email, login, SCM accounts, group memberships

        :param str name: Optional, New name of the user
        :param str email: Optional, New email of the user
        :param str login: Optional, New login of the user
        :param list[str] groups: Optional, List of groups to add membership
        :param list[str] scmAccounts: Optional, List of SCM accounts
        :return: self
        """
        log.debug("Updating %s with %s", str(self), str(kwargs))
        params = self.api_params(c.UPDATE)
        my_data = vars(self)
        self.set_groups(util.csv_to_list(kwargs.get("groups", "")))
        if not self.is_local:
            return self
        params.update({k: kwargs[k] for k in ("name", "email") if k in kwargs and kwargs[k] != my_data[k]})
        if len(params) >= 1:
            api = User.api_for(c.UPDATE, self.endpoint)
            if self.endpoint.version() >= (10, 4, 0):
                self.patch(f"{api}/{self.id}", params=params)
            else:
                self.post(api, params=params)
            if "name" in params:
                self.name = kwargs["name"]
            if "email" in params:
                self.email = kwargs["email"]
        if "scmAccounts" in kwargs:
            self.set_scm_accounts(kwargs["scmAccounts"])
        if "login" in kwargs:
            new_login = kwargs["login"]
            o = User.CACHE.get(new_login, self.endpoint.url)
            if not o:
                api = User.api_for("UPDATE_LOGIN", self.endpoint)
                if self.endpoint.version() >= (10, 4, 0):
                    self.patch(f"{api}/{self.id}", params={"login": new_login})
                else:
                    self.post(api, params={**self.api_params(User.API["UPDATE_LOGIN"]), "newLogin": new_login})
                User.CACHE.pop(self)
                self.login = new_login
                User.CACHE.put(self)
        return self

    def add_to_group(self, group_name: str) -> bool:
        """Adds group membership to the user

        :param str group_name: Group to add membership
        :return: Whether operation succeeded
        :rtype: bool
        """
        try:
            group = groups.Group.read(endpoint=self.endpoint, name=group_name)
        except exceptions.ObjectNotFound:
            log.warning("Group '%s' does not exists, can't add membership for %s", group_name, str(self))
            raise
        ok = group.add_user(self)
        if ok:
            self._groups.append(group_name)
            self._groups = sorted(self._groups)
        return ok

    def remove_from_group(self, group_name: str) -> bool:
        """Removes group membership to the user

        :param str group_name: Group to remove membership
        :raises UnsupportedOperation: if trying to remove a user from built-in groups ("sonar-users" only for now)
        :raises ObjectNotFound: if group name not found
        :return: Whether operation succeeded
        :rtype: bool
        """
        group = groups.Group.read(endpoint=self.endpoint, name=group_name)
        if group.is_default():
            raise exceptions.UnsupportedOperation(f"Group '{group_name}' is built-in, can't remove membership for {str(self)}")
        ok = group.remove_user(self)
        if ok:
            self._groups.remove(group_name)
        return ok

    def deactivate(self) -> bool:
        """Deactivates the user

        :return: Whether the deactivation succeeded
        """
        return self.delete()

    def delete(self) -> bool:
        """Deactivates the user (true deleting is not possible)

        :return: Whether the deactivation succeeded
        """
        log.info("Deleting %s", str(self))
        try:
            if self.endpoint.version() >= (10, 4, 0):
                ok = self.endpoint.delete(api=f"{User.API[c.DELETE]}/{self.id}").ok
            else:
                ok = self.post(api=User.API_V1[c.DELETE], params=self.api_params(c.DELETE)).ok
            if ok:
                log.info("Removing from %s cache", str(self.__class__.__name__))
                self.__class__.CACHE.pop(self)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"deleting {str(self)}", catch_http_errors=(HTTPStatus.NOT_FOUND,))
            raise exceptions.ObjectNotFound(self.key, f"{str(self)} not found")
        return ok

    def api_params(self, op: str = c.GET) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        if self.endpoint.version() >= (10, 4, 0):
            ops = {c.GET: {}}
        else:
            ops = {c.GET: {"login": self.login}}
        return ops[op] if op in ops else ops[c.GET]

    def set_groups(self, group_list: list[str]) -> bool:
        """Set the user group membership (replaces current groups)

        :param list[str] group_list: List of groups to set membership
        :return: Whether all group membership were OK
        :rtype: bool
        """
        ok = True
        for g in list(set(group_list) - set(self.groups())):
            if g != "sonar-users":
                ok = ok and self.add_to_group(g)
        for g in list(set(self.groups()) - set(group_list)):
            if g != "sonar-users":
                ok = ok and self.remove_from_group(g)
        if not ok:
            self.refresh()
        return ok

    def add_scm_accounts(self, accounts_list: list[str]) -> bool:
        """Adds SCM accounts to the user (on top of existing ones)

        :param list[str] accounts_list: List of SCM accounts to add
        :return: Whether SCM accounts were successfully set
        :rtype: bool
        """
        if len(accounts_list) == 0:
            return False
        log.info("Adding SCM accounts '%s' to %s", str(accounts_list), str(self))
        return self.set_scm_accounts(list(set(self.scm_accounts) | set(accounts_list)))

    def set_scm_accounts(self, accounts_list: list[str]) -> bool:
        """Sets SCM accounts to the user (on top of existing ones)

        :param list[str] accounts_list: List of SCM accounts to set
        :return: Whether SCM accounts were successfully set
        :rtype: bool
        """
        log.debug("Setting SCM accounts of %s to '%s'", str(self), str(accounts_list))
        api = User.api_for(c.UPDATE, self.endpoint)
        if self.endpoint.version() >= (10, 4, 0):
            r = self.patch(f"{api}/{self.id}", params={"scmAccounts": accounts_list})
        else:
            params = self.api_params()
            params["scmAccount"] = ",".join(set(accounts_list))
            r = self.post(api, params=params)
        if not r.ok:
            self.scm_accounts = []
            return False
        self.scm_accounts = list(set(accounts_list))
        return True

    def audit(self, settings: types.ConfigSettings = None) -> list[Problem]:
        """Audits a user (user last connection date and tokens) and
        returns the list of problems found (too old)

        :param settings: Options of what to audit and thresholds to raise problems
        :type settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        log.debug("Auditing %s", str(self))
        protected_users = util.csv_to_list(settings.get("audit.tokens.neverExpire", ""))
        if self.login in protected_users:
            log.info("%s is protected, last connection date is ignored, tokens never expire", str(self))
            return []

        today = dt.datetime.now(dt.timezone.utc).astimezone()
        problems = []
        for t in self.tokens():
            problems += t.audit(settings=settings, today=today)

        if self.last_login:
            age = util.age(self.last_login, now=today)
            if age > settings.get("audit.users.maxLoginAge", 180):
                problems.append(Problem(get_rule(RuleId.USER_UNUSED), self, str(self), age))
        return problems

    def to_json(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Exports the user data (login, email, groups, SCM accounts local or not) as dict

        :return: User data
        :rtype: dict
        """
        json_data = self.sq_json.copy()
        json_data["login"] = self.login
        json_data["scmAccounts"] = self.scm_accounts
        json_data["groups"] = self.groups().copy()
        if export_settings.get("MODE", "") == "MIGRATION":
            return json_data
        if "sonar-users" in json_data["groups"]:
            json_data["groups"].remove("sonar-users")

        if not self.endpoint.is_sonarcloud() and not export_settings["FULL_EXPORT"] and not json_data["local"]:
            json_data.pop("local")
        for key in "sonarQubeLastConnectionDate", "externalLogin", "externalProvider", "id", "managed":
            json_data.pop(key, None)
        return util.filter_export(json_data, SETTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False))


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, User]:
    """Searches users in SonarQube or SonarCloud

    :param Platform endpoint: Reference to the SonarQube platform
    :param ApiParams params: list of parameters to narrow down the search
    :return: list of users
    :rtype: dict{login: User}
    """
    log.debug("Searching users with params %s", str(params))
    api_version = 2 if endpoint.version() >= (10, 4, 0) else 1
    return dict(sorted(sqobject.search_objects(endpoint=endpoint, object_class=User, params=params, api_version=api_version).items()))


def get_list(endpoint: pf.Platform) -> dict[str, User]:
    """Returns the list of users

    :params Platform endpoint: Reference to the SonarQube platform
    :return: The list of users
    """
    log.info("Listing users")
    return search(endpoint)


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports all users in JSON representation

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :return: list of users JSON representation
    :rtype: ObjectJsonRepr
    """
    log.info("Exporting users")
    write_q = kwargs.get("write_q", None)
    u_list = {}
    for u_login, u_obj in sorted(search(endpoint=endpoint).items()):
        u_list[u_login] = u_obj.to_json(export_settings)
        if write_q:
            write_q.put(u_list[u_login])
        else:
            u_list[u_login].pop("login", None)
    if write_q:
        write_q.put(util.WRITE_END)
    return u_list


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings, **kwargs) -> list[Problem]:
    """Audits all users for last login date and too old tokens

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings audit_settings: Configuration of audit
    :return: list of problems found
    :rtype: list[Problem]
    """
    if not audit_settings.get("audit.users", True):
        log.info("Auditing users is disabled, skipping...")
        return []
    log.info("--- Auditing users ---")
    problems = []
    for u in search(endpoint=endpoint).values():
        problems += u.audit(audit_settings)
    if "write_q" in kwargs:
        kwargs["write_q"].put(problems)
    return problems


def get_login_from_name(endpoint: pf.Platform, name: str) -> Union[str, None]:
    """Returns the login corresponding to name
    If more than one login matches the name, the first occurence is returned

    :param Platform endpoint: reference to the SonarQube platform
    :param str name: User name
    :return: User login or None if name not found
    :rtype: str or None
    """
    u_list = search(endpoint=endpoint, params={"q": name})
    if not u_list:
        return None
    if len(u_list) > 1:
        log.warning("More than 1 user with name '%s', will return the 1st one", name)
    return list(u_list.keys()).pop(0)


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> None:
    """Imports in SonarQube a complete users configuration described from a sonar-config JSON

    :param Platform endpoint: reference to the SonarQube platform
    :param ObjectJsonRepr config_data: the configuration to import
    :return: Nothing
    """
    if "users" not in config_data:
        log.info("No users to import")
        return
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Can't import users in SonarCloud")
    log.info("Importing users")
    for login, data in config_data["users"].items():
        data["scmAccounts"] = util.csv_to_list(data.pop("scmAccounts", ""))
        data["groups"] = util.csv_to_list(data.pop("groups", ""))
        data.pop("login", None)
        try:
            o = User.get_object(endpoint, login)
        except exceptions.ObjectNotFound:
            o = User.create(endpoint, login, data.get("name", login), data.get("local", False))
        o.update(**data)


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    return util.dict_to_list(original_json, "login")


def exists(endpoint: pf.Platform, login: str) -> bool:
    """
    :param endpoint: reference to the SonarQube platform
    :param login: user login to check
    :return: whether the group exists
    """
    return User.get_object(endpoint=endpoint, login=login) is not None
