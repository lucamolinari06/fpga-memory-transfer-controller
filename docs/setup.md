# Setup and reproducibility

## Host and selected installation

macOS 26.6 (25G72), Apple Silicon (Darwin arm64). Apple Command Line Tools finished installing during the 2026-10-21 review, confirmed by the user. The compiler is Apple Clang 21.0.0; Make is GNU Make 3.81; Python is 3.9.6; Git is 2.50.1 (Apple Git-155). A successful version query alone does not prove compilation: the initial source build exposed an SDK mismatch, described below.

Homebrew's official noninteractive installer stopped because it lacked administrator access to `/opt/homebrew`; Homebrew was not installed. The project instead provides an administrator-free local source installation. Only Apple's prerequisite is system-installed; M4, Autoconf, Bison, help2man and Verilator install beneath ignored `.tools/`. Python's `.venv/` is local. No third-party Python package is needed at this stage. Select plotting dependencies later, when used.

## Reproduce on macOS

Install Apple's free Command Line Tools using `xcode-select --install` in a local Terminal if needed, and finish its dialog. Then, from the project root:

```sh
bash scripts/setup_local_macos.sh
bash scripts/check_tools.sh
bash scripts/lint.sh
bash scripts/smoke.sh
```

`setup_local_macos.sh` downloads pinned official source archives: GNU M4 1.4.19, Autoconf 2.72, Bison 3.8.2, help2man 1.49.3, and Verilator v5.048. Verilator requires help2man to generate an installation man page; the initial build exposed and then resolved that dependency. It checks SHA-256 values in `scripts/toolchain.sha256`, builds with four jobs by default (`FPGA_BUILD_JOBS` overrides), and installs in `.tools/`. The hashes record the official HTTPS downloads acquired during setup; they are not a claim of separate signature verification. It then creates `.venv`, reports versions, lints and runs the SystemVerilog smoke test.

Downloads and build logs stay in `build/`. Source build directories under `/private/tmp/fpga-tool-build.*` are retained for diagnosis; their exact names are printed. To resume a partially completed source build, set `FPGA_TOOL_BUILD_DIR` to that printed directory when rerunning the setup script. They may be removed after successful installation. Installed files remain in the project. Build-from-source upstream warnings are distinct from project RTL lint results.

The project path contains spaces. `scripts/tool_env.sh` creates a user/project-specific, whitespace-free symlink in `/private/tmp` pointing to `.tools/`, and prepends its bin directory to PATH for the project scripts. It also sets `VERILATOR_ROOT` and `VERILATOR_BIN` to the alias paths because the Verilator Perl launcher resolves symlinks before constructing shell commands. These settings avoid unquoted tool prefixes in the launcher and generated Makefiles. It checks for path collisions and recreates a missing alias after temporary-directory cleanup. The smoke build also uses a whitespace-free temporary source directory. No shell profile or global tool selection is changed. To invoke the local tools directly in **Bash**, run `source scripts/tool_env.sh` first. Moving/renaming the project requires rebuilding `.tools` because configured prefixes contain its alias identity; do not copy this macOS tool installation to Linux.

The new Command Line Tools select `MacOSX26.5.sdk` through `SDKs/MacOSX.sdk`, but an `xcrun` query initially selected `MacOSX27.0.sdk`. Linking then failed with `unknown architecture arm64e.x1` in `libSystem.B.tbd`. Project scripts explicitly set their process-local SDKROOT to the installed tools' `SDKs/MacOSX.sdk` symlink. No global SDK files or symlinks are edited. The effective SDK path is recorded with the tool inventory.

`bash scripts/setup.sh` is the general setup entry point: it uses the pinned local build on macOS. Users who already maintain Homebrew may instead run `brew install verilator python`; the normal lint/smoke scripts also work with tools on PATH when `.tools/` is absent. Homebrew or later upstream versions must be validated rather than assumed equivalent to the recorded installation.

## Linux / Windows

Use native Linux or WSL Ubuntu on Windows. In Ubuntu:

```sh
sudo apt-get update
sudo apt-get install verilator build-essential python3 python3-venv git
python3 -m venv .venv
bash scripts/check_tools.sh
bash scripts/lint.sh
bash scripts/smoke.sh
```

Use Verilator 5.x with `--binary` and `--timing`. Linux/WSL commands are documented but have not been executed here. No native Windows build is claimed. RTL and testbench sources contain no macOS dependencies. Do not include `.tools`, `.venv` or generated files when transferring the source to another platform.

## Evidence

Setup, strict lint, and real SystemVerilog smoke simulation now pass. Verilator identifies itself as `5.048 2026-04-26 rev vUNKNOWN-built20261021`; the source tarball has no Git checkout metadata, so the recorded archive hash identifies the input. See PROJECT_STATUS.md and docs/validation/ for actual outcomes. `build/smoke.log` always describes the latest attempt, including a prerequisite failure. The tool-check script reports every version query and fails if any required tool is missing. Record configurations and new versions when rebuilding; a floating latest package version is not automatically a tested version.

Primary references: [Verilator installation](https://verilator.org/guide/latest/install.html), [binary simulation example](https://verilator.org/guide/latest/example_binary.html), [GNU source distribution](https://ftp.gnu.org/gnu/), [Homebrew installation](https://docs.brew.sh/Installation).

## Stage 2 regression

After setup, run `bash scripts/test.sh` for the baseline/model and hybrid suites, or `bash scripts/test.sh stage2` for the 36-case baseline/model suite. The general setup script runs lint and the small counter smoke test; it does not automatically run the full controller suites. Details and retained evidence are in PROJECT_STATUS.md and docs/validation/stage2/.

## Benchmark charts (single-buffer checkpoint)

The benchmark runner uses Python's standard library. Static PNG/SVG charts use the existing project virtual environment with Matplotlib 3.9.4. Installed with `.venv/bin/python -m pip install --no-cache-dir 'matplotlib==3.9.4'`; all resolved versions are retained in `benchmarks/requirements-plot-lock.txt` (macOS arm64, Python 3.9.6). Reinstall with `.venv/bin/python -m pip install -r benchmarks/requirements-plot-lock.txt`. No global Python packages or vendor tools were installed. Chart generation uses a writable temporary Matplotlib config directory.
