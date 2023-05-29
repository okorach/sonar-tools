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
    This script manipulates custom measures. You may:

    Update a custom measure value:
        Usage: cust_measures.py -t <SQ_TOKEN> -u <SQ_URL> -k <projectKey> -m <metricKey> --updateValue <value>
"""

from sonar import custom_measures, platform, utilities, options


def parse_args(desc):
    parser = utilities.set_common_args(desc)
    parser = utilities.set_key_arg(parser)
    parser.add_argument("-m", "--metricKey", required=True, help="What custom metric to work on")
    parser.add_argument("--value", required=False, help="Updates the value of the metric")
    parser.add_argument("--description", required=False, help="Updates the description of the metric")
    return utilities.parse_and_check_token(parser)


def main():
    args = parse_args("Manipulate custom metrics")
    sqenv = platform.Platform(some_url=args.url, some_token=args.token)
    if sqenv.version() >= (9, 0, 0):
        utilities.exit_fatal("Custom measures are no longer supported after 8.9.x", options.UnsupportedOperation)
    else:
        utilities.logger.warning("Custom measures are are deprecated in 8.9 and lower and are dropped starting from SonarQube 9.0")
    # Remove unset params from the dict
    params = vars(args)
    for key in params.copy():
        if params[key] is None:
            del params[key]
    # Add SQ environment
    params.update({"env": sqenv})

    if params.get("value", None) is not None:
        custom_measures.update(
            project_key=params["componentKeys"],
            metric_key=params["metricKey"],
            value=params["value"],
            description=params.get("description", None),
        )


if __name__ == "__main__":
    main()
