#!/bin/bash

rm -rf build dist
python3 setup.py bdist_wheel

python3 -m pip uninstall sonar-tools
python3 -m pip install dist/*-py3-*.whl

if [ "$1" = "publish" ]; then
    python3 -m twine upload dist/*
fi