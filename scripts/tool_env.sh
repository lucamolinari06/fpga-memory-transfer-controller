#!/usr/bin/env bash
# Source this file; use a whitespace-free alias for locally installed Make paths.
fpga_project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [ "$(uname -s)" = Darwin ] && fpga_developer_dir=$(xcode-select -p 2>/dev/null); then
    # Prefer the SDK selected by the installed CLT symlink; xcrun may cache an older selection.
    if [ -d "$fpga_developer_dir/SDKs/MacOSX.sdk" ]; then
        export SDKROOT="$fpga_developer_dir/SDKs/MacOSX.sdk"
    fi
fi
if [ -d "$fpga_project_root/.tools" ]; then
    fpga_path_key=$(printf '%s' "$fpga_project_root" | cksum | awk '{print $1}')
    fpga_tools_alias="/private/tmp/fpga-tools-$(id -u)-$fpga_path_key"
    if [ ! -e "$fpga_tools_alias" ] && [ ! -L "$fpga_tools_alias" ]; then
        ln -s "$fpga_project_root/.tools" "$fpga_tools_alias" || return 1
    fi
    if [ "$(readlink "$fpga_tools_alias")" != "$fpga_project_root/.tools" ]; then
        echo "Tool alias already belongs to another path: $fpga_tools_alias" >&2
        return 1
    fi
    export PATH="$fpga_tools_alias/bin:$PATH"
    if [ -x "$fpga_tools_alias/bin/verilator_bin" ]; then
        # Verilator's Perl wrapper resolves symlinks; keep its shell command and Make root space-free.
        export VERILATOR_BIN="$fpga_tools_alias/bin/verilator_bin"
        export VERILATOR_ROOT="$fpga_tools_alias/share/verilator"
    fi
fi
