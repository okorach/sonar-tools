#
# sonar-tools tests
# Copyright (C) 2024-2026 Olivier Korach
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

"""sonar.languages tests"""

from sonar import languages
import utilities as tutil


def test_read() -> None:
    """test_read"""
    lang = languages.Language.read(tutil.SQ, "py")
    nbr_total_rules = lang.number_of_rules()
    counts = {t: lang.number_of_rules(t) for t in ("VULNERABILITY", "BUG", "CODE_SMELL", "SECURITY_HOTSPOT")}
    print(f"COUNTS = {str(counts)}")
    assert sum(counts.values()) >= nbr_total_rules
    assert lang.number_of_rules("FOO") == nbr_total_rules
