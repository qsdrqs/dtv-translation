FROM nixos/nix:latest

# Copy flake files
COPY flake.nix flake.lock /opt/dtv-flake/

# Enable flakes and configure Nix
RUN mkdir -p /etc/nix && \
    echo "experimental-features = nix-command flakes" >> /etc/nix/nix.conf && \
    echo "filter-syscalls = false" >> /etc/nix/nix.conf

# Install packages from pinned nixpkgs via flake.
# Python is NOT installed from nixpkgs: nixpkgs-unstable's python3 resolves to
# 3.13.8 at build time, which crashes torch @overload AST parser
# (pytorch/pytorch#178255). Instead uv manages its own CPython matching
# .python-version, pinned via requires-python in pyproject.toml.
RUN cd /opt/dtv-flake && \
    nix profile install --profile /nix/var/nix/profiles/dtv \
        --inputs-from . \
        nixpkgs#nodejs \
        nixpkgs#rustup \
        nixpkgs#uv \
        nixpkgs#tree-sitter \
        nixpkgs#gcc \
        nixpkgs#bash \
        nixpkgs#coreutils \
        nixpkgs#findutils \
        nixpkgs#gnugrep \
        nixpkgs#gnused \
        nixpkgs#gawk \
        nixpkgs#less \
        nixpkgs#which \
        nixpkgs#diffutils \
        nixpkgs#gnutar \
        nixpkgs#gzip \
        nixpkgs#zlib

# Install libstdc++ runtime (needed by numpy/torch wheels) and pin as GC root
RUN cd /opt/dtv-flake && \
    GCC_LIB=$(nix build --no-link --print-out-paths --inputs-from . 'nixpkgs#gcc.cc.lib') && \
    nix-store --add-root /nix/var/nix/gcroots/gcc-lib --indirect -r "$GCC_LIB" && \
    echo "$GCC_LIB/lib" > /opt/gcc-lib-path

# Pin zlib runtime path (needed by newer numpy wheels) as GC root
RUN cd /opt/dtv-flake && \
    ZLIB_OUT=$(nix build --no-link --print-out-paths --inputs-from . 'nixpkgs#zlib') && \
    nix-store --add-root /nix/var/nix/gcroots/zlib --indirect -r "$ZLIB_OUT" && \
    echo "$ZLIB_OUT/lib" > /opt/zlib-lib-path

# uv-managed CPython is a standalone FHS binary that hardcodes
# /lib/ld-linux-<arch>.so.1 as its interpreter. nixos/nix base has no /lib,
# so we pin glibc, expose its loader at the FHS path, and put its libs on
# LD_LIBRARY_PATH.
RUN cd /opt/dtv-flake && \
    GLIBC_OUT=$(nix build --no-link --print-out-paths --inputs-from . 'nixpkgs#glibc^out') && \
    nix-store --add-root /nix/var/nix/gcroots/glibc --indirect -r "$GLIBC_OUT" && \
    echo "$GLIBC_OUT/lib" > /opt/glibc-lib-path && \
    LOADER=$(ls "$GLIBC_OUT"/lib/ld-linux-*.so.* 2>/dev/null | head -1) && \
    if [ -z "$LOADER" ]; then echo "ERROR: no ld-linux loader in $GLIBC_OUT/lib" >&2; ls "$GLIBC_OUT"/lib | head -40 >&2; exit 1; fi && \
    LOADER_NAME=$(basename "$LOADER") && \
    mkdir -p /lib /lib64 && \
    ln -sf "$LOADER" "/lib/$LOADER_NAME" && \
    ln -sf "$LOADER" "/lib64/$LOADER_NAME"

# Install Rust toolchain
ENV RUSTUP_HOME=/opt/rustup
ENV CARGO_HOME=/opt/cargo
ENV PATH="/nix/var/nix/profiles/dtv/bin:/opt/cargo/bin:${PATH}"
RUN rustup install nightly-2025-11-13 && \
    rustup default nightly-2025-11-13 && \
    rustup component add rustfmt clippy rust-analyzer

# Clean up Nix garbage (gcc lib kept via GC root)
RUN nix-collect-garbage -d

# Verify
RUN export LD_LIBRARY_PATH="$(cat /opt/glibc-lib-path):$(cat /opt/gcc-lib-path):$(cat /opt/zlib-lib-path):${LD_LIBRARY_PATH:-}" && \
    node --version && npm --version && rustc --version && uv --version && gcc --version && echo "ALL_OK"

ENV PATH="/nix/var/nix/profiles/dtv/bin:/opt/cargo/bin:${PATH}"
ENV RUSTUP_HOME=/opt/rustup
ENV CARGO_HOME=/opt/cargo
ENV LD_LIBRARY_PATH_FILE=/opt/gcc-lib-path

ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
COPY . /opt/dtv-project
# Host-built node_modules is shipped as-is (pure JS, no native bindings).
# Running `npm install` here breaks under qemu-arm64: "Exit handler never called!".
RUN export LD_LIBRARY_PATH="$(cat /opt/glibc-lib-path):$(cat /opt/gcc-lib-path):$(cat /opt/zlib-lib-path):${LD_LIBRARY_PATH:-}" && \
    cd /opt/dtv-project && \
    uv sync && \
    node -e "require.resolve('typescript'); require.resolve('typescript-eslint'); require.resolve('eslint');" && \
    echo 'uv sync OK and node_modules verified'

ENV NODE_PATH=/opt/dtv-project/node_modules
ENV PATH="/opt/dtv-project/node_modules/.bin:/nix/var/nix/profiles/dtv/bin:/opt/cargo/bin:${PATH}"

# Set LD_LIBRARY_PATH permanently
# (shell reads /opt/*-lib-path at runtime; ENV can't expand file contents,
#  so we bake the resolved paths at build time)
RUN mkdir -p /etc/profile.d && echo "export LD_LIBRARY_PATH=\"$(cat /opt/glibc-lib-path):$(cat /opt/gcc-lib-path):$(cat /opt/zlib-lib-path):\${LD_LIBRARY_PATH:-}\"" >> /etc/profile.d/gcc-lib.sh
