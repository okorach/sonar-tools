#!/usr/bin/env python3
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

""" Test of the tasks module and class """

import utilities as tutil
from sonar import tasks, logging


def test_task() -> None:
    """test_task"""
    task = tasks.search_last(component_key=tutil.LIVE_PROJECT, endpoint=tutil.SQ, type="REPORT")
    assert task is not None
    assert task.url() == f"{tutil.SQ.url}/project/background_tasks?id={tutil.LIVE_PROJECT}"
    task.sq_json = None
    task._load()
    assert task.sq_json is not None
    if tutil.SQ.version() >= (10, 0, 0):
        assert len(task.id()) == 36
    else:
        assert len(task.id()) == 20
    assert task.status() == tasks.SUCCESS
    assert 100 <= task.execution_time() <= 100000
    assert task.submitter() == "admin"
    assert task.warning_count() > 0
    assert task.error_message() is None


def test_audit() -> None:
    """test_audit"""
    task = tasks.search_last(component_key=tutil.LIVE_PROJECT, endpoint=tutil.SQ, type="REPORT")
    settings = {
        "audit.projects.suspiciousExclusionsPatterns": "\\*\\*/[^\/]+/\\*\\*, \\*\\*/\\*[\.\w]*, \\*\\*/\\*, \\*\\*/\\*\\.(java|jav|cs|csx|py|php|js|ts|sql|html|css|cpp|c|h|hpp)\\*?",
        "audit.projects.suspiciousExclusionsExceptions": "\\*\\*/(__pycache__|libs|lib|vendor|node_modules)/\\*\\*",
    }
    assert len(task.audit(settings)) > 0
    settings["audit.project.scm.disabled"] = False
    settings["audit.projects.analysisWarnings"] = False
    settings["audit.projects.failedTasks"] = False
    assert len(task.audit(settings)) > 0
    settings["audit.projects.exclusions"] = False
    assert len(task.audit(settings)) == 0


def test_no_scanner_context() -> None:
    """test_no_scanner_context"""
    tutil.start_logging()
    task = tasks.search_last(component_key="project1", endpoint=tutil.SQ, type="REPORT")
    if not task:
        return
    if tutil.SQ.version() >= (10, 0, 0):
        assert task.scanner_context() is None
    settings = {}
    task.audit(settings)


def test_search_all_task() -> None:
    """test_search_all_task"""
    assert len(tasks.search_all_last(tutil.SQ)) > 0


def test_suspicious_patterns() -> None:
    """test_suspicious_patterns"""
    pats = "\\*\\*/[^\/]+/\\*\\*, \\*\\*/\\*[\.\w]*, \\*\\*/\\*, \\*\\*/\\*\\.(java|jav|cs|csx|py|php|js|ts|sql|html|css|cpp|c|h|hpp)\\*?"
    s_pats = tasks._get_suspicious_exclusions(pats)
    l_pats = [s.strip() for s in pats.split(",")]
    logging.debug(f"{s_pats} == {l_pats}")
    assert set(tasks._get_suspicious_exclusions(pats)) == set([s.strip() for s in pats.split(",")])
    assert set(tasks._get_suspicious_exclusions(None)) == set([s.strip() for s in pats.split(",")])
    pats = "\\*\\*/(__pycache__|libs|lib|vendor|node_modules)/\\*\\*"
    assert set(tasks._get_suspicious_exceptions(pats)) == set([s.strip() for s in pats.split(",")])
    assert set(tasks._get_suspicious_exceptions(None)) == set([s.strip() for s in pats.split(",")])


# Test does not work - You can't request branch master when scan happened without the branch spec
# def test_search_branch() -> None:
#     """test_search_branch"""
#     logging.set_logger(tutil.TEST_LOGFILE)
#     logging.set_debug_level("DEBUG")
#     assert tasks.search_last(tutil.SQ, component_key=tutil.LIVE_PROJECT, branch="master") is not None
#     assert tasks.search_last(tutil.SQ, component_key=tutil.LIVE_PROJECT, branch="comma,branch") is None
