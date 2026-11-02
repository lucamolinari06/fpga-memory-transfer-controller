#!/usr/bin/env bash
set -u
source "$(dirname "$0")/tool_env.sh" || exit 1
failed=0
check() {
    printf '\nCommand:'
    printf ' %s' "$@"
    printf '\n'
    "$@" || failed=1
}
printf 'Host: '; uname -sm
if [ "$(uname -s)" = Darwin ]; then check sw_vers; check xcode-select -p; fi
printf 'Effective SDKROOT: %s\n' "${SDKROOT:-not set}"
if [ -n "${SDKROOT:-}" ] && [ -L "$SDKROOT" ]; then check readlink "$SDKROOT"; fi
check verilator --version
check c++ --version
check make --version
check python3 --version
check git --version
exit "$failed"
