#!/usr/local/bin/python3
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
    This script propagates the manual issue changes (FP, WF, Change
    of severity, of issue type, comments) from:
    - One project to another (normally on different platforms but not necessarily).
      The 2 platform don't need to be identical in version, edition or plugins
    - One branch of a project to another branch of the same project (normally LLBs)

    Only issues with a 100% match are synchronized. When there's a doubt, nothing is done
"""

import sys
import datetime
from typing import Optional

from cli import options
import sonar.logging as log
import sonar.platform as pf
from sonar import syncer, exceptions, projects, branches, version
import sonar.utilities as util

TOOL_NAME = "sonar-findings-sync"


def __parse_args(desc: str) -> object:
    """Defines CLI arguments and parses them"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json,"))
    parser = options.set_target_sonar_args(parser)
    parser.add_argument(
        "-r",
        "--recover",
        required=False,
        help="""What information to replicate. Default is FP and WF, but issue assignment,
                        tags, severity and type change can be recovered too""",
    )
    parser.add_argument("-b", "--sourceBranch", required=False, help="Name of the source branch")
    parser.add_argument("-B", "--targetBranch", required=False, help="Name of the target branch")
    parser.add_argument(
        "-K",
        "--targetProjectKey",
        required=False,
        help="""key of the target project when synchronizing 2 projects or 2 branches on a same platform""",
    )
    parser.add_argument(
        "--login",
        required=False,
        help="DEPRECATED, IGNORED: One (or several comma separated) service account(s) used for issue-sync",
    )
    parser.add_argument(
        "--nocomment",
        required=False,
        default=False,
        action="store_true",
        help="If specified, will not comment related to the sync in the target issue",
    )
    parser.add_argument(
        "--sinceDate",
        required=False,
        default=None,
        help="If specified, only sync issues that had a change since the given date (YYYY-MM-DD format)",
    )
    options.add_thread_arg(parser, "issue sync")
    # parser.add_argument('--noassign', required=False, default=False, action='store_true',
    #                    help="If specified, will not apply issue assignment in the target issue")
    parser.add_argument(
        "--nolink",
        required=False,
        default=False,
        action="store_true",
        help="If specified, will not add a link to source issue in the target issue comments",
    )

    return options.parse_and_check(parser=parser, logger_name=TOOL_NAME)


def __dump_report(report: dict[str, any], file: Optional[str]) -> None:
    """Dumps a problem report in a file or stdout"""
    txt = util.json_dump(report)
    if file is None:
        log.info("Dumping report to stdout")
        print(txt)
    else:
        log.info("Dumping report to file '%s'", file)
        with open(file, "w", encoding="utf-8") as fh:
            print(txt, file=fh)


def __since_date(**kwargs) -> Optional[datetime.datetime]:
    """Returns the CLI since date if present None otherwise"""
    since = None
    if kwargs["sinceDate"] is not None:
        try:
            since = datetime.datetime.strptime(kwargs["sinceDate"], util.SQ_DATE_FORMAT).replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            log.warning("sinceDate value '%s' is not in the expected YYYY-MM-DD date format, ignored", kwargs["sinceDate"])
    return since


def __check_comparison_params(source_env: pf.Platform, target_env: pf.Platform, **kwargs) -> tuple[str, str, Optional[str], Optional[str]]:
    """Check input parameters and verfiy they are correct for the desired comparison"""
    source_key = kwargs[options.KEYS][0]
    target_key = kwargs.get("targetProjectKey", source_key)
    source_url = kwargs[options.URL]
    source_branch = kwargs.get("sourceBranch", None)
    target_branch = kwargs.get("targetBranch", None)

    if source_url == kwargs.get("urlTarget", source_url):
        if source_key == target_key:
            if source_branch is None or target_branch is None:
                raise options.ArgumentsError("Branches must be specified when sync'ing within a same project")
            if source_branch == target_branch:
                raise options.ArgumentsError("Specified branches must different when sync'ing within a same project")
        else:
            if source_branch and not target_branch or not source_branch and target_branch:
                raise options.ArgumentsError("One branch or no branch should be specified for each source and target project, aborting...")
    else:
        if source_branch and not target_branch or not source_branch and target_branch:
            raise options.ArgumentsError("One branch or no branch should be specified for each source and target project, aborting...")

    if not projects.exists(source_key, endpoint=source_env):
        raise exceptions.ObjectNotFound(source_key, f"Project key '{source_key}' does not exist")
    if not projects.exists(target_key, endpoint=target_env):
        raise exceptions.ObjectNotFound(target_key, f"Project key '{target_key}' does not exist")

    return source_key, target_key, source_branch, target_branch


def main() -> None:
    """Main entry point"""
    start_time = util.start_clock()
    try:
        args = __parse_args(
            "Synchronizes issues changelog of different branches of same or different projects, "
            "see: https://pypi.org/project/sonar-tools/#sonar-issues-sync"
        )
        params = util.convert_args(args)
        source_env = pf.Platform(**params)
        source_env.verify_connection()
        source_env.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        util.check_token(args.tokenTarget)

        target_params = util.convert_args(args, second_platform=True)
        target_env = pf.Platform(**target_params)
        target_env.verify_connection()
        target_env.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        source_key, target_key, source_branch, target_branch = __check_comparison_params(source_env, target_env, **params)

        params["login"] = target_env.user()
        if params["login"] == "admin":
            raise options.ArgumentsError("sonar-findings-sync should not be run with 'admin' user token, but with an account dedicated to sync")

        settings = {
            syncer.SYNC_ADD_COMMENTS: not params["nocomment"],
            syncer.SYNC_ADD_LINK: not params["nolink"],
            syncer.SYNC_ASSIGN: True,
            syncer.SYNC_IGNORE_COMPONENTS: False,
            syncer.SYNC_SERVICE_ACCOUNTS: util.csv_to_list(params["login"]),
            syncer.SYNC_SINCE_DATE: __since_date(**params),
            syncer.SYNC_THREADS: params["threads"],
        }

        report = []
        counters = {}

        if source_branch and target_branch:
            log.info("Syncing findings between 2 branches")
            src_branch = branches.Branch.get_object(projects.Project.get_object(source_env, source_key), source_branch)
            tgt_branch = branches.Branch.get_object(projects.Project.get_object(target_env, target_key), target_branch)
            (report, counters) = src_branch.sync(tgt_branch, sync_settings=settings)
        else:
            log.info("Syncing findings between 2 projects (branch by branch)")
            settings[syncer.SYNC_IGNORE_COMPONENTS] = target_key != source_key
            src_project = projects.Project.get_object(key=source_key, endpoint=source_env)
            tgt_project = projects.Project.get_object(key=target_key, endpoint=target_env)
            (report, counters) = src_project.sync(tgt_project, sync_settings=settings)

        __dump_report(report, args.file)
        log.info("%d issues needed to be synchronized", counters.get("nb_to_sync", 0))
        log.info("%d issues were synchronized successfully", counters.get("nb_applies", 0))
        log.info("%d issues could not be synchronized because no match was found in target", counters.get("nb_no_match", 0))
        log.info("%d issues could not be synchronized because there were multiple matches", counters.get("nb_multiple_matches", 0))
        log.info("%d issues could not be synchronized because the match was approximate", counters.get("nb_approx_match", 0))
        log.info("%d issues could not be synchronized because target issue already had a changelog", counters.get("nb_tgt_has_changelog", 0))

    except (exceptions.SonarException, options.ArgumentsError) as e:
        util.exit_fatal(e.message, e.errcode)

    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
