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

"""Test of settings"""

import utilities as tutil
from sonar import settings


def test_autodetect_ai() -> None:
    """test_autodetect_ai"""

    o = settings.get_object(tutil.SQ, "sonar.autodetect.ai.code")
    if tutil.SQ.version() < (2025, 1, 0):
        assert o is None

    val = o.value
    assert o.set(True)
    assert o.value
    assert o.set(False)
    assert not o.value
    assert o.set(val)


def test_mqr_mode() -> None:
    """test_mqr_mode"""
    o = settings.get_object(tutil.SQ, "sonar.multi-quality-mode.enabled")
    if tutil.SQ.version() < (2025, 1, 0):
        assert o is None
    val = o.value
    assert o.set(True)
    assert o.value
    assert o.set(False)
    assert not o.value
    assert o.set(val)

def test_unsettable() -> None:
    """test_unsettable"""
    o = settings.get_object(tutil.SQ, "sonar.core.startTime")
    assert o is not None
    assert not o.set("2025-01-01")
