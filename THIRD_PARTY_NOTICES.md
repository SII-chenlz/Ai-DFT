# Third-party notices

AIFS source is distributed under the MIT License in `LICENSE`. This does not replace the licenses of bundled dependencies.

The desktop plugin bundles schema/error helper code from DeepSeek Harness packages (`dsh-tools`, `dsh-session`, `dsh-llm`, and `schemastery`). Their original license texts are shipped in `licenses/`; versions are recorded in `build-info.json`. DSH itself is an external host, and REST is not bundled.

The frozen Python backend includes CPython and Python dependencies. Build-time collection preserves installed distribution license/notice files in the runtime's `licenses/`, together with the Python runtime license and a package/version index. PyInstaller's license and bundling exception are included in those notices. Static notices for OpenSSL and SQLite are included alongside the runtime. Additional native library attribution is included when supplied by the Python distribution.

Build dependency versions are recorded in `build-requirements.lock` and `build-info.json`. Platform runtime files and their hashes are recorded in `runtime.json`.
