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
    "scan": "Execute Analysis"
}

PROJECT_PERMISSIONS = {
    "user": "Browse",
    "codeviewer": "See source code",
    "issueadmin": "Administer Issues",
    "securityhotspotadmin": "Create Projects",
    "scan": "Execute Analysis",
    "admin": "Administer Project"
}

def get(endpoint, perm_type, **kwargs):
    if perm_type not in ('users', 'groups'):
        return None
    kwargs['ps'] = 100
    data = json.loads(endpoint.get(f'permissions/{perm_type}', params=kwargs).text)
    active_perms = []
    for item in data.get(perm_type, []):
        if item['permissions']:
            active_perms.append(item)
    return active_perms


def counts(some_perms, perms_dict):
    perm_counts = {k: 0 for k in perms_dict}
    # counts = dict(zip(perms_dict.keys(), [0, 0, 0, 0, 0, 0, 0]))
    perm_counts['overall'] = 0
    for p in some_perms:
        if not p['permissions']:
            continue
        perm_counts['overall'] += 1
        for perm in PROJECT_PERMISSIONS:
            if perm in p['permissions']:
                perm_counts[perm] += 1
    return perm_counts


def simplify(perms_array):
    permiss = {}
    for p in perms_array:
        permiss[p['name']] = ', '.join(p['permissions'])
    return permiss


def __get_perms(endpoint, url, perm_type, pfield, params, exit_on_error):
    perms = []
    resp = endpoint.get(url, params=params, exit_on_error=exit_on_error)
    if (resp.status_code // 100) == 2:
        for p in json.loads(resp.text)[perm_type]:
            perms.append(p[pfield])
    elif resp.status_code not in (400, 404):
        utilities.exit_fatal(f"HTTP error {resp.status_code} - Exiting", options.ERR_SONAR_API)
    return perms

def get_qg(endpoint, qg_name, perm_type, pfield):
    perms = __get_perms(endpoint, f'qualitygates/search_{perm_type}', perm_type, pfield, {'gateName': qg_name}, False)
    return perms if len(perms) > 0 else None

def get_qp(endpoint, qp_name, qp_language, perm_type, pfield):
    perms = __get_perms(endpoint, f'qualityprofiles/search_{perm_type}', perm_type, pfield,
                        {'qualityProfile': qp_name, 'language': qp_language}, False)
    return perms if len(perms) > 0 else None
