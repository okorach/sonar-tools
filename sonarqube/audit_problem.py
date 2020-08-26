import enum
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

class Problem:
    def __init__(self, problem_type, severity, msg):
        self.problem_type = problem_type
        self.severity = severity
        self.message = msg

    def __str__(self):
        return "Type: {0} - Severity: {1} - Description: {2}".format(
            repr(self.problem_type.name), repr(self.severity.name), self.message)
