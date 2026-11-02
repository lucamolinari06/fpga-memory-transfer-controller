#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(uname -s)" = Darwin ] || { echo 'This source-build setup is for macOS.' >&2; exit 1; }
xcode-select -p >/dev/null
mkdir -p .tools build/toolchain-downloads
source scripts/tool_env.sh
fpga_downloads="$fpga_project_root/build/toolchain-downloads"
fetch() {
    if [ ! -f "$fpga_downloads/$1" ]; then
        curl --fail --location --connect-timeout 20 --max-time 180 "$2" -o "$fpga_downloads/$1.part"
        mv "$fpga_downloads/$1.part" "$fpga_downloads/$1"
    fi
}
fetch m4-1.4.19.tar.xz https://ftp.gnu.org/gnu/m4/m4-1.4.19.tar.xz
fetch autoconf-2.72.tar.xz https://ftp.gnu.org/gnu/autoconf/autoconf-2.72.tar.xz
fetch bison-3.8.2.tar.xz https://ftp.gnu.org/gnu/bison/bison-3.8.2.tar.xz
fetch help2man-1.49.3.tar.xz https://ftp.gnu.org/gnu/help2man/help2man-1.49.3.tar.xz
fetch verilator-5.048.tar.gz https://github.com/verilator/verilator/archive/refs/tags/v5.048.tar.gz
(cd "$fpga_downloads" && shasum -a 256 -c "$fpga_project_root/scripts/toolchain.sha256")
fpga_build_dir=${FPGA_TOOL_BUILD_DIR:-$(mktemp -d /private/tmp/fpga-tool-build.XXXXXX)}
trap 'echo "Source build directory retained at $fpga_build_dir"' EXIT
fpga_jobs=${FPGA_BUILD_JOBS:-4}
build_gnu() {
    local package=$1
    local executable=$2
    if [ -x "$fpga_tools_alias/bin/$executable" ]; then return; fi
    echo "Building $package (log: build/$package.log)"
    tar -xf "$fpga_downloads/$package.tar.xz" -C "$fpga_build_dir"
    (
        cd "$fpga_build_dir/$package"
        ./configure --prefix="$fpga_tools_alias" --disable-nls
        make -j "$fpga_jobs"
        make install
    ) > "$fpga_project_root/build/$package.log" 2>&1
}
build_gnu m4-1.4.19 m4
build_gnu autoconf-2.72 autoconf
build_gnu bison-3.8.2 bison
build_gnu help2man-1.49.3 help2man
if [ ! -x "$fpga_tools_alias/bin/verilator_bin" ]; then
    echo 'Building Verilator 5.048 (log: build/verilator-5.048.log)'
    if [ ! -d "$fpga_build_dir/verilator-5.048" ]; then
        tar -xf "$fpga_downloads/verilator-5.048.tar.gz" -C "$fpga_build_dir"
    fi
    (
        cd "$fpga_build_dir/verilator-5.048"
        unset VERILATOR_ROOT
        if [ ! -f Makefile ]; then
            autoconf
            ./configure --prefix="$fpga_tools_alias"
        fi
        make -j "$fpga_jobs"
        make install
    ) > "$fpga_project_root/build/verilator-5.048.log" 2>&1
fi
python3 -m venv .venv
bash scripts/check_tools.sh
bash scripts/lint.sh
bash scripts/smoke.sh
# Retain source build directory for diagnosis; safe to remove manually afterward.
