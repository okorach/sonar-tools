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
    This script exports findings as CSV, JSON, or SARIF

    Usage: sonar-findings-export.py -t <SQ_TOKEN> -u <SQ_URL> [<filters>]

"""

import sys
import os
import csv
from typing import TextIO
from queue import Queue
from threading import Thread
from argparse import Namespace

from requests import RequestException

from cli import options
from sonar.util.types import ConfigSettings
import sonar.logging as log
from sonar import platform, exceptions, errcodes, version
from sonar import issues, hotspots, findings
from sonar import projects, applications, portfolios
from sonar.util import types
import sonar.utilities as util

TOOL_NAME = "sonar-findings"
TOTAL_FINDINGS = 0
DATES_WITHOUT_TIME = False

SARIF_HEADER = """{
   "version": "2.1.0",
   "$schema": "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.4.json",
   "runs": [
       {
          "tool": {
            "driver": {
                "name": "SonarQube",
                "informationUri": "https://www.sonarsource.com/products/sonarqube/"
            }
          },
          "results": [
"""

_OPTIONS_INCOMPATIBLE_WITH_USE_FINDINGS = (
    options.STATUSES,
    options.DATE_AFTER,
    options.DATE_BEFORE,
    options.RESOLUTIONS,
    options.SEVERITIES,
    options.TYPES,
    options.TAGS,
    options.LANGUAGES,
)


def parse_args(desc: str) -> Namespace:
    """Sets CLI parameters and parses them"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("csv", "json", "sarif"))
    parser = options.add_thread_arg(parser, "findings search")
    parser = options.add_component_type_arg(parser)
    parser.add_argument(
        f"-{options.BRANCHES_SHORT}",
        f"--{options.BRANCHES}",
        required=False,
        default=None,
        help="Comma separated list of branches to export. Use * to export findings from all branches. "
        "If not specified, only findings of the main branch will be exported",
    )
    parser.add_argument(
        f"-{options.PULL_REQUESTS_SHORT}",
        f"--{options.PULL_REQUESTS}",
        required=False,
        default=None,
        help="Comma separated list of pull requests to export. Use * to export findings from all PRs.",
    )
    parser.add_argument(
        f"--{options.STATUSES}",
        required=False,
        help="comma separated status among " + util.list_to_csv(issues.STATUSES + hotspots.STATUSES),
    )
    parser.add_argument(
        f"--{options.DATE_AFTER}",
        required=False,
        help="findings created on or after a given date (YYYY-MM-DD)",
    )
    parser.add_argument(
        f"--{options.DATE_BEFORE}",
        required=False,
        help="findings created on or before a given date (YYYY-MM-DD)",
    )
    parser.add_argument(
        f"--{options.RESOLUTIONS}",
        required=False,
        help="Comma separated resolution of the findings among " + util.list_to_csv(issues.RESOLUTIONS + hotspots.RESOLUTIONS),
    )
    parser.add_argument(
        f"--{options.SEVERITIES}",
        required=False,
        help="Comma separated severities among" + util.list_to_csv(issues.SEVERITIES + hotspots.SEVERITIES),
    )
    parser.add_argument(
        f"--{options.TYPES}",
        required=False,
        help="Comma separated types among " + util.list_to_csv(issues.TYPES + hotspots.TYPES),
    )
    parser.add_argument(f"--{options.TAGS}", help="Comma separated findings tags", required=False)
    parser.add_argument(
        f"--{options.USE_FINDINGS}", required=False, default=False, action="store_true", help="Use export_findings() whenever possible"
    )
    parser.add_argument(
        "--sarifNoCustomProperties",
        required=False,
        default=False,
        action="store_true",
        help="For SARIF export, turn off Sonar custom findings properties, default is turned on",
    )
    options.add_url_arg(parser)
    options.add_dateformat_arg(parser)
    options.add_language_arg(parser, "findings")
    return options.parse_and_check(parser=parser, logger_name=TOOL_NAME)


def __write_header(fd: TextIO, **kwargs) -> None:
    """Writes the file header"""
    if kwargs[options.FORMAT] == "sarif":
        print(SARIF_HEADER, file=fd)
    elif kwargs[options.FORMAT] == "json":
        print("[\n", file=fd)
    else:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        row = findings.to_csv_header(kwargs["sonar"])
        row[0] = "# " + row[0]
        if kwargs[options.WITH_URL]:
            row.append("URL")
        csvwriter.writerow(row)


def __write_footer(fd: TextIO, format: str) -> None:
    """Writes the closing characters of export file depending on export format"""
    if format in ("json", "sarif"):
        closing_sequence = "\n]\n}\n]\n}" if format == "sarif" else "\n]"
        print(f"{closing_sequence}", file=fd)


def __write_json_findings(findings_list: dict[str, findings.Finding], fd: TextIO, **kwargs) -> None:
    """Appends a list of findings in JSON or SARIF format in a file"""
    log.debug("in write_json_findings")
    i = len(findings_list)
    comma = ","
    for finding in findings_list.values():
        i -= 1
        if i == 0:
            comma = ""
        if kwargs[options.FORMAT] == "json":
            json_data = finding.to_json(DATES_WITHOUT_TIME)
        else:
            json_data = finding.to_sarif(kwargs.get("full", True))
        if not kwargs[options.WITH_URL]:
            json_data.pop("url", None)
        print(f"{util.json_dump(json_data, indent=1)}{comma}", file=fd)


def __write_csv_findings(findings_list: dict[str, findings.Finding], fd: TextIO, **kwargs) -> None:
    """Appends a list of findings in a CSV file"""
    csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
    for finding in findings_list.values():
        row = finding.to_csv()
        if kwargs[options.WITH_URL]:
            row.append(finding.url())
        csvwriter.writerow(row)


def __write_findings(queue: Queue[list[findings.Finding]], params: ConfigSettings) -> None:
    """Writes a list of findings in an output file or stdout"""
    global TOTAL_FINDINGS
    TOTAL_FINDINGS = 0
    is_first = True
    file = params[options.REPORT_FILE]
    with util.open_file(file=file) as fd:
        __write_header(fd, **params)
        while True:
            findings_list = queue.get()
            if findings_list == util.WRITE_END:
                log.debug("End of write queue reached")
                queue.task_done()
                break

            log.debug("Processing write queue for project")
            if len(findings_list) == 0:
                queue.task_done()
                continue

            if params[options.FORMAT] in ("sarif", "json") and not is_first:
                print(",", file=fd)
            is_first = False
            log.info(
                "Writing %d more findings to %s in format %s", len(findings_list), f"file '{file}'" if file else "stdout", params[options.FORMAT]
            )
            if params[options.FORMAT] in ("json", "sarif"):
                __write_json_findings(findings_list=findings_list, fd=fd, **params)
            else:
                __write_csv_findings(findings_list=findings_list, fd=fd, **params)
            TOTAL_FINDINGS += len(findings_list)
            queue.task_done()
        __write_footer(fd, params[options.FORMAT])

    log.debug("End of write findings")


def __verify_inputs(params: types.ApiParams) -> bool:
    """Verifies if findings-export inputs are correct"""
    diff = util.difference(util.csv_to_list(params.get(options.RESOLUTIONS, None)), issues.RESOLUTIONS + hotspots.RESOLUTIONS)
    if diff:
        util.exit_fatal(f"Resolutions {str(diff)} are not legit resolutions", errcodes.WRONG_SEARCH_CRITERIA)

    diff = util.difference(util.csv_to_list(params.get(options.STATUSES, None)), issues.STATUSES + hotspots.STATUSES)
    if diff:
        util.exit_fatal(f"Statuses {str(diff)} are not legit statuses", errcodes.WRONG_SEARCH_CRITERIA)

    diff = util.difference(util.csv_to_list(params.get(options.SEVERITIES, None)), issues.SEVERITIES + hotspots.SEVERITIES)
    if diff:
        util.exit_fatal(f"Severities {str(diff)} are not legit severities", errcodes.WRONG_SEARCH_CRITERIA)

    diff = util.difference(util.csv_to_list(params.get(options.TYPES, None)), issues.TYPES + hotspots.TYPES)
    if diff:
        util.exit_fatal(f"Types {str(diff)} are not legit types", errcodes.WRONG_SEARCH_CRITERIA)
    if len(params[options.CSV_SEPARATOR]) > 1:
        util.exit_fatal(f"CSV separator must be a single character, {params[options.CSV_SEPARATOR]} is not legit", errcodes.WRONG_SEARCH_CRITERIA)

    return True


def __get_component_findings(queue: Queue[tuple[object, ConfigSettings]], write_queue: Queue[dict[str, findings.Finding]]) -> None:
    """Gets the findings of a component and puts them in a writing queue"""
    while not queue.empty():
        (component, params) = queue.get()
        search_findings = params.pop(options.USE_FINDINGS)
        status_list = util.csv_to_list(params.get(options.STATUSES, None))
        i_statuses = util.intersection(status_list, issues.STATUSES)
        h_statuses = util.intersection(status_list, hotspots.STATUSES)
        resol_list = util.csv_to_list(params.get(options.RESOLUTIONS, None))
        i_resols = util.intersection(resol_list, issues.RESOLUTIONS)
        h_resols = util.intersection(resol_list, hotspots.RESOLUTIONS)
        type_list = util.csv_to_list(params.get(options.TYPES, None))
        i_types = util.intersection(type_list, issues.TYPES)
        h_types = util.intersection(type_list, hotspots.TYPES)
        sev_list = util.csv_to_list(params.get(options.SEVERITIES, None))
        i_sevs = util.intersection(sev_list, issues.SEVERITIES)
        h_sevs = util.intersection(sev_list, hotspots.SEVERITIES)

        if status_list or resol_list or type_list or sev_list or options.LANGUAGES in params:
            search_findings = False

        if search_findings:
            try:
                findings_list = findings.export_findings(
                    component.endpoint, component.key, branch=params.get("branch", None), pull_request=params.get("pullRequest", None)
                )
            except (ConnectionError, RequestException) as e:
                util.handle_error(e, f"exporting findings of {str(component)}, skipped", catch_all=True)
            write_queue.put(findings_list)
        else:
            new_params = params.copy()
            for p in (
                "sarifNoCustomProperties",
                options.NBR_THREADS,
                options.CSV_SEPARATOR,
                options.COMPONENT_TYPE,
                options.DATES_WITHOUT_TIME,
                options.REPORT_FILE,
                options.WITH_LAST_ANALYSIS,
                options.WITH_URL,
                options.HTTP_TIMEOUT,
                "http_timeout",
                options.LOGFILE,
                options.FORMAT,
            ):
                new_params.pop(p, None)
            if options.PULL_REQUESTS in new_params:
                new_params["pullRequest"] = new_params.pop(options.PULL_REQUESTS)
            if options.BRANCHES in new_params:
                new_params["branch"] = new_params.pop(options.BRANCHES)
            findings_list = {}
            if (i_statuses or not status_list) and (i_resols or not resol_list) and (i_types or not type_list) and (i_sevs or not sev_list):
                try:
                    findings_list = component.get_issues(filters=new_params)
                except (ConnectionError, RequestException) as e:
                    util.handle_error(e, f"exporting issues of {str(component)}", catch_all=True)
            else:
                log.debug("Status = %s, Types = %s, Resol = %s, Sev = %s", str(i_statuses), str(i_types), str(i_resols), str(i_sevs))
                log.info("Selected types, severities, resolutions or statuses disables issue search")

            if (h_statuses or not status_list) and (h_resols or not resol_list) and (h_types or not type_list) and (h_sevs or not sev_list):
                try:
                    findings_list.update(component.get_hotspots(filters=new_params))
                except (ConnectionError, RequestException) as e:
                    util.handle_error(e, f"exporting hotspots of {str(component)}", catch_all=True)
            else:
                log.debug("Status = %s, Types = %s, Resol = %s, Sev = %s", str(h_statuses), str(h_types), str(h_resols), str(h_sevs))
                log.info("Selected types, severities, resolutions or statuses disables issue search")
            log.debug("WRITE_QUEUE put ISSUES and HOTSPOTS for %s", str(component))
            write_queue.put(findings_list)

        log.debug("Queue %s task for %s done", str(queue), str(component))
        queue.task_done()


def store_findings(components_list: dict[str, object], params: ConfigSettings) -> None:
    """Export all findings of a given project list"""
    components_queue = Queue(maxsize=0)
    for comp in components_list.values():
        try:
            log.debug("Queue %s task %s put", str(components_queue), str(comp))
            components_queue.put((comp, params.copy()))
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"exporting issues of {str(comp)}", catch_all=True)

    log.info("Starting finding writer thread 'findingWriter'")
    write_queue = Queue(maxsize=0)
    write_worker = Thread(target=__write_findings, args=[write_queue, params.copy()])
    write_worker.setDaemon(True)
    write_worker.setName("findingWriter")
    write_worker.start()

    threads = params.get(options.NBR_THREADS, 4)
    for i in range(min(threads, len(components_list))):
        log.debug("Starting finding search thread 'findingSearch%d'", i)
        worker = Thread(target=__get_component_findings, args=[components_queue, write_queue])
        worker.setDaemon(True)
        worker.setName(f"findingSearch{i}")
        worker.start()
    components_queue.join()
    # Tell the writer thread that writing is complete
    log.debug("WriteQueue %s task WRITE_END put", str(write_queue))
    write_queue.put(util.WRITE_END)
    write_queue.join()
    log.debug("WriteQueue joined")


def __turn_off_use_findings_if_needed(endpoint: object, params: dict[str, str]) -> dict[str, str]:
    """Turn off use-findings option if some incompatible options (issue filters) are used"""
    if not params[options.USE_FINDINGS]:
        return params
    if util.is_sonarcloud_url(endpoint.url):
        log.warning("--%s option is not available with SonarCloud, disabling the option to proceed", options.USE_FINDINGS)
        params[options.USE_FINDINGS] = False
        return params

    for p in _OPTIONS_INCOMPATIBLE_WITH_USE_FINDINGS:
        if params.get(p, None) is not None:
            log.warning("Selected search criteria %s will disable --%s", params[p], options.USE_FINDINGS)
            params[options.USE_FINDINGS] = False
            break
    return params


def main() -> None:
    """Main entry point"""
    global DATES_WITHOUT_TIME
    start_time = util.start_clock()
    try:
        kwargs = util.convert_args(parse_args("Sonar findings export"))
        sqenv = platform.Platform(**kwargs)
        sqenv.verify_connection()
        sqenv.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")
    except (options.ArgumentsError, exceptions.ObjectNotFound) as e:
        util.exit_fatal(e.message, e.errcode)
    del kwargs[options.TOKEN]
    kwargs.pop(options.HTTP_TIMEOUT, None)
    del kwargs[options.URL]
    DATES_WITHOUT_TIME = kwargs[options.DATES_WITHOUT_TIME]
    params = util.remove_nones(kwargs.copy())
    params[options.REPORT_FILE] = kwargs[options.REPORT_FILE]
    __verify_inputs(params)

    params = __turn_off_use_findings_if_needed(sqenv, params=params)

    try:
        if params[options.COMPONENT_TYPE] == "portfolios":
            components_list = portfolios.get_list(endpoint=sqenv, key_list=params.get(options.KEYS, None))
        elif params[options.COMPONENT_TYPE] == "apps":
            components_list = applications.get_list(endpoint=sqenv, key_list=params.get(options.KEYS, None))
        else:
            components_list = projects.get_list(endpoint=sqenv, key_list=params.get(options.KEYS, None))
    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, errcodes.NO_SUCH_KEY)
    except exceptions.UnsupportedOperation as e:
        util.exit_fatal(e.message, errcodes.UNSUPPORTED_OPERATION)

    fmt, fname = params.get(options.FORMAT, None), params.get(options.REPORT_FILE, None)
    params[options.FORMAT] = util.deduct_format(fmt, fname, allowed_formats=("csv", "json", "sarif"))
    if fname is not None and os.path.exists(fname):
        os.remove(fname)

    log.info("Exporting findings for %d projects with params %s", len(components_list), str(params))
    try:
        params["sonar"] = sqenv
        store_findings(components_list, params=params)
    except (PermissionError, FileNotFoundError) as e:
        util.exit_fatal(f"OS error while exporting findings: {e}", exit_code=errcodes.OS_ERROR)
    log.info("%d returned findings from %s", TOTAL_FINDINGS, sqenv.url)
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
