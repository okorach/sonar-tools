#!/usr/bin/env python3
#
# sonar-migration tests
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

""" sonar-migration tests """

import os
import sys
import json
from unittest.mock import patch
import pytest

import utilities as util
from sonar import errcodes
import cli.options as opt
from cli import migration

CMD = "migration.py"
OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]


def test_migration_help() -> None:
    """test_migration_help"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + ["-h"]):
            migration.main()
    assert int(str(e.value)) == 10
    assert not os.path.isfile(util.JSON_FILE)


def test_migration() -> None:
    """test_config_export"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS):
            migration.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    with open(file=util.JSON_FILE, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())

    u = json_config["users"]["admin"]
    assert "sonar-users" in u["groups"]
    assert u["local"] and u["active"]
    assert "sonarQubeLastConnectionDate" in u
    assert "sonarLintLastConnectionDate" in u
    assert json_config["users"]["olivier"]["externalProvider"] == "sonarqube"

    u = json_config["users"]["olivier-korach65532"]
    assert u["externalProvider"] == "github"
    assert u["name"] == "Olivier Korach"
    assert not u["local"]
    assert u["externalLogin"] == "okorach"
    assert u["email"] == "olivier.korach@gmail.com"

    p = json_config["projects"]["okorach_sonar-tools"]
    assert "lastTaskScannerContext" in p["backgroundTasks"]
    for elem in "detectedCi", "lastAnalysis", "revision":
        assert elem in p
    assert p["ncloc"]["py"] > 0
    assert p["ncloc"]["total"] > 0

    iss = p["branches"]["master"]["issues"]
    assert iss["accepted"] > 0
    assert iss["fslePositives"] > 0
    assert iss["thirdParty"] == 0

    p = json_config["projects"]["checkstyle-issues"]
    assert len(p["branches"]["issues"]["thirdParty"]) > 0

    assert json_config["projects"]["demo:gitlab-ci-maven"]["detectedCi"] == "GitLab CI"
    assert json_config["projects"]["demo:gitlab-actions-cli"]["detectedCi"] == "Github Actions"

    util.clean(util.JSON_FILE)
