#!/bin/bash
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
set -euo pipefail

DEFAULT_OPTS='-e SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true \
              -e SONAR_WEB_JAVAOPTS="-Xmx512m -Xms128m" \
              -e SONAR_CE_JAVAOPTS="-Xmx512m -Xms128m" \
              -e SONAR_SEARCH_JAVAOPTS="-Xmx512m -Xms512m'

usage() { echo "Usage: $0 [-e ce|de|ee] [-v lts|latest] [-p <port>] [-s|-S]" 1>&2; exit 1; }

edition="enterprise"
port=""
op="start"
while getopts ":e:p:v:sS" o; do
    case "${o}" in
        e)
            if [ "${OPTARG}" = "ce" ]; then
                edition="community"
            elif [ "${OPTARG}" = "de" ]; then
                edition="developer"
            elif [ "${OPTARG}" = "ee" ]; then
                edition="enterprise"
            else
                echo "ERROR: Wrong edition ${OPTARG}" && usage
            fi
            ;;
        p)
            port=${OPTARG}
            ;;
        v)
            if [  "${OPTARG}" != "lts" ] && [ "${OPTARG}" != "latest" ]; then
                echo "ERROR: Wrong version ${OPTARG}" && usage
            fi
            version=${OPTARG}
            ;;
        S)
            op="stop"
            ;;
        s)
            op="start"
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

if [ "$port" = "" ]; then
    if [ "$version" = "lts" ]; then
        pfx="8"
    else
        pfx="9"
    fi
    if  [ "$edition" = "enterprise" ]; then
        port="${pfx}800"
    elif  [ "$edition" = "developer" ]; then
        port="${pfx}700"
    else
        port="${pfx}600"
    fi
fi

pfx=""
if [ "$version" = "lts" ]; then
    pfx="lts-"
fi

#SONAR_JDBC_USERNAME=
#SONAR_JDBC_PASSWORD=

if [ "$op" = "start" ]; then
    echo "docker run -d --name \"sonar-$version-$edition\" $DEFAULT_OPTS -p \"$port:9000\" sonarqube:${pfx}${edition}"
    docker run -d --name "sonar-$version-$edition" "$DEFAULT_OPTS" -p "$port:9000" "sonarqube:${pfx}${edition}"
else
    docker stop "sonar-$version-$edition"
    docker rm "sonar-$version-$edition"
fi