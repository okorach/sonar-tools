import enum


class Type(enum.Enum):
    SECURITY = 1
    GOVERNANCE = 2
    CONFIGURATION = 3
    PERFORMANCE = 4
    BAD_PRACTICE = 5
    OPERATIONS = 6

    def __str__(self):
        return repr(self.name)[1:-1]


def to_type(val):
    for enum_val in Type:
        if repr(enum_val.name)[1:-1] == val:
            return enum_val
    return None
