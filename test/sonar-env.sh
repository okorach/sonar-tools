#!/usr/bin/bash

source ~/.sonar_rc

case $1 in
    lts)
        export SONAR_TOKEN=$SONAR_TOKEN_LTS_ADMIN_USER
        export SONAR_TOKEN_ADMIN=$SONAR_TOKEN_LTS_ADMIN_USER
        export SONAR_HOST_URL=$SONAR_HOST_URL_LTS
        # $SONAR_HOST_URL_LTS
        ;;
    lts-user)
        export SONAR_TOKEN=$SONAR_TOKEN_LTS_ADMIN_USER
        export SONAR_TOKEN_ADMIN=$SONAR_TOKEN_LTS_ADMIN_USER
        export SONAR_HOST_URL=$SONAR_HOST_URL_LTS
        # $SONAR_HOST_URL_LTS
        ;;
    lts-audit)
        export SONAR_TOKEN=$SONAR_TOKEN_LTS_ADMIN_ANALYSIS
        export SONAR_TOKEN_ADMIN=$SONAR_TOKEN_LTS_ADMIN_USER
        export SONAR_HOST_URL=http://localhost:9800
        ;;
    latest)
        export SONAR_TOKEN=$SONAR_TOKEN_LATEST_ADMIN_USER
        export SONAR_TOKEN_ADMIN=$SONAR_TOKEN_LATEST_ADMIN_USER
        export SONAR_HOST_URL=$SONAR_HOST_URL_LATEST
        ;;
    latest-user)
        export SONAR_TOKEN=$SONAR_TOKEN_LATEST_ADMIN_USER
        export SONAR_TOKEN_ADMIN=$SONAR_TOKEN_LATEST_ADMIN_USER
        export SONAR_HOST_URL=$SONAR_HOST_URL_LATEST
        ;;
    nautilus)
        export SONAR_TOKEN=$SONAR_TOKEN_NAUTILUS
        export SONAR_HOST_URL=$SONAR_HOST_URL_NAUTILUS
        ;;
    sonarcloud)
        export SONAR_TOKEN=$SONAR_TOKEN_SONARCLOUD
        export SONAR_HOST_URL=$SONAR_HOST_URL_SONARCLOUD
        ;;
    *)
        echo -u2 "Unsupported sonar environment $1 - Chose between latest lts or nautilus"
        ;;
esac
