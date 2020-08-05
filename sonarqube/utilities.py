#!/usr/local/bin/python3
'''

    Utilities for SonarQube API

'''
import sys
import logging
import json

DEBUG_LEVEL = 0
DRY_RUN = 'dryrun'
CONFIRM = 'confirm'
BATCH = 'batch'
RUN_MODE = DRY_RUN
ISO_DATE_FORMAT = "%04d-%02d-%02d"

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
                        help='Token to authenticate to the source SonarQube - Unauthenticated usage is not possible')
    parser.add_argument('-u', '--url', required=False, default='http://localhost:9000',
                        help='Root URL of the source SonarQube server, default is http://localhost:9000')

    parser.add_argument('--mode', required=True, help='Mode of execution (dryrun, batch, confirm)')
    parser.add_argument('-g', '--debug', required=False, help='Debug level')
    return parser

def set_component_args(parser):
    parser.add_argument('-k', '--componentKeys', '--projectKey', '--projectKeys', required=False,
                        help='Commas separated key of the components')
    return parser

def set_target_args(parser):
    parser.add_argument('-U', '--urlTarget', required=False, help='Root URL of the target SonarQube server')
    parser.add_argument('-T', '--tokenTarget', required=False,
                        help='Token to authenticate to target SonarQube - Unauthenticated usage is not possible')
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

def set_run_mode(run_mode):
    global RUN_MODE
    RUN_MODE = run_mode
    logger.info("Set run mode to %s", run_mode)

def get_run_mode():
    global RUN_MODE
    return RUN_MODE

def check_environment(kwargs):
    set_debug_level(kwargs.pop('debug', 0))
    set_run_mode(kwargs.pop('mode', 'dryrun'))

def json_dump_debug(json_data, pre_string = ''):
    logger.debug("%s%s", pre_string, json.dumps(json_data, \
                 sort_keys=True, indent=3, separators=(',', ': ')))

def format_date_ymd(year, month, day):
    return ISO_DATE_FORMAT % (year, month, day)

def format_date(somedate):
    return ISO_DATE_FORMAT % (somedate.year, somedate.month, somedate.day)