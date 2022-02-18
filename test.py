import os
import re

import requests

from keys import *

api_key = os.getenv('RDB_API_TOKEN')
assert api_key is not None
API_TOKEN = f'Token {api_key}'

RDB_HOST = os.getenv('RDB_HOST')
assert RDB_HOST is not None
DEPLOYMENT_NUMBER = 'CP01CNSM-T0012'


def request_url(url):
    print(f'requesting {url}')
    return requests.get(url, headers={'Authorization': API_TOKEN}).json()


def request_endpoint(endpoint):
    url = f'https://{RDB_HOST}/api/v1/{endpoint}'
    return request_url(url)


class Build(object):
    def __init__(self, deployment_number):
        self.assembly_parts = {}
        self.ancestors = {}
        record = request_endpoint(f'oms-builds/?deployment_number={deployment_number}')[0]
        assembly_part_records = record[ASSEMBLY_PARTS]
        for assembly_part_record in assembly_part_records:
            assembly_part = AssemblyPart(assembly_part_record)
            self.assembly_parts[assembly_part.url] = assembly_part
            assembly_part.walk_parent(self.ancestors)


def component_basename(component_name):
    # remove trailing numbers from component names as appropriate
    if component_name is None:
        return ''
    return re.sub(r'[0-9]+$', '', component_name)
    # FIXME add support for 3dmgx3, fb250


class AssemblyPart(object):
    def __init__(self, record):
        self.url = record[ASSEMBLY_PART_URL]
        self.name = record[PART_NAME]
        # populate configuration values
        config_values_list = record[CONFIGURATION_VALUES]
        config_values = {}
        for cv in config_values_list:
            config_values[cv['name']] = cv['value']
        self.config = config_values
        self.component_name = self.config.get(COMPONENT_NAME)
        self.parent_cpu = self.config.get(PARENT_CPU)
        self.instance_on_subassembly = self.config.get(INSTANCE_ON_SUBASSEMBLY)
        self.data_source_log_identifier = self.config.get(DATA_SOURCE_LOG_IDENTIFIER)
        self.component_basename = component_basename(self.component_name)
        # parent (does not fetch)
        self.parent = None
        self.parent_url = record[PARENT_ASSEMBLY_PART_URL]

    @property
    def is_cpu(self):
        return self.component_basename in CPUS

    def walk_parent(self, cache):
        if self.parent_url not in cache:
            part = Part(self.parent_url)
            cache[self.parent_url] = part
        else:
            part = cache[self.parent_url]
        self.parent = part
        part.walk_ancestors(cache)

    @property
    def subassembly(self):
        parent = self.parent
        while parent is not None:
            if parent.parent is None:
                return parent
            parent = parent.parent
        # unreachable

    def __str__(self):
        return f'{self.name} ({self.component_name})'


class Part(object):
    def __init__(self, url):
        expanded_url = f'{url}?expand=config_default_events.config_defaults.config_name'
        record = request_url(url)
        self.url = url
        self.parent_url = record.get(PARENT)
        self.parent = None
        self.name = record[PART_NAME]
        self.config = {}

    def walk_ancestors(self, cache):
        if self.parent_url is not None:
            if self.parent_url not in cache:
                self.parent = Part(self.parent_url)
                cache[self.parent_url] = self.parent
            else:
                self.parent = cache[self.parent_url]
            self.parent.walk_ancestors(cache)

    @property
    def subassembly_component_name(self):
        name = self.name.lower()
        for sa_name in SUBASSEMBLIES:
            if sa_name in name:
                return sa_name

    def __str__(self):
        return self.name


def main():
    build = Build(DEPLOYMENT_NUMBER)

    for url, assembly_part in build.assembly_parts.items():
        print(assembly_part, end='')
        parent = assembly_part.parent
        while parent is not None:
            print(f' > {parent}', end='')
            parent = parent.parent
        print()

    for url, assembly_part in build.assembly_parts.items():
        sa_name = assembly_part.subassembly.subassembly_component_name
        ios = assembly_part.instance_on_subassembly
        cname = assembly_part.component_basename
        outpath = f'{sa_name}/{cname}'
        if ios is not None:
            outpath += f'-{ios}'
        print(f'{assembly_part}: {outpath}')


if __name__ == '__main__':
    main()