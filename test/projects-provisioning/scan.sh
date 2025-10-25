#!/bin/bash
# This script runs the SonarQube scanner for multiple projects

ME="$( basename "${BASH_SOURCE[0]}" )"
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

cd "$DIR"

url=${1:-$SONAR_HOST_URL}

projects="project1 project2 project3 project4 proyecto5"
for p in $projects; do
    echo "Processing $p"
    sonar-scanner -Dsonar.projectKey=$p -Dsonar.host.url=$url -Dsonar.branch.name=develop -Dsonar.login=$SONAR_TOKEN -Dsonar.token=$SONAR_TOKEN
done

branches="feature/new-feature some-branch release-3.x"
for b in $branches; do
    echo "Processing $p"
    sonar-scanner -Dsonar.projectKey=$p -Dsonar.host.url=$url -Dsonar.projectKey=project1 -Dsonar.branch.name=$b -Dsonar.login=$SONAR_TOKEN -Dsonar.token=$SONAR_TOKEN
done

projects=" \
test:project1 test:project2 test:project3 test:project4 test:proyecto5
INSURANCE-LIFE INSURANCE-HOME INSURANCE-PET INSURANCE-HEALTH
BANKING-INVESTMENT-ACQUISITIONS BANKING-INVESTMENT-EQUITY BANKING-INVESTMENT-DILIGENCE BANKING-INVESTMENT-MERGER
BANKING-RETAIL-ATM BANKING-RETAIL-WEB BANKING-RETAIL-CLERK
BANKING-TRADING-EURO BANKING-TRADING-JAPAN BANKING-TRADING-NASDAQ
BANKING-PRIVATE-ASSETS BANKING-PRIVATE-WEALTH 
BANKING-PORTAL
BANKING-ASIA-OPS BANKING-AFRICA-OPS
"

for p in $projects; do
    echo "Processing $p"
    sonar-scanner -Dsonar.projectKey=$p -Dsonar.host.url=$url -Dsonar.login=$SONAR_TOKEN -Dsonar.token=$SONAR_TOKEN
done

