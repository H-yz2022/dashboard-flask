from flask import Flask, render_template
import folium
import bisect
import json
import os

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SQFT_PER_ACRE = 43560
TAZ_COLORS = ['#ffffe5', '#f7fcb9', '#d9f0a3', '#addd8e', '#78c679',
              '#41ab5d', '#238443', '#006837', '#004529']  # YlGn, 9 classes


def load_geojson(filename, keep=None, precision=6):
    """Read a GeoJSON file, rounding coordinates (~0.1 m) and optionally keeping only
    the properties in `keep`, so the map page stays smaller."""
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        data = json.load(f)

    def round_coords(coords):
        if isinstance(coords[0], (int, float)):
            return [round(c, precision) for c in coords]
        return [round_coords(c) for c in coords]

    for feature in data["features"]:
        if keep is not None:
            feature["properties"] = {k: feature["properties"].get(k) for k in keep}
        if feature.get("geometry"):
            feature["geometry"]["coordinates"] = round_coords(feature["geometry"]["coordinates"])
    data.pop("crs", None)
    return data


def build_node_data(nodes):
    """AADT time series for each count station, as plain Python types (JSON-serializable)."""
    marker_data = []
    for feature in nodes["features"]:
        props = feature["properties"]
        years = sorted(int(k[4:]) for k in props if k.startswith("AADT") and k[4:].isdigit())
        # 0 / missing means no count that year -> null, so the chart shows a gap instead of a drop to 0
        values = [props[f"AADT{y}"] or None for y in years]
        lng, lat = feature["geometry"]["coordinates"]
        marker_data.append({
            "lat": lat, "lng": lng,
            "N": props["N"],
            "facility": props.get("FACILITY"),
            "years": years, "values": values,
        })
    return marker_data


def build_map(taz, nodes, centroid, highway_update):
    # TAZ_Area is very skewed (1.4 .. 29,000 acres), so a linear scale paints almost every
    # zone the same color. Use quantile classes instead: each color covers ~1/9 of the zones.
    acres = sorted(f["properties"]["TAZ_Area"] / SQFT_PER_ACRE
                   for f in taz["features"] if f["properties"].get("TAZ_Area"))
    breaks = [acres[round(i * (len(acres) - 1) / len(TAZ_COLORS))] for i in range(len(TAZ_COLORS) + 1)]

    def colormapper_with_zero(area_sqft):
        if not area_sqft:
            return "#faded1"
        return TAZ_COLORS[min(bisect.bisect_right(breaks, area_sqft / SQFT_PER_ACRE) - 1, len(TAZ_COLORS) - 1)]

    m = folium.Map(location=[38.88, -77.24], zoom_start=9, tiles=None)
    # CARTO basemaps now require an API key, so use Esri's free light-gray canvas
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
        name="Esri Light Gray",
        max_zoom=16,
        control=False,
    ).add_to(m)

    # TAZ layer
    taz_layer = folium.GeoJson(
        taz,
        name="TAZ",
        style_function=lambda f: {
            'fillColor': colormapper_with_zero(f['properties']['TAZ_Area']),
            'color': 'black',
            'weight': 0.5,
            'fillOpacity': 0.4,
        },
        tooltip=folium.GeoJsonTooltip(fields=['TAZ', 'NAME', 'Community', 'TAZ_Area'])
    ).add_to(m)

    # Centroid connectors (hidden by default: dense, toggle on from the layer control)
    folium.GeoJson(
        centroid,
        name="Centroid connectors",
        show=False,
        style_function=lambda f: {'color': 'yellow', 'weight': 0.7, 'fillOpacity': 0.5},
        highlight_function=lambda f: {'color': 'yellow', 'weight': 1},
        tooltip=folium.GeoJsonTooltip(fields=LINK_FIELDS)
    ).add_to(m)

    # Highway updates
    folium.GeoJson(
        highway_update,
        name="Highway updates",
        style_function=lambda f: {'color': 'blue', 'weight': 0.7, 'fillOpacity': 0.5},
        highlight_function=lambda f: {'color': 'red', 'weight': 1},
        tooltip=folium.GeoJsonTooltip(fields=LINK_FIELDS)
    ).add_to(m)

    # Legend for the TAZ colors
    fmt = lambda a: f"{a:,.0f}" if a >= 10 else f"{a:.1f}"
    rows = "".join(
        f'<div><i style="background:{c}"></i>{fmt(breaks[i])} &ndash; {fmt(breaks[i + 1])}</div>'
        for i, c in enumerate(TAZ_COLORS)
    )
    m.get_root().html.add_child(folium.Element(f"""
        <div style="position:fixed; bottom:24px; right:10px; z-index:1000; background:white;
                    padding:8px 10px; border-radius:5px; box-shadow:0 1px 5px rgba(0,0,0,.4);
                    font:12px/18px Arial, sans-serif;">
            <b>TAZ area (acres)</b>
            <style>.taz-legend i {{display:inline-block; width:14px; height:14px; margin-right:6px;
                    vertical-align:-3px; opacity:.8; border:1px solid #999;}}</style>
            <div class="taz-legend">{rows}</div>
        </div>
    """))

    # Count stations - click one to show its AADT chart
    nodes_layer = folium.GeoJson(
        nodes,
        name="Count stations (click to show chart)",
        marker=folium.CircleMarker(radius=6, color='black', weight=1,
                                   fill=True, fill_color='#e6550d', fill_opacity=0.8),
        tooltip=folium.GeoJsonTooltip(fields=['N', 'FACILITY'], aliases=['Node', 'Facility'])
    ).add_to(m)

    # Tell the parent dashboard page which station was clicked
    m.get_root().script.add_child(folium.Element(f"""
        window.addEventListener('load', function () {{
            {nodes_layer.get_name()}.eachLayer(function (layer) {{
                layer.on('click', function () {{
                    window.parent.postMessage({{type: 'node-click', N: layer.feature.properties.N}}, '*');
                }});
            }});
        }});
    """))

    folium.LayerControl(collapsed=False).add_to(m)
    m.fit_bounds(taz_layer.get_bounds())
    return m.get_root().render()


# Build everything once at startup instead of re-reading ~15 MB of GeoJSON on every request
LINK_FIELDS = ['TAZ', 'ATYPE', 'MDLANE', 'MDLIMIT', 'TIMEPEN']
MARKER_DATA = build_node_data(load_geojson("Zonehwy_Node_External_Time.geojson"))
MAP_HTML = build_map(
    load_geojson("TPBTAZ3722_TPBMod.geojson", keep=['TAZ', 'NAME', 'Community', 'TAZ_Area']),
    load_geojson("Zonehwy_Node_External_Time.geojson", keep=['N', 'FACILITY']),
    load_geojson("Zonehwy_Line_Centroid_Connectors.geojson", keep=LINK_FIELDS),
    load_geojson("Zonehwy_Line_Update.geojson", keep=LINK_FIELDS),
)

DEFAULT_NODE = next((n for n in MARKER_DATA if n["N"] == 3722), MARKER_DATA[0])


@app.route('/')
def index():
    return render_template("dashboard5.html",
                           marker_data=json.dumps(MARKER_DATA),
                           default_node=json.dumps(DEFAULT_NODE))


@app.route('/map')
def map_page():
    return MAP_HTML


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8006)), debug=True, use_reloader=False)
