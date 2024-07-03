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
    This script propagates the manual issue changes (FP, WF, Change
    of severity, of issue type, comments) from:
    - One project to another (normally on different platforms but not necessarily).
      The 2 platform don't need to be identical in version, edition or plugins
    - One branch of a project to another branch of the same project (normally LLBs)

    Only issues with a 100% match are synchronized. When there's a doubt, nothing is done
"""

import sys
import datetime

from cli import options
import sonar.logging as log
from sonar import platform, syncer, exceptions, projects, branches, errcodes
import sonar.utilities as util

_WITH_COMMENTS = {"additionalFields": "comments"}


def __parse_args(desc):
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser)
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

    args = options.parse_and_check(parser=parser, logger_name="sonar-findings-sync")
    return args


def __dump_report(report, file):
    txt = util.json_dump(report)
    if file is None:
        log.info("Dumping report to stdout")
        print(txt)
    else:
        log.info("Dumping report to file '%s'", file)
        with open(file, "w", encoding="utf-8") as fh:
            print(txt, file=fh)


def main() -> int:
    """Main entry point"""
    start_time = util.start_clock()
    args = __parse_args(
        "Synchronizes issues changelog of different branches of same or different projects, "
        "see: https://pypi.org/project/sonar-tools/#sonar-issues-sync"
    )

    params = util.convert_args(args)
    source_env = platform.Platform(**params)
    source_key = params[options.KEYS][0]
    target_key = params.get("targetProjectKey", None)
    if target_key is None:
        target_key = source_key
    source_url = params[options.URL]
    source_branch = params.get("sourceBranch", None)
    target_branch = params.get("targetBranch", None)
    target_url = params.get("urlTarget", None)
    if target_url is None:
        if source_key == target_key and source_branch is None or target_branch is None:
            util.exit_fatal("Branches must be specified when sync'ing within a same project", errcodes.ARGS_ERROR)
        target_env, target_url = source_env, source_url
    else:
        util.check_token(args.tokenTarget)
        target_params = util.convert_args(args, second_platform=True)
        target_env = platform.Platform(**target_params)
    params["login"] = target_env.user()
    if params["login"] == "admin":
        util.exit_fatal("sonar-findings-sync should not be run with 'admin' user token, but with an account dedicated to sync", errcodes.ARGS_ERROR)

    since = None
    if params["sinceDate"] is not None:
        try:
            since = datetime.datetime.strptime(params["sinceDate"], util.SQ_DATE_FORMAT).replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            log.warning("sinceDate value '%s' is not in the expected YYYY-MM-DD date format, ignored", params["sinceDate"])
    settings = {
        syncer.SYNC_ADD_COMMENTS: not params["nocomment"],
        syncer.SYNC_ADD_LINK: not params["nolink"],
        syncer.SYNC_ASSIGN: True,
        syncer.SYNC_IGNORE_COMPONENTS: False,
        syncer.SYNC_SERVICE_ACCOUNTS: util.csv_to_list(params["login"]),
        syncer.SYNC_SINCE_DATE: since,
        syncer.SYNC_THREADS: params["threads"],
    }

    report = []
    try:
        if not projects.exists(source_key, endpoint=source_env):
            raise exceptions.ObjectNotFound(source_key, f"Project key '{source_key}' does not exist")
        if not projects.exists(target_key, endpoint=target_env):
            raise exceptions.ObjectNotFound(source_key, f"Project key '{target_key}' does not exist")
        if source_branch is not None and target_branch is not None:
            log.info("Syncing findings between 2 branches")
            if source_url != target_url or source_branch != target_branch:
                src_branch = branches.Branch.get_object(projects.Project.get_object(source_key, source_env), source_branch)
                tgt_branch = branches.Branch.get_object(projects.Project.get_object(source_key, source_env), target_branch)
                (report, counters) = src_branch.sync(tgt_branch, sync_settings=settings)
            else:
                log.critical("Can't sync same source and target branch or a same project, aborting...")
        else:
            log.info("Syncing findings between 2 projects (branch by branch)")
            settings[syncer.SYNC_IGNORE_COMPONENTS] = target_key != source_key
            src_project = projects.Project.get_object(key=source_key, endpoint=source_env)
            tgt_project = projects.Project.get_object(key=target_key, endpoint=target_env)
            (report, counters) = src_project.sync(tgt_project, sync_settings=settings)

        __dump_report(report, args.file)
        log.info("%d issues needed to be synchronized", counters.get("nb_to_sync", 0))
        log.info("%d issues were synchronized successfully", counters.get("nb_applies", 0))
        log.info(
            "%d issues could not be synchronized because no match was found in target",
            counters.get("nb_no_match", 0),
        )
        log.info(
            "%d issues could not be synchronized because there were multiple matches",
            counters.get("nb_multiple_matches", 0),
        )
        log.info(
            "%d issues could not be synchronized because the match was approximate",
            counters.get("nb_approx_match", 0),
        )
        log.info(
            "%d issues could not be synchronized because target issue already had a changelog",
            counters.get("nb_tgt_has_changelog", 0),
        )

    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, errcodes.NO_SUCH_KEY)
    except exceptions.UnsupportedOperation as e:
        util.exit_fatal(e.message, errcodes.UNSUPPORTED_OPERATION)
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
