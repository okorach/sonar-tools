#!/usr/bin/env python3
#
# sonar-tools
# Copyright (C) 2022-2026 Olivier Korach
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
"""Exports LoC per projects"""

from typing import Any
import csv
import datetime
from requests import RequestException

from cli import options
import sonar.logging as log
from sonar import platform, portfolios, applications, projects, errcodes, exceptions, version
import sonar.utilities as sutil
import sonar.util.misc as util
import sonar.util.constants as c
from sonar.util import component_helper
import sonar.util.common_helper as chelp

TOOL_NAME = "sonar-loc"


def __get_csv_header_list(**kwargs: Any) -> list[str]:
    """Returns CSV header"""
    arr = [f"# {kwargs[options.COMPONENT_TYPE][0:-1]} key", "type", "branch", "pr"]
    arr.append("ncloc")
    if kwargs[options.WITH_NAME]:
        arr.append(f"{kwargs[options.COMPONENT_TYPE][0:-1]} name")
    if kwargs[options.WITH_LAST_ANALYSIS]:
        arr.append("last analysis")
    if kwargs[options.WITH_TAGS]:
        arr.append("tags")
    if kwargs[options.WITH_URL]:
        arr.append("URL")
    return arr


def __get_csv_row(o: object, **kwargs: Any) -> tuple[list[str], str]:
    """Returns CSV row of object"""
    d = __get_object_json_data(o, **kwargs)
    parent_type = kwargs[options.COMPONENT_TYPE][:-1]
    arr = [d[parent_type], type(o).__name__.lower(), d["branch"], d["pr"]]
    # Add the rest of the columns as before
    arr += [d[k] for k in ("ncloc", f"{parent_type}Name", "lastAnalysis", "tags", "url") if k in d]
    return arr, d["ncloc"]


def __dump_csv(object_list: list[object], file: str, **kwargs: Any) -> None:
    """Dumps LoC of passed list of objects (projects, apps or portfolios) as CSV"""
    if len(object_list) <= 0:
        log.warning("No objects with LoCs to dump, dump skipped")
        return
    obj_type = type(object_list[0]).__name__.lower()
    nb_objects = 0
    # For correct sum: group by project key, take max ncloc per project
    project_max_loc = {}
    with util.open_file(file) as fd:
        writer = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        writer.writerow(__get_csv_header_list(**kwargs))

        for o in object_list:
            arr, _ = __get_csv_row(o, **kwargs)
            writer.writerow(arr)
            nb_objects += 1
            # arr[0] is project key, arr[3] (or arr[-1] if columns change) is ncloc
            project_key = arr[0]
            try:
                ncloc = int(arr[3])
            except (ValueError, IndexError):
                ncloc = 0
            if project_key not in project_max_loc or ncloc > project_max_loc[project_key]:
                project_max_loc[project_key] = ncloc
            if nb_objects % 50 != 0:
                continue
            log.info("%d objects dumped, still working...", nb_objects)
    total_projects = len(project_max_loc)
    total_loc = sum(project_max_loc.values())
    log.info("%d %s (grouped) and %d LoCs in total (max per project)", total_projects, obj_type, total_loc)


def __get_object_json_data(o: object, **kwargs: Any) -> dict[str, str]:
    """Returns the object data as JSON"""
    parent_type = kwargs[options.COMPONENT_TYPE][:-1]
    otype = type(o).__name__.lower()
    is_branch = otype in ("branch", "applicationbranch")
    is_pr = otype == "pullrequest"
    parent_o = o.concerned_object if (is_branch or is_pr) else o
    d = {parent_type: parent_o.key, "ncloc": ""}
    try:
        d["ncloc"] = o.loc()
        # Always fill branch: for project use 'main' or '', for branch use name, for PR use key
        d["branch"] = o.name if is_branch else ""
        d["pr"] = o.key if is_pr else ""
        if kwargs[options.WITH_TAGS]:
            d["tags"] = util.list_to_csv(parent_o.get_tags())
        if kwargs[options.WITH_NAME]:
            d[f"{parent_type}Name"] = parent_o.name if (is_branch or is_pr) else o.name
        if kwargs[options.WITH_LAST_ANALYSIS]:
            d["lastAnalysis"] = ""
            if (last_ana := o.last_analysis()) is not None:
                d["lastAnalysis"] = datetime.datetime.isoformat(last_ana)
        if kwargs[options.WITH_URL]:
            d["url"] = o.url()
    except (ConnectionError, RequestException) as e:
        sutil.handle_error(e, f"LoC extract of {o} failed", catch_all=True)
    return d


def __dump_json(object_list: list[object], file: str, **kwargs: Any) -> None:
    """Dumps LoC of passed list of objects (projects, branches or portfolios) as JSON"""
    nb_loc, nb_objects = 0, 0
    data = []
    if len(object_list) <= 0:
        log.warning("No objects with LoCs to dump, dump skipped")
        return
    obj_type = type(object_list[0]).__name__.lower()
    # Collect all objects data
    for o in object_list:
        data.append(__get_object_json_data(o, **kwargs))
        nb_objects += 1
        if nb_objects % 50 != 0:
            continue
        if obj_type == "project":
            log.info("%d %ss and %d LoCs, still counting...", nb_objects, str(obj_type), nb_loc)
        else:
            log.info("%d %ss dumped, still counting...", nb_objects, str(obj_type))

    with util.open_file(file) as fd:
        print(util.json_dump(data), file=fd)
    if obj_type == "project":
        log.info("%d %ss and %d LoCs in total", len(object_list), str(obj_type), nb_loc)
    else:
        log.info("%d %ss dumped in total", len(object_list), str(obj_type))


def __dump_loc(object_list: list[object], file: str, **kwargs: Any) -> None:
    """Dumps the LoC of collection of objects either in CSV or JSON format"""
    log.info("%d objects with LoCs to export, in format %s...", len(object_list), kwargs[options.FORMAT])
    if kwargs[options.FORMAT] == "json":
        __dump_json(object_list, file, **kwargs)
    else:
        __dump_csv(object_list, file, **kwargs)


def __parse_args(desc: str) -> object:
    """Defines and parses CLI arguments"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json", "csv"))

    args = [f"-{options.WITH_NAME_SHORT}", f"--{options.WITH_NAME}"]
    options.add_optional_arg(parser, *args, action="store_true", help="Also list the project name on top of the project key")

    args = [f"-{options.WITH_LAST_ANALYSIS_SHORT}", f"--{options.WITH_LAST_ANALYSIS}"]
    options.add_optional_arg(parser, *args, action="store_true", help="Also list the last analysis date on top of nbr of LoC")

    options.add_optional_arg(parser, f"--{options.WITH_TAGS}", action="store_true", help="Also include project tags in export")

    args = [f"-{options.PULL_REQUESTS_SHORT}", f"--{options.PULL_REQUESTS}"]
    options.add_optional_arg(parser, *args, action="store_true", help="Include pull requests in LoC export")

    options.add_url_arg(parser)
    options.add_branch_arg(parser)
    options.add_component_type_arg(parser)

    help_str = "Extracts only toplevel portfolios LoCs, not sub-portfolios"
    options.add_optional_arg(parser, "--topLevelOnly", action="store_true", help=help_str)

    return options.parse_and_check(parser=parser, logger_name=TOOL_NAME)


def __check_options(edition: str, kwargs: dict[str, str]) -> dict[str, str]:
    """Verifies a certain number of options for compatibility with edition"""
    kwargs[options.FORMAT] = util.deduct_format(kwargs[options.FORMAT], kwargs[options.REPORT_FILE])
    if kwargs[options.BRANCH_REGEXP] and edition == c.CE:
        chelp.clear_cache_and_exit(errcodes.UNSUPPORTED_OPERATION, f"No branches in {edition} edition, aborting...")
    if kwargs[options.COMPONENT_TYPE] == "portfolios" and edition in (c.CE, c.DE):
        chelp.clear_cache_and_exit(errcodes.UNSUPPORTED_OPERATION, f"No portfolios in {edition} edition, aborting...")
    if kwargs[options.COMPONENT_TYPE] == "portfolios" and kwargs[options.BRANCH_REGEXP]:
        log.warning("Portfolio LoC export selected, branch option is ignored")
        kwargs[options.BRANCH_REGEXP] = None
    return kwargs


def main() -> None:
    """sonar-loc entry point"""
    start_time = util.start_clock()
    try:
        desc = """Extract projects, applications or portfolios lines of code -
        for projects LoC it is as computed for the license"""
        kwargs = sutil.convert_args(__parse_args(desc))
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        portfolios.Portfolio.CACHE.clear()
        applications.Application.CACHE.clear()
        projects.Project.CACHE.clear()

        kwargs = __check_options(endpoint.edition(), kwargs)

        if endpoint.edition() == c.CE and kwargs.get(options.PULL_REQUESTS, False):
            raise exceptions.UnsupportedOperation(f"Option --{options.PULL_REQUESTS} not supported in Community Edition")
        objects_list = component_helper.get_components(
            endpoint=endpoint,
            component_type=kwargs[options.COMPONENT_TYPE],
            key_regexp=kwargs[options.KEY_REGEXP],
            branch_regexp=kwargs[options.BRANCH_REGEXP],
            topLevelOnly=kwargs["topLevelOnly"],
            pull_requests=kwargs.get(options.PULL_REQUESTS, False),
        )
        if len(objects_list) == 0:
            raise exceptions.SonarException(f"No object matching regexp '{kwargs[options.KEY_REGEXP]}'", errcodes.WRONG_SEARCH_CRITERIA)
        __dump_loc(objects_list, **kwargs)
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)
    except (PermissionError, FileNotFoundError) as e:
        chelp.clear_cache_and_exit(errcodes.OS_ERROR, f"OS error while writing LoCs: {e}")

    chelp.clear_cache_and_exit(0, start_time=start_time)


if __name__ == "__main__":
    main()
