#!/bin/bash

rm -rf build dist
python3 setup.py bdist_wheel

# python3 -p pip uninstall sonar-tools
# python3 -m pip install dist/*-py3-*.whl
# python3 -m twine upload dist/*