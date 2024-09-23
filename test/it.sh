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
set -euo pipefail

DIR="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source "$DIR/test-tools.sh"
DB_BACKUPS_DIR=~/backup

function backup_for {
    case $1 in
        lts|lta|lts-ce|lta-ce|lts-de|lta-de)
            db="$DB_BACKUPS_DIR/db.lts.backup"
            ;;
        lts-audit|lta-audit|lts-audit-ce|lta-audit-ce|lts-audit-de|lta-audit-de)
            db="$DB_BACKUPS_DIR/db.lts-audit.backup"
            ;;
        latest|latest-ce|latest-de|latest-audit|latest-audit-ce|latest-audit-de)
            db="$DB_BACKUPS_DIR/db.latest.backup"
            ;;
        *)
            logmsg "ERROR: Instance $1 has no correspon ding DB backup"
            db="NO_DB_BACKUP"
    esac
    echo $db
}

function tag_for {
    case $1 in
        lts|lta|lts-audit|lta-audit)
            tag="lts-enterprise"
            ;;
        lts-ce|lta-ce|lts-audit-ce|lta-audit-ce)
            tag="lts-community"
            ;;
        lts-de|lta-de|lts-de-audit|lta-de-audit)
            tag="lts-developer"
            ;;
        latest|latest-audit)
            tag="enterprise"
            ;;
        latest-de|latest-audit-de)
            tag="developer"
            ;;
        latest-ce|latest-audit-ce)
            tag="latest"
            ;;
        *)
            logmsg "ERROR: Instance $1 has no corresponding tag"
            tag="NO_TAG"
    esac
    echo $tag
}

[ $# -eq 0 ] && echo "Usage: $0 <env1> [... <envN>]" && exit 1

REPO_ROOT="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; cd .. ; pwd -P )"
TMP="$REPO_ROOT/tmp"
IT_LOG_FILE="$TMP/it.log"
mkdir -p "$TMP"
rm -f "$TMP"/*.log "$TMP"/*.csv "$TMP"/*.json

noExport=0
if [ "$1" == "--noExport" ]; then
    noExport=1
    shift
fi

logmsg "$(date)"

for env in "$@"
do

    logmsg "Install sonar-tools current local version: root = $TMP"
    cd "$REPO_ROOT"; ./deploy.sh nodoc nodocker 1>$IT_LOG_FILE 2>&1; cd -

    if [ "$env" = "sonarcloud" ]; then
        logmsg "Running with environment $env"
        export SONAR_TOKEN=$SONAR_TOKEN_SONARCLOUD
        export SONAR_HOST_URL=$SONAR_HOST_URL_SONARCLOUD        
    else
        id="it$$"
        logmsg "Creating IT test environment $env - sonarId $id"
        sqport=10020
        # echo sonar create -i $id -t "$(tag_for "$env")" -s $sqport -p 6020 -f "$(backup_for "$env")"
        sonar create -i $id -t "$(tag_for "$env")" -s $sqport -p 6020 -f "$(backup_for "$env")" 1>$IT_LOG_FILE 2>&1
        export SONAR_TOKEN=$SONAR_TOKEN_ADMIN_USER
        export SONAR_HOST_URL="http://localhost:$sqport"
    fi

    f="measures-$env-unrel.csv"; run_test "$f" sonar-measures-export -b -f "$f" -m _main --withURL
    f="measures-$env-2.csv";     run_test_stdout "$f" sonar-measures-export -b -m _main --withURL
    f="measures-$env-3.csv";     run_test_stdout "$f" sonar-measures-export -b -p -r -d -m _all

    f="measures-$env-1.json";    run_test "$f" sonar-measures-export -b -f "$f" -m _all
    f="measures-$env-2.json";    run_test_stdout "$f" sonar-measures-export -b -p -r -d -m _all --format json
    f="measures-$env-3.csv";     run_test "$f" sonar-measures-export -b -f "$f" --csvSeparator '+' -m _main

    f="measures-history-$env-1.csv";     run_test "$f" sonar-measures-export -b -f "$f" --history
    f="measures-history-$env-2.csv";     run_test "$f" sonar-measures-export -b -f "$f" -k okorach_sonar-tools --history --asTable
    f="measures-history-$env-3.json";    run_test "$f" sonar-measures-export -b -f "$f" --history

    logmsg "IT $env sonar-findings-export"

    f="findings-$env-unrel.csv";  run_test "$f" sonar-findings-export -v DEBUG -f "$f"
    f="findings-$env-1.json";     run_test "$f" sonar-findings-export -f "$f"
    f="findings-$env-2.json";     run_test_stdout "$f" sonar-findings-export -v DEBUG --format json -k okorach_audio-video-tools,okorach_sonar-tools
    f="findings-$env-3.json";     run_test_stdout "$f" sonar-findings-export -v DEBUG --format json -k okorach_audio-video-tools,okorach_sonar-tools --useFindings
    f="findings-$env-4.csv";      run_test_stdout "$f" sonar-findings-export --format csv -k okorach_audio-video-tools,okorach_sonar-tools --csvSeparator '+'
    
    if [ "$env" = "sonarcloud" ]; then
        logmsg "IT $env sonar-audit SKIPPED"
        logmsg "IT $env sonar-housekeeper SKIPPED"
    else
        logmsg "IT $env sonar-audit"
        f="audit-$env-unrel.csv";     run_test_stdout "$f" sonar-audit
        f="audit-$env-1.json";        run_test "$f" sonar-audit -f "$f"
        f="audit-$env-2.json";        run_test_stdout "$f" sonar-audit --format json --what qualitygates,qualityprofiles,settings
        f="audit-$env-3.csv";         run_test_stdout "$f" sonar-audit  --csvSeparator '+' --format csv

        logmsg "IT $env sonar-housekeeper"
        f="housekeeper-$env-1.csv";   run_test_stdout "$f" sonar-housekeeper -P 365 -B 90 -T 180 -R 30
    fi

    logmsg "IT $env sonar-loc"
    f="loc-$env-1.csv";           run_test_stdout "$f" sonar-loc
    f="loc-$env-unrel.csv";       run_test_stdout "$f" sonar-loc -n -a
    f="loc-$env-2.csv";           run_test "$f" sonar-loc -n -a -f "$f" --csvSeparator ';'

    logmsg "sonar-rules $env"
    f="rules-$env-1.csv";         run_test_stdout "$f" sonar-rules -e
    f="rules-$env-2.csv";         run_test "$f" sonar-rules -e -f "$f"
    f="rules-$env-3.json";        run_test_stdout "$f" sonar-rules -e --format json
    f="rules-$env-4.json";        run_test "$f" sonar-rules -e -f "$f"

    logmsg "sonar-config $env"
    f="config-$env-1.json";       run_test_stdout "$f" sonar-config -e -w "qualitygates, qualityprofiles, projects" -k okorach_audio-video-tools,okorach_sonar-tools
    f="config-$env-2.json";       run_test_stdout "$f" sonar-config --export
    f="config-$env-unrel.json";   run_test "$f" sonar-config --export -f "$f"

    if [ $noExport -eq 1 ]; then
        logmsg "sonar-projects-export $env test skipped"
    elif [ "$env" = "sonarcloud" ]; then
        logmsg "sonar-projects-export $env SKIPPED"
    else
        logmsg "sonar-projects-export $env"
        sonar-projects-export
    fi

    logmsg "sonar-findings-export $env ADMIN export"
    f1="findings-$env-admin.csv";   run_test "$f1" sonar-findings-export -v DEBUG -f "$f1" -k okorach_audio-video-tools,okorach_sonar-tools

    if [ "$env" = "sonarcloud" ]; then
        logmsg "sonar-projects-export $env SKIPPED"
    else
        logmsg "sonar-findings-export $env USER export"
        export SONAR_TOKEN=$SONAR_TOKEN_USER_USER
        f2="findings-$env-user.csv";    run_test "$f2" sonar-findings-export -v DEBUG -f "$f2" -k okorach_audio-video-tools,okorach_sonar-tools
    fi

    # Restore admin token as long as previous version is 2.9 or less
    logmsg "Restore sonar-tools last released version"
    pip install --force-reinstall sonar-tools
    
    export SONAR_TOKEN="$SONAR_TOKEN_ADMIN_USER"
    logmsg "IT released tools $env"
    run_test sonar-measures-export -b -f "measures-$env-rel.csv" -m _main --withURL
    run_test sonar-findings-export -f "findings-$env-rel.csv"
    run_test sonar-audit -f "audit-$env-rel.csv"
    run_test sonar-loc -n -a -f "loc-$env-rel.csv"
    run_test sonar-config -e -f "config-$env-rel.json"

    logmsg "IT compare released and unreleased $env"
    for f in measures findings audit loc
    do
        root="$f-$env"
        announce_test "$f-$env diff"
        sort -o "$root-rel.csv" "$root-rel.csv"
        sort -o "$root-unrel.csv" "$root-unrel.csv"
        test_passed_if_identical "$TMP/$root-rel.csv" "$TMP/$root-unrel.csv"
    done
    for f in config
    do
        root="$f-$env"
        announce_test "$f-$env diff"
        test_passed_if_identical "$TMP/$root-rel.json" "$TMP/$root-unrel.json"
    done
    announce_test "findings-$env admin vs user diff"
    test_passed_if_identical "$TMP/findings-$env-admin.csv" "$TMP/findings-$env-user.csv"
    if [ "$env" != "sonarcloud" ]; then
        logmsg "Deleting environment sonarId $id"
        sonar delete -i "$id"
    fi
done

logmsg "====================================="
logmsg "          IT tests end"
logmsg "====================================="
