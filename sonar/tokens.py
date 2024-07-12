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

import json

import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf
import sonar.utilities as util


class UserToken(sq.SqObject):
    """
    Abstraction of the SonarQube "user token" concept
    """

    API_ROOT = "user_tokens"
    API_REVOKE = API_ROOT + "/revoke"
    API_SEARCH = API_ROOT + "/search"
    API_GENERATE = API_ROOT + "/generate"

    def __init__(self, endpoint: pf.Platform, login: str, json_data: dict[str, str], name: str = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=login)
        self.login = login  #: User login
        self.name = name  #: Token name
        self.created_at = None  #: Token creation date
        self.last_connection_date = None  #: Token last connection date
        if self.name is None:
            self.name = json_data.get("name", None)
        if "createdAt" in json_data:
            self.created_at = util.string_to_date(json_data["createdAt"])
        if "lastConnectionDate" in json_data:
            self.last_connection_date = util.string_to_date(json_data["lastConnectionDate"])
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
