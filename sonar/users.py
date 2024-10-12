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

from __future__ import annotations
from queue import Queue
from typing import Union, Optional
import datetime as dt
import json

import sonar.logging as log
from sonar import platform as pf
from sonar.util import types
from sonar import groups, sqobject, tokens, exceptions
import sonar.utilities as util
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem


_OBJECTS = {}


CREATE_API = "users/create"
UPDATE_API = "users/update"
DEACTIVATE_API = "users/deactivate"
UPDATE_LOGIN_API = "users/update_login"
_GROUPS_API_SC = "users/groups"
_GROUPS_API_V2 = "v2/authorizations/group-memberships"

SETTABLE_PROPERTIES = ("login", "name", "scmAccounts", "email", "groups", "local")


class User(sqobject.SqObject):
    """
    Abstraction of the SonarQube "user" concept
    Objects of this class must be created with one of the 3 available class constructor methods. Don't use __init__
    """

    SEARCH_API = "users/search"
    SEARCH_API_V2 = "v2/users-management/users"
    SEARCH_KEY_FIELD = "login"
    SEARCH_RETURN_FIELD = "users"

    SEARCH_API_SC = "organizations/search_members"

    def __init__(self, endpoint: pf.Platform, login: str, data: types.ApiPayload) -> None:
        """Do not use to create users, use on of the constructor class methods"""
        super().__init__(endpoint=endpoint, key=login)
        self.login = login  #: User login (str)
        self._id = None  #: SonarQube 10+ User Id (str)
        self.name = None  #: User name (str)
        self._groups = None  #: User groups (list)
        self.scm_accounts = None  #: User SCM accounts (list)
        self.email = None  #: User email (str)
        self.is_local = None  #: Whether user is local (bool) - read-only
        self.last_login = None  #: User last login (datetime) - read-only
        self.nb_tokens = None  #: Nbr of tokens (int) - read-only
        self.__tokens = None
        self.__load(data)
        log.debug("Created %s", str(self))
        _OBJECTS[self.uuid()] = self

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
    def create(cls, endpoint: pf.Platform, login: str, name: str = None, is_local: bool = True, password: str = None) -> User:
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
        log.debug("Creating user '%s'", login)
        params = {"login": login, "local": str(is_local).lower(), "name": name}
        if is_local:
            params["password"] = password if password else login
        endpoint.post(CREATE_API, params=params)
        return cls.get_object(endpoint=endpoint, login=login)

    @classmethod
    def get_object(cls, endpoint: pf.Platform, login: str) -> User:
        """Creates a User object corresponding to the user with same login in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str login: User login
        :raise ObjectNotFound: if login not found
        :return: The user object
        :rtype: User
        """
        uid = sqobject.uuid(login, endpoint.url)
        if uid in _OBJECTS:
            return _OBJECTS[uid]
        log.debug("Getting user '%s'", login)
        for k, o in search(endpoint, params={"q": login}).items():
            if k == login:
                return o
        raise exceptions.ObjectNotFound(login, f"User '{login}' not found")

    @classmethod
    def get_search_api(cls, endpoint: object) -> Optional[str]:
        api = cls.SEARCH_API
        if endpoint.is_sonarcloud():
            api = cls.SEARCH_API_SC
        elif endpoint.version() >= (10, 4, 0):
            api = cls.SEARCH_API_V2
        return api

    def __str__(self) -> str:
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"user '{self.login}'"

    def __load(self, data: types.ApiPayload) -> None:
        self.name = data["name"]  #: User name
        self.scm_accounts = data.pop("scmAccounts", None)  #: User SCM accounts
        self.email = data.get("email", None)  #: User email
        self.is_local = data.get("local", False)  #: User is local - read-only
        self.last_login = None  #: User last login - read-only
        self.nb_tokens = None
        if self.endpoint.version() < (10, 4, 0):
            self.last_login = util.string_to_date(data.get("lastConnectionDate", None))
            self.nb_tokens = data.get("tokenCount", None)  #: Nbr of tokens - read-only
        else:
            dt1 = util.string_to_date(data.get("sonarQubeLastConnectionDate", None))
            dt2 = util.string_to_date(data.get("sonarQubeLastConnectionDate", None))
            if not dt1:
                self.last_login = dt2
            elif not dt2:
                self.last_login = dt1
            else:
                self.last_login = max(dt1, dt2)
            self._id = data["id"]
        self.__tokens = None
        self._groups = self.groups(data)  #: User groups
        self._json = data

    def groups(self, data: types.ApiPayload = None) -> types.KeyList:
        """Returns the list of groups of a user"""
        if self._groups is not None:
            return self._groups
        if self.endpoint.is_sonarcloud():
            data = json.loads(self.get(_GROUPS_API_SC, {"login": self.key}).text)["groups"]
            self._groups = [g["name"] for g in data]
        elif self.endpoint.version() < (10, 4, 0):
            self._groups = data.get("groups", [])  #: User groups
        else:
            data = json.loads(self.get(_GROUPS_API_V2, {"userId": self._id, "pageSize": 500}).text)["groupMemberships"]
            util.log.debug("Groups = %s", str(data))
            self._groups = [groups.get_object_from_id(self.endpoint, g["groupId"]).name for g in data]
        return self._groups

    def refresh(self) -> User:
        """Refreshes a User object from SonarQube data

        :return:  The user itself
        """
        if self.endpoint.is_sonarcloud():
            api = User.SEARCH_API_SC
        elif self.endpoint.version() < (10, 4, 0):
            api = User.SEARCH_API
        else:
            api = User.SEARCH_API_V2
        data = self.get(api, params={"q": self.login})
        for d in data["users"]:
            if d["login"] == self.login:
                self.__load(d)
                break
        return self

    def url(self) -> str:
        """
        :return: the SonarQube permalink to the user, actually the global users page only
                 since this is as close as we can get to the precise user definition
        :rtype: str
        """
        return f"{self.endpoint.url}/admin/users"

    def deactivate(self) -> bool:
        """Deactivates the user

        :return: Whether the deactivation succeeded
        :rtype: bool
        """
        return self.post(DEACTIVATE_API, {"name": self.name, "login": self.login}).ok

    def tokens(self) -> list[tokens.UserToken]:
        """
        :return: The list of tokens of the user
        :rtype: list[Token]
        """
        if self.__tokens is None:
            self.__tokens = tokens.search(self.endpoint, self.login)
        return self.__tokens

    def update(self, **kwargs) -> User:
        """Updates a user with name, email, login, SCM accounts, group memberships

        :param name: New name of the user
        :type name: str, optional
        :param email: New email of the user
        :type email: str, optional
        :param login: New login of the user
        :type login: str, optional
        :param KeyList groups: List of groups to add membership
        :param scm_accounts: List of SCM accounts
        :type scm_accounts: list[str], optional
        :return: self
        :rtype: User
        """
        log.debug("Updating %s with %s", str(self), str(kwargs))
        params = {"login": self.login}
        my_data = vars(self)
        if self.is_local:
            for p in ("name", "email"):
                if p in kwargs and kwargs[p] != my_data[p]:
                    params[p] = kwargs[p]
            if len(params) > 1:
                self.post(UPDATE_API, params=params)
            self.set_scm_accounts(kwargs.get("scmAccounts", None))
            if "login" in kwargs:
                new_login = kwargs["login"]
                if new_login not in _OBJECTS:
                    self.post(UPDATE_LOGIN_API, params={"login": self.login, "newLogin": new_login})
                    _OBJECTS.pop(self.uuid(), None)
                    self.login = new_login
                    _OBJECTS[self.uuid()] = self
        self.set_groups(kwargs.get("groups", ""))
        return self

    def add_to_group(self, group_name: str) -> bool:
        """Adds group membership to the user

        :param str group_name: Group to add membership
        :return: Whether operation succeeded
        :rtype: bool
        """
        group = groups.Group.read(endpoint=self.endpoint, name=group_name)
        if not group:
            log.warning("Group '%s' does not exists, can't add membership for %s", group_name, str(self))
            return False
        return group.add_user(self.login)

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
        return group.remove_user(self.login)

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
        if ok:
            self._groups = group_list
        else:
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
        r = self.post(UPDATE_API, params={"login": self.login, "scmAccount": ",".join(accounts_list)})
        if not r.ok:
            self.scm_accounts = []
            return False
        self.scm_accounts = accounts_list
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
            age = util.age(t.created_at, now=today)
            if age > settings.get("audit.tokens.maxAge", 90):
                problems.append(Problem(get_rule(RuleId.TOKEN_TOO_OLD), t, str(t), age))
            if t.last_connection_date is None and age > settings.get("audit.tokens.maxUnusedAge", 30):
                problems.append(Problem(get_rule(RuleId.TOKEN_NEVER_USED), t, str(t), age))
            if t.last_connection_date is None:
                continue
            last_cnx_age = util.age(t.last_connection_date, now=today)
            if last_cnx_age > settings.get("audit.tokens.maxUnusedAge", 30):
                problems.append(Problem(get_rule(RuleId.TOKEN_UNUSED), t, str(t), last_cnx_age))

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
        json_data = self._json.copy()
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
        return util.filter_export(json_data, SETTABLE_PROPERTIES, export_settings["FULL_EXPORT"])


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, User]:
    """Searches users in SonarQube or SonarCloud

    :param Platform endpoint: Reference to the SonarQube platform
    :param ApiParams params: list of parameters to narrow down the search
    :return: list of users
    :rtype: dict{login: User}
    """
    log.debug("Searching users with params %s", str(params))
    return sqobject.search_objects(endpoint=endpoint, object_class=User, params=params)


def export(
    endpoint: pf.Platform, export_settings: types.ConfigSettings, key_list: Optional[types.KeyList] = None, write_q: Optional[Queue] = None
) -> types.ObjectJsonRepr:
    """Exports all users in JSON representation

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :param KeyList key_list: Unused
    :return: list of users JSON representation
    :rtype: ObjectJsonRepr
    """
    log.info("Exporting users")
    u_list = {}
    for u_login, u_obj in sorted(search(endpoint=endpoint).items()):
        u_list[u_login] = u_obj.to_json(export_settings)
        if write_q:
            write_q.put(u_list[u_login])
        else:
            u_list[u_login].pop("login", None)
    if write_q:
        write_q.put(None)
    return u_list


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings) -> list[Problem]:
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
    for _, u in search(endpoint=endpoint).items():
        problems += u.audit(audit_settings)
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
        data["scm_accounts"] = util.csv_to_list(data.pop("scmAccounts", ""))
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
