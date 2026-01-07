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

"""Test of the hotspots module and class, as well as changelog"""

from datetime import datetime
import utilities as tutil
from sonar import hotspots
import sonar.util.misc as util


def test_transitions() -> None:
    """test_transitions"""
    hotspot_d = hotspots.Hotspot.search(tutil.SQ, project="test:juice-shop")
    hotspot = list(hotspot_d.values())[0]

    assert hotspot.mark_as_safe()
    assert hotspot.reopen()

    if tutil.SQ.is_sonarcloud():
        hotspot = list(hotspots.Hotspot.search(tutil.SQ, project=tutil.LIVE_PROJECT).values())[0]
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


def test_search_by_project() -> None:
    """test_search_by_project"""
    nbr_hotspots = len(hotspots.Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT))
    assert nbr_hotspots > 0
    assert len(hotspots.Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT, statuses=["TO_REVIEW"])) < nbr_hotspots
    assert len(hotspots.Hotspot.search_by_project(tutil.SQ, project=tutil.LIVE_PROJECT, severities=["BLOCKER", "CRITICAL"])) < nbr_hotspots


def test_sanitize_filter() -> None:
    """test_sanitize_filter"""
    assert hotspots.Hotspot.sanitize_search_params(endpoint=tutil.SQ) == {}
    good = ["TO_REVIEW", "REVIEWED"]
    assert hotspots.Hotspot.sanitize_search_params(endpoint=tutil.SQ, statuses=["DEAD"] + good) == {"status": ",".join(good)}
    assert hotspots.Hotspot.sanitize_search_params(endpoint=tutil.SQ, statuses=good + ["DEAD"]) == {"status": ",".join(good)}


def test_comments_after() -> None:
    """test_comments_after"""
    hotspot = list(hotspots.Hotspot.search(endpoint=tutil.SQ, project="test:juice-shop").values())[0]
    after = util.add_tz(datetime(2024, 1, 1))
    comments = hotspot.comments(after=after)
    assert all(c["date"] >= after for c in comments.values())
