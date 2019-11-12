import sys
import logging

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
