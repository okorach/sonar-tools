#!/bin/bash

DOCKER_URL=http://host.docker.internal:10000
HOST_URL=http://localhost:10000

DOCKER_LOG="sonar-tools.docker.log"
HOST_LOG="sonar-tools.host.log"

DOCKER_OPTS="-u $DOCKER_URL -t $SONAR_TOKEN -l $DOCKER_LOG"
HOST_OPTS="-u $HOST_URL -t $SONAR_TOKEN -l $HOST_LOG"

DIR="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"
source "$DIR/test-tools.sh"

echo "=== Test sonar-findings-export"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-findings-export $DOCKER_OPTS -f findings.tmp.csv 2>/dev/null
sort findings.tmp.csv >findings.docker.csv
sonar-findings-export $HOST_OPTS 2>/dev/null | sort > findings.host.csv
test_passed_if_identical findings.docker.csv findings.host.csv

exit 0

echo "=== Test sonar-loc"
docker run --rm -w `pwd` -v `pwd`:`pwd` -e SONAR_TOKEN=$SONAR_TOKEN -e SONAR_HOST_URL=$DOCKER_URL sonar-tools sonar-loc -l $DOCKER_LOG -f loc.docker.csv 2>/dev/null
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-loc $DOCKER_OPTS -f loc.docker.2.csv 2>/dev/null
test_passed_if_identical loc.docker.csv loc.docker.2.csv

echo "=== Test sonar-loc 2"
sonar-loc $HOST_OPTS -f loc.host.csv 2>/dev/null
test_passed_if_identical loc.docker.csv loc.host.csv

echo "=== Test sonar-measures-export"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-measures-export $DOCKER_OPTS 2>/dev/null | sort > measures.docker.csv
sonar-measures-export $HOST_OPTS  | sort > measures.host.csv
test_passed_if_identical measures.docker.csv measures.host.csv

echo "=== Test sonar-findings-export"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-findings-export $DOCKER_OPTS -f findings.tmp.csv 2>/dev/null
sort findings.tmp.csv >findings.docker.csv
sonar-findings-export $HOST_OPTS  2>/dev/null | sort > findings.host.csv
test_passed_if_identical findings.docker.csv findings.host.csv

echo "Test sonar-config"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-config $DOCKER_OPTS -f config.docker.json 2>/dev/null
sonar-config $HOST_OPTS -f config.host.json 2>/dev/null
test_passed_if_identical config.docker.json config.host.json

echo "Test sonar-audit"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-audit $DOCKER_OPTS 2>/dev/null | sort > audit.docker.csv
sonar-audit $HOST_OPTS 2>/dev/null | sort > audit.host.csv
test_passed_if_identical audit.docker.csv audit.host.csv

echo "Test sonar-projects-export"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-projects-export $DOCKER_OPTS -k "project1,project2,project8" -f proj-export.docker.json 2>/dev/null

echo "Test sonar-rules"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-rules $DOCKER_OPTS 2>/dev/null | sort > rules.docker.csv
sonar-rules $HOST_OPTS 2>/dev/null | sort > rules.host.csv
test_passed_if_identical rules.docker.csv rules.host.csv

echo "Test sonar-housekeeper"
docker run --rm -w `pwd` -v `pwd`:`pwd` sonar-tools sonar-housekeeper $DOCKER_OPTS 2>/dev/null | sort > housekeeper.docker.csv
sonar-housekeeper $HOST_OPTS 2>/dev/null | sort > housekeeper.host.csv
test_passed_if_identical housekeeper.docker.csv housekeeper.host.csv
