#!/bin/bash

source ~/.sonar_rc

case $1 in
   9)
      url=$SONAR_HOST_URL_9
      ;;
   9-ce)
      url=$SONAR_HOST_URL_9_CE
      ;;
   9-de)
      url=$SONAR_HOST_URL_9_DE
      ;;
   lts)
      url=$SONAR_HOST_URL_LTS
      ;;
   lts-de)
      url=$SONAR_HOST_URL_LTS_DE
      ;;
   latest)
      url=$SONAR_HOST_URL_LATEST
      ;;
   latest-de)
      url=$SONAR_HOST_URL_LATEST_DE
      ;;
   cb)
      url=$SONAR_HOST_URL_CB
      ;;
   cloud)
      url="https://sonarcloud.io"
      ;;
   *)
      echo "Error: Usage: $0 [lts|latest|lts-de|latest-de|cb|9|9-de|9-ce|cloud]"
      return
      ;;
esac

export SONAR_HOST_URL=$url

echo "SONAR_HOST_URL=$url"
