import enum


class Severity(enum.Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4

    def __str__(self):
        return repr(self.name)[1:-1]


def to_severity(val):
    for enum_val in Severity:
        if repr(enum_val.name)[1:-1] == val:
            return enum_val
    return None
