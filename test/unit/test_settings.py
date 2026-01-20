# sonar-tools tests
# Copyright (C) 2026 Olivier Korach
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


def test_set_standard() -> None:
    """test_set_standard"""

    o = settings.Setting.get_object(tutil.SQ, "sonar.java.file.suffixes")
    val = o.value
    new_val = [".jav", ".java", ".javacard"]
    assert o.set(new_val)
    assert sorted(o.value) == sorted(new_val)

    new_val = [".jav", ".java", ".javacard", ".jah"]
    assert o.set(", ".join(new_val))
    assert sorted(o.value) == sorted(new_val)

    assert o.reset()
    assert sorted(o.value) == sorted([".jav", ".java"])
    assert o.set(val)
    assert sorted(o.value) == sorted(val)


def test_autodetect_ai() -> None:
    """test_autodetect_ai"""

    o = settings.Setting.get_object(tutil.SQ, "sonar.autodetect.ai.code")
    # Even if invisible in the UI, the setting is present in the API in Community Builds
    if tutil.SQ.version() < (25, 1, 0):
        assert o is None
        return

    val = o.value
    assert o.set(True)
    assert o.value
    assert o.set(False)
    assert not o.value
    assert o.set(val)


def test_mqr_mode() -> None:
    """test_mqr_mode"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.multi-quality-mode.enabled")
    if tutil.SQ.version() < (25, 0, 0):
        assert o is None
        return
    val = o.value
    assert o.set(True)
    assert o.value
    assert o.set(False)
    assert not o.value
    assert o.set(val)


def test_unsettable() -> None:
    """test_unsettable"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.core.startTime")
    assert o is not None
    assert not o.set("2025-01-01")
    o = settings.Setting.get_object(tutil.SQ, "sonar.auth.github.apiUrl")
    assert o is not None
    res = True if tutil.SQ.version() < (10, 0, 0) else False
    assert o.set("https://api.github.com/") == res
