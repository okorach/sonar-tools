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

from cli import options
import sonar.logging as log
from sonar import metrics, platform, exceptions, errcodes
from sonar import projects, applications, portfolios
import sonar.utilities as util

RATINGS = "letters"
PERCENTS = "float"
DATEFMT = "datetime"
CONVERT_OPTIONS = {"ratings": "letters", "percents": "float", "dates": "datetime"}


def __last_analysis(component: object) -> str:
    """Returns the last analysis of a component as a string"""
    last_analysis = component.last_analysis()
    if last_analysis is None:
        last_analysis = "Never"
    else:
        last_analysis = util.date_to_string(last_analysis, CONVERT_OPTIONS["dates"] != "dateonly")
    return last_analysis


def __get_json_measures_history(obj: object, wanted_metrics: list[str]) -> dict[str, str]:
    """Returns the measure history of an object (project, branch, application, portfolio)"""
    data = {}
    try:
        data["history"] = obj.get_measures_history(wanted_metrics)
    except HTTPError as e:
        log.error("HTTP Error %s, measures history export of %s skipped", str(e), str(obj))
    return data


def __get_object_measures(obj: object, wanted_metrics: list[str]) -> dict[str, str]:
    """Returns the list of requested measures of an object"""
    log.info("Getting measures for %s", str(obj))
    measures_d = {k: v.value if v else None for k, v in obj.get_measures(wanted_metrics).items()}
    measures_d["lastAnalysis"] = __last_analysis(obj)
    measures_d.pop("quality_gate_details", None)
    return measures_d


def __get_wanted_metrics(endpoint: platform.Platform, wanted_metrics: list[str]) -> list[str]:
    """Returns an ordered list of metrics based on CLI inputs"""
    if wanted_metrics[0] == "_all":
        all_metrics = list(metrics.search(endpoint).keys())
        all_metrics.remove("quality_gate_details")
        # Hack: With SonarQube 7.9 and below new_development_cost measure can't be retrieved
        if not endpoint.is_sonarcloud() and endpoint.version() < (8, 0, 0):
            all_metrics.remove("new_development_cost")
        wanted_metrics = list(metrics.MAIN_METRICS + tuple(set(all_metrics) - set(metrics.MAIN_METRICS)))
    elif wanted_metrics[0] == "_main":
        wanted_metrics = list(metrics.MAIN_METRICS)
    else:
        # Verify that requested metrics do exist
        non_existing_metrics = util.difference(wanted_metrics, metrics.search(endpoint).keys())
        if len(non_existing_metrics) > 0:
            miss = ",".join(non_existing_metrics)
            util.exit_fatal(f"Requested metric keys '{miss}' don't exist", errcodes.NO_SUCH_KEY)
    log.info("Exporting %s metrics", len(wanted_metrics))
    return wanted_metrics


def __parse_args(desc):
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser)
    parser.add_argument(
        f"-{options.METRIC_KEYS_SHORT}",
        f"--{options.METRIC_KEYS}",
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
    parser = options.add_component_type_arg(parser)
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
    args = options.parse_and_check(parser=parser, logger_name="sonar-measures-export")
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
    row = ["key", "date", "name"]
    if w_br:
        row.append("branch")
    row += wanted_metrics
    if w_url:
        row.append("url")

    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(row)
        for component_data in data:
            key = component_data["key"]
            name = component_data["name"]
            branch = component_data.get("branch", "")
            url = component_data.get("url", "")
            hist_data = {}
            if "history" not in component_data:
                continue
            for h in component_data["history"]:
                ts = __get_ts(h[0], **kwargs)
                if ts not in hist_data:
                    hist_data[ts] = {"key": key, "name": name, "branch": branch, "url": url}
                hist_data[ts].update({h[1]: h[2]})

            for ts, row_data in hist_data.items():
                row = [row_data["key"], ts, row_data.get("name", "")]
                if w_br:
                    row.append(row_data.get("branch", ""))
                row += [row_data.get(m, "") for m in wanted_metrics]
                if w_url:
                    row.append(row_data.get("url", ""))
                csvwriter.writerow(row)


def __write_measures_history_csv_as_list(file: str, data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""

    header_list = ["timestamp", "key"]
    if kwargs[options.WITH_BRANCHES]:
        header_list.append("branch")
    header_list += ["metric", "value"]
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(header_list)
        for component_data in data:
            key = component_data["name"]
            if "history" not in component_data:
                continue
            for metric_data in component_data["history"]:
                csvwriter.writerow([__get_ts(metric_data[0], **kwargs), key, metric_data[1], metric_data[2]])


def __write_measures_history_csv(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""
    if kwargs["asTable"]:
        __write_measures_history_csv_as_table(file, wanted_metrics, data, **kwargs)
    else:
        __write_measures_history_csv_as_list(file, data, **kwargs)


def __write_measures_csv(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """writes measures in CSV"""
    header_list = ["key", "type"]
    if kwargs[options.WITH_NAME]:
        header_list.append("name")
    if kwargs[options.WITH_BRANCHES]:
        header_list.append("branch")
    header_list.append("lastAnalysis")
    header_list += wanted_metrics
    if kwargs[options.WITH_URL]:
        header_list.append("url")
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(header_list)
        for comp_data in data:
            row = [comp_data.get(m, "") for m in header_list]
            csvwriter.writerow(row)


def __get_concerned_objects(endpoint: platform.Platform, **kwargs) -> list[projects.Project]:
    """Returns the list of objects concerned by the measures export"""
    try:
        comp_type = kwargs.get("compType", "projects")
        if comp_type == "apps":
            object_list = applications.get_list(endpoint=endpoint, key_list=kwargs[options.KEYS])
        elif comp_type == "portfolios":
            object_list = portfolios.get_list(endpoint=endpoint, key_list=kwargs[options.KEYS])
        else:
            object_list = projects.get_list(endpoint=endpoint, key_list=kwargs[options.KEYS])
    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, errcodes.NO_SUCH_KEY)
    obj_list = []
    log.info("Collecting %s branches", comp_type)
    if kwargs[options.WITH_BRANCHES] and comp_type in ("projects", "apps"):
        for project in object_list.values():
            obj_list += project.branches().values()
    else:
        obj_list = object_list.values()
    return obj_list


def main():
    start_time = util.start_clock()
    kwargs = util.convert_args(__parse_args("Extract measures of projects"))
    endpoint = platform.Platform(**kwargs)

    wanted_metrics = __get_wanted_metrics(endpoint=endpoint, wanted_metrics=kwargs[options.METRIC_KEYS])
    file = kwargs.pop(options.OUTPUTFILE)
    fmt = util.deduct_format(kwargs[options.FORMAT], file)
    edition = endpoint.edition()
    if edition == "community" and kwargs[options.WITH_BRANCHES]:
        log.warning("SonarQube instance is a community edition, branch option ignored")
        kwargs[options.WITH_BRANCHES] = False
    if edition in ("community", "developer") and kwargs[options.COMPONENT_TYPE] == "portfolio":
        log.warning("SonarQube instance is a %s edition, there are no portfolios", edition)
        util.exit_fatal("SonarQube instance is a %s edition, there are no portfolios", exit_code=errcodes.UNSUPPORTED_OPERATION)
    kwargs[options.WITH_NAME] = True

    try:
        obj_list = __get_concerned_objects(endpoint=endpoint, **kwargs)
        nb_branches = len(obj_list)

        measure_list = []
        for obj in obj_list:
            data = obj.component_data()
            try:
                if kwargs["history"]:
                    data.update(__get_json_measures_history(obj, wanted_metrics))
                else:
                    data.update(__get_object_measures(obj, wanted_metrics))
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.FORBIDDEN:
                    log.error("Insufficient permission to retrieve measures of %s, export skipped for this object", str(obj))
                else:
                    log.error("HTTP Error %s while retrieving measures of %s, export skipped for this object", str(e), str(obj))
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
            log.info("File '%s' created", file)
        log.info("%d %s, %d branches", len(obj_list), kwargs[options.COMPONENT_TYPE], nb_branches)
        util.stop_clock(start_time)
        sys.exit(0)
    except exceptions.UnsupportedOperation as e:
        util.stop_clock(start_time)
        util.exit_fatal(e.message, errcodes.UNSUPPORTED_OPERATION)


if __name__ == "__main__":
    main()
