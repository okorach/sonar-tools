import enum
import json
# Using enum class create enumerations

class Type(enum.Enum):
    SECURITY = 1
    GOVERNANCE = 2
    CONFIGURATION = 3
    PERFORMANCE = 4
    BAD_PRACTICE = 5
    OPERATIONS = 6

class Severity(enum.Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class Problem():
    def __init__(self, problem_type, severity, msg):
        # dict.__init__(type=problem_type, severity=severity, message=msg)
        self.type = problem_type
        self.severity = severity
        self.message = msg

    def __str__(self):
        return "Type: {0} - Severity: {1} - Description: {2}".format(
            repr(self.type.name)[1:-1], repr(self.severity.name)[1:-1], self.message)

    def to_json(self):
        d = vars(self)
        d['type'] = repr(self.type.name)[1:-1]
        d['severity'] = repr(self.severity.name)[1:-1]
        return json.dumps(d, indent=4, sort_keys=False, separators=(',', ': '))

    def to_csv(self):
        return '{0},{1},"{2}"'.format(
            repr(self.type.name)[1:-1], repr(self.severity.name)[1:-1], self.message)
