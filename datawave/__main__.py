"""
Main entry point for the DataWave application.
"""

import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="DataWave: Data Over Sound application.")
    parser.add_argument("--gui", action="store_true", help="Start in GUI mode (default if no arguments)")
    parser.add_argument("--cli", action="store_true", help="Start in CLI mode")

    args, unknown = parser.parse_known_args()

    if args.cli:
        from datawave.ui.cli import main as cli_main
        cli_main()
    else:
        # Default to GUI
        try:
            from datawave.ui.gui import main as gui_main
            gui_main()
        except ImportError:
            print("wxPython not found, falling back to CLI mode.")
            from datawave.ui.cli import main as cli_main
            cli_main()

if __name__ == "__main__":
    main()
