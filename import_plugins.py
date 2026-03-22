import os
import shutil
import sys
import argparse
from datawave.utils.settings import get_appdata_dir

TEMPLATES_DIR = "templates"
PLUGINS_DIR = os.path.join(get_appdata_dir(), "plugins")

def list_templates():
    if not os.path.exists(TEMPLATES_DIR):
        print("Templates directory not found.")
        return []

    templates = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".py")]
    return templates

def import_template(template_name):
    src = os.path.join(TEMPLATES_DIR, template_name)
    if not os.path.exists(src):
        print(f"Template {template_name} not found.")
        return False

    if not os.path.exists(PLUGINS_DIR):
        os.makedirs(PLUGINS_DIR)

    dst = os.path.join(PLUGINS_DIR, template_name)
    shutil.copy2(src, dst)
    print(f"Imported {template_name} to {PLUGINS_DIR}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Import remote command templates into DataWave.")
    parser.add_argument("--list", action="store_true", help="List available templates")
    parser.add_argument("--all", action="store_true", help="Import all templates")
    parser.add_argument("templates", nargs="*", help="Specific templates to import (e.g., shutdown.py)")

    args = parser.parse_args()

    available = list_templates()

    if args.list:
        print("Available templates:")
        for t in available:
            print(f"  - {t}")
        return

    if args.all:
        for t in available:
            import_template(t)
    elif args.templates:
        for t in args.templates:
            if not t.endswith(".py"):
                t += ".py"
            import_template(t)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
