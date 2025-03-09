#!/bin/bash
#
# sonar-tools
# Copyright (C) 2021-2025 Olivier Korach
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

REPO_ROOT="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; cd ../.. ; pwd -P )"
TMP="$REPO_ROOT/tmp"
IT_LOG_FILE="$TMP/it.log"
mkdir -p "$TMP"

YELLOW=$(tput setaf 3)
RED=$(tput setaf 1)
GREEN=$(tput setaf 2)
RESET=$(tput setaf 7)

function logmsg {
    echo "$@" | tee -a "$IT_LOG_FILE"
}

function run_test {
    file=$1; shift
    announced_args=$(get_announced_args $@)  
    announce_test "$announced_args -f $file"
    if [ "$1" != "docker" ]; then
        file="$REPO_ROOT/tmp/$file"
    fi
    if [ "$SONAR_HOST_URL" == "$SONAR_HOST_URL_SONARCLOUD" ]; then
        "$@" -o okorach -f "$file" 2>>$IT_LOG_FILE
    else
        # echo "$@" -f "$file"
        "$@" -f "$file" 2>>$IT_LOG_FILE
    fi
    test_passed_if_file_not_empty "$file"
}

function get_announced_args {
    skipnext="false"
    announced_args=""
    for arg in $@; do
        if [ "$arg" = "-t" ] ||  [ "$arg" = "-u" ]; then
            skipnext="true"
        elif [ "$skipnext" = "true" ]; then
            skipnext="false"
        else
            announced_args="$announced_args $arg"
        fi
    done
    echo $announced_args 
}

function run_test_stdout {
    file=$1; shift
    announced_args=$(get_announced_args $@)  
    announce_test "$announced_args >$file"
    file="$REPO_ROOT/tmp/$file"
    if [ "$SONAR_HOST_URL" == "$SONAR_HOST_URL_SONARCLOUD" ]; then
        "$@" -o okorach >"$file" 2>>$IT_LOG_FILE
    else
        "$@" >"$file" 2>>$IT_LOG_FILE
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