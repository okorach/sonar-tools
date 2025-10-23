#
# sonar-tools tests
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

"""sonar-findings-export tests"""

import os
from collections.abc import Generator

import utilities as tutil
from sonar import errcodes as e
import cli.options as opt
from cli import findings_export
from sonar import projects
from sonar.audit import rules

CMD = f"sonar-findings-export.py {tutil.SQS_OPTS}"

def test_export_portfolios_findings(csv_file: Generator[str]) -> None:
    """test_export_portfolios_findings"""
    assert tutil.run_cmd(findings_export.main, f"{CMD} --portfolios --{opt.KEY_REGEXP} Banking --{opt.REPORT_FILE} {csv_file}") == e.OK
    # Portfolio 'Banking' has only 4 small projects and less than 300 issues in total
    assert tutil.csv_nbr_lines(csv_file) < 300
