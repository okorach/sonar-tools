#!/usr/bin/python3
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

    Audits a SonarQube platform

"""
import sys
import datetime
import json

from cli import options
from sonar import errcodes, exceptions
import sonar.logging as log
from sonar import platform, users, groups, qualityprofiles, qualitygates, sif, portfolios, applications, projects
import sonar.utilities as util
from sonar.audit import problem, config

_ALL_AUDITABLE = [
    options.WHAT_SETTINGS,
    options.WHAT_USERS,
    options.WHAT_GROUPS,
    options.WHAT_GATES,
    options.WHAT_PROFILES,
    options.WHAT_PROJECTS,
    options.WHAT_APPS,
    options.WHAT_PORTFOLIOS,
]


def _audit_sif(sysinfo, audit_settings):
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
    server_id = sif_obj.server_id()
    return (server_id, sif_obj.audit(audit_settings))


def _audit_sq(sq, settings: dict[str, str], what_to_audit: list[str] = None, key_list: list[str] = None) -> list[problem.Problem]:
    """Audits a SonarQube/Cloud platform"""
    problems = []
    everything = False
    if not what_to_audit:
        everything = True
        what_to_audit = options.WHAT_AUDITABLE
    if options.WHAT_PROJECTS in what_to_audit:
        problems += projects.audit(endpoint=sq, audit_settings=settings, key_list=key_list)
    if options.WHAT_PROFILES in what_to_audit:
        problems += qualityprofiles.audit(endpoint=sq, audit_settings=settings)
    if options.WHAT_GATES in what_to_audit:
        problems += qualitygates.audit(endpoint=sq, audit_settings=settings)
    if options.WHAT_SETTINGS in what_to_audit:
        problems += sq.audit(audit_settings=settings)
    if options.WHAT_USERS in what_to_audit:
        problems += users.audit(endpoint=sq, audit_settings=settings)
    if options.WHAT_GROUPS in what_to_audit:
        problems += groups.audit(endpoint=sq, audit_settings=settings)
    if options.WHAT_PORTFOLIOS in what_to_audit:
        try:
            problems += portfolios.audit(endpoint=sq, audit_settings=settings, key_list=key_list)
        except exceptions.UnsupportedOperation:
            if not everything:
                log.warning("No portfolios in %s edition, audit of portfolios ignored", sq.edition())
    if options.WHAT_APPS in what_to_audit:
        try:
            problems += applications.audit(endpoint=sq, audit_settings=settings, key_list=key_list)
        except exceptions.UnsupportedOperation:
            if not everything:
                log.warning("No applications in %s edition, audit of portfolios ignored", sq.edition())

    return problems


def __parser_args(desc):
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser)
    parser = options.set_url_arg(parser)
    parser = options.add_thread_arg(parser, "project audit")
    parser = options.set_what(parser, what_list=_ALL_AUDITABLE, operation="audit")
    parser.add_argument("--sif", required=False, help="SIF file to audit when auditing SIF")
    parser.add_argument(
        "--config",
        required=False,
        dest="config",
        action="store_true",
        help="Creates the $HOME/.sonar-audit.properties configuration file, if not already present or outputs to stdout if it already exist",
    )
    args = options.parse_and_check(parser=parser, logger_name="sonar-audit", verify_token=False)
    if args.sif is None and args.config is None:
        util.check_token(args.token)
    return args


def main():
    start_time = util.start_clock()
    kwargs = util.convert_args(__parser_args("Audits a SonarQube platform or a SIF (Support Info File or System Info File)"))
    sq = platform.Platform(**kwargs)

    settings = config.load("sonar-audit")
    settings["threads"] = kwargs[options.NBR_THREADS]
    if kwargs.get("config", False):
        config.configure()
        sys.exit(0)

    if kwargs.get("sif", None) is not None:
        err = errcodes.SIF_AUDIT_ERROR
        try:
            (server_id, problems) = _audit_sif(kwargs["sif"], settings)
        except json.decoder.JSONDecodeError:
            util.exit_fatal(f"File {kwargs['sif']} does not seem to be a legit JSON file, aborting...", err)
        except FileNotFoundError:
            util.exit_fatal(f"File {kwargs['sif']} does not exist, aborting...", err)
        except PermissionError:
            util.exit_fatal(f"No permissiont to open file {kwargs['sif']}, aborting...", err)
        except sif.NotSystemInfo:
            util.exit_fatal(f"File {kwargs['sif']} does not seem to be a system info or support info file, aborting...", err)
    else:
        server_id = sq.server_id()
        util.check_token(kwargs[options.TOKEN])
        key_list = kwargs[options.KEYS]
        if key_list is not None and len(key_list) > 0 and "projects" in util.csv_to_list(kwargs[options.WHAT]):
            for key in key_list:
                if not projects.exists(key, sq):
                    util.exit_fatal(f"Project key '{key}' does not exist", errcodes.NO_SUCH_KEY)
        try:
            problems = _audit_sq(sq, settings, what_to_audit=util.check_what(kwargs[options.WHAT], _ALL_AUDITABLE, "audited"), key_list=key_list)
        except exceptions.ObjectNotFound as e:
            util.exit_fatal(e.message, errcodes.NO_SUCH_KEY)

    ofile = kwargs.pop(options.OUTPUTFILE)
    problem.dump_report(problems, file=ofile, server_id=server_id, format=util.deduct_format(kwargs[options.FORMAT], ofile))

    log.info("Total audit execution time: %s", str(datetime.datetime.today() - start_time))
    if problems:
        log.warning("%d issues found during audit", len(problems))
    else:
        log.info("%d issues found during audit", len(problems))
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
