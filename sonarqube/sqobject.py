#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube general object concept

'''
import sonarqube.env


class SqObject:

    def __init__(self, key, env):
        self.key = key
        self.env = env

    def set_env(self, env):
        self.env = env

    def get_env(self):
        return self.env

    def get(self, api, params=None):
        return sonarqube.env.get(api, params, self.env)

    def post(self, api, params=None):
        return sonarqube.env.post(api, params, self.env)

    def delete(self, api, params=None):
        resp = sonarqube.env.delete(api, params, self.env)
        return (resp.status_code // 100) == 2
