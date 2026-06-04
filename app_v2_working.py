
# ======================================
# IMPORT LIBRARIES
# ======================================

import zipfile
import os
import tempfile
import ee
import geopandas as gpd
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import folium
import numpy as np

from streamlit_folium import st_folium
from datetime import date


# ======================================
# INITIALIZE EARTH ENGINE
# ======================================

try:

    ee.Initialize()

except:

    ee.Authenticate()

    ee.Initialize()


# ======================================
# LANDSAT 8 + 9 COLLECTION
# ======================================

landsat8 = ee.ImageCollection(
    'LANDSAT/LC08/C02/T1_L2'
)

landsat9 = ee.ImageCollection(
    'LANDSAT/LC09/C02/T1_L2'
)

landsat = landsat8.merge(
    landsat9
)


# ======================================
# PAGE CONFIG
# ======================================

st.set_page_config(
    page_title="Urban Heat Intelligence",
    layout="wide"
)


# ======================================
# SIDEBAR
# ======================================

st.sidebar.title(
    "Urban Climate Controls"
)

st.sidebar.write(
    "Configure analysis settings"
)


# ======================================
# NAVIGATION
# ======================================

page = st.sidebar.radio(
    "Navigation",
    [
        "Map Analysis",
        "Time-Series Analytics"
    ]
)


# ======================================
# MAP ANALYSIS PAGE
# ======================================

if page == "Map Analysis":

    st.title(
        "Urban Heat Intelligence Platform"
    )

    st.write(
        """
        Upload GeoJSON, KML, or ZIP Shapefile
        to generate:
        - Land Surface Temperature
        - NDVI
        - Hotspot Analysis
        """
    )

    # ==================================
    # DATE RANGE
    # ==================================

    start_date = st.sidebar.date_input(
        "Start Date",
        date(2024, 1, 1)
    )

    end_date = st.sidebar.date_input(
        "End Date",
        date(2024, 12, 31)
    )

    # ==================================
    # BASEMAP
    # ==================================

    basemap = st.sidebar.selectbox(
        "Select Basemap",
        [
            "OpenStreetMap",
            "SATELLITE",
            "HYBRID",
            "TERRAIN"
        ]
    )

    # ==================================
    # LAYER TOGGLES
    # ==================================

    show_lst = st.sidebar.checkbox(
        "Show LST",
        value=True
    )

    show_ndvi = st.sidebar.checkbox(
        "Show NDVI",
        value=True
    )

    show_hotspot = st.sidebar.checkbox(
        "Show Hotspot",
        value=True
    )

    # ==================================
    # FILE UPLOAD
    # ==================================

    uploaded_file = st.sidebar.file_uploader(
        "Upload Boundary",
        type=["geojson", "kml", "zip"]
    )

    # ==================================
    # PROCESS FILE
    # ==================================

    if uploaded_file is not None:

        file_extension = os.path.splitext(
            uploaded_file.name
        )[1]

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=file_extension
        )

        temp_file.write(
            uploaded_file.read()
        )

        temp_file.close()

        # ==============================
        # READ FILES
        # ==============================

        if uploaded_file.name.endswith(
            ".geojson"
        ):

            gdf = gpd.read_file(
                temp_file.name
            )

        elif uploaded_file.name.endswith(
            ".kml"
        ):

            gdf = gpd.read_file(
                temp_file.name,
                driver="KML"
            )

        elif uploaded_file.name.endswith(
            ".zip"
        ):

            extract_path = tempfile.mkdtemp()

            with zipfile.ZipFile(
                temp_file.name,
                "r"
            ) as zip_ref:

                zip_ref.extractall(
                    extract_path
                )

            shp_file = None

            for root, dirs, files in os.walk(
                extract_path
            ):

                for file in files:

                    if file.endswith(".shp"):

                        shp_file = os.path.join(
                            root,
                            file
                        )

            gdf = gpd.read_file(
                shp_file
            )

        st.success(
            "Boundary uploaded successfully!"
        )

        # ==============================
        # EARTH ENGINE GEOMETRY
        # ==============================

        geojson = gdf.__geo_interface__

        ee_geometry = ee.FeatureCollection(
            geojson
        )

        # ==============================
        # CLOUD MASK
        # ==============================

        def mask_clouds(image):

            qa = image.select(
                'QA_PIXEL'
            )

            cloud = qa.bitwiseAnd(
                1 << 3
            ).eq(0)

            cloud_shadow = qa.bitwiseAnd(
                1 << 4
            ).eq(0)

            mask = cloud.And(
                cloud_shadow
            )

            return image.updateMask(mask)

        # ==============================
        # CALCULATE INDICES
        # ==============================

        def calculate_indices(image):

            thermal = image.select(
                'ST_B10'
            ).multiply(
                0.00341802
            ).add(
                149.0
            )

            lst = thermal.subtract(
                273.15
            ).rename(
                'LST'
            )

            ndvi = image.normalizedDifference(
                ['SR_B5', 'SR_B4']
            ).rename(
                'NDVI'
            )

            return image.addBands([
                lst,
                ndvi
            ])

        # ==============================
        # PROCESS COLLECTION
        # ==============================

        processed = landsat \
            .filterBounds(
                ee_geometry
            ) \
            .filterDate(
                str(start_date),
                str(end_date)
            ) \
            .filter(
                ee.Filter.lt(
                    'CLOUD_COVER',
                    20
                )
            ) \
            .map(
                mask_clouds
            ) \
            .map(
                calculate_indices
            )

        # ==============================
        # CREATE COMPOSITES
        # ==============================

        lst_image = processed.select(
            'LST'
        ).median().clip(
            ee_geometry
        )

        ndvi_image = processed.select(
            'NDVI'
        ).median().clip(
            ee_geometry
        )

        # ==============================
        # HOTSPOT CLASSIFICATION
        # ==============================

        hotspot = lst_image.expression(

            "(b('LST') < 25) ? 1" +
            ": (b('LST') < 30) ? 2" +
            ": (b('LST') < 35) ? 3" +
            ": (b('LST') < 40) ? 4" +
            ": 5"

        ).rename(
            'Hotspot'
        ).clip(
            ee_geometry
        )

        # ==============================
        # VISUALIZATION
        # ==============================

        lst_vis = {
            'min': 20,
            'max': 40,
            'palette': [
                'blue',
                'green',
                'yellow',
                'orange',
                'red'
            ]
        }

        ndvi_vis = {
            'min': -1,
            'max': 1,
            'palette': [
                'brown',
                'yellow',
                'green'
            ]
        }

        hotspot_vis = {

            'min': 1,

            'max': 5,

            'palette': [

                '#2c7bb6',
                '#abd9e9',
                '#ffffbf',
                '#fdae61',
                '#d7191c'

            ]
        }

        # ==============================
        # MAP CENTER
        # ==============================

        centroid = gdf.geometry.centroid.iloc[0]

        map_center = [
            centroid.y,
            centroid.x
        ]

        # ==============================
        # CREATE MAP
        # ==============================

        m = folium.Map(
            location=map_center,
            zoom_start=8,
            control_scale=True
        )

        # ==============================
        # BASEMAPS
        # ==============================

        if basemap == "OpenStreetMap":

            folium.TileLayer(
                'OpenStreetMap',
                name='OpenStreetMap'
            ).add_to(m)

        elif basemap == "SATELLITE":

            folium.TileLayer(
                tiles='https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                attr='Google',
                name='Satellite'
            ).add_to(m)

        elif basemap == "HYBRID":

            folium.TileLayer(
                tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
                attr='Google',
                name='Hybrid'
            ).add_to(m)

        elif basemap == "TERRAIN":

            folium.TileLayer(
                tiles='https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
                attr='Google',
                name='Terrain'
            ).add_to(m)

        # ==============================
        # STUDY AREA OUTLINE
        # ==============================

        folium.GeoJson(
            geojson,
            name="Study Area",
            style_function=lambda x: {
                'fillColor': 'none',
                'color': 'black',
                'weight': 2
            }
        ).add_to(m)

        # ==============================
        # LST LAYER
        # ==============================

        if show_lst:

            map_id = ee.Image(
                lst_image
            ).getMapId(lst_vis)

            folium.TileLayer(
                tiles=map_id['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name='LST',
                overlay=True,
                control=True
            ).add_to(m)

        # ==============================
        # NDVI LAYER
        # ==============================

        if show_ndvi:

            map_id = ee.Image(
                ndvi_image
            ).getMapId(ndvi_vis)

            folium.TileLayer(
                tiles=map_id['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name='NDVI',
                overlay=True,
                control=True
            ).add_to(m)

        # ==============================
        # HOTSPOT LAYER
        # ==============================

        if show_hotspot:

            map_id = ee.Image(
                hotspot
            ).getMapId(
                hotspot_vis
            )

            folium.TileLayer(
                tiles=map_id['tile_fetcher'].url_format,
                attr='Google Earth Engine',
                name='Hotspot',
                overlay=True,
                control=True
            ).add_to(m)

        # ==============================
        # LAYER CONTROL
        # ==============================

        folium.LayerControl().add_to(m)

        # ==============================
        # COMBINED LEGENDS
        # ==============================

        legend_html = ""

        # ==============================
        # LST LEGEND
        # ==============================

        if show_lst:

            legend_html += """

            <div style="
            position: fixed;
            bottom: 50px;
            right: 50px;
            width: 180px;
            height: 170px;
            background-color: white;
            border:2px solid grey;
            z-index:9999;
            font-size:14px;
            padding: 10px;
            border-radius:8px;
            ">

            <b>LST (°C)</b><br><br>

            <i style="background:blue;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Very Low<br>

            <i style="background:green;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Low<br>

            <i style="background:yellow;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Moderate<br>

            <i style="background:orange;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            High<br>

            <i style="background:red;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Extreme

            </div>

            """

        # ==============================
        # NDVI LEGEND
        # ==============================

        if show_ndvi:

            legend_html += """

            <div style="
            position: fixed;
            bottom: 240px;
            right: 50px;
            width: 180px;
            height: 130px;
            background-color: white;
            border:2px solid grey;
            z-index:9999;
            font-size:14px;
            padding: 10px;
            border-radius:8px;
            ">

            <b>NDVI</b><br><br>

            <i style="background:brown;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Low Vegetation<br>

            <i style="background:yellow;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Moderate<br>

            <i style="background:green;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            High Vegetation

            </div>

            """

        # ==============================
        # HOTSPOT LEGEND
        # ==============================

        if show_hotspot:

            legend_html += """

            <div style="
            position: fixed;
            bottom: 390px;
            right: 50px;
            width: 180px;
            height: 170px;
            background-color: white;
            border:2px solid grey;
            z-index:9999;
            font-size:14px;
            padding: 10px;
            border-radius:8px;
            ">

            <b>Heat Hotspots</b><br><br>

            <i style="background:#2c7bb6;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Very Low<br>

            <i style="background:#abd9e9;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Low<br>

            <i style="background:#ffffbf;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Moderate<br>

            <i style="background:#fdae61;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            High<br>

            <i style="background:#d7191c;
            width:15px;
            height:15px;
            float:left;
            margin-right:8px;"></i>
            Extreme

            </div>

            """

        m.get_root().html.add_child(
            folium.Element(
                legend_html
            )
        )

        # ==============================
        # DISPLAY MAP
        # ==============================

        st_folium(
            m,
            width=1200,
            height=700
        )


# ======================================
# TIMESERIES PAGE
# ======================================

if page == "Time-Series Analytics":

    st.title(
        "Climate Time-Series Analytics"
    )

    st.write(
        """
        Analyze:
        - Yearly Trends
        - Monthly Trends
        - Correlation Analysis
        """
    )

    # ==================================
    # TIMESERIES TYPE
    # ==================================

    timeseries_type = st.sidebar.radio(
        "Time-Series Type",
        [
            "Yearly",
            "Monthly"
        ]
    )

    # ==================================
    # ANALYSIS TYPE
    # ==================================

    analysis_type = st.sidebar.selectbox(
        "Analysis Type",
        [
            "LST Trend",
            "NDVI Trend",
            "LST-NDVI Correlation"
        ]
    )

    # ==================================
    # YEARLY SETTINGS
    # ==================================

    if timeseries_type == "Yearly":

        start_year = st.sidebar.selectbox(
            "Start Year",
            list(range(2015, 2026)),
            index=0
        )

        end_year = st.sidebar.selectbox(
            "End Year",
            list(range(2015, 2026)),
            index=10
        )

    # ==================================
    # MONTHLY SETTINGS
    # ==================================

    elif timeseries_type == "Monthly":

        start_month = st.sidebar.date_input(
            "Start Month",
            date(2015, 1, 1)
        )

        end_month = st.sidebar.date_input(
            "End Month",
            date.today()
        )

    # ==================================
    # FILE UPLOAD
    # ==================================

    uploaded_file = st.sidebar.file_uploader(
        "Upload Boundary",
        type=["geojson", "kml", "zip"],
        key="timeseries_upload"
    )

    # ==================================
    # PROCESS FILE
    # ==================================

    if uploaded_file is not None:

        file_extension = os.path.splitext(
            uploaded_file.name
        )[1]

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=file_extension
        )

        temp_file.write(
            uploaded_file.read()
        )

        temp_file.close()

        # ==============================
        # READ FILES
        # ==============================

        if uploaded_file.name.endswith(".geojson"):

            gdf = gpd.read_file(
                temp_file.name
            )

        elif uploaded_file.name.endswith(".kml"):

            gdf = gpd.read_file(
                temp_file.name,
                driver="KML"
            )

        elif uploaded_file.name.endswith(".zip"):

            extract_path = tempfile.mkdtemp()

            with zipfile.ZipFile(
                temp_file.name,
                "r"
            ) as zip_ref:

                zip_ref.extractall(
                    extract_path
                )

            shp_file = None

            for root, dirs, files in os.walk(
                extract_path
            ):

                for file in files:

                    if file.endswith(".shp"):

                        shp_file = os.path.join(
                            root,
                            file
                        )

            gdf = gpd.read_file(
                shp_file
            )

        st.success(
            "Boundary uploaded successfully!"
        )

        # ==============================
        # EARTH ENGINE GEOMETRY
        # ==============================

        geojson = gdf.__geo_interface__

        ee_geometry = ee.FeatureCollection(
            geojson
        )

        # ==============================
        # CLOUD MASK
        # ==============================

        def mask_clouds(image):

            qa = image.select(
                'QA_PIXEL'
            )

            cloud = qa.bitwiseAnd(
                1 << 3
            ).eq(0)

            cloud_shadow = qa.bitwiseAnd(
                1 << 4
            ).eq(0)

            mask = cloud.And(
                cloud_shadow
            )

            return image.updateMask(mask)

        # ==============================
        # CALCULATE INDICES
        # ==============================

        def calculate_indices(image):

            thermal = image.select(
                'ST_B10'
            ).multiply(
                0.00341802
            ).add(
                149.0
            )

            lst = thermal.subtract(
                273.15
            ).rename(
                'LST'
            )

            ndvi = image.normalizedDifference(
                ['SR_B5', 'SR_B4']
            ).rename(
                'NDVI'
            )

            return image.addBands([
                lst,
                ndvi
            ])

        # ==============================
        # PERIODS
        # ==============================

        if timeseries_type == "Yearly":

            periods = list(
                range(start_year, end_year + 1)
            )

            x_values = periods

        else:

            monthly_dates = pd.date_range(
                start=start_month,
                end=end_month,
                freq='MS'
            )

            periods = monthly_dates

            x_values = [
                d.strftime("%b-%Y")
                for d in monthly_dates
            ]

        lst_values = []

        ndvi_values = []

        # ==============================
        # ANALYSIS LOOP
        # ==============================

        with st.spinner(
            "Generating analysis..."
        ):

            for period in periods:

                if timeseries_type == "Yearly":

                    start = f"{period}-01-01"

                    end = f"{period}-12-31"

                else:

                    start = period.strftime(
                        "%Y-%m-%d"
                    )

                    if period.month == 12:

                        next_month = period.replace(
                            year=period.year + 1,
                            month=1
                        )

                    else:

                        next_month = period.replace(
                            month=period.month + 1
                        )

                    end = next_month.strftime(
                        "%Y-%m-%d"
                    )

                collection = landsat \
                    .filterBounds(
                        ee_geometry
                    ) \
                    .filterDate(
                        start,
                        end
                    ) \
                    .filter(
                        ee.Filter.lt(
                            'CLOUD_COVER',
                            20
                        )
                    ) \
                    .map(
                        mask_clouds
                    ) \
                    .map(
                        calculate_indices
                    )

                # ==========================
                # LST
                # ==========================

                lst_image = collection.select(
                    'LST'
                ).median()

                lst_stats = lst_image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_geometry,
                    scale=500,
                    bestEffort=True
                )

                lst_mean = lst_stats.getInfo().get(
                    'LST',
                    None
                )

                if lst_mean is None:

                    if len(lst_values) > 0:

                        lst_mean = round(
                            sum(lst_values) / len(lst_values),
                            2
                        )

                    else:

                        lst_mean = 0

                else:

                    lst_mean = round(
                        lst_mean,
                        2
                    )

                lst_values.append(
                    lst_mean
                )

                # ==========================
                # NDVI
                # ==========================

                ndvi_image = collection.select(
                    'NDVI'
                ).median()

                ndvi_stats = ndvi_image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_geometry,
                    scale=500,
                    bestEffort=True
                )

                ndvi_mean = ndvi_stats.getInfo().get(
                    'NDVI',
                    None
                )

                if ndvi_mean is None:

                    if len(ndvi_values) > 0:

                        ndvi_mean = round(
                            sum(ndvi_values) / len(ndvi_values),
                            3
                        )

                    else:

                        ndvi_mean = 0

                else:

                    ndvi_mean = round(
                        ndvi_mean,
                        3
                    )

                ndvi_values.append(
                    ndvi_mean
                )

        # ==============================
        # DATAFRAME
        # ==============================

        df = pd.DataFrame({

            'Period': x_values,

            'Mean_LST': lst_values,

            'Mean_NDVI': ndvi_values

        })

        st.subheader(
            "Time-Series Data"
        )

        st.dataframe(df)

        # ==============================
        # PLOT
        # ==============================

        fig, ax = plt.subplots(
            figsize=(12, 5)
        )

        if analysis_type == "LST Trend":

            ax.plot(
                x_values,
                lst_values,
                marker='o'
            )

            ax.set_ylabel(
                "Mean LST (°C)"
            )

        elif analysis_type == "NDVI Trend":

            ax.plot(
                x_values,
                ndvi_values,
                marker='s'
            )

            ax.set_ylabel(
                "Mean NDVI"
            )

        elif analysis_type == "LST-NDVI Correlation":

            correlation = df[
                'Mean_LST'
            ].corr(
                df['Mean_NDVI']
            )

            r2 = correlation ** 2

            col1, col2 = st.columns(2)

            with col1:

                st.metric(
                    "Correlation",
                    round(correlation, 3)
                )

            with col2:

                st.metric(
                    "R²",
                    round(r2, 3)
                )

            ax.scatter(
                ndvi_values,
                lst_values
            )

            ax.set_xlabel(
                "Mean NDVI"
            )

            ax.set_ylabel(
                "Mean LST (°C)"
            )

        ax.grid(True)

        plt.xticks(
            rotation=45
        )

        st.pyplot(fig)

        # ==============================
        # EXPORT PNG
        # ==============================

        chart_path = "timeseries_chart.png"

        fig.savefig(
            chart_path,
            dpi=300,
            bbox_inches='tight'
        )

        with open(
            chart_path,
            "rb"
        ) as file:

            st.download_button(
                label="Download Chart PNG",
                data=file,
                file_name="Climate_Timeseries_Chart.png",
                mime="image/png"
            )

        # ==============================
        # EXPORT EXCEL
        # ==============================

        excel_path = "timeseries_data.xlsx"

        df.to_excel(
            excel_path,
            index=False
        )

        with open(
            excel_path,
            "rb"
        ) as file:

            st.download_button(
                label="Download Excel Data",
                data=file,
                file_name="Climate_Timeseries_Data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


