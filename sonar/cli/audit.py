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
"""Audits a SonarQube platform"""

from __future__ import annotations

import json
import csv
import re
from typing import TextIO, Optional
from threading import Thread
from queue import Queue
from requests import RequestException
from cli import options

from sonar import errcodes, exceptions, version
from sonar.util import types, component_helper
import sonar.logging as log
from sonar import platform, users, groups, qualityprofiles, qualitygates, sif, portfolios, applications, projects
import sonar.utilities as sutil
import sonar.util.misc as util
from sonar.audit import problem
import sonar.util.conf_mgr as audit_conf
import sonar.util.common_helper as chelp

TOOL_NAME = "sonar-audit"
CONFIG_FILE = "sonar-audit.properties"

WHAT_AUDITABLE = {
    options.WHAT_SETTINGS: platform.audit,
    options.WHAT_USERS: users.audit,
    options.WHAT_GROUPS: groups.audit,
    options.WHAT_GATES: qualitygates.audit,
    options.WHAT_PROFILES: qualityprofiles.audit,
    options.WHAT_PROJECTS: projects.audit,
    options.WHAT_APPS: applications.audit,
    options.WHAT_PORTFOLIOS: portfolios.audit,
}

PROBLEM_KEYS = "problems"


def _audit_sif(sysinfo: str, audit_settings: types.ConfigSettings) -> tuple[str, list[problem.Problem]]:
    """Audits a SIF and return found problems"""
    log.info("Auditing SIF file '%s'", sysinfo)
    try:
        with open(sysinfo, encoding="utf-8") as f:
            sysinfo = json.loads(f.read())
    except json.decoder.JSONDecodeError:
        log.critical("File %s does not seem to be a legit JSON file", sysinfo)
        raise
    except FileNotFoundError:
        log.critical("File %s does not exist", sysinfo)
        raise
    except PermissionError:
        log.critical("No permission to open file %s", sysinfo)
        raise
    sif_obj = sif.Sif(sysinfo)
    return sif_obj.server_id(), sif_obj.audit(audit_settings)


def __filter_problems(problems: list[problem.Problem], settings: types.ConfigSettings) -> list[problem.Problem]:
    """Filters audit problems by severity and/or type and/or problem key"""
    if settings.get(options.SEVERITIES, None):
        log.debug("Filtering audit problems with severities: %s", settings[options.SEVERITIES])
        problems = [p for p in problems if str(p.severity) in settings[options.SEVERITIES]]
    if settings.get(options.TYPES, None):
        log.debug("Filtering audit problems with types: %s", settings[options.TYPES])
        problems = [p for p in problems if str(p.type) in settings[options.TYPES]]
    if settings.get(PROBLEM_KEYS, None):
        log.debug("Filtering audit problems with keys: %s", settings[PROBLEM_KEYS])
        problems = [p for p in problems if re.match(rf"^{settings[PROBLEM_KEYS]}$", str(p.rule_id))]
    return problems


def write_csv(queue: Queue[list[problem.Problem]], fd: TextIO, settings: types.ConfigSettings) -> None:
    """Thread callback to write audit problems in a CSV file"""
    server_id = settings.get("SERVER_ID", None)
    with_url = settings.get("WITH_URL", False)
    csvwriter = csv.writer(fd, delimiter=settings.get("CSV_DELIMITER", ","))
    header = ["Server Id"] if server_id else []
    header += ["Problem", "Type", "Severity", "Message"]
    header += ["URL"] if with_url else []
    csvwriter.writerow(header)
    while (problems := queue.get()) is not sutil.WRITE_END:
        problems = __filter_problems(problems, settings)
        for p in problems:
            json_data = p.to_json(with_url)
            data = [server_id] if server_id else []
            data += [json_data[k] for k in ("problem", "type", "severity", "message", "url") if k in json_data]
            csvwriter.writerow(data)
        queue.task_done()
    queue.task_done()


def write_json(queue: Queue[list[problem.Problem]], fd: TextIO, settings: types.ConfigSettings) -> None:
    """Thread callback to write problems in a JSON file"""
    server_id = settings.get("SERVER_ID", None)
    with_url = settings.get("WITH_URL", False)
    comma = ""
    print("[", file=fd)
    while (problems := queue.get()) is not sutil.WRITE_END:
        problems = __filter_problems(problems, settings)
        for p in problems:
            json_data = p.to_json(with_url)
            if server_id:
                json_data |= {"serverId": server_id}
            print(f"{comma}{util.json_dump(json_data)}", file=fd)
            comma = ","
        queue.task_done()
    print("]", file=fd)
    queue.task_done()
    log.info("Writing audit problems complete")


def _audit_sq(
    sq: platform.Platform, settings: types.ConfigSettings, what_to_audit: Optional[list[str]] = None, key_list: Optional[types.KeyList] = None
) -> list[problem.Problem]:
    """Audits a SonarQube/Cloud platform"""
    everything = what_to_audit is None
    if everything:
        what_to_audit = list(WHAT_AUDITABLE.keys())

    problems = []
    write_q = Queue(maxsize=0)
    file = settings.get("FILE", None)
    fmt = settings.get("format", "csv")
    func = write_csv if fmt == "csv" else write_json
    with util.open_file(file=file, mode="w") as fd:
        worker = Thread(target=func, args=(write_q, fd, settings))
        worker.daemon = True
        worker.name = "AuditWriter"
        worker.start()
        for element, func in WHAT_AUDITABLE.items():
            if element not in what_to_audit:
                continue
            try:
                pbs = func(endpoint=sq, audit_settings=settings, write_q=write_q, key_list=key_list)
                problems += pbs
            except exceptions.SonarException as e:
                if not everything:
                    log.warning(e.message)
        write_q.put(sutil.WRITE_END)
        write_q.join()
    if file and fmt == "json":
        util.pretty_print_json(file)
    return problems


def __parser_args(desc: str) -> object:
    """Adds all sonar-audit CLI arguments and parse them"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("csv", "json"))
    parser = options.add_url_arg(parser)
    parser = options.add_thread_arg(parser, "project audit")
    parser = options.set_what(parser, what_list=WHAT_AUDITABLE, operation="audit")
    parser.add_argument("--sif", required=False, help="SIF file to audit when auditing SIF")
    parser = options.add_config_arg(parser, file=f".{CONFIG_FILE}")
    parser = options.add_settings_arg(parser)

    help_str = "Report only audit problems with the given severities (comma separate values LOW, MEDIUM, HIGH, CRITICAL)"
    parser = options.add_optional_arg(parser, f"--{options.SEVERITIES}", help=help_str)

    help_str = "Report only audit problems of the given comma separated problem types"
    parser = options.add_optional_arg(parser, f"--{options.TYPES}", help=help_str)

    help_str = "Report only audit problems whose type key matches the given regexp"
    parser = options.add_optional_arg(parser, f"--{PROBLEM_KEYS}", help=help_str)

    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME, verify_token=False)
    if args.sif is None and args.config is None:
        sutil.check_token(args.token)
    return args


def __check_keys_exist(key_regexp: list[str], sq: platform.Platform, what: list[str]) -> None:
    """Checks if project keys exist"""
    if key_regexp and "projects" in what and len(component_helper.get_components(sq, "projects", key_regexp)) == 0:
        raise options.ArgumentsError(f"No projects found with key matching regexp '{key_regexp}'")


def main() -> None:
    """Main entry point"""
    start_time = util.start_clock()
    errcode = errcodes.OS_ERROR
    try:
        kwargs = sutil.convert_args(__parser_args("Audits a SonarQube Server or Cloud platform or a SIF (Support Info File or System Info File)"))
        cli_settings = {}
        for val in kwargs.get("settings", []) or []:
            key, value = val[0].split("=", maxsplit=1)
            cli_settings[key] = value
        settings = audit_conf.load(CONFIG_FILE, __file__) | cli_settings
        settings |= kwargs
        file = ofile = kwargs.pop(options.REPORT_FILE)
        fmt = util.deduct_format(kwargs[options.FORMAT], ofile)
        settings.update(
            {
                "FILE": file,
                "CSV_DELIMITER": kwargs[options.CSV_SEPARATOR],
                "WITH_URL": kwargs[options.WITH_URL],
                "format": fmt,
            }
        )
        if kwargs.get("config", False):
            audit_conf.configure(CONFIG_FILE, __file__)
            chelp.clear_cache_and_exit(errcodes.OK, start_time=start_time)
        if kwargs["sif"]:
            file = kwargs["sif"]
            errcode = errcodes.SIF_AUDIT_ERROR
            (settings["SERVER_ID"], problems) = _audit_sif(file, settings)
            problems = __filter_problems(problems, settings)
            problem.dump_report(problems, file=ofile, server_id=settings["SERVER_ID"], fmt=fmt)
        else:
            sutil.check_token(kwargs[options.TOKEN], sutil.is_sonarcloud_url(kwargs[options.URL]))
            sq = platform.Platform(**kwargs)
            sq.verify_connection()
            sq.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")
            settings["SERVER_ID"] = sq.server_id()
            __check_keys_exist(kwargs[options.KEY_REGEXP], sq, kwargs[options.WHAT])
            what = sutil.check_what(kwargs[options.WHAT], WHAT_AUDITABLE, "audited")
            problems = _audit_sq(sq, settings, what_to_audit=what, key_list=kwargs[options.KEY_REGEXP])
            loglevel = log.WARNING if len(problems) > 0 else log.INFO
            log.log(loglevel, "%d issues found during audit", len(problems))

        # problem.dump_report(problems, file=ofile, server_id=settings["SERVER_ID"], format=util.deduct_format(kwargs[options.FORMAT], ofile))

    except (PermissionError, FileNotFoundError) as e:
        chelp.clear_cache_and_exit(errcode, f"OS error while writing file '{file}': {e}")
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)
    except json.decoder.JSONDecodeError:
        chelp.clear_cache_and_exit(errcodes.SIF_AUDIT_ERROR, f"File {kwargs['sif']} does not seem to be a legit JSON file, aborting...")
    except sif.NotSystemInfo:
        chelp.clear_cache_and_exit(
            errcodes.SIF_AUDIT_ERROR, f"File {kwargs['sif']} does not seem to be a system info or support info file, aborting..."
        )
    except RequestException as e:
        chelp.clear_cache_and_exit(errcodes.SONAR_API, f"HTTP error while auditing: {e}")
    chelp.clear_cache_and_exit(errcodes.OK, start_time=start_time)


if __name__ == "__main__":
    main()
