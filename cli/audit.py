#!/usr/bin/python3
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

    Audits a SonarQube platform

"""
import sys
import json
import csv
from typing import TextIO
from threading import Thread
from queue import Queue
from requests import RequestException
from cli import options

from sonar import errcodes, exceptions, version
from sonar.util import types
import sonar.logging as log
from sonar import platform, users, groups, qualityprofiles, qualitygates, sif, portfolios, applications, projects
import sonar.utilities as util
from sonar.audit import problem
from sonar.audit import audit_config as audit_conf

TOOL_NAME = "sonar-audit"
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


def _audit_sif(sysinfo: str, audit_settings: types.ConfigSettings) -> tuple[str, list[problem.Problem]]:
    """Audits a SIF and return found problems"""
    log.info("Auditing SIF file '%s'", sysinfo)
    try:
        with open(sysinfo, "r", encoding="utf-8") as f:
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


def write_problems(queue: Queue[list[problem.Problem]], fd: TextIO, settings: types.ConfigSettings) -> None:
    """
    Thread to write problems in a CSV file
    """
    csvwriter = csv.writer(fd, delimiter=settings.get("CSV_DELIMITER", ","))
    server_id = settings.get("SERVER_ID", None)
    with_url = settings.get("WITH_URL", False)
    while True:
        problems = queue.get()
        if problems is util.WRITE_END:
            queue.task_done()
            break
        for p in problems:
            data = [] if not server_id else [server_id]
            data += list(p.to_json(with_url).values())
            csvwriter.writerow(data)
        queue.task_done()
    log.info("Writing audit problems complete")


def _audit_sq(
    sq: platform.Platform, settings: types.ConfigSettings, what_to_audit: list[str] = None, key_list: types.KeyList = None
) -> list[problem.Problem]:
    """Audits a SonarQube/Cloud platform"""
    everything = what_to_audit is None
    if everything:
        what_to_audit = list(WHAT_AUDITABLE.keys())

    problems = []
    write_q = Queue(maxsize=0)

    with util.open_file(settings.get("FILE", None), mode="w") as fd:
        worker = Thread(target=write_problems, args=(write_q, fd, settings))
        worker.daemon = True
        worker.name = "AuditWriter"
        worker.start()
        for element, func in WHAT_AUDITABLE.items():
            if element in what_to_audit:
                try:
                    pbs = func(endpoint=sq, audit_settings=settings, write_q=write_q, key_list=key_list)
                    problems += pbs
                except exceptions.UnsupportedOperation as e:
                    if not everything:
                        log.warning(e.message)
        write_q.put(None)
        write_q.join()
    return problems


def __parser_args(desc: str) -> object:
    """Adds all sonar-audit CLI arguments and parse them"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("csv", "json"))
    parser = options.set_url_arg(parser)
    parser = options.add_thread_arg(parser, "project audit")
    parser = options.set_what(parser, what_list=WHAT_AUDITABLE, operation="audit")
    parser.add_argument("--sif", required=False, help="SIF file to audit when auditing SIF")
    parser.add_argument(
        "--config",
        required=False,
        dest="config",
        action="store_true",
        help="Creates the $HOME/.sonar-audit.properties configuration file, if not already present or outputs to stdout if it already exist",
    )
    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME, verify_token=False)
    if args.sif is None and args.config is None:
        util.check_token(args.token)
    return args


def __check_keys_exist(key_list: list[str], sq: platform.Platform, what: list[str]) -> None:
    """Checks if project keys exist"""
    if key_list and len(key_list) > 0 and "projects" in what:
        missing_proj = [key for key in key_list if not projects.exists(key, sq)]
        if len(missing_proj) > 0:
            raise exceptions.ObjectNotFound(missing_proj[0], f"Projects key {', '.join(missing_proj)} do(es) not exist")


def main() -> None:
    """Main entry point"""
    start_time = util.start_clock()
    errcode = errcodes.OS_ERROR
    try:
        kwargs = util.convert_args(__parser_args("Audits a SonarQube platform or a SIF (Support Info File or System Info File)"))
        settings = audit_conf.load(TOOL_NAME)
        file = ofile = kwargs.pop(options.REPORT_FILE)
        settings.update(
            {
                "FILE": file,
                "CSV_DELIMITER": kwargs[options.CSV_SEPARATOR],
                "WITH_URL": kwargs[options.WITH_URL],
                "threads": kwargs[options.NBR_THREADS],
            }
        )
        if kwargs.get("config", False):
            audit_conf.configure()
            sys.exit(errcodes.OK)

        if kwargs["sif"]:
            file = kwargs["sif"]
            errcode = errcodes.SIF_AUDIT_ERROR
            (settings["SERVER_ID"], problems) = _audit_sif(file, settings)
            problem.dump_report(problems, file=ofile, server_id=settings["SERVER_ID"], format=util.deduct_format(kwargs[options.FORMAT], ofile))

        else:
            sq = platform.Platform(**kwargs)
            sq.verify_connection()
            sq.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")
            settings["SERVER_ID"] = sq.server_id()
            __check_keys_exist(kwargs[options.KEYS], sq, kwargs[options.WHAT])
            what = util.check_what(kwargs[options.WHAT], WHAT_AUDITABLE, "audited")
            problems = _audit_sq(sq, settings, what_to_audit=what, key_list=kwargs[options.KEYS])
            loglevel = log.WARNING if len(problems) > 0 else log.INFO
            log.log(loglevel, "%d issues found during audit", len(problems))

        # problem.dump_report(problems, file=ofile, server_id=settings["SERVER_ID"], format=util.deduct_format(kwargs[options.FORMAT], ofile))

    except exceptions.ConnectionError as e:
        util.exit_fatal(e.message, e.errcode)
    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, errcodes.NO_SUCH_KEY)
    except (PermissionError, FileNotFoundError) as e:
        util.exit_fatal(f"OS error while writing file '{file}': {e}", errcode)
    except options.ArgumentsError as e:
        util.exit_fatal(e.message, e.errcode)
    except json.decoder.JSONDecodeError:
        util.exit_fatal(f"File {kwargs['sif']} does not seem to be a legit JSON file, aborting...", errcodes.SIF_AUDIT_ERROR)
    except sif.NotSystemInfo:
        util.exit_fatal(f"File {kwargs['sif']} does not seem to be a system info or support info file, aborting...", errcodes.SIF_AUDIT_ERROR)
    except RequestException as e:
        util.exit_fatal(f"HTTP error while auditing: {str(e)}", errcodes.SONAR_API)
    util.stop_clock(start_time)
    sys.exit(errcodes.OK)


if __name__ == "__main__":
    main()
