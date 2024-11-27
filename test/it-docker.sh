#!/bin/bash
#
# sonar-tools
# Copyright (C) 2021-2024 Olivier Korach
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

env=${1:-gen}

DIR="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source "$DIR/it-tools.sh"
IT_LOG_FILE="$TMP/it.log"

# DOCKER_COMMON="docker run --rm -w `pwd` -v `pwd`:/home/sonar olivierkorach/sonar-tools"
DOCKER_COMMON="docker run --rm olivierkorach/sonar-tools"
CREDS="-u $SONAR_HOST_URL -t $SONAR_TOKEN"
root="docker-$env"

for cmd in loc measures-export rules
do
    f="$root-$cmd-stdout.csv"; run_test_stdout "$f" $DOCKER_COMMON "sonar-$cmd" $CREDS
done

f="$root-audit-stdout.csv"; run_test_stdout "$f" $DOCKER_COMMON sonar-audit -w settings,users,groups,qualitygates $CREDS

f="$root-findings-stdout.csv"; run_test_stdout "$f" $DOCKER_COMMON sonar-findings-export --severities BLOCKER,CRITICAL $CREDS

f="$root-config-stdout.json"; run_test_stdout "$f" $DOCKER_COMMON sonar-config -e -w qualitygates,users,groups $CREDS

f="$root-housekeeper-stdout.csv"; run_test_stdout "$f" $DOCKER_COMMON "sonar-housekeeper" $CREDS

f="$root-tools.txt"; run_test_stdout "$f" $DOCKER_COMMON

DOCKER_COMMON="docker run -w /home/sonar -v `pwd`:/home/sonar --rm olivierkorach/sonar-tools"
HOST_IT_LOG=$IT_LOG_FILE
IT_LOG_FILE="it.log"
CREDS="-u $SONAR_HOST_URL -t $SONAR_TOKEN -l $IT_LOG_FILE"

for cmd in loc measures-export rules
do
    f="$root-$cmd-file.csv"; run_test "$f" $DOCKER_COMMON "sonar-$cmd" $CREDS
    mv "$f" "$TMP"
    cat $IT_LOG_FILE >>$HOST_IT_LOG
done

f="$root-audit-file.csv"; run_test "$f" $DOCKER_COMMON sonar-audit -w settings,users,groups,qualitygates $CREDS
mv "$f" "$TMP"
cat $IT_LOG_FILE >>$HOST_IT_LOG
f="$root-findings-file.csv"; run_test "$f" $DOCKER_COMMON sonar-findings-export --severities BLOCKER,CRITICAL $CREDS
mv "$f" "$TMP"
cat $IT_LOG_FILE >>$HOST_IT_LOG
f="$root-config-file.json"; run_test "$f" $DOCKER_COMMON sonar-config -e -w qualitygates,users,groups $CREDS
mv "$f" "$TMP"
cat $IT_LOG_FILE >>$HOST_IT_LOG
