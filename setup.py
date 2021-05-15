#
# sonar-tools
# Copyright (C) 2019-2020 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
import setuptools
import sonarqube.version as version


with open("README.md", "r") as fh:
    long_description = fh.read()
setuptools.setup(
    name='sonar-tools',
    version=version.PACKAGE_VERSION,
    scripts=['sonar-tools'],
    author="Olivier Korach",
    author_email="olivier.korach@gmail.com",
    description="A collection of utility scripts for SonarQube",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/okorach/sonarqube-tools",
    project_urls={
        "Bug Tracker": "https://github.com/okorach/sonarqube-tools/issues",
        "Documentation": "https://github.com/okorach/sonarqube-tools/README.md",
        "Source Code": "https://github.com/okorach/sonarqube-tools",
    },
    packages=setuptools.find_packages(),
    package_data={
        "sonarqube": ["LICENSE", "rules.json", "sonar-audit.properties"]
    },
    install_requires=[
        'pytz',
        'argparse',
        'datetime',
        'requests',
        'jprops'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': [
            'sonar-audit = sonarqube.audit:main',
            'sonar-projects-export = sonarqube.projects_export:main',
            'sonar-projects-import = sonarqube.projects_import:main',
            'sonar-measures-export = sonarqube.measures_export:main',
            'sonar-housekeeper = sonarqube.housekeeper:main',
            'sonar-issues-sync = sonarqube.issues_sync:main',
            'sonar-issues-export = sonarqube.issues_export:main'
        ]
    },
    python_requires='>=3.6',
)
