#
# sonar-tools tests
# Copyright (C) 2025 Olivier Korach
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


from sonar.api.manager import ApiOperation as op
from sonar.api.manager import ApiManager as Api
from sonar.groups import Group
import sonar.util.constants as c
import utilities as tutil


def test_api_mgr() -> None:
    api_def = Api(Group, op.REMOVE_USER, tutil.SQ)
    api, method, params, ret = api_def.get_all(id="membership_id", login="user.login", name="group.name")
    if tutil.SQ.version() >= c.GROUP_API_V2_INTRO_VERSION:
        assert api == "v2/authorizations/group-memberships/membership_id"
        assert method == "DELETE"
        assert params == {}
        assert ret is None
    else:
        assert api == "api/user_groups/remove_user"
        assert method == "POST"
        assert params == {"login": "user.login", "name": "group.name"}
        assert ret is None
