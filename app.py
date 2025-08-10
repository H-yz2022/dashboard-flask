from flask import Flask, render_template
import geopandas as gpd
import folium
from branca import colormap
import json
import os

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

@app.route('/')
def index():
    # Load smaller, preprocessed GeoJSON files
    taz = gpd.read_file(os.path.join(DATA_DIR, "TPBTAZ3722_TPBMod.geojson"))
    nodes_time = gpd.read_file(os.path.join(DATA_DIR, "Zonehwy_Node_External_Time.geojson"))
    centroid = gpd.read_file(os.path.join(DATA_DIR, "Zonehwy_Line_Centroid_Connectors.geojson"))
    highway_update = gpd.read_file(os.path.join(DATA_DIR, "Zonehwy_Line_Update.geojson"))

    # Color mapper
    colormapper = colormap.linear.YlGn_09.scale(
        taz['TAZ_Area'].min(),
        taz['TAZ_Area'].max()
    )
    colormapper.caption = "TAZ Area"

    def colormapper_with_zero(x):
        return "#faded1" if x == 0 else colormapper(x)

    # Base map
    m = folium.Map(location=[39.23, -76.68], zoom_start=11, tiles='CartoDB positron')
    interaction_group = folium.FeatureGroup(name="Click to Show Chart").add_to(m)

    # TAZ layer
    folium.GeoJson(
        taz,
        style_function=lambda f: {
            'fillColor': colormapper_with_zero(f['properties']['TAZ_Area']),
            'color': 'black',
            'weight': 0.5,
            'fillOpacity': 0.4,
        },
        tooltip=folium.GeoJsonTooltip(fields=['TAZ', 'NAME', 'Community', 'TAZ_Area'])
    ).add_to(m)

    # Centroid connectors
    folium.GeoJson(
        centroid,
        style_function=lambda f: {'color': 'yellow', 'weight': 0.7, 'fillOpacity': 0.5},
        highlight_function=lambda f: {'color': 'yellow', 'weight': 1},
        tooltip=folium.GeoJsonTooltip(fields=['TAZ', 'ATYPE', 'MDLANE', 'MDLIMIT', 'TIMEPEN'])
    ).add_to(m)

    # Highway updates
    folium.GeoJson(
        highway_update,
        style_function=lambda f: {'color': 'blue', 'weight': 0.7, 'fillOpacity': 0.5},
        highlight_function=lambda f: {'color': 'red', 'weight': 1},
        tooltip=folium.GeoJsonTooltip(fields=['TAZ', 'ATYPE', 'MDLANE', 'MDLIMIT', 'TIMEPEN'])
    ).add_to(m)

    colormapper.add_to(m)

    # Node markers
    marker_data = []
    for _, row in nodes_time.iterrows():
        years = [int(c.replace('AADT', '')) for c in row.index if c.startswith('AADT')]
        values = [row[f"AADT{y}"] for y in years]
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=5, color='black', fill=True, fill_opacity=0.3,
            tooltip=f"Node {row['N']}"
        ).add_to(interaction_group)
        marker_data.append({"lat": row.geometry.y, "lng": row.geometry.x, "N": row["N"], "years": years, "values": values})

    folium.LayerControl().add_to(m)

    # Save map HTML
    static_map_path = os.path.join("static", "map-3.html")
    m.save(static_map_path)

    default_node = next((n for n in marker_data if n["N"] == "3722"), marker_data[0])

    return render_template("dashboard5.html",
                           marker_data=json.dumps(marker_data),
                           default_node=json.dumps(default_node))

if __name__ == '__main__':
    app.run(port=8006, debug=True, use_reloader=False)


