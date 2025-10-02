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

"""Cache manager"""

from typing import Optional
from sonar import logging as log
from sonar import (
    projects,
    branches,
    pull_requests,
    issues,
    hotspots,
    measures,
    metrics,
    users,
    groups,
    rules,
    languages,
    qualityprofiles,
    qualitygates,
    portfolios,
    applications,
    app_branches,
    devops,
    organizations,
    portfolio_reference,
    settings,
    tokens,
    webhooks,
    tasks,
)
from sonar.permissions import permission_templates


def clear_cache(class_list: Optional[tuple] = None) -> None:
    """Clears the cache"""
    if class_list is None:
        class_list = (
            projects.Project,
            branches.Branch,
            pull_requests.PullRequest,
            issues.Issue,
            hotspots.Hotspot,
            measures.Measure,
            metrics.Metric,
            users.User,
            groups.Group,
            rules.Rule,
            languages.Language,
            qualityprofiles.QualityProfile,
            qualitygates.QualityGate,
            portfolios.Portfolio,
            applications.Application,
            app_branches.ApplicationBranch,
            devops.DevopsPlatform,
            organizations.Organization,
            portfolio_reference.PortfolioReference,
            settings.Setting,
            tasks.Task,
            tokens.UserToken,
            permission_templates.PermissionTemplate,
            webhooks.WebHook,
        )
    log.info("Clearing cache")
    for a_class in class_list:
        a_class.CACHE.clear()
