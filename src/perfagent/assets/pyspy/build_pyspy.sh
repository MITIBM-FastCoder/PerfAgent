#!/bin/bash
# Build py-spy from its crates.io source with perfagent's patch applied, and install it.
#
# Runs inside the task container at materialize time (see perfagent/pyspy.py): the executable has
# to link against the image's own libunwind, and every task image carries the Rust toolchain.
#
# usage: build_pyspy.sh <py-spy version> <workdir containing py-spy.patch> <install path>
set -euo pipefail
version="$1"
workdir="$2"
install_path="$3"

# shellcheck disable=SC1091
source "$HOME/.cargo/env"
cd "$workdir"
curl -sSfL -o py-spy.crate "https://static.crates.io/crates/py-spy/py-spy-${version}.crate"
rm -rf "py-spy-${version}"
tar xzf py-spy.crate
cd "py-spy-${version}"
patch -p1 < "${workdir}/py-spy.patch"
# --locked: build exactly the dependency set the py-spy release shipped with (Cargo.lock is in the crate).
cargo build --release --locked --features unwind
install -m 755 target/release/py-spy "$install_path"
"$install_path" --version
# Leave nothing behind for the agent to trip over.
cd /
rm -rf "$workdir"
