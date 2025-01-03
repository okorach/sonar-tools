#
# sonar-tools
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

"""Cache module"""
from typing import Optional
from sonar import platform, projects, branches, pull_requests
from sonar import applications, app_branches, portfolios
from sonar import rules, issues, hotspots, metrics, measures
from sonar import qualitygates, qualityprofiles
from sonar import devops, settings, tasks, tokens, webhooks


def clear(endpoint: Optional[platform.Platform] = None) -> None:
    """
    Clear the cache of a given class
    :param Platform endpoint: Optional, clears only the cache for this platform if specified, clear all if not
    """
    for obj_class in (
        projects.Project,
        branches.Branch,
        pull_requests.PullRequest,
        applications.Application,
        app_branches.ApplicationBranch,
        portfolios.Portfolio,
        issues.Issue,
        hotspots.Hotspot,
        metrics.Metric,
        measures.Measure,
        rules.Rule,
        qualitygates.QualityGate,
        qualityprofiles.QualityProfile,
        devops.DevopsPlatform,
        settings.Setting,
        tasks.Task,
        tokens.UserToken,
        webhooks.WebHook,
    ):
        obj_class.clear_cache(endpoint)
