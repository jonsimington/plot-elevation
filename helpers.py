from rasterio.merge import merge
from rasterio.plot import show
import glob
from osgeo import gdal, ogr
import matplotlib.pyplot as plt
import os
import elevation
import rasterio as rio
from rasterio.mask import mask
import geopandas as gpd
import svgwrite
from shapely.geometry import mapping
import xml.etree.ElementTree as ET

def merge_tiffs(base_output_path, merged_output_path):
    """
    Merges TIFF files in a specified directory into a single TIFF file.

    Parameters:
    - base_output_path: The base path used for the output files during download.
    - merged_output_path: The path for the merged output file.
    """
    # Find all TIFF files generated by the download process
    tiff_files = find_clipped_tiff_files(base_output_path)

    print(tiff_files)

    # List to hold open raster datasets
    src_files_to_mosaic = []
    
    # Open and append each raster dataset to the list
    for fp in tiff_files:
        src = rio.open(fp)
        src_files_to_mosaic.append(src)
    
    # Merge function returns a single mosaic array and the transformation info
    mosaic, out_trans = merge(src_files_to_mosaic)
    
    # Copy the metadata
    out_meta = src.meta.copy()
    
    # Update the metadata to reflect the number of layers
    out_meta.update({"driver": "GTiff",
                     "height": mosaic.shape[1],
                     "width": mosaic.shape[2],
                     "transform": out_trans,
                     "crs": src.crs})
    
    # Write the mosaic raster to disk
    with rio.open(merged_output_path, "w", **out_meta) as dest:
        dest.write(mosaic)

    # Close the opened files
    for src in src_files_to_mosaic:
        src.close()

    print(f"Merged TIFF saved to {merged_output_path}")

def find_clipped_tiff_files(base_output_path):
    search_criteria = f"/home/jon/.cache/elevation/SRTM1/{base_output_path}_*_clipped.tif"
    tiff_files = glob.glob(search_criteria)

    return tiff_files

def find_tiff_files(base_output_path):
    search_criteria = f"/home/jon/.cache/elevation/SRTM1/{base_output_path}_*.tif"
    tiff_files = glob.glob(search_criteria)

    return tiff_files

def clip_raster(input_tif, output_tif, bbox):
    """
    Clips a raster file to the specified bounding box.

    Parameters:
    - input_tif: Path to the input TIFF file.
    - output_tif: Path to the output TIFF file.
    - bbox: A tuple of (xmin, ymax, xmax, ymin) for the bounding box.
    """
    xmin, ymax, xmax, ymin = bbox
    ds = gdal.Translate(output_tif, input_tif, projWin=[xmin, ymax, xmax, ymin])
    ds = None  # Close the dataset

def calculate_bbox_rows_cols(bbox, tile_size_degree):
    """
    Calculate the number of rows and columns needed to cover the area defined by bbox.
    
    Parameters:
    - bbox: A tuple of (min_lon, min_lat, max_lon, max_lat)
    - tile_size_degree: The size of each tile in degrees (assuming square tiles)
    
    Returns:
    - A tuple of (rows, columns)
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_diff = max_lon - min_lon
    lat_diff = max_lat - min_lat
    
    cols = int(lon_diff / tile_size_degree) + 1
    rows = int(lat_diff / tile_size_degree) + 1
    
    return (rows, cols)

def save_boundary_svg(state_boundary, state_name):
    # Configure the plot to not display axis for a cleaner SVG
    fig, ax = plt.subplots(figsize=(10, 10))
    state_boundary.plot(ax=ax, color='none', edgecolor='black')
    ax.axis('off')

    # Save the plot as an SVG file
    svg_file_path = f"{state_name.lower()}_boundary.svg"
    plt.savefig(svg_file_path, format='svg', bbox_inches='tight')
    plt.close()

def save_shapefile(state_boundary, state_name):
    state_folder_name = state_name.lower()

    # Define the output path for the shapefile
    output_filename = f'./{state_folder_name}/{state_name.lower()}_boundary.shp'

    # Export the GeoDataFrame to a shapefile
    state_boundary.to_file(output_filename)

    return output_filename

def download_elevation_data(sub_boxes, base_output_path, shapefile_path):
    """
    Downloads elevation data for each section defined by sub_boxes and clips it to a shapefile.

    Parameters:
    - sub_boxes: List of bounding boxes for each section.
    - base_output_path: Base path for output files, which will have indexes appended.
    - shapefile_path: Path to the shapefile used for clipping the elevation data.
    """

    state_boundary_gdf = gpd.read_file(shapefile_path)

    for idx, bbox in enumerate(sub_boxes):
        output_file = f"{base_output_path}_{idx}.tif"
        actual_output_path = f'/home/jon/.cache/elevation/SRTM1/{output_file}'
        
        elevation.clip(bounds=bbox, output=output_file, product='SRTM1')

        with rio.open(actual_output_path) as src:
            # Clip the tile to the shapefile boundary
            out_image, out_transform = mask(src, state_boundary_gdf.geometry, crop=True)
            out_meta = src.meta.copy()
            
            # Update metadata for the clipped file
            out_meta.update({"driver": "GTiff",
                             "height": out_image.shape[1],
                             "width": out_image.shape[2],
                             "transform": out_transform})
                             
            # Save the clipped tile to a new file
            clipped_output_path = f"{actual_output_path.replace('.tif', '')}_clipped.tif"
            with rio.open(clipped_output_path, "w", **out_meta) as dest:
                dest.write(out_image)

        print(f"Clipped and downloaded {clipped_output_path}")
        
        # Optionally, display the clipped DEM
        with rio.open(clipped_output_path) as clipped_dem:
            show(clipped_dem, title=f"Clipped DEM {idx}")

        elevation.clean()  # Clean cache after each download

def split_bbox(bbox, rows, cols):
    """
    Splits the bounding box into smaller sections.

    Parameters:
    - bbox: Tuple of (min_lon, min_lat, max_lon, max_lat).
    - rows, cols: How many sections to split into vertically and horizontally.

    Returns:
    - List of tuples representing the smaller bounding boxes.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_step = (max_lon - min_lon) / cols
    lat_step = (max_lat - min_lat) / rows

    sub_boxes = []
    for i in range(rows):
        for j in range(cols):
            sub_min_lon = min_lon + j * lon_step
            sub_max_lon = sub_min_lon + lon_step
            sub_min_lat = min_lat + i * lat_step
            sub_max_lat = sub_min_lat + lat_step
            sub_boxes.append((sub_min_lon, sub_min_lat, sub_max_lon, sub_max_lat))

    return sub_boxes

def validate_state_name(state_name):
    us_states = [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", 
        "Colorado", "Connecticut", "Delaware", "Florida", "Georgia", 
        "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", 
        "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", 
        "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", 
        "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", 
        "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", 
        "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", 
        "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", 
        "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"
    ]

    return state_name in us_states

def clean_up_intermediate_files(state_name):
    tiff_files = find_tiff_files(f'{state_name}_section_elevation')

    for file_path in tiff_files:
        if os.path.exists(file_path):
            os.remove(file_path)

def generate_contours(input_tif, output_shp, interval=10.0, attribute_name='elev'):
    """
    Generate contours from a GeoTIFF and save them to a shapefile.

    Parameters:
    - input_tif: Path to the input GeoTIFF file.
    - output_shp: Path for the output shapefile.
    - interval: Elevation interval between contour lines.
    - attribute_name: Name of the attribute to store the elevation value.
    """
    # Open the input GeoTIFF file
    src_ds = gdal.Open(input_tif)
    if src_ds is None:
        print(f"Unable to open {input_tif}")
        return

    band = src_ds.GetRasterBand(1)
    driver = ogr.GetDriverByName('ESRI Shapefile')
    if driver is None:
        print("ESRI Shapefile driver not available.")
        return

    if os.path.exists(output_shp):
        driver.DeleteDataSource(output_shp)

    out_ds = driver.CreateDataSource(output_shp)
    srs = src_ds.GetProjectionRef()
    layer = out_ds.CreateLayer(output_shp, gdal.osr.SpatialReference(wkt=srs), ogr.wkbLineString)
    layer.CreateField(ogr.FieldDefn(attribute_name, ogr.OFTReal))

    # Use the index of the created field for the elevation attribute
    field_idx = layer.FindFieldIndex(attribute_name, 1)

    elevations = [0, 100, 200, 300, 400, 500, 527]

    gdal.ContourGenerate(band, interval, 0, elevations, 0, 0, layer, field_idx, 0)

    del src_ds, out_ds

def contours_to_svg(shapefile_path, svg_path, state_name, simplification_tolerance=0.001):
    # Load the shapefile
    gdf = gpd.read_file(shapefile_path)

    gdf = gdf[gdf.is_valid & ~gdf.is_empty]
    
    # Simplify geometries
    gdf['geometry'] = gdf['geometry'].simplify(simplification_tolerance, preserve_topology=True)

    rows, cols = calculate_bbox_rows_cols(gdf.total_bounds, 1)

    # Assuming svg_width and svg_height are determined externally or set to a fixed value
    svg_width, svg_height = calculate_svg_dimensions_based_on_grid(rows+1, cols+1) # Placeholder values, adjust or calculate as needed

    # Normalize the geometry to fit the SVG canvas
    bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
    x_range = bounds[2] - bounds[0]
    y_range = bounds[3] - bounds[1]

    # Create an SVG drawing
    dwg = svgwrite.Drawing(svg_path, size=(svg_width, svg_height))

    # Add contours to the SVG
    for _, row in gdf.iterrows():
        if row['geometry'].geom_type == 'LineString':
            points = [(svg_width * (x - bounds[0]) / x_range, 
                       svg_height * (1 - (y - bounds[1]) / y_range))  # Flip y-axis to match SVG coordinate system
                      for x, y in mapping(row['geometry'])['coordinates']]
            dwg.add(dwg.polyline(points, stroke=svgwrite.rgb(10, 10, 16, '%'), fill='none'))
        elif row['geometry'].geom_type == 'MultiLineString':
            for line in row['geometry']:
                points = [(svg_width * (x - bounds[0]) / x_range, 
                           svg_height * (1 - (y - bounds[1]) / y_range))  # Flip y-axis to match SVG coordinate system
                          for x, y in mapping(line)['coordinates']]
                dwg.add(dwg.polyline(points, stroke=svgwrite.rgb(10, 10, 16, '%'), fill='none'))

    # Calculate the position for the text element
    # Assuming the lowest point is at the bottom of the SVG, adjust the y-position by the specified number of pixels
    pixels_below_lowest_point = 20
    text_y_position = svg_height - pixels_below_lowest_point
    text = state_name.title()
    font_size = '20px'
    font_family = 'Roboto Mono'

    # Add text element below the lowest contour
    dwg.add(dwg.text(text, insert=(svg_width / 2, text_y_position), font_size=font_size, font_family=font_family, text_anchor="middle"))


    # Save the SVG
    dwg.save()

def calculate_svg_dimensions_based_on_grid(rows, cols, base_dimension=1000):
    """
    Calculate SVG dimensions to match the aspect ratio defined by the number of rows and columns,
    ensuring the SVG has a non-stretched version of the grid.

    Parameters:
    - rows: Number of rows in the grid.
    - cols: Number of columns in the grid.
    - base_dimension: The base size for the shorter side of the SVG to maintain aspect ratio.

    Returns:
    - A tuple containing the width and height of the SVG.
    """
    # Calculate the aspect ratio based on the grid
    aspect_ratio = cols / rows
    
    # Determine which dimension to match to the base_dimension
    if aspect_ratio >= 1:
        # Width is greater than or equal to height
        svg_width = base_dimension * aspect_ratio
        svg_height = base_dimension
    else:
        # Height is greater than width
        svg_width = base_dimension
        svg_height = base_dimension / aspect_ratio

    return int(svg_width), int(svg_height)

