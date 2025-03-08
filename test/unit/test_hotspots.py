#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024-2025 Olivier Korach
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

""" Test of the hotspots module and class, as well as changelog """

import utilities as tutil
from sonar import hotspots
from sonar.util import constants as c


def test_transitions() -> None:
    hotspot_d = hotspots.search(endpoint=tutil.SQ, filters={"project": "okorach_sonar-tools"})
    hotspot = list(hotspot_d.values())[0]

    assert hotspot.mark_as_safe()
    assert hotspot.reopen()

    assert hotspot.mark_as_to_review()
    assert hotspot.reopen()
