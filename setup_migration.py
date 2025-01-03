#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

"""

   Package setup

"""
import setuptools
from sonar import version

with open("migration/README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()
setuptools.setup(
    name="sonar-migration",
    version=version.MIGRATION_TOOL_VERSION,
    scripts=["migration/sonar_migration"],
    author="Olivier Korach",
    author_email="olivier.korach@gmail.com",
    description="A SonarQube collection tool to use in the context of SonarQube to SonarCloud migration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/okorach/sonar-tools",
    project_urls={
        "Bug Tracker": "https://github.com/okorach/sonar-tools/issues",
        "Documentation": "https://github.com/okorach/sonar-tools/migration/README.md",
        "Source Code": "https://github.com/okorach/sonar-tools",
    },
    packages=setuptools.find_packages(),
    package_data={"sonar": ["LICENSE", "audit/rules.json", "audit/sonar-audit.properties"]},
    install_requires=[
        "argparse",
        "datetime",
        "python-dateutil",
        "requests",
        "jprops",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "sonar-migration = migration.migration:main",
        ]
    },
    python_requires=">=3.8",
)
