# This file is part of McIndi's Automated Solutions Tool (MAST).
#
# MAST is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3
# as published by the Free Software Foundation.
#
# MAST is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with MAST.  If not, see <https://www.gnu.org/licenses/>.
#
# Copyright 2015-2019, McIndi Solutions, All rights reserved.
import os
from setuptools import setup


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    with open(os.path.join(os.path.dirname(__file__), fname), "rb")as fin:
        return fin.read()

setup(
    name="mast",
    version="2.4.0",
    author="Clifford Bressette",
    author_email="cliffordbressette@mcindi.com",
    description=(
        "A utility to help manage multiple IBM DataPower appliances"
    ),
    license="GPLv3",
    keywords="DataPower backup checkpoint accounts network ssh system",
    url="http://github.com/mcindi/mast",
    install_requires=["mock"],
    packages=[
        'mast',
        'mast.cli',
        'mast.config',
        'mast.cron',
        'mast.daemon',
        'mast.datapower',
        'mast.datapower.accounts',
        'mast.datapower.backups',
        'mast.datapower.crypto',
        'mast.datapower.datapower',
        'mast.datapower.datapower.et',
        'mast.datapower.deployment',
        'mast.datapower.developer',
        'mast.datapower.network',
        'mast.datapower.ssh',
        'mast.datapower.status',
        'mast.datapower.system',
        'mast.datapower.web',
        'mast.hashes',
        'mast.logging',
        'mast.plugins',
        'mast.plugin_utils',
        'mast.pprint',
        'mast.test',
        'mast.testsuite',
        'mast.testsuite.unit',
        'mast.testsuite.integration',
        'mast.testsuite.regression',
        'mast.timestamp',
        'mast.xor',
    ],
    entry_points={
        'mast_web_plugin': [
            'accounts = mast.datapower.accounts:WebPlugin',
            'backups = mast.datapower.backups:WebPlugin',
            'crypto = mast.datapower.crypto:WebPlugin',
            'deployment = mast.datapower.deployment:WebPlugin',
            'developer = mast.datapower.developer:WebPlugin',
            'network = mast.datapower.network:WebPlugin',
            'ssh = mast.datapower.ssh:WebPlugin',
            'status = mast.datapower.status:WebPlugin',
            'system = mast.datapower.system:WebPlugin',
        ],
        'mastd_plugin': [
            'mastd_web_plugin = mast.datapower.web:Plugin',
            'mastd_cron_plugin = mast.cron:Plugin',
        ]

    },
    package_data={
        "mast.datapower.accounts": ["docroot/*"],
        "mast.datapower.backups": ["docroot/*"],
        "mast.datapower.crypto": ["docroot/*"],
        "mast.datapower.deployment": ["docroot/*"],
        "mast.datapower.developer": ["docroot/*"],
        "mast.datapower.network": ["docroot/*"],
        "mast.datapower.ssh": ["docroot/*"],
        "mast.datapower.status": ["docroot/*"],
        "mast.datapower.system": ["docroot/*"],
    },
    incude_package_data=True,
    long_description=read('README.md'),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Topic :: Utilities",
        "License :: OSI Approved :: GPLv3",
    ],
)
