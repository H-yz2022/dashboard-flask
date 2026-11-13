"""Save the dashboard as plain HTML files so it can be hosted without a Python server.

app.py builds both pages once at startup and every request returns the same HTML,
so they can be written to disk and served by any static host (GitHub Pages here).

    python build_static.py [output_dir]    # default: site/

Produces index.html (the dashboard) and map.html (the Folium map it loads in an iframe).
"""
import os
import sys

from app import MAP_HTML, app, render_dashboard


def main(out_dir="site"):
    os.makedirs(out_dir, exist_ok=True)
    with app.app_context():
        pages = {
            "index.html": render_dashboard("map.html"),
            "map.html": MAP_HTML,
        }
    for name, html in pages.items():
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"wrote {path} ({os.path.getsize(path) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main(*sys.argv[1:])
