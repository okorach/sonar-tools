#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

from requests import RequestException
from cli import options
import sonar.logging as log
from sonar import platform, tokens, users, projects, branches, pull_requests, version, errcodes
from sonar.util import types
import sonar.util.constants as c
import sonar.utilities as util
import sonar.exceptions as ex
from sonar.audit import problem

TOOL_NAME = "sonar-housekeeper"
PROJ_MAX_AGE = "audit.projects.maxLastAnalysisAge"


def get_project_problems(settings: dict[str, str], endpoint: object) -> list[problem.Problem]:
    """Returns the list of problems that would require housekeeping for a given project"""
    problems = []
    if settings[PROJ_MAX_AGE] != 0 and settings[PROJ_MAX_AGE] < 90:
        log.error("As a safety measure, can't delete projects more recent than 90 days")
        return problems

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

    loglevel = log.WARNING if nb_proj > 0 else log.INFO
    log.log(
        loglevel,
        "%d projects older than %d days found during housekeeping (%d LoC)",
        nb_proj,
        settings[PROJ_MAX_AGE],
        total_loc,
    )
    return problems


def get_user_problems(settings: dict[str, str], endpoint: platform.Platform) -> list[problem.Problem]:
    """Collects problems related to user accounts"""
    user_problems = users.audit(endpoint=endpoint, audit_settings=settings)
    loglevel = log.WARNING if len(user_problems) > 0 else log.INFO
    log.log(
        loglevel,
        "%d user tokens older than %d days, or unused since 90 days, found during housekeeping",
        len(user_problems),
        settings["audit.tokens.maxAge"],
    )
    # group_problems = groups.audit(endpoint=endpoint, audit_settings=settings)
    # user_problems += group_problems
    # nb_problems = len(group_problems)
    # loglevel = log.WARNING if nb_problems > 0 else log.INFO
    # log.log(loglevel, "%d empty groups found during audit", nb_problems)
    return user_problems


def _parse_arguments() -> object:
    """Parses CLI arguments"""
    parser = options.set_common_args("Deletes projects, branches, PR, user tokens not used since a given number of days")
    parser = options.set_output_file_args(parser, allowed_formats=("csv",))
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
        default=0,
        help="Deletes projects not analyzed since a given number of days",
    )
    parser.add_argument(
        "-B",
        "--branchesMaxAge",
        required=False,
        type=int,
        default=0,
        help="Deletes branches not to be kept and not analyzed since a given number of days",
    )
    parser.add_argument(
        "--keepWhenInactive",
        required=False,
        type=str,
        help="Regexp of branches to keep when inactive, overrides the SonarQube default sonar.dbcleaner.branchesToKeepWhenInactive value",
    )
    parser.add_argument(
        "-R",
        "--pullrequestsMaxAge",
        required=False,
        type=int,
        default=0,
        help="Deletes pull requests not analyzed since a given number of days",
    )
    parser.add_argument(
        "-T",
        "--tokensMaxAge",
        required=False,
        type=int,
        default=0,
        help="Deletes user tokens older than a certain number of days",
    )
    return options.parse_and_check(parser=parser, logger_name=TOOL_NAME)


def _delete_objects(problems: problem.Problem, mode: str, settings: types.ConfigSettings) -> tuple[int, int, int, int, int]:
    """Deletes objects (that should be housekept)"""
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
            if isinstance(obj, (tokens.UserToken, users.User)) and (mode != "delete" or obj.revoke()):
                revoked_token_count += 1
            elif settings[PROJ_MAX_AGE] > 0 and obj.project().key in deleted_projects:
                log.info("%s deleted, so no need to delete %s", str(obj.project()), str(obj))
            elif mode != "delete" or obj.delete():
                log.info("%s to delete", str(obj))
                if isinstance(obj, branches.Branch):
                    deleted_branch_count += 1
                elif isinstance(obj, pull_requests.PullRequest):
                    deleted_pr_count += 1

        except ex.ObjectNotFound:
            log.warning("%s does not exist, deletion skipped...", str(obj))

    return (
        len(deleted_projects),
        deleted_loc,
        deleted_branch_count,
        deleted_pr_count,
        revoked_token_count,
    )


def main() -> None:
    """Main entry point"""
    start_time = util.start_clock()
    try:
        kwargs = util.convert_args(_parse_arguments())
        sq = platform.Platform(**kwargs)
        sq.verify_connection()
        sq.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        mode, proj_age, branch_age, pr_age, token_age, keep_regexp = (
            kwargs["mode"],
            kwargs["projectsMaxAge"],
            kwargs["branchesMaxAge"],
            kwargs["pullrequestsMaxAge"],
            kwargs["tokensMaxAge"],
            kwargs.get("keepWhenInactive", None),
        )
        settings = {
            "audit.tokens.maxAge": token_age,
            "audit.tokens.maxUnusedAge": 90,
            PROJ_MAX_AGE: proj_age,
            "audit.projects.branches.maxLastAnalysisAge": branch_age,
            "audit.projects.pullRequests.maxLastAnalysisAge": pr_age,
            "audit.projects.branches.keepWhenInactive": keep_regexp,
            c.AUDIT_MODE_PARAM: "housekeeper",
            options.NBR_THREADS: kwargs[options.NBR_THREADS],
        }
        log.info("Housekeeper settings = %s", util.json_dump(settings))
        problems = []
        if proj_age > 0 or branch_age > 0 or pr_age > 0:
            problems = get_project_problems(settings, sq)

        if token_age:
            problems += get_user_problems(settings, sq)

        problem.dump_report(problems, file=kwargs[options.REPORT_FILE], format="csv")

        op = "to delete"
        if mode == "delete":
            op = "deleted"
        (deleted_proj, deleted_loc, deleted_branches, deleted_prs, revoked_tokens) = _delete_objects(problems, mode, settings=settings)

        if proj_age > 0:
            log.info("%d projects older than %d days (%d LoCs) %s", deleted_proj, proj_age, deleted_loc, op)
        if branch_age > 0:
            log.info("%d branches older than %d days %s", deleted_branches, branch_age, op)
        if pr_age > 0:
            log.info("%d pull requests older than %d days %s", deleted_prs, pr_age, op)
        if token_age > 0:
            log.info("%d tokens older than %d days %s", revoked_tokens, token_age, "revoked" if mode == "deleted" else "to revoke")

    except (PermissionError, FileNotFoundError) as e:
        util.final_exit(errcodes.OS_ERROR, f"OS error while housekeeping: {str(e)}")
    except ex.SonarException as e:
        util.final_exit(e.errcode, e.message)
    except RequestException as e:
        util.final_exit(errcodes.SONAR_API, f"HTTP error while housekeeping: {str(e)}")
    util.final_exit(0, start_time=start_time)


if __name__ == "__main__":
    main()
