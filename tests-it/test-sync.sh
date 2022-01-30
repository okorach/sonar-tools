for proj in source target
do
	curl -X POST -u $SONAR_TOKEN: "$SONAR_HOST_URL/api/projects/delete?project=$proj"
	opts="-Dsonar.projectKey=$proj -Dsonar.projectName=$proj"
	scan.sh $opts
	for branch in release-1.x
	do
		scan.sh $* $opts -Dsonar.branch.name=$branch
	done
done
