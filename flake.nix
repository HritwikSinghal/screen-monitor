{
  description = "Screen monitor — GNOME Wayland screen capture with PipeWire";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachSystem [ "x86_64-linux" "aarch64-linux" ] (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;

        pythonEnv = python.withPackages (ps: with ps; [
          dbus-python
          pygobject3
          numpy
          opencv4
          pillow
          pytest
        ]);

        gstPackages = with pkgs.gst_all_1; [
          gstreamer
          gst-plugins-base
          gst-plugins-good
        ];

        giTypelibPath = pkgs.lib.makeSearchPathOutput "out" "lib/girepository-1.0"
          (gstPackages ++ [ pkgs.gobject-introspection ]);

        # PipeWire bundles its own GStreamer plugin (pipewiresrc) separately from gst_all_1
        gstPluginPath = "${pkgs.lib.makeSearchPathOutput "out" "lib/gstreamer-1.0" gstPackages}:${pkgs.pipewire}/lib/gstreamer-1.0";

        startApp = pkgs.writeShellApplication {
          name = "screen-monitor-start";
          runtimeInputs = [ pythonEnv pkgs.pipewire ] ++ gstPackages;
          text = ''
            export GI_TYPELIB_PATH="${giTypelibPath}"
            export GST_PLUGIN_PATH="${gstPluginPath}"
            python main.py
          '';
        };

        testApp = pkgs.writeShellApplication {
          name = "screen-monitor-test";
          runtimeInputs = [ pythonEnv ];
          text = "python -m pytest tests/ -v";
        };

      in {
        apps = {
          start = {
            type = "app";
            program = "${startApp}/bin/screen-monitor-start";
          };
          test = {
            type = "app";
            program = "${testApp}/bin/screen-monitor-test";
          };
        };

        devShells.default = pkgs.mkShell {
          packages = [ pythonEnv pkgs.uv pkgs.pipewire ] ++ gstPackages;
          shellHook = ''
            export GI_TYPELIB_PATH="${giTypelibPath}"
            export GST_PLUGIN_PATH="${gstPluginPath}"
            export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
          '';
        };
      }
    );
}
