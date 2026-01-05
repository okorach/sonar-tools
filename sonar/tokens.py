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

"""Abstraction of the SonarQube User Token concept"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

import json
import datetime as dt

from sonar.sqobject import SqObject
import sonar.logging as log
import sonar.utilities as sutil
import sonar.util.misc as util
from sonar.util import cache, constants as c
from sonar.audit.problem import Problem
from sonar.audit.rules import get_rule, RuleId
from sonar.api.manager import ApiOperation as Oper
from sonar.api.manager import ApiManager as Api

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ConfigSettings


class UserToken(SqObject):
    """Abstraction of the SonarQube "user token" concept"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, login: str, json_data: ApiPayload, name: Optional[str] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=login)
        self.login = login  #: User login
        self.name = name  #: Token name
        self.sq_json = json_data  #: JSON data returned by the API
        if self.name is None:
            self.name = json_data.get("name", None)
        self.created_at = sutil.string_to_date(json_data["createdAt"]) if "createdAt" in json_data else None
        self.last_connection_date = sutil.string_to_date(json_data["lastConnectionDate"]) if "lastConnectionDate" in json_data else None
        self.expiration_date: Optional[dt.datetime] = sutil.string_to_date(json_data["expirationDate"]) if "expirationDate" in json_data else None
        self.token = json_data.get("token", None)
        log.debug("Constructed '%s'", str(self))

    @classmethod
    def create(cls, endpoint: Platform, login: str, name: str) -> UserToken:
        """Creates a user token in SonarQube

        :param endpoint: Reference to the SonarQube platform
        :param login: User for which the token must be created
        :param name: Token name
        """
        api, _, params, _ = Api(cls, Oper.CREATE, endpoint).get_all(name=name, login=login)
        data = json.loads(endpoint.post(api, params).text)
        return UserToken(endpoint=endpoint, login=data["login"], json_data=data, name=name)

    def __str__(self) -> str:
        """
        :return: Token string representation
        """
        return f"token '{self.name}' of user '{self.login}'"

    @classmethod
    def search(cls, endpoint: Platform, login: str) -> list[UserToken]:
        """Searches tokens of a given user

        :param login: login of the user
        :return: list of tokens
        """
        api, _, params, ret = Api(cls, Oper.SEARCH, endpoint).get_all(login=login)
        data = json.loads(endpoint.get(api, params).text)
        return [cls(endpoint=endpoint, login=data["login"], json_data=tk) for tk in data[ret]]

    def revoke(self) -> bool:
        """Revokes the token
        :return: Whether the revocation succeeded
        """
        return self.delete_object(name=self.name, login=self.login)

    def api_params(self, operation: Oper = Oper.GET) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {Oper.GET: {"name": self.name, "login": self.login}}
        return ops[operation] if operation in ops else ops[Oper.GET]

    def is_expired(self) -> bool:
        """Returns True if the token is expired, False otherwise"""
        return self.sq_json.get("isExpired", False) or (
            self.expiration_date is not None and self.expiration_date < dt.datetime.now(dt.timezone.utc).astimezone()
        )

    def audit(self, settings: ConfigSettings, today: Optional[dt.datetime] = None) -> list[Problem]:
        """Audits a token

        :return: List of problem found
        """
        if self.is_expired():
            return [Problem(get_rule(RuleId.TOKEN_EXPIRED), self, str(self))]
        problems = []
        mode = settings.get(c.AUDIT_MODE_PARAM, "")
        max_age = settings.get("audit.tokens.maxAge", 90)
        if not today:
            today = dt.datetime.now(dt.timezone.utc).astimezone()
        age = util.age(self.created_at, now=today)
        if mode != "housekeeper" and not self.expiration_date:
            problems.append(Problem(get_rule(RuleId.TOKEN_WITHOUT_EXPIRATION), self, str(self), age))
        if max_age == 0:
            log.info("%s: Audit of token max age is disabled, skipped")
        elif age > max_age:
            problems.append(Problem(get_rule(RuleId.TOKEN_TOO_OLD), self, str(self), age))
        if self.last_connection_date and mode != "housekeeper":
            last_cnx_age = util.age(self.last_connection_date, now=today)
            if last_cnx_age > settings.get("audit.tokens.maxUnusedAge", 30):
                problems.append(Problem(get_rule(RuleId.TOKEN_UNUSED), self, str(self), last_cnx_age))
        elif mode != "housekeeper":
            problems.append(Problem(get_rule(RuleId.TOKEN_NEVER_USED), self, str(self), age))
        return problems
