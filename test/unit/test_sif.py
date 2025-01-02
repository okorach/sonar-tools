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
import pytest
import utilities as util
from sonar import sif, errcodes
from sonar.dce import app_nodes, search_nodes
from cli import audit
import cli.options as opt

CMD = "sonar-audit.py"
CSV_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE]
JSON_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]

_FILES_ROOT = "test/files/"


def test_audit_sif() -> None:
    """test_audit_sif"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", [CMD, "--sif", f"{_FILES_ROOT}/sif1.json", f"--{opt.REPORT_FILE}", util.CSV_FILE]):
            audit.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_audit_sif_dce1() -> None:
    """test_audit_sif_dce1"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", [CMD, "--sif", f"{_FILES_ROOT}/sif.dce.1.json", f"--{opt.REPORT_FILE}", util.CSV_FILE]):
            audit.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_audit_sif_dce2() -> None:
    """test_audit_sif_dce2"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", [CMD, "--sif", f"{_FILES_ROOT}/sif.dce.2.json", f"--{opt.REPORT_FILE}", util.CSV_FILE]):
            audit.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_sif_1() -> None:
    """test_sif_1"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--sif", f"{_FILES_ROOT}/sif1.json"]):
            audit.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_sif_2() -> None:
    """test_sif_2"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["--sif", f"{_FILES_ROOT}/sif2.json"]):
            audit.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_audit_sif_ut() -> None:
    """test_audit_sif_ut"""
    with open(f"{_FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
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
    sysinfo = sif.Sif(json_sif, concerned_object=util.SQ)
    assert sysinfo.url() == util.SQ.url
    assert str(sysinfo).split("@")[1] == util.SQ.url


def test_modified_sif() -> None:
    """test_modified_sif"""
    with open("test/files/sif1.json", "r", encoding="utf-8") as f:
        json_sif = json.loads(f.read())

    json_sif["System"].pop("Edition")
    assert sif.Sif(json_sif).edition() == "enterprise"
    json_sif["License"].pop("edition")
    assert sif.Sif(json_sif).edition() is None

    json_sif["License"].pop("type")
    assert sif.Sif(json_sif).license_type() is None
    json_sif.pop("License")
    assert sif.Sif(json_sif).license_type() is None


def test_json_not_sif() -> None:
    """Tests that the right exception is raised if JSON file is not a SIF"""
    with pytest.raises(sif.NotSystemInfo) as e:
        with open("test/files/config.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
            _ = sif.Sif(json_sif)
    assert e.type == sif.NotSystemInfo


def test_dce_sif_ut() -> None:
    """test_audit_sif_ut"""
    with open("test/files/sif.dce.1.json", "r", encoding="utf-8") as f:
        json_sif = json.loads(f.read())

    sysinfo = sif.Sif(json_sif)
    app_nodes.audit(sub_sif=json_sif["Application Nodes"], sif_object=sysinfo, audit_settings={})
    for appnode in json_sif["Application Nodes"]:
        node = app_nodes.AppNode(appnode, sysinfo)
        assert str(node).startswith("App Node")
        assert len(node.plugins()) == 6
        assert node.health() == "GREEN"
        assert node.node_type() == "APPLICATION"
        assert node.start_time() == datetime.datetime(2024, 2, 22, 22, 4, 30)
        assert node.version() == (9, 9, 0)
        assert node.edition() == "datacenter"
        assert node.name().startswith("app-node")
        _ = node.audit(audit_settings={})

    search_nodes.audit(sub_sif=json_sif["Search Nodes"], sif=sysinfo, audit_settings={})
    for searchnode in json_sif["Search Nodes"]:
        node = search_nodes.SearchNode(searchnode, sysinfo)
        assert str(node).startswith("Search Node")
        assert node.node_type() == "SEARCH"
        assert node.name().startswith("search-node")
        assert 20000 < node.store_size() < 25000
        _ = node.audit(audit_settings={})
