#!/usr/bin/env python3
#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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
    Exports LoC per projects
"""
import sys
import csv
import datetime
from requests import RequestException

from cli import options
import sonar.logging as log
from sonar import platform, portfolios, applications, projects, errcodes, exceptions, version
import sonar.utilities as util
import sonar.util.constants as c
from sonar.util import component_helper

TOOL_NAME = "sonar-loc"


def __get_csv_header_list(**kwargs) -> list[str]:
    """Returns CSV header"""
    arr = [f"# {kwargs[options.COMPONENT_TYPE][0:-1]} key"]
    if kwargs[options.BRANCH_REGEXP]:
        arr.append("branch")
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


def __get_csv_row(o: object, **kwargs) -> tuple[list[str], str]:
    """Returns CSV row of object"""
    d = __get_object_json_data(o, **kwargs)
    parent_type = kwargs[options.COMPONENT_TYPE][:-1]
    arr = [d[k] for k in (parent_type, "branch", "ncloc", f"{parent_type}Name", "lastAnalysis", "tags", "url") if k in d]
    return arr, d["ncloc"]


def __dump_csv(object_list: list[object], file: str, **kwargs) -> None:
    """Dumps LoC of passed list of objects (projects, branches or portfolios) as CSV"""

    if len(object_list) <= 0:
        log.warning("No objects with LoCs to dump, dump skipped")
        return
    obj_type = type(object_list[0]).__name__.lower()
    nb_loc, nb_objects = 0, 0
    with util.open_file(file) as fd:
        writer = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        writer.writerow(__get_csv_header_list(**kwargs))

        for o in object_list:
            arr, loc = __get_csv_row(o, **kwargs)
            writer.writerow(arr)
            nb_objects += 1
            if loc != "":
                nb_loc += loc
            if nb_objects % 50 != 0:
                continue
            if obj_type == "project":
                log.info("%d %ss and %d LoCs, still counting...", nb_objects, obj_type, nb_loc)
            else:
                log.info("%d %ss objects dumped, still working...", nb_objects, obj_type)
    if obj_type == "project":
        log.info("%d %ss and %d LoCs in total", len(object_list), obj_type, nb_loc)
    else:
        log.info("%d %ss objects dumped in total...", len(object_list), obj_type)


def __get_object_json_data(o: object, **kwargs) -> dict[str, str]:
    """Returns the object data as JSON"""
    parent_type = kwargs[options.COMPONENT_TYPE][:-1]
    is_branch = type(o).__name__.lower() in ("branch", "applicationbranch")
    parent_o = o.concerned_object if is_branch else o
    d = {parent_type: parent_o.key, "ncloc": ""}
    try:
        d["ncloc"] = o.loc()
        if is_branch:
            d["branch"] = o.name
        if kwargs[options.WITH_TAGS]:
            d["tags"] = util.list_to_csv(parent_o.get_tags())
        if kwargs[options.WITH_NAME]:
            d[f"{parent_type}Name"] = parent_o.name if is_branch else o.name
        if kwargs[options.WITH_LAST_ANALYSIS]:
            d["lastAnalysis"] = ""
            if o.last_analysis() is not None:
                d["lastAnalysis"] = datetime.datetime.isoformat(o.last_analysis())
        if kwargs[options.WITH_URL]:
            d["url"] = o.url()
    except (ConnectionError, RequestException) as e:
        util.handle_error(e, f"LoC extract of {str(o)} failed", catch_all=True)
    return d


def __dump_json(object_list: list[object], file: str, **kwargs) -> None:
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


def __dump_loc(object_list: list[object], file: str, **kwargs) -> None:
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
    parser.add_argument(
        f"-{options.WITH_NAME_SHORT}",
        f"--{options.WITH_NAME}",
        required=False,
        default=False,
        action="store_true",
        help="Also list the project name on top of the project key",
    )
    parser.add_argument(
        f"-{options.WITH_LAST_ANALYSIS_SHORT}",
        f"--{options.WITH_LAST_ANALYSIS}",
        required=False,
        default=False,
        action="store_true",
        help="Also list the last analysis date on top of nbr of LoC",
    )
    parser.add_argument(
        f"--{options.WITH_TAGS}",
        required=False,
        default=False,
        action="store_true",
        help="Also include project tags in export",
    )
    options.add_url_arg(parser)
    options.add_branch_arg(parser)
    options.add_component_type_arg(parser)
    parser.add_argument(
        "--topLevelOnly",
        required=False,
        default=False,
        action="store_true",
        help="Extracts only toplevel portfolios LoCs, not sub-portfolios",
    )
    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME)
    return args


def __check_options(edition: str, kwargs: dict[str, str]) -> dict[str, str]:
    """Verifies a certain number of options for compatibility with edition"""
    kwargs[options.FORMAT] = util.deduct_format(kwargs[options.FORMAT], kwargs[options.REPORT_FILE])
    if kwargs[options.BRANCH_REGEXP] and edition == c.CE:
        util.final_exit(errcodes.UNSUPPORTED_OPERATION, f"No branches in {edition} edition, aborting...")
    if kwargs[options.COMPONENT_TYPE] == "portfolios" and edition in (c.CE, c.DE):
        util.final_exit(errcodes.UNSUPPORTED_OPERATION, f"No portfolios in {edition} edition, aborting...")
    if kwargs[options.COMPONENT_TYPE] == "portfolios" and kwargs[options.BRANCH_REGEXP]:
        log.warning("Portfolio LoC export selected, branch option is ignored")
        kwargs[options.BRANCH_REGEXP] = None
    return kwargs


def main() -> None:
    """sonar-loc entry point"""
    start_time = util.start_clock()
    try:
        kwargs = util.convert_args(
            __parse_args("Extract projects, applications or portfolios lines of code - for projects LoC it is as computed for the license")
        )
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        portfolios.Portfolio.CACHE.clear()
        applications.Application.CACHE.clear()
        projects.Project.CACHE.clear()

        kwargs = __check_options(endpoint.edition(), kwargs)

        objects_list = component_helper.get_components(
            endpoint=endpoint,
            component_type=kwargs[options.COMPONENT_TYPE],
            key_regexp=kwargs[options.KEY_REGEXP],
            branch_regexp=kwargs[options.BRANCH_REGEXP],
            topLevelOnly=kwargs["topLevelOnly"],
        )
        if len(objects_list) == 0:
            raise exceptions.SonarException(f"No object matching regexp '{kwargs[options.KEY_REGEXP]}'", errcodes.WRONG_SEARCH_CRITERIA)
        __dump_loc(objects_list, **kwargs)
    except exceptions.SonarException as e:
        util.final_exit(e.errcode, e.message)
    except (PermissionError, FileNotFoundError) as e:
        util.final_exit(errcodes.OS_ERROR, f"OS error while writing LoCs: {e}")

    util.final_exit(0, start_time=start_time)


if __name__ == "__main__":
    main()
