"""Application entry point."""

import argparse
import sys

from kbl.config import Config
from kbl.main_window import MainWindow
from kbl.workspaces import WorkspaceManager


def main(argv=None):
    parser = argparse.ArgumentParser(description="Knowledge base librarian")
    parser.add_argument(
        "--workspace",
        help="open (and add) a workspace folder on launch",
    )
    args = parser.parse_args(argv)

    config = Config()
    if args.workspace:
        WorkspaceManager(config).set_active(args.workspace)

    window = MainWindow(config)
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
