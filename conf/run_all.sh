#!/bin/bash
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

# ME="$( basename "${BASH_SOURCE[0]}" )"
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd .. && pwd )"
CONF_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

. "${CONF_DIR}/env.sh"

dolint="true"
dotest="false"
if [[ "${CI}" = "" ]]; then
  localbuild="true"
else
  localbuild="false"
fi

scanOpts=()

while [[ $# -ne 0 ]]
do
  case "${1}" in
    -nolint)
      dolint="false"
      ;;
    -test)
      dotest="true"
      ;;
    -9)
      external_format="v1"
      auth="-Dsonar.login=${SONAR_TOKEN}"
      ;;
    -local)
      localbuild="true"
      ;;
    *)
      scanOpts=("${scanOpts[@]}" "${1}")
      ;;
  esac
  shift
done

if [[ "${dolint}" != "false" ]]; then
  "${CONF_DIR}"/run_linters.sh "${external_format}" "${localbuild}"
fi

if [[ "${dotest}" = "true" ]]; then
  "${CONF_DIR}"/run_tests.sh
fi

"${CONF_DIR}"/run_scanner.sh "${scanOpts[@]}"
