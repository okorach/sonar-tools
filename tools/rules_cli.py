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
    Exports rules
"""
import sys
import csv
from sonar import rules, platform, version, options, exceptions
import sonar.utilities as util


def __get_fmt_and_file(args: object) -> tuple[str]:
    """Returns the desired format and file of export from the CLI args"""
    kwargs = vars(args)
    fmt = kwargs["format"]
    fname = kwargs.get("file", None)
    if fname is not None:
        ext = fname.split(".")[-1].lower()
        if ext in ("csv", "json"):
            fmt = ext
    return (fmt, fname)


def __parse_args(desc: str) -> object:
    """Sets and parses CLI arguments"""
    parser = util.set_common_args(desc)
    parser = util.set_key_arg(parser)
    parser = util.set_output_file_args(parser)
    parser.add_argument(
        "-m",
        "--metricKeys",
        required=False,
        help="Comma separated list of metrics or _all or _main",
    )
    parser.add_argument(
        "-e",
        required=False,
        action="store_true",
    )
    parser.add_argument(
        "--" + options.WITH_URL,
        action="store_true",
        default=False,
        required=False,
        help="Add rules URLs in report",
    )

    args = util.parse_and_check_token(parser)
    util.check_environment(vars(args))
    util.check_token(args.token)
    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    return args


def main() -> int:
    """Main entry point"""
    args = __parse_args("Extract rules")
    endpoint = platform.Platform(some_url=args.url, some_token=args.token, cert_file=args.clientCert, http_timeout=args.httpTimeout)

    (fmt, file) = __get_fmt_and_file(args)

    rule_list = rules.get_list(endpoint=endpoint)
    if fmt == "json":
        with util.open_file(file) as fd:
            print("[", end="", file=fd)
            for rule in rule_list.values():
                if not is_first:
                    print(",", end="", file=fd)
                print(util.json_dump(rule.to_json()), file=fd)
                is_first = False
            print("\n]\n", file=fd)
    if fmt == "csv":
        with util.open_file(file) as fd:
            csvwriter = csv.writer(fd, delimiter=args.csvSeparator, quotechar='"', quoting=csv.QUOTE_MINIMAL)
            for rule in rule_list.values():
                csvwriter.writerow([str(x) for x in rule.to_csv()])

    util.logger.info("%d rules exported", len(rule_list))
    sys.exit(0)


if __name__ == "__main__":
    main()
