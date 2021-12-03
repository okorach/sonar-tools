#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
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
'''

    Audits a SonarQube platform

'''
import sys
import json
import sonarqube.projects as projects
import sonarqube.qualityprofiles as qualityprofiles
import sonarqube.qualitygates as qualitygates
import sonarqube.portfolios as pf
import sonarqube.applications as apps
import sonarqube.users as users
import sonarqube.utilities as util
import sonarqube.version as version
import sonarqube.env as env
import sonarqube.audit_problem as pb
import sonarqube.audit_config as conf


def __deduct_format__(fmt, file):
    if fmt is not None:
        return fmt
    if file is not None:
        ext = file.split('.').pop(-1).lower()
        if ext in ('csv', 'json'):
            return ext
    return 'csv'


def _audit_sif(sif):
    try:
        with open(sif, 'r') as f:
            sif = json.loads(f.read())
    except json.decoder.JSONDecodeError:
        util.logger.critical("File %s does not seem to be a legit JSON file", sif)
        raise
    except FileNotFoundError:
        util.logger.critical("File %s does not exist", sif)
        raise
    except PermissionError:
        util.logger.critical("No permission to open file %s", sif)
        raise
    return env.audit_sysinfo(sif)


def _audit_sq(sq, settings, what=None):
    if what is None:
        what = 'qp,qg,settings,projects,users,portfolios,apps'
    what_to_audit = what.split(',')
    problems = []
    if 'projects' in what_to_audit:
        problems += projects.audit(endpoint=sq, audit_settings=settings)
    if 'qp' in what_to_audit:
        problems += qualityprofiles.audit(endpoint=sq, audit_settings=settings)
    if 'qg' in what_to_audit:
        problems += qualitygates.audit(endpoint=sq, audit_settings=settings)
    if 'settings' in what_to_audit:
        problems += sq.audit(audit_settings=settings)
    if 'users' in what_to_audit:
        problems += users.audit(endpoint=sq, audit_settings=settings)
    if 'portfolios' in what_to_audit:
        problems += pf.audit(endpoint=sq, audit_settings=settings)
    if 'apps' in what_to_audit:
        problems += apps.audit(endpoint=sq, audit_settings=settings)
    return problems


def main():
    util.set_logger('sonar-audit')
    parser = util.set_common_args('Audits a SonarQube platform or a SIF (Support Info File or System Info File)')
    parser.add_argument('-w', '--what', required=False,
                        help='What to audit (qp,qg,settings,projects,users,portfolios,apps) '
                        'comma separated, everything by default')
    parser.add_argument('--format', choices=['csv', 'json'], required=False,
                        help="Output format for audit report.\nIf not specified, "
                             "it is the output file extension if json or csv, then csv by default")
    parser.add_argument('--sif', required=False, help='SIF file to audit when auditing SIF')
    parser.add_argument('--config', required=False, dest='config', action='store_true',
                        help='Creates the $HOME/.sonar-audit.properties configuration file, if not already present'
                        'or outputs to stdout if it already exist')
    parser.add_argument('-f', '--file', required=False, help='Output file for the report, stdout by default')
    args = parser.parse_args()
    kwargs = vars(args)
    if args.sif is None and args.config is None and args.token is None:
        util.logger.critical("Token is missing (Argument -t/--token) when not analyzing local SIF")
        sys.exit(4)
    sq = env.Environment(url=args.url, token=args.token)

    util.check_environment(kwargs)
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    settings = conf.load('sonar-audit')

    if kwargs.get('config', False):
        conf.configure()
        sys.exit(0)

    if kwargs.get('sif', None) is not None:
        try:
            problems = _audit_sif(kwargs['sif'])
        except json.decoder.JSONDecodeError:
            print(f"File {kwargs['sif']} does not seem to be a legit JSON file, aborting...")
            sys.exit(3)
        except FileNotFoundError:
            print(f"File {kwargs['sif']} does not exist, aborting...")
            sys.exit(4)
        except PermissionError:
            print(f"No permissiont to open file {kwargs['sif']}, aborting...")
            sys.exit(5)
        except env.NotSystemInfo:
            print(f"File {kwargs['sif']} does not seem to be a system info or support info file, aborting...")
            sys.exit(6)
    else:
        problems = _audit_sq(sq, settings, args.what)

    args.format = __deduct_format__(args.format, args.file)
    pb.dump_report(problems, args.file, args.format)

    if problems:
        util.logger.warning("%d issues found during audit", len(problems))
    else:
        util.logger.info("%d issues found during audit", len(problems))
    sys.exit(len(problems))

if __name__ == "__main__":
    main()
