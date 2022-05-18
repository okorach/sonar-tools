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
