import sys
import logging
import json

DEBUG_LEVEL = 0
DRY_RUN = False
logger = logging.getLogger('sonarqube-tools')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh = logging.FileHandler('sonarqube-tools.log')
ch = logging.StreamHandler()
logger.addHandler(fh)
logger.addHandler(ch)
fh.setFormatter(formatter)
ch.setFormatter(formatter)

def set_common_args(desc):
    """Parses options common to all sonarqube-tools scripts"""
    try:
        import argparse
    except ImportError:
        if sys.version_info < (2, 7, 0):
            print("""Error: You are running an old version of python. Two options to fix the problem
                Option 1: Upgrade to python version >= 2.7
                Option 2: Install argparse library for the current python version
                See: https://pypi.python.org/pypi/argparse""")
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-t', '--token', required=True,
                        help='Token to authenticate to SonarQube - Unauthenticated usage is not possible')
    parser.add_argument('-u', '--url', required=False, default='http://localhost:9000',
                        help='Root URL of the SonarQube server, default is http://localhost:9000')
    parser.add_argument('-k', '--componentKeys', '--projectKey', '--projectKeys', required=False,
                        help='Commas separated key of the components')
    parser.add_argument('-U', '--urlTarget', required=False, help='Root URL of the target SonarQube server')
    parser.add_argument('-T', '--tokenTarget', required=False,
                        help='Token to authenticate to target SonarQube - Unauthenticated usage is not possible')

    parser.add_argument('-g', '--debug', required=False, help='Debug level')
    return parser

def get_logging_level(intlevel):
    if intlevel >= 2:
        lvl = logging.DEBUG
    elif intlevel >= 1:
        lvl = logging.INFO
    elif intlevel >= 0:
        lvl = logging.ERROR
    else:
        lvl = logging.CRITICAL
    return lvl

def set_debug_level(level):
    global DEBUG_LEVEL
    DEBUG_LEVEL = 0 if level is None else int(level)
    global logger
    logger.setLevel(get_logging_level(DEBUG_LEVEL))
    logger.info("Set debug level to %d", DEBUG_LEVEL)

def set_dry_run(dry_run):
    global DRY_RUN
    DRY_RUN = dry_run
    logger.info("Set dry run to %s", str(dry_run))

def check_environment(kwargs):
    set_debug_level(kwargs.pop('debug', 0))
    set_dry_run(kwargs.pop('dry_run', 'false'))

def json_dump_debug(json_data):
    logger.debug(json.dump(json_data, sys.stdout, sort_keys=True, indent=3, separators=(',', ': ')))
