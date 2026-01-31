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

"""sonar Language class tests"""

from sonar.languages import Language
import utilities as tutil


def test_search() -> None:
    """test_search"""
    langs = Language.search(tutil.SQ)
    langs_cached = Language.search(tutil.SQ, use_cache=True)
    assert len(langs) == len(langs_cached)
    assert sorted(langs.keys()) == sorted(langs_cached.keys())
    assert len(langs) > 0
    for lang in ("py", "java", "js", "ts", "go"):
        assert lang in langs
    for lang in ("fubar", "unknown", "python", "JavaScript"):
        assert lang not in langs


def test_exists() -> None:
    """Test exists"""
    for lang in ("py", "java", "js", "ts", "go"):
        assert Language.exists(tutil.SQ, language=lang)
    for lang in ("fubar", "unknown", "python", "JavaScript"):
        assert not Language.exists(tutil.SQ, language=lang)


def test_read() -> None:
    """test_read"""
    lang = Language.read(tutil.SQ, "py", use_cache=False)
    assert lang is not None
    assert lang.key == "py"
    assert lang.name == "Python"


def test_number_of_rules() -> None:
    """test_number_of_rules"""
    lang: Language = Language.read(tutil.SQ, "java", use_cache=False)
    nbr_total_rules = lang.number_of_rules()
    counts = {t: lang.number_of_rules(t) for t in ("VULNERABILITY", "BUG", "CODE_SMELL", "SECURITY_HOTSPOT")}
    assert sum(counts.values()) >= nbr_total_rules

    assert lang.number_of_rules("FOO") == 0
