#!/bin/bash

for proj in source target
do
   curl -X POST -u "$SONAR_TOKEN:" "$SONAR_HOST_URL/api/projects/delete?project=$proj"
   opts=("-Dsonar.projectKey=$proj" "-Dsonar.projectName=$proj")
   conf/run_all.sh "${opts[@]}" "$@"
   for branch in release-2.x release-2.x
   do
      conf/run_all.sh "${opts[@]}" "$@" "-Dsonar.branch.name=$branch"
   done
done
