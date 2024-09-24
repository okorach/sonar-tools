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

#set -euo pipefail

REPO_ROOT="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; cd .. ; pwd -P )"
TMP="$REPO_ROOT/tmp"
IT_LOG_FILE="$TMP/it.log"
mkdir -p "$TMP"

RED=$(tput setaf 1)
GREEN=$(tput setaf 2)
RESET=$(tput setaf 7)

function logmsg {
    echo "$@" | tee -a "$IT_LOG_FILE"
}

function run_test {
    file=$1; shift
    announce_test "$@ -f $file"
    file="$REPO_ROOT/tmp/$file"
    # logmsg "========================================="
    # logmsg "$@"
    # logmsg "========================================="
    if [ "$SONAR_HOST_URL" == "$SONAR_HOST_URL_SONARCLOUD" ]; then
        "$@" -o okorach -l $IT_LOG_FILE -f "$file" >/dev/null
    else
        # echo "$@" -o okorach -l $IT_LOG_FILE -f "$file"
        "$@" -l $IT_LOG_FILE -f "$file" 2>/dev/null
    fi
    test_passed_if_file_not_empty "$file"
}

function run_test_stdout {
    file=$1; shift
    announce_test "$@ >$file"
    file="$REPO_ROOT/tmp/$file"
    
    # logmsg "========================================="
    # logmsg "$@ >$file"
    # logmsg "========================================="
    if [ "$SONAR_HOST_URL" == "$SONAR_HOST_URL_SONARCLOUD" ]; then
        "$@" -o okorach -l $IT_LOG_FILE >"$file" 2>/dev/null
    else
        # echo "$@" -o okorach -l $IT_LOG_FILE "> $file"
        "$@" -l $IT_LOG_FILE >"$file" 2>/dev/null
    fi
    test_passed_if_file_not_empty "$file"
}

check_file_not_empty() {
    if [ -s "$1" ]; then
        logmsg "Output file $1 is OK"
    else
        logmsg "Output file $1 is missing or empty"
        # exit 1
    fi
}

test_passed_if_identical() {
    code=0
    diff $* >> $IT_LOG_FILE || code=$? || true
    test_result $code
    return $code
}

test_passed_if_file_not_empty() {
    [ -s "$1" ]
    code=$?
    test_result $code
    return $code
}

test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "--> ${GREEN}PASSED${RESET}"
    else
        echo -e "==> ${RED}*** FAILED ***${RESET}"
    fi
}

announce_test() {
    echo -n "Test: $* "
}