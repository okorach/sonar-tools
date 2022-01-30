for proj in source target
do
	opts="-Dsonar.projectKey=$proj -Dsonar.projectName=$proj"
	scan.sh $opts
	for branch in release-1.x hotfix
	do
		scan.sh $opts -Dsonar.branch.name=$branch
	done
done
