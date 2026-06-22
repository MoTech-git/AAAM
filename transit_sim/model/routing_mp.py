import itertools
import pandas as pd
from multiprocessing import Pool, cpu_count
import sys
sys.path.insert(0, '..') ### sp is in a parallel folder as transit_sim
from sp import interface

#############################################################
############## Build network graph with weight ##############
#############################################################

def build_network_graph(links_df, start_col='start_nid', end_col='end_nid', weight_col='initial_weight'):
    return interface.from_dataframe(links_df, start_col, end_col, weight_col)

#############################################################
#################### Single OD functions ####################
#############################################################

# Define global graph variable
global_g = None

def init_worker(g_obj):
    global global_g
    global_g = g_obj

def _run_dijkstra(g, start_nid, end_nid):

    ### find paths using Dijkstra's algorithm
    sp = g.dijkstra(start_nid, end_nid)
    sp_dist = sp.distance(end_nid)

    if sp_dist > 1e8:
        ### no path found
        sp_path = []
        sp.clear()
    else:
        ### return sp_path as [(l0s, l0e), (l10, l1e), ...]
        sp_path = list(sp.route(end_nid))
        sp.clear()
    
    return sp_dist, sp_path

def _run_dijkstra_wrapper(args):
    start_nid, end_nid = args
    global global_g
    sp_dist, sp_path = _run_dijkstra(global_g, start_nid, end_nid)
    return (start_nid, end_nid, sp_dist, sp_path)

def _get_key_stops(sp_path, network):
    key_stops = []
    for (start_nid, end_nid) in sp_path:
        if network.node_id_route_dict[start_nid] != network.node_id_route_dict[end_nid]:
            key_stops += [start_nid, end_nid]
    if (len(key_stops)>0) and (key_stops[0] != sp_path[0][0]):
        key_stops = [sp_path[0][0]] + key_stops
    return key_stops

#############################################################
################## Batch routing functions ##################
#############################################################

# def batch_routing(network, g, routing_travelers):
    
#     key_stops_list = []
#     unfulfilled_trips = 0
#     for (start_nid, end_nid), travelers in routing_travelers.groupby(['next_nid', 'destin_nid']):
        
#         start_nid = int(start_nid)
#         end_nid = int(end_nid)
#         sp_dist, sp_path = _run_dijkstra(g, start_nid, end_nid)
#         ### unfulfilled trips
#         if sp_dist > 1e8:
#             unfulfilled_trips += travelers.shape[0]
#             continue
#         ### convert to key stops list: only when agents change lines
#         key_stops = _get_key_stops(sp_path, network)
#         key_stops_list += list(itertools.product(travelers['traveler_id'], key_stops))
    
#     routing_travelers_key_nids = pd.DataFrame(key_stops_list, columns=['traveler_id', 'key_nid'])
#     routing_travelers_key_nids['r_seq'] = routing_travelers_key_nids.groupby(['traveler_id']).cumcount()
#     routing_travelers_key_nids['next_key_nid'] = routing_travelers_key_nids.groupby(['traveler_id'])['key_nid'].shift(-1)
#     routing_travelers_key_nids['status'] = 'future'
#     return routing_travelers_key_nids, unfulfilled_trips

def batch_routing(network, g, routing_travelers):
    
    # Prepare input for Dijkstra part only
    grouped = list(routing_travelers.groupby(['next_nid', 'destin_nid']))
    dijkstra_args = [(int(start_nid), int(end_nid)) for (start_nid, end_nid), _ in grouped]

    key_stops_list = []
    unfulfilled_trips = 0
    traveler_lookup = {(int(start), int(end)): df for (start, end), df in grouped}

    with Pool(cpu_count(), initializer=init_worker, initargs=(g,)) as pool:
        for start_nid, end_nid, sp_dist, sp_path in pool.imap_unordered(_run_dijkstra_wrapper, dijkstra_args):
            travelers = traveler_lookup[(start_nid, end_nid)]
            if sp_dist > 1e8:
                unfulfilled_trips += len(travelers)
                continue
            key_stops = _get_key_stops(sp_path, network)
            key_stops_list += list(itertools.product(travelers['traveler_id'], key_stops))

    routing_travelers_key_nids = pd.DataFrame(key_stops_list, columns=['traveler_id', 'key_nid'])
    routing_travelers_key_nids['r_seq'] = routing_travelers_key_nids.groupby('traveler_id').cumcount()
    routing_travelers_key_nids['next_key_nid'] = routing_travelers_key_nids.groupby('traveler_id')['key_nid'].shift(-1)
    routing_travelers_key_nids['status'] = 'future'

    return routing_travelers_key_nids, unfulfilled_trips