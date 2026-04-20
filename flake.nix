{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { nixpkgs, ... }:
    let
      mkDevShell =
        system:
        let
          pkgs = import nixpkgs {
            config.allowUnfree = true;
            inherit system;
          };
        in
        pkgs.mkShell {
          buildInputs = with pkgs; [
            python3
            rustup
            uv
            tree-sitter
            nodejs
            nodePackages.typescript
            zlib
          ];
          shellHook = ''
          '';
        };
    in
    {
      devShells.x86_64-linux.default = mkDevShell "x86_64-linux";
      devShells.aarch64-linux.default = mkDevShell "aarch64-linux";
    };
}
