#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2024 Olivier Korach
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
    Exports the measures history of projects
    - Either all measures (-m _all)
    - Or the main measures (-m _main)
    - Or a custom selection of measures (-m <measure1,measure2,measure3...>)
"""
import sys
from sonar import metrics, platform, options, exceptions
from sonar.projects import projects
import sonar.utilities as util

RATINGS = "letters"
PERCENTS = "float"
DATEFMT = "datetime"
CONVERT_OPTIONS = {"ratings": "letters", "percents": "float", "dates": "datetime"}


def __get_csv_header(edition: str, **kwargs) -> str:
    """returns the CSV header"""
    sep = kwargs["csvSeparator"]
    header = f"# Project Key:1{sep}Project Name:2{sep}Date:3{sep}Metric:4{sep}Value:5"
    if edition != "community" and kwargs[options.WITH_BRANCHES]:
        header += f"{sep}Branch:6"
    return header


def __get_object_measures(obj: object, wanted_metrics: list[str]) -> dict[str, str]:
    """Returns the measure history of an object (project, branch, application, portfolio)"""
    data = {}
    data["history"] = obj.get_measures_history(wanted_metrics)
    data["url"] = obj.url()
    proj = obj
    if not isinstance(obj, projects.Project):
        proj = obj.concerned_object
        data["branch"] = obj.name
    data["projectKey"] = proj.key
    data["projectName"] = proj.name
    return data


def __get_json_measures(obj: object, wanted_metrics: list[str], **kwargs) -> dict[str, str]:
    """Returns the measure history of an object (project, branch, application, portfolio) as JSON"""
    d = __get_object_measures(obj, wanted_metrics)
    if not kwargs[options.WITH_URL]:
        d.pop("url", None)
    if not kwargs[options.WITH_BRANCHES]:
        d.pop("branch", None)
    return d


def __get_csv_measures(obj: object, wanted_metrics: list[str], **kwargs) -> str:
    """Returns a CSV list of measures history of an object, as CSV string"""
    data = __get_object_measures(obj, wanted_metrics)
    if not kwargs[options.WITH_URL]:
        data.pop("url", None)
    if not kwargs[options.WITH_BRANCHES]:
        data.pop("branch", None)
    sep = kwargs[options.CSV_SEPARATOR]

    line = ""
    projkey = data["projectKey"]
    projname = data["projectName"]
    branch = data.get("branch", "")
    for m in data["history"]:
        if m[1] == "quality_gate_details":
            continue
        if CONVERT_OPTIONS["dates"] == "dateonly":
            m[0] = m[0].split("T")[0]
        line += projkey + sep + projname + sep
        if kwargs[options.WITH_BRANCHES]:
            line += branch + sep
        line += sep.join(m) + "\n"
    return line[:-1]


def __get_wanted_metrics(args: object, endpoint: platform.Platform) -> list[str]:
    """Returns a lits of metrics based on cmd line choices"""
    main_metrics = util.list_to_csv(metrics.MAIN_METRICS)
    wanted_metrics = args.metricKeys
    if wanted_metrics == "_all":
        all_metrics = metrics.search(endpoint).keys()
        # Hack: With SonarQube 7.9 and below new_development_cost measure can't be retrieved
        if endpoint.version() < (8, 0, 0):
            all_metrics.pop("new_development_cost")
        util.logger.info("Exporting %s metrics", len(all_metrics))
        wanted_metrics = main_metrics + "," + util.list_to_csv(set(all_metrics) - set(metrics.MAIN_METRICS))
    elif wanted_metrics == "_main" or wanted_metrics is None:
        wanted_metrics = main_metrics
    return util.csv_to_list(wanted_metrics)


def __get_fmt_and_file(args: object) -> tuple[str, str]:
    """Returns output format and filename based on cmd lines choices"""
    kwargs = vars(args)
    fmt = kwargs["format"]
    fname = kwargs.get("file", None)
    if fname is not None:
        ext = fname.split(".")[-1].lower()
        if ext in ("csv", "json"):
            fmt = ext
    return fmt, fname


def __parse_args(desc: str) -> object:
    """Defines and parses cmd line options"""
    parser = util.set_common_args(desc)
    parser = util.set_key_arg(parser)
    parser = util.set_output_file_args(parser)
    parser.add_argument(
        "-m",
        "--metricKeys",
        required=False,
        help="Comma separated list of metrics or _all or _main",
    )
    parser.add_argument(
        "-b",
        "--" + options.WITH_BRANCHES,
        required=False,
        action="store_true",
        help="Also extract branches metrics",
    )
    parser.add_argument(
        "--withTags",
        required=False,
        action="store_true",
        help="Also extract project tags",
    )
    parser.set_defaults(withBranches=False, withTags=False)
    parser.add_argument(
        "-r",
        "--ratingsAsNumbers",
        action="store_true",
        default=False,
        required=False,
        help="Reports ratings as 12345 numbers instead of ABCDE letters",
    )
    parser.add_argument(
        "-p",
        "--percentsAsString",
        action="store_true",
        default=False,
        required=False,
        help="Reports percentages as string xy.z%% instead of float values 0.xyz",
    )
    parser.add_argument(
        "-d",
        f"--{options.DATES_WITHOUT_TIME}",
        action="store_true",
        default=False,
        required=False,
        help="Reports timestamps only with date, not time",
    )
    parser.add_argument(
        "--" + options.WITH_URL,
        action="store_true",
        default=False,
        required=False,
        help="Add projects/branches URLs in report",
    )
    args = util.parse_and_check(parser)
    if args.ratingsAsNumbers:
        CONVERT_OPTIONS["ratings"] = "numbers"
    if args.percentsAsString:
        CONVERT_OPTIONS["percents"] = "percents"
    if args.datesWithoutTime:
        util.logger.debug("Dates only")
        CONVERT_OPTIONS["dates"] = "dateonly"

    return args


def main() -> None:
    """Main entry point"""
    args = __parse_args("Extract measures of projects")
    endpoint = platform.Platform(
        some_url=args.url, some_token=args.token, org=args.organization, cert_file=args.clientCert, http_timeout=args.httpTimeout
    )

    with_branches = args.withBranches
    if endpoint.edition() == "community":
        with_branches = False

    wanted_metrics = __get_wanted_metrics(args, endpoint)
    (fmt, file) = __get_fmt_and_file(args)

    try:
        project_list = projects.get_list(endpoint=endpoint, key_list=args.projectKeys)
    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, options.ERR_NO_SUCH_KEY)
    is_first = True
    obj_list = []
    if with_branches:
        for project in project_list.values():
            obj_list += project.branches().values()
    else:
        obj_list = project_list.values()
    nb_branches = len(obj_list)

    with util.open_file(file) as fd:
        if fmt == "json":
            print("[", end="", file=fd)
        else:
            print(__get_csv_header(endpoint.edition(), **vars(args)), file=fd)

        for obj in obj_list:
            if fmt == "json":
                if not is_first:
                    print(",", end="", file=fd)
                values = __get_json_measures(obj, wanted_metrics, **vars(args))
                json_str = util.json_dump(values)
                print(json_str, file=fd)
                is_first = False
            else:
                print(__get_csv_measures(obj, wanted_metrics, **vars(args)), file=fd)

        if fmt == "json":
            print("\n]\n", file=fd)

        # Stop computing LoC, this is expensive in API calls
        #    util.logger.info("Computing LoCs")
        #    nb_loc = 0
        #    for project in project_list.values():
        #        nb_loc += project.loc()

        util.logger.info("%d PROJECTS %d branches", len(project_list), nb_branches)
        sys.exit(0)


if __name__ == "__main__":
    main()
