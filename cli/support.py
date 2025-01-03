#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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
from http import HTTPStatus
import sys
import os
import json
import argparse
import requests

from cli import options
import sonar.logging as log
from sonar import sif, errcodes
from sonar.audit import problem, severities, config
import sonar.utilities as util

PRIVATE_COMMENT = [{"key": "sd.public.comment", "value": {"internal": "true"}}]


def __get_args(desc):
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-p",
        "--password",
        required=False,
        default=os.getenv("JIRA_PASSWORD", None),
        help="Password to authenticate to JIRA, default is environment variable $JIRA_PASSWORD",
    )
    parser.add_argument(
        "-l",
        "--login",
        required=False,
        default=os.getenv("JIRA_LOGIN"),
        help="Password to authenticate to JIRA, default is environment variable $JIRA_LOGIN",
    )
    parser.add_argument(
        "-u", "--url", required=False, default="https://services.sonarsource.com", help="ServiceDesk URL, default is https://services.sonarsource.com"
    )
    parser.add_argument(
        "-v",
        "--" + options.VERBOSE,
        required=False,
        choices=["ERROR", "WARN", "INFO", "DEBUG"],
        default="ERROR",
        help="Logging verbosity level, default is ERROR",
    )
    parser.add_argument(
        "-c",
        "--comment",
        required=False,
        dest="comment",
        action="store_true",
        default=False,
        help="Post a comment in the ticket after audit",
    )
    parser.add_argument("-t", "--ticket", required=True, help="Support ticket to audit, in format SUPPORT-XXXXX or XXXXX")
    args = parser.parse_args()
    if not args.login or not args.password:
        util.exit_fatal("Login and Password are required to authenticate to ServiceDesk", errcodes.TOKEN_MISSING)
    return args


def __get_issue_id(**kwargs):
    """Converts a ticket number into issue id needed to post on the issue"""
    tix = kwargs["ticket"]
    url = f'{kwargs["url"]}/rest/servicedeskapi/request/{tix}'
    r = requests.get(url, auth=kwargs["creds"], timeout=10)
    if not r.ok:
        if r.status_code == HTTPStatus.NOT_FOUND:
            return None
        else:
            util.exit_fatal(f"Ticket {tix}: URL '{url}' status code {r.status_code}", errcodes.SONAR_API)
    return json.loads(r.text)["issueId"]


def __add_comment(comment, **kwargs):
    url = f'{kwargs["url"]}/rest/api/2/issue/{__get_issue_id(**kwargs)}/comment'
    requests.post(url, auth=kwargs["creds"], json={"body": comment, "properties": PRIVATE_COMMENT}, timeout=10)


def __get_sysinfo_from_ticket(**kwargs):
    tix = kwargs["ticket"]
    url = f"{kwargs['url']}/rest/servicedeskapi/request/{tix}"
    log.debug("Check %s - URL %s", kwargs["ticket"], url)
    r = requests.get(url, auth=kwargs["creds"], timeout=10)
    if not r.ok:
        if r.status_code == HTTPStatus.NOT_FOUND:
            print(f"Ticket {tix} not found")
            sys.exit(3)
        else:
            util.exit_fatal(f"Ticket {tix}: URL '{url}' status code {r.status_code}", errcodes.SONAR_API)

    data = json.loads(r.text)
    log.debug("Ticket %s found: searching SIF", tix)
    sif_list = {}
    for d in data["requestFieldValues"]:
        if d.get("fieldId", "") != "attachment":
            continue
        for v in d["value"]:
            file_type = v["filename"].split(".")[-1].lower()
            if file_type not in ("json", "txt"):
                continue
            attachment_url = v["content"]
            attachment_file = attachment_url.split("/")[-1]
            log.info("Ticket %s: Verifying attachment '%s' found", tix, attachment_file)
            r = requests.get(attachment_url, auth=kwargs["creds"], timeout=10)
            if not r.ok:
                util.exit_fatal(f"ERROR: Ticket {tix} get attachment status code {r.status_code}", errcodes.SONAR_API)
            try:
                sif_list[attachment_file] = json.loads(r.text)
            except json.decoder.JSONDecodeError:
                log.info("Ticket %s: Attachment '%s' is not a JSON file, skipping", tix, attachment_file)
                continue
    return sif_list


def main():
    kwargs = vars(__get_args("Audits a Sonar ServiceDesk ticket (Searches for SIF attachment and audits SIF)"))
    kwargs["creds"] = (kwargs.pop("login"), kwargs.pop("password"))
    if not kwargs["ticket"].startswith("SUPPORT-"):
        kwargs["ticket"] = f'SUPPORT-{kwargs["ticket"]}'
    sif_list = __get_sysinfo_from_ticket(**kwargs)
    if len(sif_list) == 0:
        print(f"No SIF found in ticket {kwargs['ticket']}")
        sys.exit(2)
    problems = []
    settings = config.load("sonar-audit")
    found_problems = False
    comment = ""
    for file, sysinfo in sif_list.items():
        try:
            problems = sif.Sif(sysinfo).audit(settings)
            comment += f"h3. SIF *[^{file}]* audit:\n"
            print(f"SIF file '{file}' audit:")
            if problems:
                found_problems = True
                log.warning("%d issues found during audit", len(problems))
                problem.dump_report(problems, file=None, format="csv")
                for p in problems:
                    sev = "(x)" if p.severity in (severities.Severity.HIGH, severities.Severity.CRITICAL) else "(!)"
                    comment += f"{sev} {p.message}\n"
            else:
                log.info("%d issues found during audit", len(problems))
                print("No issues found is SIFs")
                comment += "(y) No issues found\n"

        except sif.NotSystemInfo:
            log.info("File '%s' does not seem to be a legit JSON file, skipped", file)

    if kwargs.pop("comment"):
        __add_comment(comment, **kwargs)

    sys.exit(1 if found_problems else 0)


if __name__ == "__main__":
    main()
