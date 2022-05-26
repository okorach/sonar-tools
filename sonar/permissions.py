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

import json
from sonar import utilities, options

GLOBAL_PERMISSIONS = {
    "admin": "Administer System",
    "gateadmin": "Administer Quality Gates",
    "profileadmin": "Administer Quality Profiles",
    "provisioning": "Create Projects",
    "portfoliocreator": "Create Portfolios",
    "applicationcreator": "Create Applications",
    "scan": "Execute Analysis",
}

PROJECT_PERMISSIONS = {
    "user": "Browse",
    "codeviewer": "See source code",
    "issueadmin": "Administer Issues",
    "securityhotspotadmin": "Create Projects",
    "scan": "Execute Analysis",
    "admin": "Administer Project",
}

__MAX_PERMS = 100
__MAX_QG_PERMS = 25


def get(endpoint, perm_type, **kwargs):
    if perm_type not in ("users", "groups", "template_users", "template_groups"):
        return None
    params = kwargs.copy()
    params["ps"] = __MAX_PERMS
    perms = []
    page, nbr_pages = 1, 1
    short_perm = perm_type.replace("template_", "")
    while page <= nbr_pages:
        params["p"] = page
        data = json.loads(endpoint.get(f"permissions/{perm_type}", params=params).text)
        # Workaround for SQ 7.9+, all groups/users even w/o permissions are returned
        # Stop collecting permissions as soon as 5 groups with no permissions are encountered
        no_perms_count = 0
        for item in data.get(short_perm, []):
            no_perms_count = 0 if item["permissions"] else no_perms_count + 1
            if item["permissions"]:
                perms.append(item)
            if no_perms_count >= 5:
                break
        if no_perms_count >= 5:
            break
        nbr_pages = utilities.nbr_pages(data)
        page += 1
    return perms


def export(endpoint, component_key=None):
    exp = {}
    for perm_type in ("users", "groups"):
        exp[perm_type] = simplify(get(endpoint, perm_type, projectKey=component_key))
        if len(exp[perm_type]) == 0:
            exp.pop(perm_type)
    return exp


def counts(some_perms, perms_dict):
    perm_counts = {k: 0 for k in perms_dict}
    # counts = dict(zip(perms_dict.keys(), [0, 0, 0, 0, 0, 0, 0]))
    perm_counts["overall"] = 0
    for p in some_perms:
        if not p["permissions"]:
            continue
        perm_counts["overall"] += 1
        for perm in PROJECT_PERMISSIONS:
            if perm in p["permissions"]:
                perm_counts[perm] += 1
    return perm_counts


def simplify(perms_array):
    permiss = {}
    for p in perms_array:
        permiss[p["name"]] = ", ".join(p["permissions"])
    return permiss


def __get_perms(endpoint, url, perm_type, pfield, params, exit_on_error):
    perms = []
    new_params = {} if params is None else params.copy()
    new_params["ps"] = __MAX_QG_PERMS
    page, nbr_pages = 1, 1
    while page <= nbr_pages:
        new_params["p"] = page
        resp = endpoint.get(url, params=new_params, exit_on_error=exit_on_error)
        if (resp.status_code // 100) == 2:
            data = json.loads(resp.text)
            for p in data[perm_type]:
                perms.append(p[pfield])
            nbr_pages = utilities.int_div_ceil(data["paging"]["total"], __MAX_QG_PERMS)
            page += 1
        elif resp.status_code not in (400, 404):
            utilities.exit_fatal(f"HTTP error {resp.status_code} - Exiting", options.ERR_SONAR_API)
        else:
            break
    return perms


def get_qg(endpoint, qg_name, perm_type, pfield):
    perms = __get_perms(
        endpoint,
        f"qualitygates/search_{perm_type}",
        perm_type,
        pfield,
        {"gateName": qg_name},
        False,
    )
    return perms if len(perms) > 0 else None


def get_qp(endpoint, qp_name, qp_language, perm_type, pfield):
    perms = __get_perms(
        endpoint,
        f"qualityprofiles/search_{perm_type}",
        perm_type,
        pfield,
        {"qualityProfile": qp_name, "language": qp_language},
        False,
    )
    return perms if len(perms) > 0 else None
