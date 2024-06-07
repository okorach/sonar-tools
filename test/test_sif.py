#!/usr/bin/env python3
#
# sonar-tools tests
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

"""
    sonar-audit SIF tests
"""

import sys
import json
import datetime
from unittest.mock import patch
import utilities as testutil
from sonar import sif
from tools import audit

CMD = "sonar-audit.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]

def test_audit_sif() -> None:
    """test_audit_sif"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", [CMD, "--sif", "test/sif1.json", "-f", testutil.CSV_FILE]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    testutil.clean(testutil.CSV_FILE)


def test_audit_sif_ut() -> None:
    """test_audit_sif_ut"""
    with open("test/sif1.json", "r", encoding="utf-8") as f:
        json_sif = json.loads(f.read())
    sysinfo = sif.Sif(json_sif)
    assert sysinfo.edition() == "enterprise"
    assert sysinfo.version() == (10, 5, 1)
    assert sysinfo.database() == "PostgreSQL"
    assert len(sysinfo.plugins()) == 0
    assert sysinfo.license_type() == "TEST"
    assert sysinfo.server_id() == "243B8A4D-AY5SFSbmgIK8PCmM81th"
    assert sysinfo.start_time() == datetime.datetime(2024, 5, 23, 13, 37, 24)
    assert sysinfo.store_size() == 131
    assert sysinfo.url() == ""
    assert sysinfo.web_jvm_cmdline() == "-Xmx512m -Xms128m -XX:+HeapDumpOnOutOfMemoryError"
    assert sysinfo.ce_jvm_cmdline() == "-Xmx1G -Xms128m -XX:+HeapDumpOnOutOfMemoryError"
    assert sysinfo.search_jvm_cmdline() == "-Xmx1G -Xms1G -XX:+HeapDumpOnOutOfMemoryError"
    sysinfo = sif.Sif(json_sif, concerned_object=testutil.SONARQUBE)
    assert sysinfo.url() == testutil.SONARQUBE.url
    assert str(sysinfo).split("@")[1] == testutil.SONARQUBE.url


def test_modified_sif() -> None:
    """test_modified_sif"""
    with open("test/sif1.json", "r", encoding="utf-8") as f:
        json_sif = json.loads(f.read())

    json_sif["System"].pop("Edition")
    assert sif.Sif(json_sif).edition() == "enterprise"
    json_sif["License"].pop("edition")
    assert sif.Sif(json_sif).edition() is None

    json_sif["License"].pop("type")
    assert sif.Sif(json_sif).license_type() is None
    json_sif.pop("License")
    assert sif.Sif(json_sif).license_type() is None


def test_json_not_sif():
    """test_audit_sif_ut"""
    with open("test/config.json", "r", encoding="utf-8") as f:
        json_sif = json.loads(f.read())
    try:
        _ = sif.Sif(json_sif)
        assert False
    except sif.NotSystemInfo:
        assert True
