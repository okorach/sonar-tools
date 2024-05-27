#!/usr/bin/env env python3
#
# test measures
# Copyright (C) 2024 Olivier Korach
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

import os
import sys
from unittest.mock import patch
from sonar import options
from tools import measures_export

LATEST = 'http://localhost:9999'
LTA = 'http://localhost:9000'

CMD = 'sonar-measures-export.py'
CSV_FILE = "temp.csv"
JSON_FILE = "temp.json"

STD_OPTS = ["-u", os.getenv("SONAR_HOST_URL"), '-t', os.getenv("SONAR_TOKEN")]
STD_OPTS = ["-u", os.getenv("SONAR_HOST_URL"), '-t', os.getenv("SONAR_TOKEN_ADMIN_USER")]

def __file_not_empty(file: str) -> bool:
    """Returns whether a file exists and is not empty"""
    if not os.path.isfile(file):
        return False
    return os.stat(file).st_size > 0

def test_measures_export():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_measures_conversion():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-r", "-p", "--withTags", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_measures_export_with_url():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-b", "-m", "_main", "--withURL", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)


def test_measures_export_json():
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-b", "-m", "_main", "-f", JSON_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(JSON_FILE)
    os.remove(JSON_FILE)

def test_measures_export_all():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-b", "-m", "_all", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_measures_export_json_all():
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-b", "-m", "_all", "-f", JSON_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(JSON_FILE)
    os.remove(JSON_FILE)

def test_measures_export_history():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["--history", "-m", "_all", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_measures_export_history_as_table():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["--history", "--asTable", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_measures_export_history_as_table_no_time():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["--history", "--asTable", "-d", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_measures_export_history_as_table_with_url():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["--history", "--asTable", "--withURL", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_measures_export_dateonly():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-d", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_specific_measure():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-m", "ncloc,sqale_index,coverage", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)

def test_non_existing_measure():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-m", "ncloc,sqale_index,bad_measure", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_NO_SUCH_KEY
    assert not os.path.isfile(CSV_FILE)
    os.remove(CSV_FILE)

def test_non_existing_project():
    os.remove(CSV_FILE)
    with patch.object(sys, 'argv', [CMD] + STD_OPTS + ["-k", "okorach_sonar-tools,bad_project", "-f", CSV_FILE]):
        try:
            measures_export.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_NO_SUCH_KEY
    assert not os.path.isfile(CSV_FILE)
    os.remove(CSV_FILE)