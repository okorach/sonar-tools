#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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
from typing import Optional, Any, TYPE_CHECKING

import concurrent.futures
from datetime import datetime, timezone, MINYEAR
import json
from requests import RequestException

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache
import sonar.util.constants as c
from sonar import groups, tokens, exceptions
import sonar.util.misc as util
import sonar.utilities as sutil
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ConfigSettings, ObjectJsonRepr, KeyList, AuditSettings

SETTABLE_PROPERTIES = ("login", "name", "email", "groups", "scmAccounts", "local")


class User(SqObject):
    """
    Abstraction of the SonarQube "user" concept
    Objects of this class must be created with one of the 3 available class constructor methods. Don't use __init__
    """

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Do not use to create users, use on of the constructor class methods"""
        self.key = data["login"]  #: User key (str)
        self.login = data["login"]  #: User login (str)
        super().__init__(endpoint, data)
        self.id: Optional[str] = None  #: SonarQube 10+ User Id (str)
        self.name: Optional[str] = None  #: User name (str)
        self._groups: Optional[list[str]] = None  #: User groups (list)
        self.scm_accounts: Optional[list[str]] = None  #: User SCM accounts (list)
        self.email: Optional[str] = None  #: User email (str)
        self.is_local: Optional[bool] = None  #: Whether user is local (bool) - read-only
        self.last_login: Optional[datetime] = None  #: User last login (datetime) - read-only
        self.nb_tokens: Optional[int] = None  #: Nbr of tokens (int) - read-only
        self.__tokens: Optional[list[tokens.UserToken]] = None
        self.__class__.CACHE.put(self)
        self.reload(data)
        log.debug("Constructed object %s id '%s'", str(self), str(self.id))

    def __str__(self) -> str:
        """Returns the string representation of the object"""
        return f"user '{self.login}'"

    @staticmethod
    def hash_payload(data: ApiPayload) -> tuple[Any, ...]:
        """Returns the hash items for a given object search payload"""
        return (data["login"],)

    def hash_object(self) -> tuple[Any, ...]:
        """Returns the hash elements for a given object"""
        return (self.login,)

    @classmethod
    def create(cls, endpoint: Platform, login: str, name: str, is_local: bool = True, password: Optional[str] = None) -> User:
        """Creates a new user in SonarQube and returns the corresponding User object

        :param endpoint: Reference to the SonarQube platform
        :param login: User login
        :param name: User name, defaults to login, optional
        :param is_local: Whether the user is local, optional, defaults to True
        :param password: The password if user is local, defaults to login, optional
        :return: The user object or None if creation failed
        """
        log.debug("Creating user '%s' name '%s'", login, name)
        params = {"login": login, "local": str(is_local).lower(), "name": name}
        if is_local:
            params["password"] = password or login
        api, _, params, ret = endpoint.api.get_details(cls, Oper.CREATE, **params)
        if ret:
            data = json.loads(endpoint.post(api, params=params).text)[ret]
        else:
            data = json.loads(endpoint.post(api, params=params).text)
        return cls.load(endpoint=endpoint, data=data)

    @classmethod
    def search(cls, endpoint: Platform, use_cache: bool = False, **search_params: Any) -> dict[str, User]:
        """Searches users in SonarQube Server or Cloud

        :param endpoint: Reference to the SonarQube platform
        :param params: list of parameters to narrow down the search
        :return: dictionary of users with login as key
        :rtype: dict{login: User}
        """
        if use_cache and len(search_params) == 0 and len(cls.CACHE.from_platform(endpoint)) > 0:
            log.debug("Searching users from cache")
            return cls.CACHE.from_platform(endpoint)
        log.info("Searching users with params %s", str(search_params))
        return cls.get_paginated(endpoint=endpoint, params=search_params)

    @classmethod
    def get_object(cls, endpoint: Platform, login: Optional[str] = None, user_id: Optional[str] = None) -> User:
        """Creates a User object corresponding to the user with same login in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param login: User login (SonarQube 10.3 and lower)
        :param id: User id (SonarQube 10.4 and above)
        :raises ObjectNotFound: if login not found
        :return: The user object
        :rtype: User
        """
        if o := cls.CACHE.get(endpoint.local_url, login):
            return o
        if user_id is not None:
            return cls.get_object_by_id(endpoint, user_id)
        log.debug("Getting user '%s'", login)
        if user := next((o for k, o in cls.search(endpoint, q=login).items() if k == login), None):
            return user
        raise exceptions.ObjectNotFound(login or user_id, f"User '{login or user_id}' not found")

    @classmethod
    def get_object_by_id(cls, endpoint: Platform, user_id: str) -> User:
        """Searches a user by its (API v2) id in SonarQube

        :param endpoint: Reference to the SonarQube platform
        :param user_id: User id
        :raises ObjectNotFound: if id not found
        :raises UnsupportedOperation: If SonarQube version < 10.4
        :return: The user object
        :rtype: User
        """
        if endpoint.version() < c.USER_API_V2_INTRO_VERSION:
            raise exceptions.UnsupportedOperation("Get by ID is an APIv2 features, staring from SonarQube 10.4")
        log.debug("Getting user id '%s'", user_id)
        api, _, params, _ = endpoint.api.get_details(cls, Oper.GET, id=user_id)
        data = json.loads(endpoint.get(api, params=params, mute=()).text)
        return cls.load(endpoint, data)

    def reload(self, data: ApiPayload) -> User:
        """Reloads a User object from SonarQube API payload

        :param data: The JSON data corresponding to the user
        :return: The user itself
        """
        super().reload(data)
        self.name = data["name"]  #: User name
        if "scmAccounts" in data:
            self.scm_accounts = list(set(util.csv_to_list(data["scmAccounts"])))  #: User SCM accounts
        if "email" in data:
            self.email = data["email"]  #: User email
        if "local" in data:
            self.is_local = data["local"]
        self.last_login = None  #: User last login - read-only
        if self.endpoint.version() < c.USER_API_V2_INTRO_VERSION:
            self.last_login = sutil.string_to_datetime(data.get("lastConnectionDate"))
            self.nb_tokens = data.get("tokenCount")  #: Nbr of tokens - read-only
        else:
            dt1 = sutil.string_to_datetime(data.get("sonarQubeLastConnectionDate"))
            dt2 = sutil.string_to_datetime(data.get("sonarLintLastConnectionDate"))
            oldest = datetime(MINYEAR, 1, 1).replace(tzinfo=timezone.utc)
            self.last_login = max(dt1 or oldest, dt2 or oldest)
            if "id" not in self.sq_json:
                log.warning("No 'id' in API payload for %s", self)
            self.id = self.sq_json.get("id")
        self.__tokens = None
        return self

    def groups(self, use_cache: bool = True, **kwargs: Any) -> list[str]:
        """Returns the list of groups of a user"""
        log.info("Getting %s groups = %s", str(self), str(self._groups))
        if self._groups is not None and use_cache:
            return self._groups
        if not self.endpoint.is_sonarcloud() and self.endpoint.version() < c.USER_API_V2_INTRO_VERSION:
            self._groups = list(set(self.sq_json.get("groups", []) + [self.endpoint.default_user_group()]))
        else:
            max_ps = self.endpoint.api.max_page_size(self, Oper.LIST_GROUPS)
            # TODO: handle pagination
            api, _, params, ret = self.endpoint.api.get_details(
                self, Oper.LIST_GROUPS, login=self.login, userId=self.id, ps=max_ps, pageSize=max_ps, name=self.name
            )
            data = json.loads(self.endpoint.get(api, params=params).text)[ret]
            log.debug("GROUP DATA = %s", util.json_dump(data))
            if self.endpoint.is_sonarcloud():
                self._groups = [g["name"] for g in data]
            else:
                self._groups = [groups.get_object_from_id(self.endpoint, g["groupId"]).name for g in data]
        self._groups = sorted(self._groups)
        return self._groups

    def refresh(self) -> User:
        """Refreshes a User object from SonarQube data

        :return:  The user itself
        """
        max_ps = self.endpoint.api.max_page_size(self, Oper.GET)
        api, _, params, ret = self.endpoint.api.get_details(self, Oper.GET, userId=self.id, q=self.login, id=self.id, ps=max_ps)
        data = json.loads(self.endpoint.get(api, params=params).text)
        if self.endpoint.version() < c.USER_API_V2_INTRO_VERSION:
            data = next((d for d in data[ret] if d["login"] == self.login), None)
            if not data:
                raise exceptions.ObjectNotFound(self.login, f"{self} not found.")
        self.reload(data)
        self.groups(use_cache=False)
        return self

    def url(self) -> str:
        """
        :return: the SonarQube permalink to the user, actually the global users page only
                 since this is as close as we can get to the precise user definition
        """
        return f"{self.base_url(local=False)}/admin/users"

    def tokens(self, **kwargs) -> list[tokens.UserToken]:
        """
        :return: The list of tokens of the user
        :rtype: list[Token]
        """
        if self.__tokens is None or not kwargs.get(c.USE_CACHE, True):
            self.__tokens = tokens.UserToken.search(self.endpoint, login=self.login)
        return self.__tokens

    def update_login(self, new_login: str) -> User:
        """Updates the login of the user

        :param new_login: The new login
        :raises ObjectAlreadyExists: if new login already exists
        :return: self
        """
        if self.__class__.CACHE.get(self.endpoint.local_url, new_login):
            raise exceptions.ObjectAlreadyExists(new_login, f"User '{new_login}' already exists")
        api, method, params, _ = self.endpoint.api.get_details(self, Oper.UPDATE, login=self.login, newLogin=new_login, id=self.id)
        if method == "PATCH":
            ok = self.endpoint.patch(api, params=params).ok
        else:
            ok = self.endpoint.post(api, params=params).ok
        if ok:
            self.__class__.CACHE.pop(self)
            self.login = new_login
            self.__class__.CACHE.put(self)
        return ok

    def update(self, **kwargs: Any) -> User:
        """Updates a user with name, email, login, SCM accounts, group memberships

        :param str name: Optional, New name of the user
        :param str email: Optional, New email of the user
        :param str login: Optional, New login of the user
        :param list[str] groups: Optional, List of groups to add membership
        :param list[str] scmAccounts: Optional, List of SCM accounts
        :return: self
        """
        log.debug("Updating %s with %s", self, kwargs)
        self.set_groups(util.csv_to_list(kwargs.get("groups", "")))
        if kwargs.get("scmAccounts"):
            self.set_scm_accounts(kwargs["scmAccounts"])
        if not self.is_local:
            return self
        if kwargs.get("login"):
            self.update_login(kwargs["login"])
        api, method, params, _ = self.endpoint.api.get_details(
            self, Oper.UPDATE, id=self.id, login=self.login, email=kwargs.get("email"), name=kwargs.get("name")
        )
        if len(params) == 0:
            return self
        if method == "PATCH":
            ok = self.endpoint.patch(api, params=params).ok
        else:
            ok = self.endpoint.post(api, params=params).ok
        if ok:
            if kwargs.get("name"):
                self.name = kwargs["name"]
            if kwargs.get("email"):
                self.email = kwargs["email"]
        return self

    def add_to_group(self, group_name: str) -> bool:
        """Adds group membership to the user

        :param str group_name: Group to add membership
        :raises UnsupportedOperation: if trying to remove a user from built-in user groups
        :raises ObjectNotFound: if group name not found
        :return: Whether operation succeeded
        """
        group = groups.Group.get_object(endpoint=self.endpoint, name=group_name)
        if group.is_default():
            raise exceptions.UnsupportedOperation(f"Group '{group_name}' is built-in, can't add membership for {self}")
        if group.add_user(self):
            self._groups = sorted(set(self._groups + [group_name]))
            return True
        return False

    def remove_from_group(self, group_name: str) -> bool:
        """Removes group membership to the user

        :param str group_name: Group to remove membership
        :raises UnsupportedOperation: if trying to remove a user from built-in groups
        :raises ObjectNotFound: if group name not found
        :return: Whether operation succeeded
        """
        group = groups.Group.get_object(endpoint=self.endpoint, name=group_name)
        if group.is_default():
            raise exceptions.UnsupportedOperation(f"Group '{group_name}' is built-in, can't remove membership for {str(self)}")
        if group.remove_user(self):
            self._groups.remove(group_name)
            return True
        return False

    def deactivate(self) -> bool:
        """Deactivates the user

        :return: Whether the deactivation succeeded
        """
        return self.delete()

    def delete(self) -> bool:
        """Deletes the user (true deleting is not possible with api v1), returns whether the operation succeeded"""
        return self.delete_object(login=self.login, id=self.id, name=self.name)

    def set_groups(self, group_list: list[str]) -> bool:
        """Set the user group membership (replaces current groups)

        :param list[str] group_list: List of groups to set membership
        :return: Whether all group membership were OK
        :rtype: bool
        """
        ok = all(self.add_to_group(g) for g in set(group_list) - set(self.groups()) if not self.endpoint.is_default_user_group(g))
        ok = ok and all(self.remove_from_group(g) for g in set(self.groups()) - set(group_list) if not self.endpoint.is_default_user_group(g))
        if not ok:
            self.refresh()
        return ok

    def add_scm_accounts(self, accounts_list: list[str]) -> bool:
        """Adds SCM accounts to the user (on top of existing ones)

        :param list[str] accounts_list: List of SCM accounts to add
        :return: Whether SCM accounts were successfully set
        """
        log.info("Adding SCM accounts '%s' to %s", str(accounts_list), str(self))
        if len(accounts_list) == 0:
            return False
        return self.set_scm_accounts(list(set(self.scm_accounts) | set(accounts_list)))

    def set_scm_accounts(self, accounts_list: list[str]) -> bool:
        """Sets SCM accounts to the user (on top of existing ones)

        :param list[str] accounts_list: List of SCM accounts to set
        :return: Whether SCM accounts were successfully set
        :rtype: bool
        """
        log.debug("Setting SCM accounts of %s to '%s'", str(self), str(accounts_list))
        if not self.is_local:
            return self
        api, method, params, _ = self.endpoint.api.get_details(self, Oper.UPDATE, id=self.id, scmAccount=accounts_list)
        if method == "PATCH":
            params = {"scmAccounts": accounts_list}
            ok = self.endpoint.patch(api, params=params).ok
        else:
            params = tuple([("login", self.login)] + [("scmAccount", v) for v in accounts_list])
            ok = self.endpoint.post(api, params=params).ok
        if not ok:
            self.scm_accounts = []
            return False
        self.scm_accounts = list(set(accounts_list))
        return True

    def __audit_active_tokens(self, settings: AuditSettings) -> list[Problem]:
        """Counts the user nbr of active (non expired) tokens and raises a problem if exceeding threshold

        :param settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        """
        log.debug("Auditing %s active tokens", str(self))
        active_tokens = [t for t in self.tokens() if not t.is_expired()]
        max_tokens = settings.get("audit.users.maxNbrOfActiveTokens", 5)
        if max_tokens != 0 and len(active_tokens) > max_tokens:
            return [Problem(get_rule(RuleId.USER_EXCESSIVE_NBR_OF_TOKENS), self, str(self), len(active_tokens), max_tokens)]
        return []

    def audit(self, settings: AuditSettings) -> list[Problem]:
        """Audits a user (user last connection date and tokens) and
        returns the list of problems found

        :param settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        """
        log.debug("Auditing %s", str(self))
        protected_users = util.csv_to_set(settings.get("audit.tokens.neverExpire", ""))
        if self.login in protected_users:
            log.info("%s is protected, last connection date is ignored, tokens never expire", str(self))
            return []

        today = datetime.now(timezone.utc).astimezone()
        problems = [p for t in self.tokens() for p in t.audit(settings=settings, today=today)]
        problems += self.__audit_active_tokens(settings=settings)
        if self.last_login and settings.get(c.AUDIT_MODE_PARAM, "") != "housekeeper":
            age = util.age(self.last_login, now=today)
            if age > settings.get("audit.users.maxLoginAge", 180):
                problems.append(Problem(get_rule(RuleId.USER_UNUSED), self, str(self), age))
        return problems

    def to_json(self, export_settings: ConfigSettings) -> ObjectJsonRepr:
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
        if self.endpoint.default_user_group() in json_data["groups"]:
            json_data["groups"].remove(self.endpoint.default_user_group())

        if not self.endpoint.is_sonarcloud() and not export_settings["FULL_EXPORT"] and not json_data["local"]:
            json_data.pop("local")
        for key in "sonarQubeLastConnectionDate", "externalLogin", "externalProvider", "id", "managed":
            json_data.pop(key, None)
        json_data = util.filter_export(json_data, SETTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False))
        return convert_user_json(json_data)


def export(endpoint: Platform, export_settings: ConfigSettings, **kwargs: Any) -> ObjectJsonRepr:
    """Exports all users in JSON representation

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :returns: list of users JSON representation
    """
    log.info("Exporting users")
    write_q = kwargs.get("write_q", None)
    u_list = []
    for _, u_obj in sorted(User.search(endpoint).items()):
        u_data = util.clean_data(u_obj.to_json(export_settings), True, True)
        u_list.append(u_data)
        if write_q:
            write_q.put(u_data)
    write_q and write_q.put(sutil.WRITE_END)
    return u_list


def audit(endpoint: Platform, audit_settings: ConfigSettings, **kwargs: Any) -> list[Problem]:
    """Audits all users for last login date and too old tokens

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings audit_settings: Configuration of audit
    :returns: list of problems found
    """
    if not audit_settings.get("audit.users", True):
        log.info("Auditing users is disabled, skipping...")
        return []
    log.info("--- Auditing users: START ---")
    problems = []
    futures, futures_map = [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="UserAudit") as executor:
        for user in User.get_paginated(endpoint=endpoint, params={}).values():
            futures.append(future := executor.submit(User.audit, user, audit_settings))
            futures_map[future] = user
        for future in concurrent.futures.as_completed(futures):
            try:
                problems += future.result(timeout=60)
            except (TimeoutError, RequestException, exceptions.SonarException) as e:
                log.error(f"Exception {str(e)} when auditing {str(futures_map[future])}.")
    "write_q" in kwargs and kwargs["write_q"].put(problems)
    log.info("--- Auditing users: END ---")
    return problems


def get_login_from_name(endpoint: Platform, name: str) -> Optional[str]:
    """Returns the login corresponding to name
    If more than one login matches the name, the first occurence is returned

    :param Platform endpoint: reference to the SonarQube platform
    :param str name: User name
    :returns: User login or None if name not found
    """
    u_list = User.search(endpoint, q=name)
    if not u_list or len(u_list) == 0:
        return None
    if len(u_list) > 1:
        log.warning("More than 1 user with name '%s', will return the 1st one", name)
    return next(iter(u_list.keys()))


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: KeyList = None) -> None:
    """Imports in SonarQube a complete users configuration described from a sonar-config JSON

    :param Platform endpoint: reference to the SonarQube platform
    :param ObjectJsonRepr config_data: the configuration to import
    :return: Nothing
    """
    if "users" not in config_data:
        log.info("No users to import")
        return
    if endpoint.is_sonarcloud():
        raise exceptions.UnsupportedOperation("Can't import users in SonarQube Cloud")
    log.info("Importing users")
    converted_data = util.list_to_dict(config_data["users"], "login")
    for login, data in converted_data.items():
        data.pop("login", None)
        try:
            o = User.get_object(endpoint, login)
        except exceptions.ObjectNotFound:
            o = User.create(endpoint, login, data.get("name", login), data.get("local", False))
        o.update(**data)


def convert_user_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts a user JSON from old to new format"""
    for k in "groups", "scmAccounts":
        if k in old_json:
            old_json[k] = util.csv_to_list(old_json[k])
    return util.order_keys(old_json, *SETTABLE_PROPERTIES)


def convert_users_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts the sonar-config users old JSON report format to the new one"""
    for k, u in old_json.items():
        old_json[k] = convert_user_json(u)
    return util.dict_to_list(old_json, "login")
