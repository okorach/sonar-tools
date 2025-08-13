#!/usr/bin/env python3
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

""" Common tests, independent of SonarQube version """

import os, stat
from collections.abc import Generator

import json
import datetime
from unittest.mock import patch
import pytest

import utilities as tutil
from sonar import sif
from sonar.dce import app_nodes, search_nodes
from cli import audit
import cli.options as opt
import sonar.util.constants as c
import sonar.errcodes as e

CMD = "sonar-audit.py"

def test_sif_broken(csv_file: Generator[str]) -> None:
    """test_sif_broken"""
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --sif {tutil.FILES_ROOT}/sif_broken.json") == e.SIF_AUDIT_ERROR


def test_sif_non_existing(csv_file: Generator[str]) -> None:
    """test_sif_non_existing"""
    non_existing_file = f"{tutil.FILES_ROOT}/sif_non_existing.json"
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --sif {non_existing_file}") == e.SIF_AUDIT_ERROR


def test_sif_not_readable(json_file: Generator[str]) -> None:
    """test_sif_not_readable"""
    unreadable_file = f"{tutil.FILES_ROOT}/sif_not_readable.json"
    NO_PERMS = ~stat.S_IRUSR & ~stat.S_IWUSR
    current_permissions = stat.S_IMODE(os.lstat(unreadable_file).st_mode)
    os.chmod(unreadable_file, current_permissions & NO_PERMS)
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {json_file} --sif {unreadable_file}") == e.SIF_AUDIT_ERROR
    os.chmod(unreadable_file, current_permissions)


def test_audit_sif(csv_file: Generator[str]) -> None:
    """test_audit_sif"""
    cmd = f"{CMD} --sif {tutil.FILES_ROOT}/sif1.json --{opt.REPORT_FILE} {csv_file}"
    assert tutil.run_cmd(audit.main, cmd) == e.OK


def test_audit_sif_dce1(csv_file: Generator[str]) -> None:
    """test_audit_sif_dce1"""
    cmd = f"{CMD} --sif {tutil.FILES_ROOT}/sif.dce.1.json --{opt.REPORT_FILE} {csv_file}"
    assert tutil.run_cmd(audit.main, cmd) == e.OK


def test_audit_sif_dce3(csv_file: Generator[str]) -> None:
    """test_audit_sif_dce1"""
    cmd = f"{CMD} --sif {tutil.FILES_ROOT}/sif.dce.2.json --{opt.REPORT_FILE} {csv_file}"
    assert tutil.run_cmd(audit.main, cmd) == e.OK


def test_sif_1(csv_file: Generator[str]) -> None:
    """test_sif_1"""
    cmd = f"{CMD} --sif {tutil.FILES_ROOT}/sif1.json --{opt.REPORT_FILE} {csv_file}"
    assert tutil.run_cmd(audit.main, cmd) == e.OK


def test_sif_2(json_file) -> None:
    """test_sif_2"""
    cmd = f"{CMD} --sif {tutil.FILES_ROOT}/sif2.json --{opt.REPORT_FILE} {json_file}"
    assert tutil.run_cmd(audit.main, cmd) == e.OK


def test_audit_sif_ut() -> None:
    """test_audit_sif_ut"""
    with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
        json_sif = json.loads(f.read())
    sysinfo = sif.Sif(json_sif)
    assert sysinfo.edition() == c.EE
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
    sysinfo = sif.Sif(json_sif, concerned_object=tutil.SQ)
    assert sysinfo.url() == tutil.SQ.external_url
    assert str(sysinfo).split("@")[1] == tutil.SQ.external_url


def test_modified_sif() -> None:
    """test_modified_sif"""
    with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
        json_sif = json.loads(f.read())

    json_sif["System"].pop("Edition")
    assert sif.Sif(json_sif).edition() == c.EE
    json_sif["License"].pop("edition")
    assert sif.Sif(json_sif).edition() is None

    json_sif["License"].pop("type")
    assert sif.Sif(json_sif).license_type() is None
    json_sif.pop("License")
    assert sif.Sif(json_sif).license_type() is None


def test_json_not_sif() -> None:
    """Tests that the right exception is raised if JSON file is not a SIF"""
    with pytest.raises(sif.NotSystemInfo) as e:
        with open(f"{tutil.FILES_ROOT}/config.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
            _ = sif.Sif(json_sif)
    assert e.type == sif.NotSystemInfo


def test_dce_sif_ut() -> None:
    """test_audit_sif_ut"""
    with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
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
        assert node.edition() == c.DCE
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
