#!/bin/bash

DOCKER_URL=http://host.docker.internal:10000
HOST_URL=http://localhost:10000

DOCKER_LOG="sonar-tools.docker.log"
HOST_LOG="sonar-tools.host.log"

DOCKER_OPTS="-u $DOCKER_URL -t $SONAR_TOKEN -l $DOCKER_LOG"
HOST_OPTS="-u $HOST_URL -t $SONAR_TOKEN -l $HOST_LOG"

DIR="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source "$DIR/it-tools.sh"

announce_test "sonar-loc"
docker run --rm -w `pwd` -v `pwd`:`pwd` -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=$DOCKER_URL sonar-tools sonar-loc -l $DOCKER_LOG -f loc.docker.csv 2>/dev/null
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-loc $DOCKER_OPTS -f loc.docker.2.csv 2>/dev/null
test_passed_if_identical loc.docker.csv loc.docker.2.csv

announce_test "sonar-loc 2"
sonar-loc $HOST_OPTS -f loc.host.csv 2>/dev/null
test_passed_if_identical loc.docker.csv loc.host.csv

announce_test "sonar-measures-export"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-measures-export $DOCKER_OPTS 2>/dev/null | sort > measures.docker.csv
sonar-measures-export $HOST_OPTS 2>/dev/null | sort > measures.host.csv
test_passed_if_identical measures.docker.csv measures.host.csv

announce_test "sonar-findings-export"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-findings-export $DOCKER_OPTS -f findings.docker.csv 2>/dev/null
sort -o findings.docker.csv findings.docker.csv
sonar-findings-export $HOST_OPTS 2>/dev/null | sort > findings.host.csv
test_passed_if_identical findings.docker.csv findings.host.csv

announce_test "sonar-config export"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-config $DOCKER_OPTS -e -f config.docker.json 2>/dev/null
sonar-config $HOST_OPTS -e -f config.host.json 2>/dev/null
test_passed_if_identical config.docker.json config.host.json

announce_test "sonar-audit"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-audit $DOCKER_OPTS 2>/dev/null | sort > audit.docker.csv
sonar-audit $HOST_OPTS 2>/dev/null | sort > audit.host.csv
# MacOS style sed
sed -i '' 's/[0-9]\{1,\} deprecation/some deprecation/' audit.docker.csv
sed -i '' 's/[0-9]\{1,\} deprecation/some deprecation/' audit.host.csv
test_passed_if_identical audit.docker.csv audit.host.csv

announce_test "sonar-projects-export"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-projects-export $DOCKER_OPTS -k "project1,project2,project8" -f proj-export.docker.json 2>/dev/null
test_result $?

announce_test "sonar-rules"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-rules $DOCKER_OPTS 2>/dev/null | sort > rules.docker.csv
sonar-rules $HOST_OPTS 2>/dev/null | sort > rules.host.csv
test_passed_if_identical rules.docker.csv rules.host.csv

announce_test "sonar-housekeeper"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-housekeeper $DOCKER_OPTS 2>/dev/null | sort > housekeeper.docker.csv
sonar-housekeeper $HOST_OPTS 2>/dev/null | sort > housekeeper.host.csv
test_passed_if_identical housekeeper.docker.csv housekeeper.host.csv
