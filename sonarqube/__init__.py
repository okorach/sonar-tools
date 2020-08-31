import sys
import sonarqube.audit_rules as rules

try:
    rules.load()
except rules.RuleConfigError as e:
    print(e.message)
    sys.exit(3)
