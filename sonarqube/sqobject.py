#!python3

import sonarqube.env

class SqObject:

    def __init__(self, **kwargs):
        self.env = kwargs['env']

    def set_env(self, env):
        self.env = env

    def get_env(self):
        return self.env

    def get(self, api, parms):
        if self.env is None:
            return sonarqube.env.get(api, parms)
        else:
            return self.env.get(api, parms)

    def post(self, api, parms):
        if self.env is None:
            return sonarqube.env.post(api, parms)
        else:
            return self.env.post(api, parms)

    def delete(self, api, parms):
        if self.env is None:
            return sonarqube.env.delete(api, parms)
        else:
            return self.env.delete(api, parms)

#--------------------- Static methods, not recommended -----------------

