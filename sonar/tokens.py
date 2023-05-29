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

import json
import sonar.sqobject as sq
import sonar.utilities as util


class UserToken(sq.SqObject):
    """
    Abstraction of the SonarQube "user token" concept
    """

    API_ROOT = "user_tokens"
    API_REVOKE = API_ROOT + "/revoke"
    API_SEARCH = API_ROOT + "/search"
    API_GENERATE = API_ROOT + "/generate"

    def __init__(self, login, name=None, json_data=None, created_at=None, token=None, endpoint=None):
        super().__init__(login, endpoint)
        self.login = login  #: User login
        self.name = name  #: Token name
        self.created_at = None  #: Token creation date
        self.last_connection_date = None  #: Token last connection date
        if isinstance(created_at, str):
            self.created_at = util.string_to_date(created_at)
        else:
            self.created_at = created_at
        if self.name is None and "name" in json_data:
            self.name = json_data["name"]
        if self.created_at is None and "createdAt" in json_data:
            self.created_at = util.string_to_date(json_data["createdAt"])
        if "lastConnectionDate" in json_data:
            self.last_connection_date = util.string_to_date(json_data["lastConnectionDate"])
        self.token = token
        util.logger.debug("Created '%s'", str(self))

    def __str__(self):
        """
        :return: Token string representation
        :rtype: str
        """
        return f"token '{self.name}' of user '{self.login}'"

    def revoke(self):
        """Revokes the token
        :return: Whether the revocation succeeded
        :rtype: bool
        """
        if self.name is None:
            return False
        util.logger.info("Revoking token '%s' of user login '%s'", self.name, self.login)
        return self.post(UserToken.API_REVOKE, {"name": self.name, "login": self.login}).ok


def search(endpoint, login):
    """Searches tokens of a given user

    :param login: login of the user
    :type login: str
    :return: list of tokens
    :rtype: list[UserToken]
    """
    data = json.loads(endpoint.get(UserToken.API_SEARCH, {"login": login}).text)
    token_list = []
    for tk in data["userTokens"]:
        token_list.append(UserToken(login=data["login"], json_data=tk, endpoint=endpoint))
    return token_list


def generate(name, endpoint, login=None):
    """Generates a new token for a given user
    :return: the generated Token object
    :rtype: Token
    """
    data = json.loads(endpoint.post(UserToken.API_GENERATE, {"name": name, "login": login}).text)
    return UserToken(endpoint=endpoint, login=data["login"], name=data["name"], created_at=data["createdAt"], token=data["token"])
