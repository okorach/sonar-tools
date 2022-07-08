#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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
from sonar import groups, sqobject, tokens
import sonar.utilities as util
from sonar.audit import rules, problem


_USERS = {}

_SEARCH_API = "users/search"
_CREATE_API = "users/create"
_UPDATE_API = "users/update"
_DEACTIVATE_API = "users/deactivate"
_ADD_GROUP_API = "user_groups/add_user"
_UPDATE_LOGIN_API = "users/update_login"

_IMPORTABLE_PROPERTIES = ("login", "name", "scmAccounts", "email", "groups", "local")


class User(sqobject.SqObject):
    """
    Abstraction of the SonarQube "user" concept
    """

    def __init__(self, login, endpoint, data=None, create_data=None):
        super().__init__(login, endpoint)
        self.login = login
        self.groups = None
        self.scmAccounts = None
        if create_data is not None:
            util.logger.info("Creating %s", str(self))
            params = {"login": login}
            local = create_data.get("local", False)
            params["local"] = str(local).lower()
            if local:
                params["password"] = create_data.get("password", login)
            for p in ("name", "email"):
                if p in create_data:
                    params[p] = create_data[p]
            self.post(_CREATE_API, params=params)
            self.add_groups(create_data.get("groups", None))
            self.add_scm_accounts(create_data.get("scmAccounts", ""))
            data = create_data
        elif data is None:
            for d in search(endpoint, params={"q": login}):
                if d["login"] == login:
                    data = d
                    break
        if create_data is None:
            util.logger.debug("Sync'ing %s", str(self))

        self._json = data
        self.name = data.get("name", None)
        self.is_local = data.get("local", False)
        self.email = data.get("email", None)
        self.scmAccounts = data.pop("scmAccounts", None)
        self.groups = data.get("groups", None)
        self.nb_tokens = data.get("tokenCount", None)
        self.tokens_list = None
        self._last_login_date = None
        util.logger.debug("Created %s", str(self))
        _USERS[self.login] = self

    def __str__(self):
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"user '{self.login}'"

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
        return self.post(_DEACTIVATE_API, {"name": self.name, "login": self.login}).ok

    def tokens(self):
        """
        :return: The list of tokens of the user
        :rtype: list[Token]
        """
        if self.tokens_list is None:
            self.tokens_list = tokens.search(self.endpoint, self.login)
        return self.tokens_list

    def last_login(self):
        """
        :return: The last login date of the user
        :rtype: datetime
        """
        if self._last_login_date is None and "lastConnectionDate" in self._json:
            self._last_login_date = util.string_to_date(self._json["lastConnectionDate"])
        return self._last_login_date

    def update(self, **kwargs):
        """Updates a user with name, email, login, group memberships

        :param name: New name of the user
        :type name: str, optional
        :param email: New email of the user
        :type email: str, optional
        :param login: New login of the user
        :type login: str, optional
        :param groups: List of groups to add membership
        :type groups: list[str]
        :return: self
        :rtype: User
        """
        util.logger.debug("Updating %s with %s", str(self), str(kwargs))
        params = {"login": self.login}
        my_data = vars(self)
        for p in ("name", "email"):
            if p in kwargs and kwargs[p] != my_data[p]:
                params[p] = kwargs[p]
        if len(params) > 1:
            self.post(_UPDATE_API, params=params)
        self.add_scm_accounts(kwargs.get("scmAccounts", ""))
        if "login" in kwargs:
            new_login = kwargs["login"]
            if new_login not in _USERS:
                self.post(_UPDATE_LOGIN_API, params={"login": self.login, "newLogin": new_login})
                _USERS.pop(self.login, None)
                self.login = new_login
                _USERS[self.login] = self
        self.add_groups(kwargs.get("groups", ""))
        return self

    def add_groups(self, group_list):
        """Adds groups membership to the user

        :param group_list: List of groups to add membership
        :type group_list: list[str]
        :return: Whether all group membership additions were OK
        :rtype: bool
        """
        ok = True
        if self.groups is None:
            self.groups = ["sonar-users"]
        for g in util.csv_to_list(group_list):
            if g in self.groups:
                continue
            if not groups.exists(g, self.endpoint):
                util.logger.warning("Group '%s' does not exists, can't add membership for %s", g, str(self))
                ok = False
                continue
            util.logger.debug("Adding group '%s' to %s", g, str(self))
            ok = ok and self.post(_ADD_GROUP_API, params={"login": self.login, "name": g}).ok
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
        if self.scmAccounts is None:
            self.scmAccounts = []
        new_scms = list(set(self.scmAccounts) | set(accounts_list))
        if len(new_scms) > len(self.scmAccounts):
            util.logger.debug("Setting SCM accounts '%s' to %s", str(new_scms), str(self))
            r = self.post(_UPDATE_API, params={"login": self.login, "scmAccount": new_scms})
            if not r.ok:
                return False
            self.scmAccounts = new_scms
        else:
            util.logger.debug("No SCM accounts to add to %s current is %s", str(self), str(self.scmAccounts))
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

        cnx = self.last_login()
        if cnx is not None:
            age = abs((today - cnx).days)
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
        scm = self.scmAccounts
        json_data["scmAccounts"] = util.list_to_csv(scm) if scm else None
        my_groups = self.groups.copy()
        my_groups.remove("sonar-users")
        json_data["groups"] = util.list_to_csv(my_groups, ", ", True)
        if not full and not json_data["local"]:
            json_data.pop("local")
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))


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
    return sqobject.search_objects(api=_SEARCH_API, params=params, returned_field="users", key_field="login", object_class=User, endpoint=endpoint)


def export(endpoint, full=False):
    """Exports all users as dict

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Env
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


def create(login, endpoint=None, **kwargs):
    util.logger.debug("Creating user '%s' with data %s", login, str(kwargs))
    o = get_object(login=login, endpoint=endpoint)
    if o is None:
        o = User(login=login, endpoint=endpoint, create_data=kwargs)
    return o


def create_or_update(endpoint, login, **kwargs):
    o = get_object(endpoint=endpoint, login=login)
    if o is None:
        util.logger.debug("User '%s' does not exist, creating...", login)
        return create(login, endpoint, **kwargs)
    else:
        return o.update(**kwargs)


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
        data.pop("login", None)
        create_or_update(endpoint, login, **data)


def get_object(endpoint, login):
    """Returns the User object corresponding to a particular login
    Returns None if login is not found

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param login: the configuration to import
    :type login: dict
    :return: Nothing
    """
    if len(_USERS) == 0:
        search(endpoint)
    return _USERS.get(login, None)
