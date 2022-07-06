#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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

    Audits a SUPPORT ticket SIF

"""
import sys
import os
import json
import argparse
import requests
from sonar import version, sif, options
import sonar.utilities as util
from sonar.audit import problem


def __get_args(desc):
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-p", "--password",
        required=False,
        default=os.getenv("JIRA_PASSWORD", None),
        help="Password to authenticate to JIRA, default is environment variable $JIRA_PASSWORD"
    )
    parser.add_argument(
        "-l", "--login",
        required=False,
        default=os.getenv("JIRA_LOGIN"),
        help="Password to authenticate to JIRA, default is environment variable $JIRA_LOGIN"
    )
    parser.add_argument(
        "-u", "--url",
        required=False,
        default="https://services.sonarsource.com",
        help="ServiceDesk URL, default is https://services.sonarsource.com"
    )
    parser.add_argument(
        "-v", "--" + util.OPT_VERBOSE,
        required=False,
        choices=["ERROR", "WARN", "INFO", "DEBUG"],
        default="ERROR",
        help="Logging verbosity level",
    )
    parser.add_argument("-t", "--ticket", required=True, help="Support ticket to audit")
    args = parser.parse_args()
    if not args.login or not args.password:
        util.exit_fatal("Login and Password are required to authenticate to ServiceDesk", options.ERR_TOKEN_MISSING)
    return args


def __get_sysinfo_from_ticket(**kwargs):
    ROOT = f'{kwargs["url"]}/rest/servicedeskapi/request'
    creds = (kwargs["login"], kwargs["password"])

    ticket = kwargs["ticket"] if kwargs["ticket"].startswith("SUPPORT-") else f'SUPPORT-{kwargs["ticket"]}'
    util.logger.debug("Check %s - URL %s", ticket, f"{ROOT}/{ticket}")
    r = requests.get(f"{ROOT}/{ticket}", auth=creds)
    if not r.ok:
        util.exit_fatal(f"Ticket {ticket}: URL '{ROOT}/{ticket}' status code {r.status_code}", options.ERR_SONAR_API)

    data = json.loads(r.text)
    util.logger.debug("Ticket %s found: searching SIF", ticket)
    sif_list = {}
    for d in data["requestFieldValues"]:
        if d.get('fieldId', '') != 'attachment':
            continue
        for v in d["value"]:
            file_type = v["filename"].split('.')[-1].lower()
            if file_type not in ('json', 'txt'):
                continue
            attachment_url = v["content"]
            attachment_file = attachment_url.split("/")[-1]
            util.logger.debug("Ticket %s: Verifying attachment '%s' found", ticket, attachment_file)
            r = requests.get(attachment_url, auth=creds)
            if not r.ok:
                util.exit_fatal(f"ERROR: Ticket {ticket} get attachment status code {r.status_code}", options.ERR_SONAR_API)
            try:
                sif_list[attachment_file] = json.loads(r.text)
            except:
                print(f"Ticket {ticket}: Attachment \'{attachment_file}\' is not a SIF, skipping")
                continue
    return sif_list

def main():
    args = __get_args("Audits a SonarQube platform or a SIF (Support Info File or System Info File)")
    kwargs = vars(args)
    util.check_environment(kwargs)
    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    sif_list = __get_sysinfo_from_ticket(**kwargs)
    problems = []
    for file, sysinfo in sif_list.items():
        try:
            problems += sif.Sif(sysinfo).audit()
        except (json.decoder.JSONDecodeError, sif.NotSystemInfo):
            util.logger.info("File %s does not seem to be a legit JSON file, skipped", file)

    kwargs["format"] = "csv"
    if problems:
        util.logger.warning("%d issues found during audit", len(problems))
    else:
        util.logger.info("%d issues found during audit", len(problems))
    problem.dump_report(problems, None, **kwargs)
    sys.exit(0)


if __name__ == "__main__":
    main()
