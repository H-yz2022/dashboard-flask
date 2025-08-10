# -*- coding: utf-8 -*-
"""
Created on Sun Jul 26 23:42:35 2025

@author: huang
"""
from flask import Flask, render_template, render_template_string
import geopandas as gpd
import pandas as pd
import folium
from folium.utilities import JsCode
from folium.features import GeoJsonPopup
import branca.colormap as cm
from branca.colormap import linear
import json
from branca import colormap
from folium import plugins
from folium import Map, CircleMarker, Element
from folium.plugins import MiniMap
import plotly.graph_objects as go


app = Flask(__name__)

@app.route('/')
def index():
    # Load shapefiles
    taz = gpd.read_file("TPBTAZ3722_TPBMod.shp").to_crs(epsg=4326)
    #highway = gpd.read_file("Zonehwy_Line.shp").to_crs(epsg=4326)
    #nodes = gpd.read_file("Zonehwy_Node.shp").to_crs(epsg=4326)
    nodes_time = gpd.read_file("Zonehwy_Node_External_Time.shp").to_crs(epsg=4326)
    centroid = gpd.read_file("Zonehwy_Line_Centroid_Connectors.shp").to_crs(epsg=4326)
    highway_update = gpd.read_file("Zonehwy_Line_Update.shp").to_crs(epsg=4326)
    
# Correct indentation (4 spaces)
    colormapper = colormap.linear.YlGn_09.scale(
        taz['TAZ_Area'].min(),
        taz['TAZ_Area'].max()
    )
    colormapper.caption = "TAZ Area"

    def colormapper_with_zero(x):
        if x==0:
            return "#faded1"
        else:
            return colormapper(x)
    # Base map
    m = folium.Map(
        location=[39.23, -76.68],  # Adjust this based on your real center
        zoom_start=11,#
        tiles='CartoDB positron' #
    )
    interaction_group = folium.FeatureGroup(name="Click to Show Chart")
    interaction_group.add_to(m)


    # Add TAZ layer
    
    folium.GeoJson(
        taz,
        style_function=lambda feature: {
            'fillColor': colormapper_with_zero(feature['properties']['TAZ_Area']),
            'color': 'black',
            'weight': 0.5,
            'fillOpacity': 0.4,
        },
        tooltip=folium.GeoJsonTooltip(fields=['TAZ', 'NAME', 'Community', 'TAZ_Area'])
    ).add_to(m)
    
    folium.GeoJson(
        centroid,
        style_function=lambda feature: {
            'fillColor': 'yellow',
            'color': 'yellow',
            'weight': 0.7,
            'fillOpacity': 0.5,
        },
        highlight_function=lambda feature: {
            'color': 'yellow',
            'weight': 1,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['TAZ', 'ATYPE', 'MDLANE', 'MDLIMIT', 'TIMEPEN'],
        ),
    ).add_to(m)
    
    folium.GeoJson(
        highway_update,
        style_function=lambda feature: {
            'fillColor': 'black',
            'color': 'blue',
            'weight': 0.7,
            'fillOpacity': 0.5,
        },
        highlight_function=lambda feature: {
            'color': 'red',
            'weight': 1,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=['TAZ', 'ATYPE', 'MDLANE', 'MDLIMIT', 'TIMEPEN'],
        ),
    ).add_to(m)
    
    colormapper.add_to(m)
    
    time_cols = [col for col in nodes_time.columns if col.startswith('AADT')]
    marker_data = []
    for _, row in nodes_time.iterrows():
        years = [int(col.replace('AADT', '')) for col in row.index if col.startswith('AADT')]
        values = [row[f"AADT{year}"] for year in years]

        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=5,
            color='black',
            fill=True,
            fill_opacity=0.3,
            tooltip=f"Node {row['N']}"
        ).add_to(interaction_group)

        marker_data.append({
            "lat": row.geometry.y,
            "lng": row.geometry.x,
            "N": row["N"],
            "years": years,
            "values": values
        })

    folium.LayerControl().add_to(m)

    # Save base map HTML
    m.save("static/map-3.html")

    # Inject custom JS into map HTML to handle postMessage
    with open("static/map-3.html", "r", encoding="utf-8") as file:
        html = file.read()

    # Inject updated, safe custom JS that waits for Leaflet
    injected_js = """
<script>
console.log("Custom map JS loaded and waiting for Leaflet...");

function waitForLeaflet(callback, attempts = 0) {
    if (typeof window.L !== 'undefined') {
        console.log("Leaflet loaded. Initializing markers...");
        callback();
    } else if (attempts < 20) {  // Wait max 2 seconds
        setTimeout(() => waitForLeaflet(callback, attempts + 1), 100);
    } else {
        console.error("Leaflet (L) not found after waiting.");
    }
}

function getMapInstance() {
    for (var key in window) {
        if (window[key] instanceof L.Map) {
            return window[key];
        }
    }
    console.error("Map instance not found.");
    return null;
}

waitForLeaflet(() => {
    window.addEventListener("message", function(event) {
        console.log("Dashboard received message:", event.data);
        const data = event.data;
        if (data.action === "initMarkers" && data.data) {
            const map = getMapInstance();
            if (!map) return;

            data.data.forEach(function(marker) {
                var circle = L.circleMarker([marker.lat, marker.lng], {
                    radius: 5,
                    color: 'blue',
                    fillColor: 'blue',
                    fillOpacity: 0.3
                }).addTo(map);

                circle.on('click', function() {
                    console.log("Marker clicked:", marker);
                    window.parent.postMessage(marker, "*");
                });
            });
        }
    });
});
</script>
</body>"""

    # Replace closing body tag to insert custom JS before </body>
    html = html.replace("</body>", injected_js)
    with open("static/map-3.html", "w", encoding="utf-8") as file:
        file.write(html)
        
    default_node = next((node for node in marker_data if node["N"] == "3722"), marker_data[0])

    return render_template(
        "dashboard5.html",
        marker_data=json.dumps(marker_data),
        default_node=json.dumps(default_node)
    )

if __name__ == '__main__':
    app.run(port=8006, debug=True, use_reloader=False)
