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
        # Register + select as this instance's active workspace. This is
        # per-instance session state and must NOT persist a single shared
        # "active_workspace", so a second window can't adopt this project.
        wm = WorkspaceManager(config)
        wm.register(args.workspace)
        wm.set_active(args.workspace, persist_default=False)
    else:
        # No explicit workspace: seed from the persisted default (single-user
        # convenience). Never a peer instance's --workspace project.
        config.active_workspace = config.data.get("default_workspace")

    window = MainWindow(config)
    window.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
