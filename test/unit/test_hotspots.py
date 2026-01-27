#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024-2026 Olivier Korach
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

"""Test of the hotspots module and class, as well as changelog"""

from datetime import datetime, timedelta

import pytest
import utilities as tutil
from sonar.hotspots import Hotspot
from sonar import exceptions
import sonar.util.misc as util
import credentials


def test_transitions() -> None:
    """test_transitions"""
    pkey = "okorach_sonar-tools-test" if tutil.SQ.is_sonarcloud() else "test:juice-shop"
    hotspot_d = Hotspot.search(tutil.SQ, project=pkey)
    hotspot = list(hotspot_d.values())[0]

    assert hotspot.mark_as_safe()
    assert hotspot.reopen()

    if tutil.SQ.is_sonarcloud():
        with pytest.raises(exceptions.UnsupportedOperation):
            hotspot.mark_as_acknowledged()
    else:
        assert hotspot.mark_as_acknowledged()
        assert hotspot.reopen()

    assert hotspot.mark_as_to_review()
    assert hotspot.reopen()

    assert hotspot.mark_as_fixed()
    assert hotspot.reopen()

    assert hotspot.assign(credentials.ADMIN_USER)
    assert hotspot.unassign()


def test_add_comment() -> None:
    """test_add_comment"""
    findings_d = Hotspot.search(tutil.SQ, project="test:juice-shop")
    finding = list(findings_d.values())[0]
    nb_comments = len(finding.comments())

    txt = f"test comment on {datetime.now()}"
    assert finding.add_comment(txt)
    comments = finding.comments()
    assert list(comments.values())[-1]["value"] == txt
    assert len(comments) == nb_comments + 1

    just_before = datetime.now().astimezone() - timedelta(seconds=2)
    comments = finding.comments(after=just_before)
    assert len(comments) == 1
    assert list(comments.values())[-1]["value"] == txt


def test_sanitize_filter() -> None:
    """test_sanitize_filter"""
    assert Hotspot.sanitize_search_params(endpoint=tutil.SQ) == {}
    good = ["TO_REVIEW", "REVIEWED"]
    assert Hotspot.sanitize_search_params(endpoint=tutil.SQ, statuses=["DEAD"] + good) == {"status": ",".join(good)}
    assert Hotspot.sanitize_search_params(endpoint=tutil.SQ, statuses=good + ["DEAD"]) == {"status": ",".join(good)}


def test_comments_after() -> None:
    """test_comments_after"""
    hotspot = list(Hotspot.search(endpoint=tutil.SQ, project="test:juice-shop").values())[0]
    after = util.add_tz(datetime(2024, 1, 1))
    comments = hotspot.comments(after=after)
    assert all(c["date"] >= after for c in comments.values())


def test_search_by_project() -> None:
    """test_search_by_project"""
    nbr_hotspots = len(Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT))
    assert nbr_hotspots > 0
    assert len(Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT, statuses=["TO_REVIEW"])) < nbr_hotspots
    assert len(Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT, severities=["BLOCKER", "CRITICAL"])) < nbr_hotspots


def test_search_on_branches() -> None:
    """test_search_on_branches"""
    proj_hotspots = Hotspot.search(tutil.SQ, project=tutil.LIVE_PROJECT)
    branch_hotspots = Hotspot.search(tutil.SQ, project=tutil.LIVE_PROJECT, branch="develop")
    assert len(proj_hotspots) != len(branch_hotspots)
    for hotspot in branch_hotspots.values():
        assert hotspot.branch == "develop"
    for hotspot in proj_hotspots.values():
        assert hotspot.branch is None or hotspot.branch == "master"


def test_search_on_pr() -> None:
    """test_search_on_pr"""
    pr_hotspots = Hotspot.search(tutil.SQ, project=tutil.LIVE_PROJECT, pullRequest="5")
    assert len(pr_hotspots) == 0
