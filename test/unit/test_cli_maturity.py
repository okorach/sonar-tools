#
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

"""sonar-maturity tests"""

import json
from collections.abc import Generator
import utilities as tutil
from sonar import errcodes as e
import sonar.util.constants as c

from sonar.cli import maturity
import cli.options as opt

CLI = "sonar-maturity.py"
CMD = f"{CLI} {tutil.SQS_OPTS}"


def test_maturity(csv_file: Generator[str]) -> None:
    """test_maturity"""
    assert tutil.run_cmd(maturity.main, f"{CMD} --{opt.REPORT_FILE} {csv_file}") == e.OK
    with open(csv_file) as fd:
        json_data = json.loads(fd.read())
    assert "platform" in json_data
    assert "summary" in json_data
    assert "details" in json_data

    proj_data = json_data["details"]
    assert sorted(proj_data.keys()) == list(proj_data.keys())
    keys = (
        "key",
        "quality_gate",
        "lines_of_code",
        "lines",
        "new_code_lines",
        "new_code_in_days",
        "last_analysis_age",
        "main_branch_last_analysis_age",
        "new_code_lines_ratio",
        "number_of_analyses_on_main_branch",
        "number_of_analyses_on_any_branch",
        "pull_requests",
        "pull_request_stats",
    )
    for proj in proj_data.values():
        for key in keys:
            assert key in proj

    summary_data = json_data["summary"]
    keys = (
        "total_projects",
        "quality_gate_project_statistics",
        "last_analysis_statistics",
        "quality_gate_enforcement_statistics",
        "new_code_statistics",
        "frequency_statistics",
    )
    for key in keys:
        assert key in summary_data
