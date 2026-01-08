#!/usr/bin/env python3
#
# sonar-migration tests
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

"""sonar-migration tests"""

from collections.abc import Generator

import json

import utilities as tutil
from sonar import errcodes
import sonar.util.constants as c

import cli.options as opt
from migration import migration

CMD = f"migration.py {tutil.SQS_OPTS}"

GLOBAL_ITEMS = ("platform", "globalSettings", "rules", "qualityProfiles", "qualityGates", "projects", "applications", "portfolios", "users", "groups")


def test_migration_help(json_file: Generator[str]) -> None:
    """test_migration_help"""
    assert tutil.run_cmd(migration.main, f"{CMD} --{opt.REPORT_FILE} {json_file} -h") == errcodes.ARGS_ERROR


def test_migration(json_file: Generator[str]) -> None:
    """test_migration"""
    assert tutil.run_cmd(migration.main, f"{CMD} --{opt.REPORT_FILE} {json_file}") == errcodes.OK
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())

    for item in GLOBAL_ITEMS:
        assert item in json_config

    item_list = ["detectedCi", "issues", "hotspots", "ncloc", "revision"]
    for p in json_config["projects"]:
        if tutil.SQ.edition() != c.CE:
            assert "branches" in p or "error" in p
        for item in item_list:
            assert item in p["migrationData"] or "error" in p

    u = next(u for u in json_config["users"] if u["login"] == "admin")
    assert tutil.SQ.default_user_group() in u["groups"]
    assert u["local"] and u["active"]
    if tutil.SQ.version() >= (10, 0, 0):
        assert "sonarQubeLastConnectionDate" in u
        assert "sonarLintLastConnectionDate" in u
    else:
        assert "lastConnectionDate" in u

    u = next(u for u in json_config["users"] if u["login"] == "olivier")
    assert u["externalProvider"] == "sonarqube"

    GH_USER = "olivier-korach65532"
    GL_USER = "olivier-korach22656" if tutil.SQ.version() > (10, 0, 0) else "olivier-korach82556"
    USER = GL_USER
    u = next(u for u in json_config["users"] if u["login"] == USER)
    assert u["name"] == "Olivier Korach"
    assert not u["local"]
    assert u["externalProvider"] == ("gitlab" if USER == GL_USER else "github")
    if tutil.SQ.version() >= (10, 0, 0):
        assert u["externalLogin"] == "okorach"
        assert u["email"] == "olivier.korach@gmail.com"

    p = next(p for p in json_config["projects"] if p["key"] == tutil.LIVE_PROJECT)
    mdata = p["migrationData"]
    assert "lastTaskScannerContext" in mdata["backgroundTasks"]
    for elem in "detectedCi", "lastAnalysis", "revision":
        assert elem in mdata
    assert mdata["ncloc"]["py"] > 0
    assert mdata["ncloc"]["total"] > 0

    if tutil.SQ.edition() != c.CE:
        master_branch = next(b for b in p["branches"] if b["name"] == "master")
        iss = master_branch["issues"]
        if tutil.SQ.version() >= (10, 0, 0):
            assert iss["accepted"] > 0
        else:
            assert iss["wontFix"] > 0

        assert iss["falsePositives"] > 0
        assert iss["thirdParty"] == 0

        assert master_branch["hotspots"]["safe"] > 0
        assert master_branch["hotspots"]["acknowledged"] == 0

    if tutil.SQ.version() >= (10, 0, 0):
        p = next(p for p in json_config["projects"] if p["key"] == "demo:gitlab-ci-maven")
        assert p["migrationData"]["detectedCi"] == "Gitlab CI"
        p = next(p for p in json_config["projects"] if p["key"] == "demo:github-actions-cli")
        assert p["migrationData"]["detectedCi"] == "Github Actions"
        # No projects have 3rd party issues for now
        #if tutil.SQ.edition() != c.CE:
        #    b = next(b for b in p["branches"] if b["name"] == "main")
        # assert (isinstance(b["issues"]["thirdParty"], int) and b["issues"]["thirdParty"] == 0) or sum(list(b["issues"]["thirdParty"].values())) > 0

    for p in json_config["portfolios"]:
        assert "projects" in p
        assert "keys" in p["projects"]


def test_migration_skip_issues(json_file: Generator[str]) -> None:
    """test_migration_skip_issues"""
    assert tutil.run_cmd(migration.main, f"{CMD} --{opt.REPORT_FILE} {json_file} --skipIssues") == errcodes.OK
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())

    for item in GLOBAL_ITEMS:
        assert item in json_config

    for p in json_config["projects"]:
        assert "issues" not in p
        assert "hotspots" not in p
