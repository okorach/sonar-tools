import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()
setuptools.setup(
    name='sonar-tools',
    version='0.1.3',
    scripts=['sonar-tools'] ,
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
    install_requires=[
        'pytz',
        'argparse',
        'datetime',
        'requests'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        'console_scripts': [
            'sonar-audit = sonarqube.audit:main'
        ]
    },
    python_requires='>=3.6',
)
