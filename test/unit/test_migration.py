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

""" sonar-migration tests """

from collections.abc import Generator

import json

import utilities as util
from sonar import errcodes
import cli.options as opt
from migration import migration

CMD = f"migration.py {util.SQS_OPTS}"

GLOBAL_ITEMS = ("platform", "globalSettings", "rules", "qualityProfiles", "qualityGates", "projects", "applications", "portfolios", "users", "groups")


def test_migration_help(get_json_file: Generator[str]) -> None:
    """test_migration_help"""
    util.run_failed_cmd(migration.main, f"{CMD} --{opt.REPORT_FILE} {get_json_file} -h", errcodes.ARGS_ERROR)


def test_migration(get_json_file: Generator[str]) -> None:
    """test_config_export"""
    file = get_json_file
    util.run_success_cmd(migration.main, f"{CMD} --{opt.REPORT_FILE} {file}")
    with open(file=file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())

    for item in GLOBAL_ITEMS:
        assert item in json_config

    item_list = ["backgroundTasks", "detectedCi", "lastAnalysis", "issues", "hotspots", "name", "ncloc", "permissions", "revision", "visibility"]
    if util.SQ.edition() != "community":
        item_list.append("branches")
    for p in json_config["projects"].values():
        for item in item_list:
            assert item in p

    u = json_config["users"]["admin"]
    assert "sonar-users" in u["groups"]
    assert u["local"] and u["active"]
    if util.SQ.version() >= (10, 0, 0):
        assert "sonarQubeLastConnectionDate" in u
        assert "sonarLintLastConnectionDate" in u
    else:
        assert "lastConnectionDate" in u
    assert json_config["users"]["olivier"]["externalProvider"] == "sonarqube"

    GH_USER = "olivier-korach65532"
    GL_USER = "olivier-korach22656" if util.SQ.version() > (10, 0, 0) else "olivier-korach82556"
    USER = GL_USER
    u = json_config["users"][USER]
    assert u["name"] == "Olivier Korach"
    assert not u["local"]
    assert u["externalProvider"] == ("gitlab" if USER == GL_USER else "github")
    if util.SQ.version() >= (10, 0, 0):
        assert u["externalLogin"] == "okorach"
        assert u["email"] == "olivier.korach@gmail.com"

    p = json_config["projects"]["okorach_sonar-tools"]
    assert "lastTaskScannerContext" in p["backgroundTasks"]
    for elem in "detectedCi", "lastAnalysis", "revision":
        assert elem in p
    assert p["ncloc"]["py"] > 0
    assert p["ncloc"]["total"] > 0

    if util.SQ.edition() != "community":
        iss = p["branches"]["master"]["issues"]
        if util.SQ.version() >= (10, 0, 0):
            assert iss["accepted"] > 0
        else:
            assert iss["wontFix"] > 0

        assert iss["falsePositives"] > 0
        assert iss["thirdParty"] == 0

        assert p["branches"]["master"]["hotspots"]["safe"] > 0
        assert p["branches"]["master"]["hotspots"]["acknowledged"] == 0

    p = json_config["projects"]["checkstyle-issues"]

    if util.SQ.version() >= (10, 0, 0):
        assert json_config["projects"]["demo:gitlab-ci-maven"]["detectedCi"] == "Gitlab CI"
        assert json_config["projects"]["demo:github-actions-cli"]["detectedCi"] == "Github Actions"
        if util.SQ.edition() != "community":
            assert sum([v for v in p["branches"]["main"]["issues"]["thirdParty"].values()]) > 0

    for p in json_config["portfolios"].values():
        assert "projects" in p
        assert "keys" in p["projects"]


def test_migration_skip_issues(get_json_file: Generator[str]) -> None:
    """test_migration_skip_issues"""
    file = get_json_file
    util.run_success_cmd(migration.main, f"{CMD} --{opt.REPORT_FILE} {file} --skipIssues")
    with open(file=file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())

    for item in GLOBAL_ITEMS:
        assert item in json_config

    for p in json_config["projects"].values():
        assert "issues" not in p
        assert "hotspots" not in p
