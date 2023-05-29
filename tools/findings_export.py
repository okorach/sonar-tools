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
    This script exports findings as CSV or JSON

    Usage: sonar-findings-export.py -t <SQ_TOKEN> -u <SQ_URL> [<filters>]

    Filters can be:
    [-k <projectKey>]
    [-s <statuses>] (FIXED, CLOSED, REOPENED, REVIEWED)
    [-r <resolutions>] (UNRESOLVED, FALSE-POSITIVE, WONTFIX)
    [-a <createdAfter>] findings created on or after a given date (YYYY-MM-DD)
    [-b <createdBefore>] findings created before or on a given date (YYYY-MM-DD)
    [--severities <severities>] Comma separated desired severities: BLOCKER, CRITICAL, MAJOR, MINOR, INFO
    [--types <types>] Comma separated findings types (VULNERABILITY,BUG,CODE_SMELL,SECURITY_HOTSPOT)
    [--tags]
"""

import sys
import os
import time
import datetime
from queue import Queue
from threading import Thread

from sonar import platform, version, options, exceptions
from sonar.projects import projects
import sonar.utilities as util
from sonar.findings import findings, issues, hotspots

WRITE_END = object()
TOTAL_FINDINGS = 0


def parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_key_arg(parser)
    parser = util.set_output_file_args(parser)
    parser = options.add_thread_arg(parser, "findings search")
    parser.add_argument(
        "-b",
        "--branches",
        required=False,
        default=None,
        help="Comma separated list of branches to export. Use * to export findings from all branches. "
        "If not specified, only findings of the main branch will be exported",
    )
    parser.add_argument(
        "-p",
        "--pullRequests",
        required=False,
        default=None,
        help="Comma separated list of pull request. Use * to export findings from all PRs. "
        "If not specified, only findings of the main branch will be exported",
    )
    parser.add_argument(
        "--statuses",
        required=False,
        help="comma separated status among " + util.list_to_csv(issues.STATUSES + hotspots.STATUSES),
    )
    parser.add_argument(
        "--createdAfter",
        required=False,
        help="findings created on or after a given date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--createdBefore",
        required=False,
        help="findings created on or before a given date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--resolutions",
        required=False,
        help="Comma separated resolution of the findings among " + util.list_to_csv(issues.RESOLUTIONS + hotspots.RESOLUTIONS),
    )
    parser.add_argument(
        "--severities",
        required=False,
        help="Comma separated severities among" + util.list_to_csv(issues.SEVERITIES + hotspots.SEVERITIES),
    )
    parser.add_argument(
        "--types",
        required=False,
        help="Comma separated types among " + util.list_to_csv(issues.TYPES + hotspots.TYPES),
    )
    parser.add_argument("--tags", help="Comma separated findings tags", required=False)
    parser.add_argument(
        "--useFindings",
        required=False,
        default=False,
        action="store_true",
        help="Use export_findings() whenever possible",
    )
    parser.add_argument(
        "--" + options.WITH_URL,
        required=False,
        default=False,
        action="store_true",
        help="Generate finding URL in the report, false by default",
    )
    args = util.parse_and_check_token(parser)
    util.check_token(args.token)
    return args


def __write_header(file, format):
    util.logger.info("Dumping report to %s", f"file '{file}'" if file else "stdout")
    with util.open_file(file) as f:
        print("[" if format == "json" else findings.to_csv_header(), file=f)


def __write_footer(file, format):
    if format != "json":
        return
    with util.open_file(file, mode="a") as f:
        print("]\n", file=f)


def __dump_findings(findings_list, file, file_format, is_last=False, **kwargs):
    i = len(findings_list)
    util.logger.info("Writing %d more findings to %s", i, f"file '{file}'" if file else "stdout")
    with util.open_file(file, mode="a") as f:
        url = ""
        sep = kwargs.get(options.CSV_SEPARATOR, ",")
        comma = ","
        for _, finding in findings_list.items():
            i -= 1
            if file_format == "json":
                finding_json = finding.to_json()
                if not kwargs[options.WITH_URL]:
                    finding_json.pop("url", None)
                if is_last and i == 0:
                    comma = ""
                print(f"{util.json_dump(finding_json, indent=1)}{comma}\n", file=f, end="")
            else:
                if kwargs[options.WITH_URL]:
                    url = f'{sep}"{finding.url()}"'
                print(f"{finding.to_csv(sep)}{url}", file=f)


def __write_findings(queue, file_to_write, file_format, with_url, separator):
    while True:
        while queue.empty():
            time.sleep(0.5)
        (data, is_last) = queue.get()
        if data == WRITE_END:
            queue.task_done()
            break

        global TOTAL_FINDINGS
        TOTAL_FINDINGS += len(data)
        __dump_findings(data, file_to_write, file_format, is_last, withURL=with_url, csvSeparator=separator)
        queue.task_done()


def __dump_compact(finding_list, file, **kwargs):
    new_dict = {}
    for finding in finding_list.values():
        f_json = finding.to_json()
        if not kwargs[options.WITH_URL]:
            f_json.pop("url", None)
        pkey = f_json.pop("projectKey")
        ftype = f_json.pop("type")
        if pkey in new_dict:
            if ftype in new_dict[pkey]:
                new_dict[pkey][ftype].append(f_json)
            else:
                new_dict[pkey].update({ftype: [f_json]})
        else:
            new_dict[pkey] = {ftype: [f_json]}
    with util.open_file(file) as f:
        print(util.json_dump(new_dict, indent=1), file=f)


def __get_list(project, list_str, list_type):
    if list_str == "*":
        list_array = [b.name for b in project.branches()] if list_type == "branch" else [p.key for p in project.pull_requests()]
    elif list_str is not None:
        list_array = util.csv_to_list(list_str)
    else:
        list_array = []
    return list_array


def __verify_inputs(params):
    diff = util.difference(util.csv_to_list(params.get("resolutions", None)), issues.RESOLUTIONS + hotspots.RESOLUTIONS)
    if diff:
        util.exit_fatal(f"Resolutions {str(diff)} are not legit resolutions", options.ERR_WRONG_SEARCH_CRITERIA)

    diff = util.difference(util.csv_to_list(params.get("statuses", None)), issues.STATUSES + hotspots.STATUSES)
    if diff:
        util.exit_fatal(f"Statuses {str(diff)} are not legit statuses", options.ERR_WRONG_SEARCH_CRITERIA)

    diff = util.difference(util.csv_to_list(params.get("severities", None)), issues.SEVERITIES + hotspots.SEVERITIES)
    if diff:
        util.exit_fatal(f"Severities {str(diff)} are not legit severities", options.ERR_WRONG_SEARCH_CRITERIA)

    diff = util.difference(util.csv_to_list(params.get("types", None)), issues.TYPES + hotspots.TYPES)
    if diff:
        util.exit_fatal(f"Types {str(diff)} are not legit types", options.ERR_WRONG_SEARCH_CRITERIA)

    return True


def __get_project_findings(queue, write_queue):
    while not queue.empty():
        (key, endpoint, params) = queue.get()
        search_findings = params["useFindings"]
        status_list = util.csv_to_list(params.get("statuses", None))
        i_statuses = util.intersection(status_list, issues.STATUSES)
        h_statuses = util.intersection(status_list, hotspots.STATUSES)
        resol_list = util.csv_to_list(params.get("resolutions", None))
        i_resols = util.intersection(resol_list, issues.RESOLUTIONS)
        h_resols = util.intersection(resol_list, hotspots.RESOLUTIONS)
        type_list = util.csv_to_list(params.get("types", None))
        i_types = util.intersection(type_list, issues.TYPES)
        h_types = util.intersection(type_list, hotspots.TYPES)
        sev_list = util.csv_to_list(params.get("severities", None))
        i_sevs = util.intersection(sev_list, issues.SEVERITIES)
        h_sevs = util.intersection(sev_list, hotspots.SEVERITIES)

        if status_list or resol_list or type_list or sev_list:
            search_findings = False

        util.logger.debug("WriteQueue %s task %s put", str(write_queue), key)
        if search_findings:
            findings_list = findings.export_findings(endpoint, key, branch=params.get("branch", None), pull_request=params.get("pullRequest", None))

            write_queue.put([findings_list, queue.empty()])
        else:
            new_params = issues.get_search_criteria(params)
            new_params.update({"branch": params.get("branch", None), "pullRequest": params.get("pullRequest", None)})
            findings_list = {}
            if (i_statuses or not status_list) and (i_resols or not resol_list) and (i_types or not type_list) and (i_sevs or not sev_list):
                findings_list = issues.search_by_project(key, params=new_params, endpoint=endpoint)
            else:
                util.logger.debug("Status = %s, Types = %s, Resol = %s, Sev = %s", str(i_statuses), str(i_types), str(i_resols), str(i_sevs))
                util.logger.info("Selected types, severities, resolutions or statuses disables issue search")

            if (h_statuses or not status_list) and (h_resols or not resol_list) and (h_types or not type_list) and (h_sevs or not sev_list):
                new_params = hotspots.get_search_criteria(params)
                new_params.update({"branch": params.get("branch", None), "pullRequest": params.get("pullRequest", None)})
                findings_list.update(hotspots.search_by_project(key, endpoint=endpoint, params=new_params))
            else:
                util.logger.debug("Status = %s, Types = %s, Resol = %s, Sev = %s", str(h_statuses), str(h_types), str(h_resols), str(h_sevs))
                util.logger.info("Selected types, severities, resolutions or statuses disables issue search")
            write_queue.put([findings_list, queue.empty()])
        util.logger.debug("Queue %s task %s done", str(queue), key)
        queue.task_done()


def store_findings(project_list, params, endpoint, file, format, threads=4, with_url=False, csv_separator=","):
    my_queue = Queue(maxsize=0)
    write_queue = Queue(maxsize=0)
    for key, project in project_list.items():
        branches = __get_list(project, params.pop("branches", None), "branch")
        prs = __get_list(project, params.pop("pullRequests", None), "pullrequest")
        for b in branches:
            params["branch"] = b
            util.logger.debug("Queue %s task %s put", str(my_queue), key)
            my_queue.put((key, endpoint, params.copy()))
        params.pop("branch", None)
        for p in prs:
            params["pullRequest"] = p
            util.logger.debug("Queue %s task %s put", str(my_queue), key)
            my_queue.put((key, endpoint, params.copy()))
        params.pop("pullRequest", None)
        if not (branches or prs):
            util.logger.debug("Queue %s task %s put", str(my_queue), key)
            my_queue.put((key, endpoint, params.copy()))

    for i in range(threads):
        util.logger.debug("Starting finding search thread 'findingSearch%d'", i)
        worker = Thread(target=__get_project_findings, args=[my_queue, write_queue])
        worker.setDaemon(True)
        worker.setName(f"findingSearch{i}")
        worker.start()

    util.logger.info("Starting finding writer thread 'findingWriter'")
    write_worker = Thread(target=__write_findings, args=[write_queue, file, format, with_url, csv_separator])
    write_worker.setDaemon(True)
    write_worker.setName("findingWriter")
    write_worker.start()

    my_queue.join()
    # Tell the writer thread that writing is complete
    util.logger.debug("WriteQueue %s task %s put", str(write_queue), str(WRITE_END))
    write_queue.put((WRITE_END, True))
    write_queue.join()


def main():
    kwargs = vars(parse_args("Sonar findings extractor"))
    sqenv = platform.Platform(some_url=kwargs["url"], some_token=kwargs["token"], cert_file=kwargs["clientCert"])
    del kwargs["token"]
    util.check_environment(kwargs)
    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    start_time = datetime.datetime.today()
    params = util.remove_nones(kwargs.copy())
    __verify_inputs(params)

    for p in ("statuses", "createdAfter", "createdBefore", "resolutions", "severities", "types", "tags"):
        if params.get(p, None) is not None:
            if params["useFindings"]:
                util.logger.warning("Selected search criteria %s will disable --useFindings", params[p])
            params["useFindings"] = False
            break
    try:
        project_list = projects.get_list(endpoint=sqenv, key_list=util.csv_to_list(kwargs.get("projectKeys", None)))
    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, options.ERR_NO_SUCH_KEY)
    fmt = kwargs.pop("format", None)
    fname = kwargs.pop("file", None)
    if fname is not None:
        ext = fname.split(".")[-1].lower()
        if os.path.exists(fname):
            os.remove(fname)
        if ext in ("csv", "json"):
            fmt = ext

    util.logger.info("Exporting findings for %d projects with params %s", len(project_list), str(params))
    __write_header(fname, fmt)
    store_findings(
        project_list,
        params=params,
        endpoint=sqenv,
        file=fname,
        format=fmt,
        threads=kwargs[options.NBR_THREADS],
        with_url=kwargs[options.WITH_URL],
        csv_separator=kwargs[options.CSV_SEPARATOR],
    )
    __write_footer(fname, fmt)
    util.logger.info("Returned findings: %d - Total execution time: %s", TOTAL_FINDINGS, str(datetime.datetime.today() - start_time))
    sys.exit(0)


if __name__ == "__main__":
    main()
