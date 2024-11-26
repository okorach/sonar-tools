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

"""Abstraction of the SonarQube User Token concept"""

from typing import Optional
import json

import datetime
import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf
import sonar.utilities as util
from sonar.util import types, cache
from sonar.audit.problem import Problem
from sonar.audit.rules import get_rule, RuleId


class UserToken(sq.SqObject):
    """
    Abstraction of the SonarQube "user token" concept
    """

    CACHE = cache.Cache()
    API_ROOT = "user_tokens"
    API_REVOKE = API_ROOT + "/revoke"
    API_SEARCH = API_ROOT + "/search"
    API_GENERATE = API_ROOT + "/generate"

    def __init__(self, endpoint: pf.Platform, login: str, json_data: types.ApiPayload, name: str = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=login)
        self.login = login  #: User login
        self.name = name  #: Token name
        if self.name is None:
            self.name = json_data.get("name", None)
        self.created_at = util.string_to_date(json_data["createdAt"]) if "createdAt" in json_data else None
        self.last_connection_date = util.string_to_date(json_data["lastConnectionDate"]) if "lastConnectionDate" in json_data else None
        self.expiration_date = util.string_to_date(json_data["expirationDate"]) if "expirationDate" in json_data else None
        self.token = json_data.get("token", None)
        log.debug("Created '%s'", str(self))

    def __str__(self) -> str:
        """
        :return: Token string representation
        :rtype: str
        """
        return f"token '{self.name}' of user '{self.login}'"

    def revoke(self) -> bool:
        """Revokes the token
        :return: Whether the revocation succeeded
        :rtype: bool
        """
        if self.name is None:
            return False
        log.info("Revoking token '%s' of user login '%s'", self.name, self.login)
        return self.post(UserToken.API_REVOKE, {"name": self.name, "login": self.login}).ok

    def audit(self, settings: types.ConfigSettings, today: Optional[datetime.datetime] = None) -> list[Problem]:
        problems = []
        mode = settings.get("audit.mode", "")
        if not today:
            today = datetime.datetime.now(datetime.timezone.utc).astimezone()
        age = util.age(self.created_at, now=today)
        if mode != "housekeeper" and not self.expiration_date:
            problems.append(Problem(get_rule(RuleId.TOKEN_WITHOUT_EXPIRATION), self, str(self), age))
        if age > settings.get("audit.tokens.maxAge", 90):
            problems.append(Problem(get_rule(RuleId.TOKEN_TOO_OLD), self, str(self), age))
        if self.last_connection_date:
            last_cnx_age = util.age(self.last_connection_date, now=today)
            if last_cnx_age > settings.get("audit.tokens.maxUnusedAge", 30):
                problems.append(Problem(get_rule(RuleId.TOKEN_UNUSED), self, str(self), last_cnx_age))
        elif mode != "housekeeper":
            problems.append(Problem(get_rule(RuleId.TOKEN_NEVER_USED), self, str(self), age))
        return problems


def search(endpoint: pf.Platform, login: str) -> list[UserToken]:
    """Searches tokens of a given user

    :param str login: login of the user
    :return: list of tokens
    :rtype: list[UserToken]
    """
    data = json.loads(endpoint.get(UserToken.API_SEARCH, {"login": login}).text)
    return [UserToken(endpoint=endpoint, login=data["login"], json_data=tk) for tk in data["userTokens"]]


def generate(name: str, endpoint: pf.Platform, login: str = None) -> UserToken:
    """Generates a new token for a given user
    :return: the generated Token object
    :rtype: Token
    """
    data = json.loads(endpoint.post(UserToken.API_GENERATE, {"name": name, "login": login}).text)
    return UserToken(endpoint=endpoint, login=data["login"], json_data=data)
