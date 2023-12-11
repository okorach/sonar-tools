#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

from sonar import platform, version, syncer, options, exceptions
from sonar.projects import projects
from sonar.projects.branches import Branch
import sonar.utilities as util

_WITH_COMMENTS = {"additionalFields": "comments"}


def __parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_key_arg(parser)
    parser = util.set_output_file_args(parser)
    parser = util.set_target_sonar_args(parser)
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
        help="""key of the target project when synchronizing 2 projects
                        or 2 branches on a same platform""",
    )
    parser.add_argument(
        "--login",
        required=True,
        help="One (or several comma separated) service account(s) used for issue-sync",
    )
    parser.add_argument(
        "--nocomment",
        required=False,
        default=False,
        action="store_true",
        help="If specified, will not comment related to the sync in the target issue",
    )
    # parser.add_argument('--noassign', required=False, default=False, action='store_true',
    #                    help="If specified, will not apply issue assignment in the target issue")
    parser.add_argument(
        "--nolink",
        required=False,
        default=False,
        action="store_true",
        help="If specified, will not add a link to source issue in the target issue comments",
    )

    args = util.parse_and_check_token(parser)
    util.check_token(args.token)
    return args


def __dump_report(report, file):
    txt = util.json_dump(report)
    if file is None:
        util.logger.info("Dumping report to stdout")
        print(txt)
    else:
        util.logger.info("Dumping report to file '%s'", file)
        with open(file, "w", encoding="utf-8") as fh:
            print(txt, file=fh)


def main():
    args = __parse_args(
        "Synchronizes issues changelog of different branches of same or different projects, "
        "see: https://pypi.org/project/sonar-tools/#sonar-issues-sync"
    )

    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    source_env = platform.Platform(some_url=args.url, some_token=args.token, cert_file=args.clientCert)
    params = vars(args)
    util.check_environment(params)
    source_key = params["projectKeys"]
    target_key = params.get("targetProjectKey", None)
    source_branch = params.get("sourceBranch", None)
    target_branch = params.get("targetBranch", None)
    target_url = params.get("urlTarget", None)

    settings = {
        syncer.SYNC_ADD_COMMENTS: not params["nocomment"],
        syncer.SYNC_ADD_LINK: not params["nolink"],
        syncer.SYNC_ASSIGN: True,
        syncer.SYNC_IGNORE_COMPONENTS: False,
        syncer.SYNC_SERVICE_ACCOUNTS: util.csv_to_list(args.login),
    }
    report = []
    try:
        if not projects.exists(source_key, endpoint=source_env):
            raise exceptions.ObjectNotFound(source_key, f"Project key '{source_key}' does not exist")
        if target_url is None and target_key is None and source_branch is None and target_branch is None:
            # Sync all branches of a given project
            (report, counters) = projects.Project.get_object(key=source_key, endpoint=source_env).sync_branches(sync_settings=settings)
        elif target_url is None and target_key is None and source_branch is not None and target_branch is not None:
            # Sync 2 branches of a given project
            if source_branch != target_branch:
                src_branch = Branch.get_object(projects.Project.get_object(source_key, source_env), source_branch)
                tgt_branch = Branch.get_object(projects.Project.get_object(source_key, source_env), target_branch)
                (report, counters) = src_branch.sync(tgt_branch, sync_settings=settings)
            else:
                util.logger.critical("Can't sync same source and target branch or a same project, aborting...")

        elif target_url is None and target_key is not None:
            # sync 2 branches of 2 different projects of the same platform
            if not projects.exists(target_key, endpoint=source_env):
                raise exceptions.ObjectNotFound(target_key, f"Project key '{target_key}' does not exist")
            settings[syncer.SYNC_IGNORE_COMPONENTS] = target_key != source_key
            src_branch = Branch.get_object(projects.Project.get_object(key=source_key, endpoint=source_env), source_branch)
            tgt_branch = Branch.get_object(projects.Project.get_object(key=target_key, endpoint=source_env), target_branch)
            (report, counters) = src_branch.sync(tgt_branch, sync_settings=settings)

        elif target_url is not None and target_key is not None:
            util.check_token(args.tokenTarget)
            target_env = platform.Platform(some_url=args.urlTarget, some_token=args.tokenTarget, cert_file=args.clientCert)
            if not projects.exists(target_key, endpoint=target_env):
                raise exceptions.ObjectNotFound(target_key, f"Project key '{target_key}' does not exist")
            settings[syncer.SYNC_IGNORE_COMPONENTS] = target_key != source_key
            if source_branch is not None or target_branch is not None:
                # sync main 2 branches of 2 projects on different platforms
                src_branch = Branch.get_object(projects.Project.get_object(key=source_key, endpoint=source_env), source_branch)
                tgt_branch = Branch.get_object(projects.Project.get_object(key=target_key, endpoint=target_env), target_branch)
                (report, counters) = src_branch.sync(tgt_branch, sync_settings=settings)
            else:
                # sync main all branches of 2 projects on different platforms
                src_project = projects.Project.get_object(key=source_key, endpoint=source_env)
                tgt_project = projects.Project.get_object(key=target_key, endpoint=target_env)
                (report, counters) = src_project.sync(tgt_project, sync_settings=settings)

        __dump_report(report, args.file)
        util.logger.info("%d issues needed to be synchronized", counters.get("nb_to_sync", 0))
        util.logger.info("%d issues were synchronized successfully", counters.get("nb_applies", 0))
        util.logger.info(
            "%d issues could not be synchronized because no match was found in target",
            counters.get("nb_no_match", 0),
        )
        util.logger.info(
            "%d issues could not be synchronized because there were multiple matches",
            counters.get("nb_multiple_matches", 0),
        )
        util.logger.info(
            "%d issues could not be synchronized because the match was approximate",
            counters.get("nb_approx_match", 0),
        )
        util.logger.info(
            "%d issues could not be synchronized because target issue already had a changelog",
            counters.get("nb_tgt_has_changelog", 0),
        )

    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, options.ERR_NO_SUCH_KEY)


if __name__ == "__main__":
    main()
