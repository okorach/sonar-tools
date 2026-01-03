#!/usr/bin/env python3
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

import datetime
from typing import Optional, Union, Any

from cli import options
import sonar.logging as log
from sonar.platform import Platform
from sonar import syncer, exceptions, projects, branches, version
import sonar.util.misc as util
import sonar.utilities as sutil
import sonar.util.common_helper as chelp

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
    parser.add_argument(
        "--tag",
        required=False,
        default="synchronized",
        help="tag to set on synchronized issues, default is 'synchronized', set to '' if you don't want any tag",
    )
    return options.parse_and_check(parser=parser, logger_name=TOOL_NAME)


def __dump_report(report: dict[str, Any], file: Optional[str]) -> None:
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
            since = util.to_date(kwargs["sinceDate"]).replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            log.warning("sinceDate value '%s' is not in the expected YYYY-MM-DD date format, ignored", kwargs["sinceDate"])
    return since


def __get_objects_pairs_to_sync(
    source_env: Platform, target_env: Platform, **kwargs: Any
) -> tuple[Union[projects.Project, branches.Branch], Union[projects.Project, branches.Branch]]:
    """Returns the 2 objects to compare (projects or branches)"""
    source_pattern = kwargs.get(options.KEY_REGEXP, ".+")
    source_projects = projects.get_matching_list(endpoint=source_env, pattern=source_pattern)
    target_pattern = kwargs.get("targetProjectKey", source_pattern)
    target_projects = projects.get_matching_list(endpoint=target_env, pattern=target_pattern)
    sync_list = ()
    if len(source_projects) > 1:
        for src_proj in source_projects.values():
            tgt_proj = next((p for p in target_projects.values() if p.key == src_proj.key), None)
            if tgt_proj:
                sync_list += ((src_proj, tgt_proj),)
        return sync_list
    elif len(source_projects) == 1 and len(target_projects) == 1:
        src_obj = list(source_projects.values())[0]
        tgt_obj = list(target_projects.values())[0]
        if source_branch := kwargs.get("sourceBranch", None):
            src_obj = branches.Branch.get_object(endpoint=src_obj.endpoint, project_key=src_obj.key, branch_name=source_branch)
        if target_branch := kwargs.get("targetBranch", None):
            tgt_obj = branches.Branch.get_object(endpoint=tgt_obj.endpoint, project_key=tgt_obj.key, branch_name=target_branch)
        return ((src_obj, tgt_obj),)
    return ((None, None),)


def main() -> None:
    """Main entry point"""
    start_time = util.start_clock()
    try:
        args = __parse_args(
            "Synchronizes findings changelog of different branches of same or different projects, "
            "see: https://pypi.org/project/sonar-tools/#sonar-findings-sync"
        )
        params = sutil.convert_args(args)
        source_env = Platform(**params)
        source_env.verify_connection()
        source_env.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        sutil.check_token(args.tokenTarget)

        target_params = sutil.convert_args(args, second_platform=True)
        target_env = Platform(**target_params)
        target_env.verify_connection()
        target_env.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        params["login"] = target_env.user()
        if params["login"] == "admin":
            raise options.ArgumentsError("sonar-findings-sync should not be run with 'admin' user token, but with an account dedicated to sync")

        settings = {
            syncer.SYNC_ADD_LINK: not params["nolink"],
            syncer.SYNC_ASSIGN: True,
            syncer.SYNC_IGNORE_COMPONENTS: False,
            syncer.SYNC_SERVICE_ACCOUNT: params["login"],
            syncer.SYNC_SINCE_DATE: __since_date(**params),
            syncer.SYNC_THREADS: params[options.NBR_THREADS],
            syncer.SYNC_TAG: params.get("tag", ""),
        }

        report, counters = [], {}
        pairs = __get_objects_pairs_to_sync(source_env, target_env, **params)
        i, total = 0, len(pairs)
        for source_obj, target_obj in pairs:
            log.info("Syncing findings between %s with %s - Global progress = %d/%d = %d%%", source_obj, target_obj, i, total, (i * 100) // total)
            if source_obj is None or target_obj is None:
                raise options.ArgumentsError("Provided arguments do not select any projects or branches to sync, aborting...")
            settings[syncer.SYNC_IGNORE_COMPONENTS] = source_obj.project_key() != target_obj.project_key()
            (obj_report, obj_counters) = source_obj.sync(target_obj, sync_settings=settings)
            report += obj_report
            counters = util.dict_add(counters, obj_counters)
            i += 1

        __dump_report(report, args.file)
        __COUNTER_MAP = {
            syncer.EXACT_MATCH: "were synchronized successfully",
            syncer.APPROX_MATCH: "could not be synchronized because the match was approximate",
            syncer.MULTIPLE_MATCHES: "could not be synchronized because there were multiple matches",
            syncer.NO_MATCH: "could not be synchronized because no match was found in target",
            "nb_tgt_has_changelog": "were not synchronized because target finding has a more recent changelog",
            "exception": "could not be synchronized because of unexpected exception",
        }
        for t in "issues", "hotspots":
            log.info("%d %s needed to be synchronized", counters.get(f"{t}_nb_to_sync", 0), t)
            if counters.get(f"{t}_nb_to_sync", 0) > 0:
                for key, desc in __COUNTER_MAP.items():
                    log.info("   %d %s %s", counters.get(f"{t}_{key}", 0), t, desc)

    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)
    chelp.clear_cache_and_exit(0, start_time=start_time)


if __name__ == "__main__":
    main()
