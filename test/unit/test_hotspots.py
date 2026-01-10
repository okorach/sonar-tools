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
import utilities as tutil
from sonar.hotspots import Hotspot
import sonar.util.misc as util
from sonar import projects


def test_transitions() -> None:
    """test_transitions"""
    hotspot_d = Hotspot.search(tutil.SQ, project="test:juice-shop")
    hotspot = list(hotspot_d.values())[0]

    assert hotspot.mark_as_safe()
    assert hotspot.reopen()

    if tutil.SQ.is_sonarcloud():
        hotspot = list(Hotspot.search(tutil.SQ, project=tutil.LIVE_PROJECT).values())[0]
        assert not hotspot.mark_as_acknowledged()
    else:
        assert hotspot.mark_as_acknowledged()
        assert hotspot.reopen()

    assert hotspot.mark_as_to_review()
    assert hotspot.reopen()

    assert hotspot.mark_as_fixed()
    assert hotspot.reopen()

    assert hotspot.assign("admin")
    assert hotspot.unassign()


def test_add_comment() -> None:
    """test_add_comment"""
    hotspot_d = Hotspot.search(tutil.SQ, project="test:juice-shop")
    hotspot = list(hotspot_d.values())[0]
    nb_comments = len(hotspot.comments())
    txt = f"test comment on {datetime.now()}"
    assert hotspot.add_comment(f"test comment on {datetime.now()}")
    comments = hotspot.comments()
    assert list(comments.values())[0]["value"] == txt
    assert len(comments) == nb_comments + 1

    cached_comments = hotspot.comments()
    assert len(cached_comments) == nb_comments

    just_before = datetime.now() - timedelta(seconds=10)
    comments = hotspot.comments(after=just_before)
    assert len(comments) == 1
    assert comments.values()[0]["value"] == txt


def test_search_by_project() -> None:
    """test_search_by_project"""
    nbr_hotspots = len(Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT))
    assert nbr_hotspots > 0
    assert len(Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT, statuses=["TO_REVIEW"])) < nbr_hotspots
    assert len(Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT, severities=["BLOCKER", "CRITICAL"])) < nbr_hotspots


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
    proj: projects.Project = projects.Project.get_object(tutil.SQ, key=tutil.LIVE_PROJECT)
    hotspot_list = Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT)
    assert len(hotspot_list) > 0
    assert len(Hotspot.search_by_project(tutil.SQ, project=proj)) == len(hotspot_list)
    assert len(Hotspot.search_by_project(tutil.SQ, project=proj, severities=["BLOCKER", "CRITICAL"])) < len(hotspot_list)
    assert len(Hotspot.search_by_project(tutil.SQ, project=proj, statuses=["TO_REVIEW"])) < len(hotspot_list)


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
    pr_hotspots = Hotspot.search(tutil.SQ, project=tutil.LIVE_PROJECT, pull_request="5")
    assert len(pr_hotspots) == 0
