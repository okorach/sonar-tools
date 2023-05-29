#!/usr/bin/python3
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

    Audits a SonarQube platform

"""
import sys
import datetime
import json

from sonar import platform, users, groups, version, qualityprofiles, qualitygates, sif, options, portfolios, applications, exceptions
from sonar.projects import projects
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


def __deduct_format__(fmt, file):
    if fmt is not None:
        return fmt
    if file is not None:
        ext = file.split(".").pop(-1).lower()
        if ext in ("csv", "json"):
            return ext
    return "csv"


def _audit_sif(sysinfo, audit_settings):
    util.logger.info("Auditing SIF file '%s'", sysinfo)
    try:
        with open(sysinfo, "r", encoding="utf-8") as f:
            sysinfo = json.loads(f.read())
    except json.decoder.JSONDecodeError:
        util.logger.critical("File %s does not seem to be a legit JSON file", sysinfo)
        raise
    except FileNotFoundError:
        util.logger.critical("File %s does not exist", sysinfo)
        raise
    except PermissionError:
        util.logger.critical("No permission to open file %s", sysinfo)
        raise
    return sif.Sif(sysinfo).audit(audit_settings)


def _audit_sq(sq, settings, what_to_audit=None, key_list=None):
    problems = []
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
        problems += portfolios.audit(endpoint=sq, audit_settings=settings, key_list=key_list)
    if options.WHAT_APPS in what_to_audit:
        problems += applications.audit(endpoint=sq, audit_settings=settings, key_list=key_list)
    return problems


def __parser_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_key_arg(parser)
    parser = util.set_output_file_args(parser)
    parser = options.set_url_arg(parser)
    parser = options.add_thread_arg(parser, "project audit")
    parser = util.set_what(parser, what_list=_ALL_AUDITABLE, operation="audit")
    parser.add_argument("--sif", required=False, help="SIF file to audit when auditing SIF")
    parser.add_argument(
        "--config",
        required=False,
        dest="config",
        action="store_true",
        help="Creates the $HOME/.sonar-audit.properties configuration file, if not already present or outputs to stdout if it already exist",
    )
    args = parser.parse_args()
    if args.sif is None and args.config is None and args.token is None:
        util.exit_fatal(
            "Token is missing (Argument -t/--token) when not analyzing local SIF",
            options.ERR_TOKEN_MISSING,
        )
    return args


def main():
    args = __parser_args("Audits a SonarQube platform or a SIF (Support Info File or System Info File)")
    kwargs = vars(args)
    sq = platform.Platform(some_url=args.url, some_token=args.token, cert_file=args.clientCert)
    util.check_environment(kwargs)
    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    start_time = datetime.datetime.today()

    settings = config.load("sonar-audit")
    settings["threads"] = kwargs["threads"]
    if kwargs.get("config", False):
        config.configure()
        sys.exit(0)

    if kwargs.get("sif", None) is not None:
        err = options.ERR_SIF_AUDIT_ERROR
        try:
            problems = _audit_sif(kwargs["sif"], settings)
        except json.decoder.JSONDecodeError:
            util.exit_fatal(f"File {kwargs['sif']} does not seem to be a legit JSON file, aborting...", err)
        except FileNotFoundError:
            util.exit_fatal(f"File {kwargs['sif']} does not exist, aborting...", err)
        except PermissionError:
            util.exit_fatal(f"No permissiont to open file {kwargs['sif']}, aborting...", err)
        except sif.NotSystemInfo:
            util.exit_fatal(f"File {kwargs['sif']} does not seem to be a system info or support info file, aborting...", err)
    else:
        util.check_token(args.token)
        key_list = util.csv_to_list(args.projectKeys)
        if len(key_list) > 0 and "projects" in util.csv_to_list(args.what):
            for key in key_list:
                if not projects.exists(key, sq):
                    util.exit_fatal(f"Project key '{key}' does not exist", options.ERR_NO_SUCH_KEY)
        try:
            problems = _audit_sq(sq, settings, what_to_audit=util.check_what(args.what, _ALL_AUDITABLE, "audited"), key_list=key_list)
        except exceptions.ObjectNotFound as e:
            util.exit_fatal(e.message, options.ERR_NO_SUCH_KEY)

    kwargs["format"] = __deduct_format__(args.format, args.file)
    ofile = kwargs.pop("file", None)
    problem.dump_report(problems, ofile, **kwargs)

    util.logger.info("Total audit execution time: %s", str(datetime.datetime.today() - start_time))
    if problems:
        util.logger.warning("%d issues found during audit", len(problems))
    else:
        util.logger.info("%d issues found during audit", len(problems))
    sys.exit(0)


if __name__ == "__main__":
    main()
