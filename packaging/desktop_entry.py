"""PyInstaller entry; the executable also provides explicit data migration."""

import sys

if len(sys.argv) > 1 and sys.argv[1] == "migrate":
    from aifs.migrate_desktop import main

    del sys.argv[1]
else:
    from aifs.desktop_launcher import main

main()
