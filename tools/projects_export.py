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

    Exports all projects of a SonarQube platform

"""
import sys
import datetime
from sonar import options, platform, utilities, version
from sonar.projects import projects


def main():
    parser = utilities.set_common_args("Exports all projects of a SonarQube platform")
    parser = utilities.set_key_arg(parser)
    parser = utilities.set_output_file_args(parser, json_fmt=True, csv_fmt=False)
    parser = options.add_thread_arg(parser, "projects zip export")
    parser.add_argument(
        "--exportTimeout",
        required=False,
        type=int,
        default=180,
        help="Maximum wait time for export",
    )
    args = utilities.parse_and_check_token(parser)
    utilities.check_environment(vars(args))
    utilities.check_token(args.token)
    utilities.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    start_time = datetime.datetime.today()
    sq = platform.Platform(some_url=args.url, some_token=args.token, cert_file=args.clientCert)

    if sq.edition() in ("community", "developer") and sq.version(digits=2) < (9, 2):
        utilities.exit_fatal(
            "Can't export projects on Community and Developer Edition before 9.2, aborting...",
            options.ERR_UNSUPPORTED_OPERATION,
        )

    with utilities.open_file(args.file) as fd:
        print(
            utilities.json_dump(projects.export_zip(endpoint=sq, key_list=args.projectKeys, export_timeout=args.exportTimeout, threads=args.threads)),
            file=fd,
        )
    utilities.logger.info("Total execution time: %s", str(datetime.datetime.today() - start_time))
    sys.exit(0)


if __name__ == "__main__":
    main()
