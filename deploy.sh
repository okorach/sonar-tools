#!/bin/bash

rm -rf build dist
python3 setup.py bdist_wheel

# Deploy locally for tests
echo "y" | python3 -m pip uninstall sonar-tools
python3 -m pip install dist/*-py3-*.whl

# Deploy on pypi.org once released
if [ "$1" = "pypi" ]; then
    python3 -m twine upload dist/*
fi