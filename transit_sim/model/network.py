import sys
import numpy as np
import pandas as pd
from .routing import build_network_graph

class Network:
    def __init__(self, all_nodes, all_links):
        self.all_nodes = all_nodes
        self.all_links = all_links

        ### node name (route_stop_id) to node graph id (nid)
        self.node_nm_id_dict = {
            getattr(row, 'route_stop_id'): getattr(row, 'nid')
            for row in self.all_nodes.itertuples()
        }
        ### station name (no platform) to node graph id (nid)
        self.station_nm_nid_dict = {
            getattr(row, 'stop_name'): getattr(row, 'nid')
            for row in self.all_nodes[self.all_nodes['type']=='station'].itertuples()
        }
        ### node graph id (nid) to node name (route_stop_id)
        self.node_id_nm_dict = {
            getattr(row, 'nid'): getattr(row, 'route_stop_id')
            for row in self.all_nodes.itertuples()
        }
        ### node graph id (nid) to route name (route_id)
        self.node_id_route_dict = {
            getattr(row, 'nid'): getattr(row, 'route_id')
            for row in self.all_nodes.itertuples()
        }
        
        # self.station_locations = {
        #     getattr(row, 'route_stop_id'): getattr(row, 'geometry')
        #     for row in self.all_nodes.itertuples()
        # }
        
        ### link nid to graph start and end
        self.all_links['start_nid'] = self.all_links['route_stop_id'].map(self.node_nm_id_dict)
        self.all_links['end_nid'] = self.all_links['next_route_stop_id'].map(self.node_nm_id_dict)
        ### graph, link weight = updating travel time
        self.network_g_t = build_network_graph(
            self.all_links, start_col='start_nid', end_col='end_nid', weight_col='initial_weight')
        ### graph, link weight = num. stops
        self.network_g_stops = build_network_graph(
            self.all_links, start_col='start_nid', end_col='end_nid', weight_col='stops_weight')
        ### graph, link weight = free-flow travel time
        self.network_g_tavg = build_network_graph(
            self.all_links, start_col='start_nid', end_col='end_nid', weight_col='tavg_weight')

        # ### geometry dictionaries
        # self.node_cx = {}
        # self.node_cy = {}
        # self.link_cx = {}
        # self.link_cy = {}
        # self.link_ux = {}
        # self.link_uy = {}

        # for row in self.all_nodes.itertuples():
        #     node_nm = getattr(row, 'route_stop_id')
        #     geom = getattr(row, 'geometry')
        #     self.node_cx[node_nm] = geom.x
        #     self.node_cy[node_nm] = geom.y

        # for row in self.all_links.itertuples():
        #     link_nm = f"{getattr(row, 'route_stop_id')}--{getattr(row, 'next_route_stop_id')}"
        #     link_geom = getattr(row, 'geometry')
        #     self.link_cx[link_nm] = link_geom.interpolate(0.2, 0.3).x
        #     self.link_cy[link_nm] = link_geom.interpolate(0.2, 0.3).y
        #     self.link_ux[link_nm] = link_geom.coords[-1][0] - link_geom.coords[0][0]
        #     self.link_uy[link_nm] = link_geom.coords[-1][1] - link_geom.coords[0][1]

    def update_waiting_time(self, t, waiting_time_list):

        waiting_time_list = [w for w in waiting_time_list if w.shape[0]>0]
        if len(waiting_time_list) == 0:
            return
        
        waiting_time_df = pd.concat(waiting_time_list)
        ### columns: association -- platform nid, update_time, prev_update_time, waiting_time
        waiting_time_grp = waiting_time_df.groupby('association').agg({'waiting_time': 'mean'}).reset_index()
        if 'waiting_time' in self.all_links.columns:
            self.all_links = self.all_links.drop(columns=['association', 'waiting_time'])
        self.all_links = self.all_links.merge(waiting_time_grp, how='left', left_on='end_nid', right_on='association')
        self.all_links['waiting_weight'] = np.where(pd.isna(self.all_links['waiting_time']), 
                                                    self.all_links['initial_weight'], self.all_links['waiting_time'])
        ### graph, link weight = updating travel time
        self.network_g_t = build_network_graph(
            self.all_links, start_col='start_nid', end_col='end_nid', weight_col='waiting_weight')

