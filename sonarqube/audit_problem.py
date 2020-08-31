import sys
import enum
import json
import sonarqube.utilities as util
# Using enum class create enumerations


class Problem():
    def __init__(self, problem_type, severity, msg, concerned_object=None):
        # dict.__init__(type=problem_type, severity=severity, message=msg)
        self.concerned_object = concerned_object
        self.type = problem_type
        self.severity = severity
        self.message = msg

    def __str__(self):
        return "Type: {0} - Severity: {1} - Description: {2}".format(
            str(self.type), str(self.severity), self.message)

    def to_json(self):
        d = vars(self)
        d['type'] = str(self.type)
        d['severity'] = str(self.severity)
        d['concerned_object'] = str(d['concerned_object'])
        return json.dumps(d, indent=4, sort_keys=False, separators=(',', ': '))

    def to_csv(self):
        return '{0},{1},"{2}"'.format(
            str(self.severity), str(self.type), self.message)


def dump_report(problems, file, file_format):
    if file is None:
        f = sys.stdout
        util.logger.info("Dumping report to stdout")
    else:
        f = open(file, "w")
        util.logger.info("Dumping report to file '%s'", file)
    if file_format == 'json':
        print("[", file=f)
    is_first = True
    for p in problems:
        if file_format is not None and file_format == 'json':
            pfx = "" if is_first else ",\n"
            p_dump = pfx + p.to_json()
            print(p_dump, file=f, end='')
            is_first = False
        else:
            p_dump = p.to_csv()
            print(p_dump, file=f)

    if file_format == 'json':
        print("\n]", file=f)
    if file is not None:
        f.close()
