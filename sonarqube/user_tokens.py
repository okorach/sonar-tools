#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
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
'''

    Abstraction of the SonarQube "user_token" concept

'''
import json
import sonarqube.env as env
import sonarqube.sqobject as sq
import sonarqube.utilities as util


class UserToken(sq.SqObject):
    API_ROOT = 'user_tokens'
    API_REVOKE = API_ROOT + '/revoke'
    API_SEARCH = API_ROOT + '/search'
    API_GENERATE = API_ROOT + '/generate'

    def __init__(self, login, name=None, json_data=None, createdAt=None, token=None, endpoint=None):
        super().__init__(key=login, env=endpoint)
        self.login = login
        if isinstance(createdAt, str):
            self.createdAt = util.string_to_date(createdAt)
        else:
            self.createdAt = createdAt
        self.name = name
        if self.name is None and 'name' in json_data:
            self.name = json_data['name']
        if self.createdAt is None and 'createdAt' in json_data:
            self.createdAt = util.string_to_date(json_data['createdAt'])
        self.lastConnectionDate = None
        if 'lastConnectionDate' in json_data:
            self.lastConnectionDate = util.string_to_date(json_data['lastConnectionDate'])
        self.token = token
        util.logger.debug("Created token '%s'", str(self))

    def __str__(self):
        return f"{self.name}:{util.redacted_token(self.token)}"

    def revoke(self):
        if self.name is None:
            return False
        util.logger.info("Revoking token '%s' of user login '%s'", self.name, self.login)
        env.post(UserToken.API_REVOKE, {'name': self.name, 'login': self.login}, self.env)
        return True


def search(login, endpoint=None):
    resp = env.get(UserToken.API_SEARCH, {'login': login}, endpoint)
    token_list = []
    data = json.loads(resp.text)
    for tk in data['userTokens']:
        token_list.append(UserToken(
            login=data['login'], json_data=tk, endpoint=endpoint))
    return token_list


def generate(name, login=None, endpoint=None):
    resp = env.post(UserToken.API_GENERATE, {'name': name, 'login': login}, endpoint)
    data = json.loads(resp.text)
    return UserToken(login=data['login'], name=data['name'],
                     createdAt=data['createdAt'], token=data['token'], endpoint=endpoint)
