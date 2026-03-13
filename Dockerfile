FROM nixos/nix:latest

# Copy flake files
COPY flake.nix flake.lock /opt/dtv-flake/

# Enable flakes and configure Nix
RUN mkdir -p /etc/nix && \
    echo "experimental-features = nix-command flakes" >> /etc/nix/nix.conf && \
    echo "filter-syscalls = false" >> /etc/nix/nix.conf

# Install packages from pinned nixpkgs via flake
RUN cd /opt/dtv-flake && \
    nix profile install --profile /nix/var/nix/profiles/dtv \
        --inputs-from . \
        nixpkgs#python3 \
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
        nixpkgs#gzip

# Install libstdc++ runtime (needed by numpy/torch wheels) and pin as GC root
RUN cd /opt/dtv-flake && \
    GCC_LIB=$(nix build --no-link --print-out-paths --inputs-from . 'nixpkgs#gcc.cc.lib') && \
    nix-store --add-root /nix/var/nix/gcroots/gcc-lib --indirect -r "$GCC_LIB" && \
    echo "$GCC_LIB/lib" > /opt/gcc-lib-path

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
RUN export LD_LIBRARY_PATH="$(cat /opt/gcc-lib-path):${LD_LIBRARY_PATH:-}" && \
    python3 --version && rustc --version && uv --version && gcc --version && echo "ALL_OK"

ENV PATH="/nix/var/nix/profiles/dtv/bin:/opt/cargo/bin:${PATH}"
ENV RUSTUP_HOME=/opt/rustup
ENV CARGO_HOME=/opt/cargo
ENV LD_LIBRARY_PATH_FILE=/opt/gcc-lib-path

COPY . /opt/dtv-project
RUN export LD_LIBRARY_PATH="$(cat /opt/gcc-lib-path):${LD_LIBRARY_PATH:-}" && \
    cd /opt/dtv-project && \
    uv sync && \
    echo 'uv sync OK'

# Set LD_LIBRARY_PATH permanently
# (shell reads /opt/gcc-lib-path at runtime; ENV can't expand file contents,
#  so we bake the resolved path at build time)
RUN mkdir -p /etc/profile.d && echo "export LD_LIBRARY_PATH=\"$(cat /opt/gcc-lib-path):\${LD_LIBRARY_PATH:-}\"" >> /etc/profile.d/gcc-lib.sh
