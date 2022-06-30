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
"""

    Abstraction of the SonarQube "user" concept

"""

import datetime as dt
import pytz
from sonar import groups, sqobject
import sonar.utilities as util
import sonar.user_tokens as tok
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
            self.add_scm_accounts(create_data.get("scmAccounts", None))
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
        _USERS[_uuid(self.login)] = self

    def __str__(self):
        return f"user '{self.login}'"

    def url(self):
        return f"{self.endpoint.url}/admin/users"

    def deactivate(self):
        self.post(_DEACTIVATE_API, {"name": self.name, "login": self.login})
        return True

    def tokens(self):
        if self.tokens_list is None:
            self.tokens_list = tok.search(self.endpoint, self.login)
        return self.tokens_list

    def last_login_date(self):
        if self._last_login_date is None and "lastConnectionDate" in self._json:
            self._last_login_date = util.string_to_date(self._json["lastConnectionDate"])
        return self._last_login_date

    def update(self, **kwargs):
        util.logger.debug("Updating %s with %s", str(self), str(kwargs))
        params = {"login": self.login}
        my_data = vars(self)
        for p in ("name", "email"):
            if p in kwargs and kwargs[p] != my_data[p]:
                params[p] = kwargs[p]
        if len(params) > 1:
            self.post(_UPDATE_API, params=params)
        self.add_scm_accounts(kwargs.get("scmAccounts", None))
        if "login" in kwargs:
            new_login = kwargs["login"]
            if new_login not in _USERS:
                self.post(_UPDATE_LOGIN_API, params={"login": self.login, "newLogin": new_login})
                _USERS.pop(self.login, None)
                self.login = new_login
                _USERS[self.login] = self
        self.add_groups(kwargs.get("groups", None))
        return self

    def add_groups(self, group_list):
        if group_list is None:
            return
        if isinstance(group_list, str):
            group_list = util.csv_to_list(group_list)
        for g in group_list:
            if self.groups is None:
                self.groups = []
            if g in self.groups:
                continue
            if g == "sonar-users":
                self.groups.append(g)
                continue
            if not groups.exists(g, self.endpoint):
                util.logger.warning("Group '%s' does not exists, can't add membership for %s", g, str(self))
                continue
            util.logger.debug("Adding group '%s' to %s", g, str(self))
            self.post(_ADD_GROUP_API, params={"login": self.login, "name": g})

    def add_scm_accounts(self, accounts_list):
        if accounts_list is None:
            return
        if isinstance(accounts_list, str):
            accounts_list = util.csv_to_list(accounts_list)
        if len(accounts_list) == 0:
            return
        util.logger.info("Adding SCM accounts '%s' to %s", str(accounts_list), str(self))
        if self.scmAccounts is None:
            self.scmAccounts = []
        new_scms = self.scmAccounts.copy()
        for a in accounts_list:
            if a not in self.scmAccounts:
                new_scms.append(a)
        if len(new_scms) > len(self.scmAccounts):
            util.logger.debug("Setting SCM accounts '%s' to %s", str(new_scms), str(self))
            self.post(_UPDATE_API, params={"login": self.login, "scmAccount": new_scms})
            self.scmAccounts = new_scms
        else:
            util.logger.debug("No SCM accounts to add to %s current is %s", str(self), str(self.scmAccounts))

    def audit(self, settings=None):
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

        cnx = self.last_login_date()
        if cnx is not None:
            age = abs((today - cnx).days)
            if age > settings["audit.users.maxLoginAge"]:
                rule = rules.get_rule(rules.RuleId.USER_UNUSED)
                msg = rule.msg.format(str(self), age)
                problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))
        return problems

    def to_json(self, full=False):
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
    return sqobject.search_objects(
        api=_SEARCH_API,
        params=params,
        returned_field="users",
        key_field="login",
        object_class=User,
        endpoint=endpoint,
    )


def get_list(endpoint, params=None):
    util.logger.info("Listing users")
    return search(params=params, endpoint=endpoint)


def export(endpoint, full=False):
    util.logger.info("Exporting users")
    u_list = {}
    for u_login, u_obj in search(endpoint=endpoint).items():
        u_list[u_login] = u_obj.to_json(full)
        u_list[u_login].pop("login", None)
    return u_list


def audit(audit_settings, endpoint=None):
    if not audit_settings["audit.users"]:
        util.logger.info("Auditing users is disabled, skipping...")
        return []
    util.logger.info("--- Auditing users ---")
    problems = []
    for _, u in search(endpoint=endpoint).items():
        problems += u.audit(audit_settings)
    return problems


def get_login_from_name(name, endpoint):
    u_list = search(params={"q": name}, endpoint=endpoint)
    if not u_list:
        return None
    if len(u_list) > 1:
        util.logger.warning("More than 1 user with name '%s', will return the 1st one", name)
    return list(u_list.keys()).pop(0)


def update(login, endpoint, **kwargs):
    o = get_object(login=login, endpoint=endpoint)
    if o is None:
        util.logger.warning("Can't update user '%s', it does not exists", login)
        return None
    return o.update(**kwargs)


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
        return update(login, endpoint, **kwargs)


def import_config(endpoint, config_data):
    if "users" not in config_data:
        util.logger.info("No users to import")
        return
    util.logger.info("Importing users")
    for login, data in config_data["users"].items():
        data.pop("login", None)
        create_or_update(endpoint, login, **data)


def get_object(login, endpoint=None):
    if len(_USERS) == 0:
        get_list(endpoint)
    u = _uuid(login)
    if u not in _USERS:
        return None
    return _USERS[u]


def _uuid(login):
    return login
