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

    Abstraction of the SonarQube general object concept

'''
import sonarqube.env


class SqObject:

    def __init__(self, key, env):
        self.key = key
        self.env = env

    def set_env(self, env):
        self.env = env

    def get_env(self):
        return self.env

    def get(self, api, params=None):
        return sonarqube.env.get(api, params, self.env)

    def post(self, api, params=None):
        return sonarqube.env.post(api, params, self.env)

    def delete(self, api, params=None):
        resp = sonarqube.env.delete(api, params, self.env)
        return (resp.status_code // 100) == 2
