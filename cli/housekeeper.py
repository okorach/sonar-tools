#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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
"""

    Removes obsolete data from SonarQube platform
    Currently:
    - projects, branches, PR not analyzed since a given number of days
    - Tokens not renewed since a given number of days

"""
import sys
import logging

from cli import options
import sonar.logging as log
from sonar import platform, tokens, users, projects, branches, pull_requests
import sonar.utilities as util
import sonar.exceptions as ex
from sonar.audit import config, problem


def get_project_problems(max_days_proj, max_days_branch, max_days_pr, nb_threads, endpoint):
    problems = []
    if max_days_proj < 90:
        log.error("As a safety measure, can't delete projects more recent than 90 days")
        return problems

    settings = {
        "audit.projects.maxLastAnalysisAge": max_days_proj,
        "audit.projects.branches.maxLastAnalysisAge": max_days_branch,
        "audit.projects.pullRequests.maxLastAnalysisAge": max_days_pr,
        "audit.projects.neverAnalyzed": False,
        "audit.projects.duplicates": False,
        "audit.projects.visibility": False,
        "audit.projects.permissions": False,
        "audit.projects.failedTasks": False,
        "audit.projects.exclusions": False,
        "audit.project.scm.disabled": False,
        "audit.projects.analysisWarnings": False,
    }
    settings = config.load(config_name="sonar-audit", settings=settings)
    settings["threads"] = nb_threads
    problems = projects.audit(endpoint=endpoint, audit_settings=settings)
    nb_proj = 0
    total_loc = 0
    project_list = []
    for p in problems:
        key = p.concerned_object.key if p.concerned_object is not None else None
        if key not in project_list and isinstance(p.concerned_object, projects.Project):
            project_list.append(key)
            nb_proj += 1
            total_loc += int(p.concerned_object.get_measure("ncloc", fallback="0"))

    if nb_proj == 0:
        log.info("%d projects older than %d days found during audit", nb_proj, max_days_proj)
    else:
        log.warning(
            "%d projects older than %d days for a total of %d LoC found during audit",
            nb_proj,
            max_days_proj,
            total_loc,
        )
    return problems


def get_user_problems(max_days, endpoint):
    settings = {
        "audit.tokens.maxAge": max_days,
        "audit.tokens.maxUnusedAge": 90,
        # "audit.groups.empty": True,
    }
    settings = config.load(config_name="sonar-audit", settings=settings)
    user_problems = users.audit(endpoint=endpoint, audit_settings=settings)
    nb_problems = len(user_problems)
    loglevel = logging.WARNING
    if nb_problems == 0:
        loglevel = logging.INFO
    log.log(loglevel, "%d user tokens older than %d days, or unused since 90 days, found during audit", nb_problems, max_days)
    # group_problems = groups.audit(endpoint=endpoint, audit_settings=settings)
    # user_problems += group_problems
    # nb_problems = len(group_problems)
    # loglevel = logging.WARNING
    # if nb_problems == 0:
    #     loglevel = logging.INFO
    # log.log(loglevel, "%d empty groups found during audit", nb_problems)
    return user_problems


def _parse_arguments():
    _DEFAULT_PROJECT_OBSOLESCENCE = 365
    _DEFAULT_BRANCH_OBSOLESCENCE = 90
    _DEFAULT_PR_OBSOLESCENCE = 30
    _DEFAULT_TOKEN_OBSOLESCENCE = 365
    parser = options.set_common_args("Deletes projects, branches, PR, user tokens not used since a given number of days")
    parser = options.add_thread_arg(parser, "auditing before housekeeping")
    parser.add_argument(
        "--mode",
        required=False,
        choices=["dry-run", "delete"],
        default="dry-run",
        help="""
                        If 'dry-run', script only lists objects (projects, branches, PRs or tokens) to delete,
                        If 'delete' it deletes projects or tokens
                        """,
    )
    parser.add_argument(
        "-P",
        "--projectsMaxAge",
        required=False,
        type=int,
        default=_DEFAULT_PROJECT_OBSOLESCENCE,
        help=f"Deletes projects not analyzed since a given number of days, by default {_DEFAULT_PROJECT_OBSOLESCENCE} days",
    )
    parser.add_argument(
        "-B",
        "--branchesMaxAge",
        required=False,
        type=int,
        default=_DEFAULT_BRANCH_OBSOLESCENCE,
        help=f"Deletes branches not to be kept and not analyzed since a given number of days, by default {_DEFAULT_BRANCH_OBSOLESCENCE} days",
    )
    parser.add_argument(
        "-R",
        "--pullrequestsMaxAge",
        required=False,
        type=int,
        default=_DEFAULT_BRANCH_OBSOLESCENCE,
        help=f"Deletes pull requests not analyzed since a given number of days, by default {_DEFAULT_PR_OBSOLESCENCE} days",
    )
    parser.add_argument(
        "-T",
        "--tokensMaxAge",
        required=False,
        type=int,
        default=_DEFAULT_TOKEN_OBSOLESCENCE,
        help=f"Deletes user tokens older than a certain number of days, by default {_DEFAULT_TOKEN_OBSOLESCENCE} days",
    )
    args = options.parse_and_check(parser=parser, logger_name="sonar-housekeeper")
    return args


def _delete_objects(problems, mode):
    revoked_token_count = 0
    deleted_projects = {}
    deleted_branch_count = 0
    deleted_pr_count = 0
    deleted_loc = 0
    for p in problems:
        obj = p.concerned_object
        if obj is None:
            continue  # BUG
        try:
            if isinstance(obj, projects.Project):
                loc = int(obj.get_measure("ncloc", fallback="0"))
                if mode == "delete":
                    log.info("Deleting %s, %d LoC", str(obj), loc)
                else:
                    log.info("%s, %d LoC should be deleted", str(obj), loc)
                if mode != "delete" or obj.delete():
                    deleted_projects[obj.key] = obj
                    deleted_loc += loc
            if isinstance(obj, branches.Branch):
                if obj.concerned_object.key in deleted_projects:
                    log.info("%s deleted, so no need to delete %s", str(obj.concerned_object), str(obj))
                elif mode != "delete" or obj.delete():
                    deleted_branch_count += 1
            if isinstance(obj, pull_requests.PullRequest):
                if obj.project.key in deleted_projects:
                    log.info("%s deleted, so no need to delete %s", str(obj.project), str(obj))
                elif mode != "delete" or obj.delete():
                    deleted_pr_count += 1
            if isinstance(obj, tokens.UserToken) and (mode != "delete" or obj.revoke()):
                revoked_token_count += 1
        except ex.ObjectNotFound:
            log.warning("%s does not exist, deletion skipped...", str(obj))

    return (
        len(deleted_projects),
        deleted_loc,
        deleted_branch_count,
        deleted_pr_count,
        revoked_token_count,
    )


def main():
    start_time = util.start_clock()
    kwargs = util.convert_args(_parse_arguments())
    sq = platform.Platform(**kwargs)
    mode, proj_age, branch_age, pr_age, token_age = (
        kwargs["mode"],
        kwargs["projectsMaxAge"],
        kwargs["branchesMaxAge"],
        kwargs["pullrequestsMaxAge"],
        kwargs["tokensMaxAge"],
    )
    problems = []
    if proj_age > 0 or branch_age > 0 or pr_age > 0:
        problems = get_project_problems(proj_age, branch_age, pr_age, kwargs[options.NBR_THREADS], sq)

    if token_age:
        problems += get_user_problems(token_age, sq)

    problem.dump_report(problems, file=None, format="csv")

    op = "to delete"
    if mode == "delete":
        op = "deleted"
    (deleted_proj, deleted_loc, deleted_branches, deleted_prs, revoked_tokens) = _delete_objects(problems, mode)

    log.info("%d projects older than %d days (%d LoCs) %s", deleted_proj, proj_age, deleted_loc, op)
    log.info("%d branches older than %d days %s", deleted_branches, branch_age, op)
    log.info("%d pull requests older than %d days %s", deleted_prs, pr_age, op)
    log.info("%d tokens older than %d days revoked", revoked_tokens, token_age)
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
