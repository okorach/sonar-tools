#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

import datetime as dt
import pytz
from sonar import groups, sqobject, tokens, exceptions
import sonar.utilities as util
from sonar.audit import rules, problem


_OBJECTS = {}

SEARCH_API = "users/search"
CREATE_API = "users/create"
UPDATE_API = "users/update"
DEACTIVATE_API = "users/deactivate"
UPDATE_LOGIN_API = "users/update_login"

SETTABLE_PROPERTIES = ("login", "name", "scmAccounts", "email", "groups", "local")


class User(sqobject.SqObject):
    """
    Abstraction of the SonarQube "user" concept
    Objects of this class must be created with one of the 3 available class constructor methods. Don't use __init__
    """

    def __init__(self, login, endpoint, data):
        """Do not use to create users, use on of the constructor class methods"""
        super().__init__(login, endpoint)
        self.login = login  #: User login (str)
        self.name = None  #: User name (str)
        self.groups = None  #: User groups (list)
        self.scm_accounts = None  #: User SCM accounts (list)
        self.email = None  #: User email (str)
        self.is_local = None  #: Whether user is local (bool) - read-only
        self.last_login = None  #: User last login (datetime) - read-only
        self.nb_tokens = None  #: Nbr of tokens (int) - read-only
        self.__tokens = None
        self.__load(data)
        util.logger.debug("Created %s", str(self))
        _OBJECTS[self.login] = self

    @classmethod
    def load(cls, endpoint, data):
        """Creates a user object from the result of a SonarQube API user search data

        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Platform
        :param data: The JSON data corresponding to the group
        :type data: dict
        :return: The user object
        :rtype: User or None
        """
        util.logger.debug("Loading user '%s'", data["login"])
        return cls(login=data["login"], endpoint=endpoint, data=data)

    @classmethod
    def create(cls, endpoint, login, name=None, is_local=True, password=None):
        """Creates a new user in SonarQube and returns the corresponding User object

        :param Platform endpoint: Reference to the SonarQube platform
        :param str login: User login
        :param name: User name, default to login
        :type name: str, optional
        :param is_local: Whether the user is local, defaults to True
        :type is_local: bool, optional
        :param password: The password if user is local, defaults to login
        :type password: str, optional
        :return: The user object
        :rtype: User or None
        """
        util.logger.debug("Creating user '%s'", login)
        params = {"login": login, "local": str(is_local).lower(), "name": name}
        if is_local:
            params["password"] = password if password else login
        endpoint.post(CREATE_API, params=params)
        return cls.get_object(endpoint=endpoint, login=login)

    @classmethod
    def get_object(cls, endpoint, login):
        """Creates a User object corresponding to the user with same login in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str login: User login
        :raise ObjectNotFound: if login not found
        :return: The user object
        :rtype: User
        """
        if login in _OBJECTS:
            return _OBJECTS[login]
        util.logger.debug("Getting user '%s'", login)
        for k, o in search(endpoint, params={"q": login}).items():
            if k == login:
                return o
        raise exceptions.ObjectNotFound(login, f"User '{login}' not found")

    def __str__(self):
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"user '{self.login}'"

    def __load(self, data):
        self.name = data["name"]  #: User name
        self.groups = data.get("groups", [])  #: User groups
        self.scm_accounts = data.pop("scmAccounts", None)  #: User SCM accounts
        self.email = data.get("email", None)  #: User email
        self.is_local = data.get("local", False)  #: User is local - read-only
        self.last_login = util.string_to_date(data.get("lastConnectionDate", None))  #: User last login - read-only
        self.nb_tokens = data.get("tokenCount", None)  #: Nbr of tokens - read-only
        self.__tokens = None
        self._json = data

    def refresh(self):
        """Refreshes a User object from SonarQube data

        :return:  Nothing
        """
        data = self.get(SEARCH_API, params={"q": self.login})
        for d in data["users"]:
            if d["login"] == self.login:
                self.__load(d)
                break

    def url(self):
        """
        :return: the SonarQube permalink to the user, actually the global users page only
                 since this is as close as we can get to the precise user definition
        :rtype: str
        """
        return f"{self.endpoint.url}/admin/users"

    def deactivate(self):
        """Deactivates the user

        :return: Whether the deactivation succeeded
        :rtype: bool
        """
        return self.post(DEACTIVATE_API, {"name": self.name, "login": self.login}).ok

    def tokens(self):
        """
        :return: The list of tokens of the user
        :rtype: list[Token]
        """
        if self.__tokens is None:
            self.__tokens = tokens.search(self.endpoint, self.login)
        return self.__tokens

    def update(self, **kwargs):
        """Updates a user with name, email, login, SCM accounts, group memberships

        :param name: New name of the user
        :type name: str, optional
        :param email: New email of the user
        :type email: str, optional
        :param login: New login of the user
        :type login: str, optional
        :param groups: List of groups to add membership
        :type groups: list[str], optional
        :param scm_accounts: List of SCM accounts
        :type scm_accounts: list[str], optional
        :return: self
        :rtype: User
        """
        util.logger.debug("Updating %s with %s", str(self), str(kwargs))
        params = {"login": self.login}
        my_data = vars(self)
        if self.is_local:
            for p in ("name", "email"):
                if p in kwargs and kwargs[p] != my_data[p]:
                    params[p] = kwargs[p]
            if len(params) > 1:
                self.post(UPDATE_API, params=params)
            self.set_scm_accounts(kwargs.get("scmAccounts", ""))
            if "login" in kwargs:
                new_login = kwargs["login"]
                if new_login not in _OBJECTS:
                    self.post(UPDATE_LOGIN_API, params={"login": self.login, "newLogin": new_login})
                    _OBJECTS.pop(self.login, None)
                    self.login = new_login
                    _OBJECTS[self.login] = self
        self.set_groups(kwargs.get("groups", ""))
        return self

    def add_to_group(self, group_name):
        """Adds group membership to the user

        :param group_name: Group to add membership
        :type group_name: str
        :return: Whether operation succeeded
        :rtype: bool
        """
        group = groups.Group.read(endpoint=self.endpoint, name=group_name)
        if not group:
            util.logger.warning("Group '%s' does not exists, can't add membership for %s", group_name, str(self))
            return False
        return group.add_user(self.login)

    def remove_from_group(self, group_name):
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

    def set_groups(self, group_list):
        """Set the user group membership (replaces current groups)

        :param group_list: List of groups to set membership
        :type group_list: list[str]
        :return: Whether all group membership were OK
        :rtype: bool
        """
        ok = True
        for g in list(set(group_list) - set(self.groups)):
            if g != "sonar-users":
                ok = ok and self.add_to_group(g)
        for g in list(set(self.groups) - set(group_list)):
            if g != "sonar-users":
                ok = ok and self.remove_from_group(g)
        if ok:
            self.groups = group_list
        else:
            self.refresh()
        return ok

    def add_scm_accounts(self, accounts_list):
        """Adds SCM accounts to the user (on top of existing ones)

        :param accounts_list: List of SCM accounts to add
        :type accounts_list: list[str]
        :return: Whether SCM accounts were successfully set
        :rtype: bool
        """
        accounts_list = util.csv_to_list(accounts_list)
        if len(accounts_list) == 0:
            return False
        util.logger.info("Adding SCM accounts '%s' to %s", str(accounts_list), str(self))
        return self.set_scm_accounts(list(set(self.scm_accounts) | set(accounts_list)))

    def set_scm_accounts(self, accounts_list):
        """Sets SCM accounts to the user (on top of existing ones)

        :param accounts_list: List of SCM accounts to set
        :type accounts_list: list[str]
        :return: Whether SCM accounts were successfully set
        :rtype: bool
        """
        accounts_list = util.csv_to_list(accounts_list)
        util.logger.debug("Setting SCM accounts of %s to '%s'", str(self), str(accounts_list))
        r = self.post(UPDATE_API, params={"login": self.login, "scmAccount": accounts_list})
        if not r.ok:
            self.scm_accounts = []
            return False
        self.scm_accounts = accounts_list
        return True

    def audit(self, settings=None):
        """Audits a user (user last connection date and tokens) and
        returns the list of problems found (too old)

        :param settings: Options of what to audit and thresholds to raise problems
        :type settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        util.logger.debug("Auditing %s", str(self))
        protected_users = util.csv_to_list(settings["audit.tokens.neverExpire"])
        if self.login in protected_users:
            util.logger.info("%s is protected, last connection date is ignored, tokens never expire", str(self))
            return []

        today = dt.datetime.today().replace(tzinfo=pytz.UTC)
        problems = []
        for t in self.tokens():
            age = abs((today - t.created_at).days)
            if age > settings["audit.tokens.maxAge"]:
                rule = rules.get_rule(rules.RuleId.TOKEN_TOO_OLD)
                msg = rule.msg.format(str(t), age)
                problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))
            if t.last_connection_date is None and age > settings["audit.tokens.maxUnusedAge"]:
                rule = rules.get_rule(rules.RuleId.TOKEN_NEVER_USED)
                msg = rule.msg.format(str(t), age)
                problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))
            if t.last_connection_date is None:
                continue
            last_cnx_age = abs((today - t.last_connection_date).days)
            if last_cnx_age > settings["audit.tokens.maxUnusedAge"]:
                rule = rules.get_rule(rules.RuleId.TOKEN_UNUSED)
                msg = rule.msg.format(str(t), last_cnx_age)
                problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))

        if self.last_login:
            age = abs((today - self.last_login).days)
            if age > settings["audit.users.maxLoginAge"]:
                rule = rules.get_rule(rules.RuleId.USER_UNUSED)
                msg = rule.msg.format(str(self), age)
                problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))
        return problems

    def to_json(self, full=False):
        """Exports the user data (login, email, groups, SCM accounts local or not) as dict

        :return: User data
        :rtype: dict
        """
        json_data = self._json.copy()
        scm = self.scm_accounts
        json_data["scmAccounts"] = util.list_to_csv(scm) if scm else None
        my_groups = self.groups.copy()
        my_groups.remove("sonar-users")
        json_data["groups"] = util.list_to_csv(my_groups, ", ", True)
        if not full and not json_data["local"]:
            json_data.pop("local")
        return util.remove_nones(util.filter_export(json_data, SETTABLE_PROPERTIES, full))


def search(endpoint, params=None):
    """Searches users in SonarQube

    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param params: list of parameters to narrow down the search
    :type params: dict
    :return: list of projects
    :rtype: dict{login: User}
    """
    util.logger.debug("Searching users with params %s", str(params))
    return sqobject.search_objects(api=SEARCH_API, params=params, returned_field="users", key_field="login", object_class=User, endpoint=endpoint)


def export(endpoint, full=False):
    """Exports all users as dict

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param full: Whether to export all settings including those useless for re-import, defaults to False
    :type full: bool, optional
    :return: list of projects
    :rtype: dict{key: Project}
    """
    util.logger.info("Exporting users")
    u_list = {}
    for u_login, u_obj in search(endpoint=endpoint).items():
        u_list[u_login] = u_obj.to_json(full)
        u_list[u_login].pop("login", None)
    return u_list


def audit(endpoint, audit_settings):
    """Audits all users for last login date and too old tokens

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param audit_settings: Configuration of audit
    :type audit_settings: dict
    :return: list of problems found
    :rtype: list[Problem]
    """
    if not audit_settings["audit.users"]:
        util.logger.info("Auditing users is disabled, skipping...")
        return []
    util.logger.info("--- Auditing users ---")
    problems = []
    for _, u in search(endpoint=endpoint).items():
        problems += u.audit(audit_settings)
    return problems


def get_login_from_name(name, endpoint):
    """Returns the login corresponding to name
    If more than one login matches the name, the first occurence is returned

    :param name: User name
    :type name: str
    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :return: User login or None if name not found
    :rtype: str or None
    """
    u_list = search(endpoint=endpoint, params={"q": name})
    if not u_list:
        return None
    if len(u_list) > 1:
        util.logger.warning("More than 1 user with name '%s', will return the 1st one", name)
    return list(u_list.keys()).pop(0)


def import_config(endpoint, config_data):
    """Imports in SonarQube a complete users configuration described from a JSON

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param config_data: the configuration to import
    :type config_data: dict
    :return: Nothing
    """
    if "users" not in config_data:
        util.logger.info("No users to import")
        return
    util.logger.info("Importing users")
    for login, data in config_data["users"].items():
        data = _decode(data)
        data.pop("login", None)
        try:
            o = User.get_object(endpoint, login)
        except exceptions.ObjectNotFound:
            o = User.create(endpoint, login, data.get("name", login), data.get("local", False))
        o.update(**data)


def _decode(data):
    data["scm_accounts"] = util.csv_to_list(data.pop("scmAccounts", ""))
    data["groups"] = util.csv_to_list(data.pop("groups", ""))
    return data
