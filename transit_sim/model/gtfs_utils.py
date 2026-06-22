import itertools
import numpy as np
import pandas as pd 
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import Point
from .config import project_crs

try:
    from IPython.display import display  # type: ignore
except Exception:
    def display(*args, **kwargs):
        return None

#############################################################
############## Reading and pre-processing GTFS ##############
#############################################################

def _read_gtfs_files(file_name):
    ### read GTFS files into a pandas dataframe
    ### transit_sim needs: trips.txt, stops.txt, stop_times.txt
    table = pd.read_csv(file_name)
    return table

def _add_capacity(trips_table, train_capacity):
    ### add capacity
    
    if isinstance(train_capacity, int):
        trips_table['capacity'] = train_capacity
    elif isinstance(train_capacity, pd.DataFrame):
        trips_table = pd.merge(trips_table, train_capacity[['trip_id', 'capacity']], 
                               how='left', on='trip_id')
    else: print('invalid train_capacity input: only integer number or dataframe')
    
    return trips_table

def _filter_trips_table_by_service_id(trips_table, service_id):
    ### filter trips in one day, or subset of trips in one day
    
    if isinstance(service_id, list):
        trips_table = trips_table[trips_table['service_id'].isin(service_id)]
    elif isinstance(service_id, str):
        trips_table = trips_table[trips_table['service_id']==service_id]
    else:
        print('invalid service_id inputs')
    return trips_table

def _gtfs_id_to_integers(trips_table=None, stops_table=None, stop_times_table=None):
    ### the trip_id and stop_id in GTFS may not be integers, which cause type conversion problems and may slow down the computation.
    
    ### convert stop_id to integer
    stops_table['stop_id_original'] = stops_table['stop_id'] 
    unique_order = pd.unique(stops_table['stop_id'])
    stops_table['stop_id'] = pd.Categorical(stops_table['stop_id'], categories=unique_order).codes
    # stops_table['stop_id'] = stops_table['stop_name'].astype('category').cat.codes ### same station has to have the same name
    print(f"stop_id ranges from {np.min(stops_table['stop_id'])} - {np.max(stops_table['stop_id'])}")
    
    ### convert trip_id to integer
    trips_table['trip_id_original'] = trips_table['trip_id']
    unique_order = pd.unique(trips_table['trip_id'])
    trips_table['trip_id'] = pd.Categorical(trips_table['trip_id'], categories=unique_order).codes
    # trips_table['trip_id'] = trips_table['trip_id'].astype('category').cat.codes
    trips_table['trip_id'] += 10**(int(np.log10(np.max(stops_table['stop_id'])))+2) ### raise the trip_id to a higher number
    print(f"trip_id ranges from {np.min(trips_table['trip_id'])} - {np.max(trips_table['trip_id'])}")

    ### change the datatype and return dataframes
    stop_times_table = stop_times_table.merge(stops_table, how='left', left_on='stop_id', right_on='stop_id_original', suffixes=['_backup', ''])
    stop_times_table = stop_times_table.merge(trips_table, how='left', left_on='trip_id', right_on='trip_id_original', suffixes=['_backup', ''])
    
    return trips_table, stops_table, stop_times_table

#############################################################
############### Creating train schedule info ################
#############################################################

def _shift_lines(schedule_table):
    ### shift lines for better plotting
    
    route_seq_dict = dict()
    seq_id = 0
    for route_id, _ in schedule_table.sort_values(by='route_id', ascending=True).groupby('route_id'):
        route_seq_dict[route_id] = seq_id
        seq_id += 1
    schedule_table = gpd.GeoDataFrame(schedule_table, crs=project_crs, 
                                      geometry=[Point(xy) for xy in zip(schedule_table.stop_lon, schedule_table.stop_lat)])
    if project_crs is not None:
        schedule_table = schedule_table.to_crs(3857)
    ### calculate shift factor
    minx, miny, maxx, maxy = schedule_table.total_bounds
    shift_factor = min(max(5, (maxx - minx)/10000), 50)
    schedule_table['stop_x'] = schedule_table.geometry.x + shift_factor * schedule_table['route_id'].map(route_seq_dict)
    schedule_table['stop_y'] = schedule_table.geometry.y + shift_factor * schedule_table['route_id'].map(route_seq_dict)
    schedule_table['geometry'] = [Point(xy) for xy in zip(schedule_table.stop_x, schedule_table.stop_y)]
    if project_crs is not None:
        schedule_table = schedule_table.to_crs(4326)
    schedule_table['stop_lon'] = schedule_table.geometry.x
    schedule_table['stop_lat'] = schedule_table.geometry.y
    
    return schedule_table

def _convert_times(schedule_table):
    ### convert arrival and departure time to seconds since midnight
    
    schedule_table['arrival_time'] = schedule_table['arrival_time'].apply(
        lambda x: 3600*int(x.split(':')[0]) + 60*int(x.split(':')[1]) + int(x.split(':')[2]))
    schedule_table['departure_time'] = schedule_table['departure_time'].apply(
        lambda x: 3600*int(x.split(':')[0]) + 60*int(x.split(':')[1]) + int(x.split(':')[2]))
    ### add 30 seconds dwell time at stop if train arrival time = train departure time in GTFS
    schedule_table['departure_time'] = np.where(schedule_table['arrival_time']==schedule_table['departure_time'],
                                                schedule_table['departure_time']+30, schedule_table['departure_time'])
    return schedule_table

def _gtfs_tables_to_schedule(trips_table=None, stops_table=None, stop_times_table=None):

    ### merge the tables
    schedule_table = stop_times_table[['trip_id', 'arrival_time', 'departure_time', 'stop_id']]
    schedule_table = pd.merge(schedule_table, trips_table[['trip_id', 'route_id', 'capacity']], how='inner', on='trip_id')
    
    ### assign a route-stop code to individual stops
    ### route_id is still the original and stop_id should be integer now
    schedule_table['route_stop_id'] = schedule_table.apply(lambda x:
                                                           '{}-{}'.format(x['route_id'], x['stop_id']), axis=1)
    ### assign locations to individual stations
    schedule_table = pd.merge(schedule_table, 
                              stops_table[['stop_id', 'stop_name', 'stop_lon', 'stop_lat']],
                              how='inner', on='stop_id')
    schedule_table = schedule_table.dropna(subset=['stop_lon']) ### keep left order

    ### shift lines for better plotting
    schedule_table = _shift_lines(schedule_table)

    ### convert arrival and departure time to seconds since midnight
    schedule_table = _convert_times(schedule_table)
    
    ### link to next stops
    schedule_table = schedule_table.sort_values(by=['trip_id', 'arrival_time'], ascending=True)
    schedule_table['next_route_stop_id'] = schedule_table['route_stop_id'].shift(-1)
    schedule_table['next_stop_name'] = schedule_table['stop_name'].shift(-1)
    schedule_table['next_stop_lon'] = schedule_table['stop_lon'].shift(-1)
    schedule_table['next_stop_lat'] = schedule_table['stop_lat'].shift(-1)
    schedule_table['next_trip_id'] = schedule_table['trip_id'].shift(-1)
    schedule_table['next_arrival_time'] = schedule_table['arrival_time'].shift(-1)
    schedule_table = schedule_table.loc[schedule_table['trip_id']==schedule_table['next_trip_id']].copy()
    # display(schedule_table[schedule_table['route_stop_id']=='昌平线.昌平西山口站方向-198'])

    return schedule_table

def _add_schedule(schedule_table):
    ### convert the cleaned GTFS data (schedule_table) into class attribute (train.schedule_df)
    
    schedule_list = []
    for row in schedule_table.itertuples():
        schedule_list.append((getattr(row, 'route_id'), getattr(row, 'trip_id'), getattr(row, 'capacity'),
                              getattr(row, 'arrival_time'), getattr(row, 'departure_time'), 'stop', 
                              '', getattr(row, 'route_stop_id'), '', 0))
        schedule_list.append((getattr(row, 'route_id'), getattr(row, 'trip_id'), getattr(row, 'capacity'),
                              getattr(row, 'departure_time'), getattr(row, 'next_arrival_time'), 'on_link',
                              getattr(row, 'route_stop_id'), '', getattr(row, 'next_route_stop_id'), 0))
    ### add final destination of the trip
    for row in schedule_table.groupby('trip_id').tail(1).itertuples():
        schedule_list.append((getattr(row, 'route_id'), getattr(row, 'trip_id'), getattr(row, 'capacity'),
                              getattr(row, 'next_arrival_time'), getattr(row, 'next_arrival_time')+30, 'stop', 
                              '', getattr(row, 'next_route_stop_id'), '', 1))
    schedule_df = pd.DataFrame(schedule_list, 
                               columns=['route_id', 'trip_id', 'capacity', 'time', 'next_time', 'status', 
                                        'prev_route_stop_id', 'route_stop_id', 'next_route_stop_id', 'is_final_location'])
    ### map stop names to node_ids
    # schedule_df['location_id'] = schedule_df['location'].map(station_nm_id_dict).fillna(-1)
    ### sort schedule info
    schedule_df = schedule_df.sort_values(by=['trip_id', 'time'], ascending=True)

    return schedule_df

#############################################################
############# Creating nodes and links (graph) ##############
#############################################################

def _add_network(schedule_table):
        
    ### process network
    all_links = schedule_table.drop_duplicates(subset=['route_stop_id', 'next_route_stop_id'])
    # display(all_links.head())
    all_links = all_links[['route_id', 'route_stop_id', 'next_route_stop_id', 'stop_name', 'next_stop_name',
                           'stop_lon', 'stop_lat', 'next_stop_lon', 'next_stop_lat']].copy()
    ### link weights
    link_weights = schedule_table[['route_stop_id', 'next_route_stop_id', 'departure_time', 'next_arrival_time']].copy()
    link_weights['travel_time'] = link_weights['next_arrival_time'] - link_weights['departure_time'] + 30
    link_weights = link_weights.groupby(['route_stop_id', 'next_route_stop_id']).agg({'travel_time': 'mean'}).reset_index(drop=False)
    all_links = all_links.merge(link_weights, how='left', on=['route_stop_id', 'next_route_stop_id'])
    all_links['tavg_weight'] =  all_links['travel_time']
    all_links['initial_weight'] =  all_links['travel_time']
    all_links['stops_weight'] = 1.0
    # Add route-specific stops_weight overrides here if certain segments span
    # multiple physical stops but appear as one stop in the GTFS data.
    # Example:
    # all_links.loc[
    #     (all_links['route_id'] == 'your_route_id') &
    #     (all_links['route_stop_id'] == 'your_route_id-from_stop') &
    #     (all_links['next_route_stop_id'] == 'your_route_id-to_stop'),
    #     'stops_weight'] = 3.0

    ### create nodes
    all_nodes = pd.DataFrame(np.vstack(
        [all_links[['route_stop_id', 'stop_lon', 'stop_lat']].values,
         all_links[['next_route_stop_id', 'next_stop_lon', 'next_stop_lat']].values]),
        columns=['route_stop_id', 'stop_lon', 'stop_lat'])
    all_nodes = all_nodes.drop_duplicates(subset=['route_stop_id'])
    all_nodes['route_id'] = all_nodes['route_stop_id'].apply(lambda x: x.rsplit('-', 1)[0])
    all_nodes['stop_id'] = all_nodes['route_stop_id'].apply(lambda x: x.split('-')[-1])
    all_nodes['type'] = 'platform'
    ### station nodes
    virtual_nodes = all_nodes.groupby('stop_id').agg({'stop_lon': 'mean', 'stop_lat': 'mean'}).reset_index(drop=False)
    virtual_nodes['stop_lon'] *= 0.999999
    virtual_nodes['route_id'] = 'station'
    virtual_nodes['route_stop_id'] = virtual_nodes['stop_id'].apply(lambda x: 'all-{}'.format(x))
    virtual_nodes['type'] = 'station'
    all_nodes = pd.concat([all_nodes, virtual_nodes[all_nodes.columns]])
    ### create graph node ID
    all_nodes['nid'] = np.arange(all_nodes.shape[0])
    ### give stop name based on stop id
    all_nodes['stop_name'] = all_nodes['stop_id'].map(
        dict(zip(schedule_table.stop_id.astype(str), schedule_table.stop_name)))
    all_nodes = gpd.GeoDataFrame(
        all_nodes, crs=project_crs, 
        geometry=[Point(xy) for xy in zip(all_nodes.stop_lon, all_nodes.stop_lat)])
    all_nodes = all_nodes[['route_stop_id', 'route_id', 'stop_id', 'stop_name', 'type', 'nid', 'stop_lon', 'stop_lat', 'geometry']]
    # station_nm_id_dict = {getattr(row, 'route_stop_id'): getattr(
    #     row, 'node_id') for row in all_nodes.itertuples()}
    # station_id_nm_dict = {getattr(row, 'node_id'): getattr(
    #     row, 'route_stop_id') for row in all_nodes.itertuples()}

    ### add transfer links
    transfer_links = []
    for stop_id, grp in all_nodes.groupby('stop_id'):
        for (stop1, stop2) in list(itertools.permutations(grp.to_dict('records'), 2)):
            transfer_links.append(['transfer', stop1['route_stop_id'], stop2['route_stop_id'], stop1['stop_name'], stop2['stop_name'],
                                   stop1['stop_lon'], stop1['stop_lat'], stop2['stop_lon'], stop2['stop_lat']])
    transfer_links_df = pd.DataFrame(transfer_links, columns=['route_id', 'route_stop_id', 'next_route_stop_id', 'stop_name', 'next_stop_name',
                                                             'stop_lon', 'stop_lat', 'next_stop_lon', 'next_stop_lat'])
    transfer_links_df['travel_time'] = 300 ### not used for simulation, only used for route planning
    transfer_links_df['tavg_weight'] = 300
    transfer_links_df['initial_weight'] = transfer_links_df['travel_time']
    transfer_links_df['stops_weight'] = 0.1
    all_links = pd.concat([all_links, transfer_links_df])

    ### map stop names to node_ids
    # all_links['start_nid'] = all_links['route_stop_id'].map(station_nm_id_dict)
    # all_links['end_nid'] = all_links['next_route_stop_id'].map(station_nm_id_dict)
    # all_links['initial_weight'] = all_links['travel_time']
    all_links['geometry'] = all_links.apply(
        lambda x: 'LINESTRING({} {}, {} {})'.format(
            x['stop_lon'], x['stop_lat'], x['next_stop_lon'], x['next_stop_lat']
        ), axis=1)
    all_links = all_links[['route_id', 'route_stop_id', 'next_route_stop_id', 'stop_name', 'next_stop_name',
                           'initial_weight', 'tavg_weight', 'stops_weight', 'geometry']]
    all_links = gpd.GeoDataFrame(all_links, crs=project_crs, geometry=all_links['geometry'].map(loads))
    return all_nodes, all_links

#############################################################
############## Schedule and network from GTFS ###############
#############################################################

def schedule_and_network_from_gtfs(stop_times_file, trips_file, stops_file, service_id, train_capacity=1460):
        
    ### read GTFS files
    stop_times_table = _read_gtfs_files(stop_times_file)
    trips_table = _read_gtfs_files(trips_file)
    stops_table = _read_gtfs_files(stops_file)

    print(trips_table.shape)
    trips_table = _add_capacity(trips_table, train_capacity)
    print(trips_table.shape)
    display(trips_table.head())
    
    ### preprocessing check:
    ### no missing or duplicated stop_name in stops_file (each will become a station)
    
    ### filter trips_table by service_id
    trips_table = _filter_trips_table_by_service_id(trips_table, service_id)

    ### convert trip_id and stop_id in the GTFS files to integers (if needed)
    trips_table, stops_table, stop_times_table = _gtfs_id_to_integers(
        trips_table=trips_table, stops_table=stops_table, stop_times_table=stop_times_table)
    
    ### GTFS table to schedule table
    schedule_table = _gtfs_tables_to_schedule(
        trips_table=trips_table, stops_table=stops_table, stop_times_table=stop_times_table)
    
    ### create schedule and network
    all_nodes, all_links = _add_network(schedule_table)
    all_schedules = _add_schedule(schedule_table)
    
    return all_nodes, all_links, all_schedules
