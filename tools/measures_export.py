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
    Exports some measures of all projects
    - Either all measures (-m _all)
    - Or the main measures (-m _main)
    - Or a custom selection of measures (-m <measure1,measure2,measure3...>)
"""
import sys
import csv
from http import HTTPStatus
from requests.exceptions import HTTPError
from sonar import metrics, platform, options, exceptions
from sonar.projects import projects
import sonar.utilities as util

RATINGS = "letters"
PERCENTS = "float"
DATEFMT = "datetime"
CONVERT_OPTIONS = {"ratings": "letters", "percents": "float", "dates": "datetime"}


def __last_analysis(project_or_branch):
    last_analysis = project_or_branch.last_analysis()
    with_time = True
    if CONVERT_OPTIONS["dates"] == "dateonly":
        with_time = False
    if last_analysis is None:
        last_analysis = "Never"
    else:
        last_analysis = util.date_to_string(last_analysis, with_time)
    return last_analysis


def __get_json_measures_history(obj: object, wanted_metrics: list[str]) -> dict[str, str]:
    """Returns the measure history of an object (project, branch, application, portfolio)"""
    data = {}
    try:
        data["history"] = obj.get_measures_history(wanted_metrics)
    except HTTPError as e:
        util.logger.error("HTTP Error %s, measures history export of %s skipped", str(e), str(obj))
    return data


def __get_object_measures(obj, wanted_metrics):
    util.logger.info("Getting measures for %s", str(obj))
    measures_d = {k: v.value if v else None for k, v in obj.get_measures(wanted_metrics).items()}
    measures_d["lastAnalysis"] = __last_analysis(obj)
    measures_d["url"] = obj.url()
    measures_d.pop("quality_gate_details", None)
    proj = obj
    if not isinstance(obj, projects.Project):
        proj = obj.concerned_object
        measures_d["branch"] = obj.name
    measures_d["projectKey"] = proj.key
    measures_d["projectName"] = proj.name
    return measures_d


def __get_wanted_metrics(kwargs: dict[str, str], endpoint: platform.Platform) -> list[str]:
    """Returns an ordered list of metrics based on CLI inputs"""
    wanted_metrics = kwargs["metricKeys"]
    if wanted_metrics[0] == "_all":
        all_metrics = list(metrics.search(endpoint).keys())
        all_metrics.remove("quality_gate_details")
        # Hack: With SonarQube 7.9 and below new_development_cost measure can't be retrieved
        if endpoint.version() < (8, 0, 0):
            all_metrics.remove("new_development_cost")
        wanted_metrics = list(metrics.MAIN_METRICS + tuple(set(all_metrics) - set(metrics.MAIN_METRICS)))
    elif wanted_metrics[0] == "_main":
        wanted_metrics = list(metrics.MAIN_METRICS)
    else:
        # Verify that requested metrics do exist
        non_existing_metrics = util.difference(wanted_metrics, metrics.search(endpoint).keys())
        if len(non_existing_metrics) > 0:
            miss = ",".join(non_existing_metrics)
            util.exit_fatal(f"Requested metric keys '{miss}' don't exist", options.ERR_NO_SUCH_KEY)
    util.logger.info("Exporting %s metrics", len(wanted_metrics))
    return wanted_metrics


def __parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_key_arg(parser)
    parser = util.set_output_file_args(parser)
    parser.add_argument(
        "-m",
        "--metricKeys",
        required=False,
        default="_main",
        help="Comma separated list of metrics or _all or _main",
    )
    options.add_branch_arg(parser)
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
        f"--{options.WITH_HISTORY}",
        action="store_true",
        default=False,
        required=False,
        help="Reports measures history not just last value",
    )
    parser.add_argument(
        "--asTable",
        action="store_true",
        default=False,
        required=False,
        help="Report measures history as table, instead of <date>,<metric>,<measure>",
    )
    options.add_dateformat_arg(parser)
    options.add_url_arg(parser)
    args = util.parse_and_check(parser=parser, logger_name="sonar-measures-export")
    if args.ratingsAsNumbers:
        CONVERT_OPTIONS["ratings"] = "numbers"
    if args.percentsAsString:
        CONVERT_OPTIONS["percents"] = "percents"
    if args.datesWithoutTime:
        CONVERT_OPTIONS["dates"] = "dateonly"

    return args


def __get_ts(ts: str, **kwargs) -> str:
    """Return datetime or date only depending on cmd line options"""
    if kwargs[options.DATES_WITHOUT_TIME]:
        ts = ts.split("T")[0]
    return ts


def __write_measures_history_csv_as_table(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""

    w_br, w_url = kwargs[options.WITH_BRANCHES], kwargs[options.WITH_URL]
    row = ["projectKey", "date", "projectName"]
    if w_br:
        row.append("branch")
    row += wanted_metrics
    if w_url:
        row.append("url")

    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(row)
        for project_data in data:
            key = project_data["projectKey"]
            name = project_data["projectName"]
            branch = project_data.get("branch", "")
            url = project_data.get("url", "")
            hist_data = {}
            if "history" not in project_data:
                continue
            for h in project_data["history"]:
                ts = __get_ts(h[0], **kwargs)
                if ts not in hist_data:
                    hist_data[ts] = {"projectKey": key, "projectName": name, "branch": branch, "url": url}
                hist_data[ts].update({h[1]: h[2]})

            for ts, row_data in hist_data.items():
                row = [row_data["projectKey"], ts, row_data.get("projectName", "")]
                if w_br:
                    row.append(row_data.get("branch", ""))
                row += [row_data.get(m, "") for m in wanted_metrics]
                if w_url:
                    row.append(row_data.get("url", ""))
                csvwriter.writerow(row)


def __write_measures_history_csv_as_list(file: str, data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""

    header_list = ["timestamp", "projectKey"]
    if kwargs[options.WITH_BRANCHES]:
        header_list.append("branch")
    header_list += ["metric", "value"]
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(header_list)
        for project_data in data:
            key = project_data["projectKey"]
            if "history" not in project_data:
                continue
            for metric_data in project_data["history"]:
                csvwriter.writerow([__get_ts(metric_data[0], **kwargs), key, metric_data[1], metric_data[2]])


def __write_measures_history_csv(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""
    if kwargs["asTable"]:
        __write_measures_history_csv_as_table(file, wanted_metrics, data, **kwargs)
    else:
        __write_measures_history_csv_as_list(file, data, **kwargs)


def __write_measures_csv(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """writes measures in CSV"""
    header_list = ["projectKey"]
    if kwargs[options.WITH_NAME]:
        header_list.append("projectName")
    if kwargs[options.WITH_BRANCHES]:
        header_list.append("branch")
    header_list.append("lastAnalysis")
    header_list += wanted_metrics
    if kwargs[options.WITH_URL]:
        header_list.append("url")
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(header_list)
        for project_data in data:
            row = []
            for m in header_list:
                row.append(project_data.get(m, ""))
            csvwriter.writerow(row)


def __general_object_data(obj: object, **kwargs) -> dict[str, str]:
    """Return general project/branch data"""
    data = {}
    proj = obj
    if kwargs[options.WITH_BRANCHES] and not isinstance(obj, projects.Project):
        proj = obj.concerned_object
        data["branch"] = obj.key
    data["projectKey"] = proj.key
    if kwargs[options.WITH_URL]:
        data["url"] = obj.url()
    if kwargs[options.WITH_NAME]:
        data["projectName"] = proj.name
    return data


def main():
    start_time = util.start_clock()
    kwargs = util.convert_args(__parse_args("Extract measures of projects"))
    endpoint = platform.Platform(**kwargs)

    wanted_metrics = __get_wanted_metrics(kwargs, endpoint)
    file = kwargs.pop("file")
    fmt = util.deduct_format(kwargs["format"], file)
    if endpoint.edition() == "community":
        kwargs[options.WITH_BRANCHES] = False
    kwargs[options.WITH_NAME] = True

    try:
        project_list = projects.get_list(endpoint=endpoint, key_list=kwargs["projectKeys"])
    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, options.ERR_NO_SUCH_KEY)
    obj_list = []
    if kwargs[options.WITH_BRANCHES]:
        for project in project_list.values():
            obj_list += project.branches().values()
    else:
        obj_list = project_list.values()
    nb_branches = len(obj_list)

    measure_list = []
    for obj in obj_list:
        data = __general_object_data(obj=obj, **kwargs)
        try:
            if kwargs["history"]:
                data.update(__get_json_measures_history(obj, wanted_metrics))
            else:
                data.update(__get_object_measures(obj, wanted_metrics))
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.FORBIDDEN:
                util.logger.error("Insufficient permission to retrieve measures of %s, export skipped for this object", str(obj))
            else:
                util.logger.error("HTTP Error %s while retrieving measures of %s, export skipped for this object", str(e), str(obj))
            continue
        measure_list += [data]

    if fmt == "json":
        with util.open_file(file) as fd:
            print(util.json_dump(measure_list), file=fd)
    elif kwargs["history"]:
        __write_measures_history_csv(file, wanted_metrics, measure_list, **kwargs)
    else:
        __write_measures_csv(file=file, wanted_metrics=wanted_metrics, data=measure_list, **kwargs)

    if file:
        util.logger.info("File '%s' created", file)
    util.logger.info("%d PROJECTS %d branches", len(project_list), nb_branches)
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
