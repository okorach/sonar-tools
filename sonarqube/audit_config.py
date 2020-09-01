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
    for key, value in CONFIG_SETTINGS.items():
        value = value.lower()
        if value == 'yes' or value == 'true' or value == 'on':
            CONFIG_SETTINGS[key] = True
            continue
        if value == 'no' or value == 'false' or value == 'off':
            CONFIG_SETTINGS[key] = False
            continue
        try:
            intval = int(value)
            CONFIG_SETTINGS[key] = intval
        except ValueError:
            pass

    return CONFIG_SETTINGS


def get_property(name, settings=None):
    if settings is None:
        global CONFIG_SETTINGS
        settings = CONFIG_SETTINGS
    return settings.get(name, '')
