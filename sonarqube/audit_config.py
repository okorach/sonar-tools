import jprops
import sonarqube.utilities as util

CONFIG_SETTINGS = None

def load(config_file=None):
    global CONFIG_SETTINGS
    if config_file is None:
        import pathlib
        config_file = pathlib.Path(__file__).parent / 'sonar-tools.properties'

    util.logger.info("Loading audit config %s", config_file)
    with open(config_file) as fp:
        CONFIG_SETTINGS = jprops.load_properties(fp)
    fp.close()
    for conf in CONFIG_SETTINGS:
        if (CONFIG_SETTINGS[conf].lower() == 'yes' or CONFIG_SETTINGS[conf].lower() == 'true' or
                CONFIG_SETTINGS[conf].lower() == 'on'):
            CONFIG_SETTINGS[conf] = True
        if (CONFIG_SETTINGS[conf].lower() == 'no' or CONFIG_SETTINGS[conf].lower() == 'false' or
                CONFIG_SETTINGS[conf].lower() == 'off'):
            CONFIG_SETTINGS[conf] = False

    return CONFIG_SETTINGS


def get_property(name, settings=None):
    if settings is None:
        global CONFIG_SETTINGS
        settings = CONFIG_SETTINGS
    return settings.get(name, '').lower()
