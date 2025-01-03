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

import csv

import sonar.logging as log
from sonar import utilities


class Problem:
    """
    Abstraction of an audit problem
    """

    def __init__(self, broken_rule: object, concerned_object: object, *args, **kwargs) -> None:
        # dict.__init__(type=problem_type, severity=severity, message=msg)
        self.concerned_object = concerned_object
        self.rule_id = broken_rule.id
        self.type = broken_rule.type
        self.severity = broken_rule.severity
        if len(args) > 0:
            self.message = broken_rule.msg.format(*args)
        else:
            self.message = broken_rule.msg
        if "severity" in kwargs:
            self.severity = kwargs["severity"]
        log.warning(self.message)

    def __str__(self):
        return f"Type: {self.type} - Severity: {self.severity} - Description: {self.message}"

    def to_json(self, with_url=False):
        d = vars(self).copy()
        d.pop("concerned_object")

        for k in ("severity", "type", "rule_id"):
            d[k] = str(d[k])
        if with_url:
            try:
                d["url"] = self.concerned_object.url()
            except AttributeError:
                d["url"] = str(self.concerned_object)
        return d


def dump_report(problems: list[Problem], file: str, server_id: str = None, format: str = "csv", with_url: bool = False, separator: str = ",") -> None:
    """Dumps to file a report about a list of problems

    :param list[Problems] problems: List of problems to dump
    :param str file: Filename to write the problems
    :param str server_id: ServerId of the platform having the problems
    :return: Nothing
    :rtype: None
    """
    log.info("Writing report to %s", f"file '{file}'" if file else "stdout")
    if format == "json":
        __dump_json(problems=problems, file=file, server_id=server_id, with_url=with_url)
    else:
        __dump_csv(problems=problems, file=file, server_id=server_id, with_url=with_url, separator=separator)


def __dump_csv(problems: list[Problem], file: str, server_id: str = None, with_url: bool = False, separator: str = ",") -> None:
    """Writes a list of problems in CSV format

    :param list[Problems] problems: List of problems to dump
    :param str file: Filename to write the problems
    :return: Nothing
    :rtype: None
    """
    with utilities.open_file(file, "w") as fd:
        csvwriter = csv.writer(fd, delimiter=separator)
        for p in problems:
            data = []
            if server_id is not None:
                data = [server_id]
            data += list(p.to_json(with_url).values())
            csvwriter.writerow(data)


def __dump_json(problems: list[Problem], file: str, server_id: str = None, with_url: bool = False) -> None:
    """Writes a list of problems in JSON format

    :param list[Problems] problems: List of problems to dump
    :param str file: Filename to write the problems
    :return: Nothing
    :rtype: None
    """
    sid_dict = {}
    if server_id is not None:
        sid_dict = {"server_id": server_id}
    json = [{**p.to_json(with_url), **sid_dict} for p in problems]
    with utilities.open_file(file) as fd:
        print(utilities.json_dump(json), file=fd)
