import osmnx as ox
import sys
import helpers

# elevation.clean()

if len(sys.argv) > 1:
    state_name = sys.argv[1].title()
else:
    print("Usage: state_boundaries.py <state_name>")
    sys.exit(1)

if not helpers.validate_state_name(state_name):
    print(f"'{state_name}' is not a valid US state name.")
    sys.exit(1)

# Configure OSMnx to use footprints (building outlines)
ox.settings.use_cache = True
ox.settings.log_console = True

# Retrieve the boundary of the state as a GeoDataFrame
state_boundary = ox.geocode_to_gdf(state_name)
bounds = state_boundary.total_bounds
tile_size_degree = 1
rows, cols = helpers.calculate_bbox_rows_cols(bounds, tile_size_degree)
sections = rows * cols
print(f'{state_name} requires {rows} rows, {cols} cols, for a total of {sections} sections')

# make state_name readable for output/filename purposes
state_name = state_name.replace(" ", "_")
base_output_path = f'{state_name.replace(" ", "_").lower()}_section_elevation'
merged_tiff_path = f'merged_{state_name.lower()}_elevation.tif'

# save boundary svg, and a shapefile
helpers.save_boundary_svg(state_boundary, state_name)
shapefile_path = helpers.save_shapefile(state_boundary, state_name)

sub_boxes = helpers.split_bbox(bounds, rows, cols)

helpers.download_elevation_data(sub_boxes, base_output_path, shapefile_path)
helpers.merge_tiffs(base_output_path, merged_tiff_path)
helpers.clean_up_intermediate_files(state_name)
