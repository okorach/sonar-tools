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

    Exports all projects of a SonarQube platform

"""
import sys

from cli import options
from sonar import platform, utilities, exceptions, projects, errcodes


def main():
    start_time = utilities.start_clock()
    parser = options.set_common_args("Exports all projects of a SonarQube platform")
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, json_fmt=True, csv_fmt=False)
    parser = options.add_thread_arg(parser, "projects zip export")
    parser.add_argument(
        "--exportTimeout",
        required=False,
        type=int,
        default=180,
        help="Maximum wait time for export",
    )
    kwargs = utilities.convert_args(options.parse_and_check(parser=parser, logger_name="sonar-projects-export"))
    sq = platform.Platform(**kwargs)

    if sq.edition() in ("community", "developer") and sq.version(digits=2) < (9, 2):
        utilities.exit_fatal(
            "Can't export projects on Community and Developer Edition before 9.2, aborting...",
            errcodes.UNSUPPORTED_OPERATION,
        )

    try:
        dump = projects.export_zip(
            endpoint=sq, key_list=kwargs[options.KEYS], export_timeout=kwargs["exportTimeout"], threads=kwargs[options.NBR_THREADS]
        )
    except exceptions.ObjectNotFound:
        sys.exit(errcodes.NO_SUCH_KEY)

    with utilities.open_file(kwargs[options.OUTPUTFILE]) as fd:
        print(utilities.json_dump(dump), file=fd)

    utilities.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
