import numpy as np
import pandas as pd

class Trains:
    
    def __init__(self, all_schedules, network):
        
        self.all_schedule = all_schedules
        self.all_schedule['prev_nid'] = self.all_schedule['prev_route_stop_id'].map(network.node_nm_id_dict).fillna(-1)
        self.all_schedule['nid'] = self.all_schedule['route_stop_id'].map(network.node_nm_id_dict).fillna(-1)
        self.all_schedule['next_nid'] = self.all_schedule['next_route_stop_id'].map(network.node_nm_id_dict).fillna(-1)
        ### for dynamically rerouting travelers: get the start location of routing
        self.trip_nid_dict = dict()

    def _initialize_train_location_occupancy(self):

        self.current_schedule = None
        ### for dynamically rerouting travelers: get the start location of routing
        self.trip_nid_dict = dict()
        ### when updating traveler status, we are only interested in trains stop at platforms
        ### as it is when travelers board or alight
        self.stop_trains = None 
        ### for updating agent locations
        self.nid_trip_stop_dict = dict()
        self.trip_nid_stop_dict = dict()
        self.trip_nid_final_stop_dict = dict()
        self.stop_train_capacities_dict = dict()
        
    def _update_location(self, t):
        
        self.all_schedule['current_location'] = np.where(
            self.all_schedule['time']>t, 'future', np.where(
            self.all_schedule['next_time']>t, 'current', 'past'))
        
        ################################################
        ### used for dynamically rerouting travelers ###
        ################################################
        self.current_schedule = self.all_schedule.loc[self.all_schedule['current_location']=='current']
        trip_nid_dict1 = {getattr(s, 'trip_id'): getattr(s, 'nid') 
                          for s in self.current_schedule[self.current_schedule['status']=='stop'].itertuples()}
        trip_nid_dict2 = {getattr(s, 'trip_id'): getattr(s, 'next_nid') 
                          for s in self.current_schedule[self.current_schedule['status']=='on_link'].itertuples()}
        self.trip_nid_dict = trip_nid_dict1 | trip_nid_dict2

        #################################################
        ### used for boarding and alighting travelers ###
        #################################################
        ### we are only interested in trains stop at platforms, as it is when travelers board or alight
        self.stop_trains = self.current_schedule.loc[self.current_schedule['status']=='stop'].copy()
        for train in self.stop_trains.itertuples():
            
            ### lookup dictionary 1: from platform_id to trip_id
            self.nid_trip_stop_dict[getattr(train, 'nid')] = getattr(train, 'trip_id')
            ### lookup dictionary 2: from trip_id to platform_id
            self.trip_nid_stop_dict[getattr(train, 'trip_id')] = getattr(train, 'nid') 
            ### lookup dictionary 3: from trip_id to final stop location of the trip
            if getattr(train, 'is_final_location') == 1:
                self.trip_nid_final_stop_dict[getattr(train, 'trip_id')] = getattr(train, 'nid') 

    def _update_occupancy(self, travelers_onboard):

        ### lookup dictionary: platform to stopped train total capacity
        train_occupancy_df = travelers_onboard.groupby('association').size().to_frame('train_occupancy')
        if train_occupancy_df.shape[0] == 0: 
            self.stop_trains['train_occupancy'] = 0
        else:
            self.stop_trains = self.stop_trains.merge(train_occupancy_df, left_on='trip_id', right_index=True, how='left')
            self.stop_trains['train_occupancy'] = self.stop_trains['train_occupancy'].fillna(0)
        self.stop_train_capacities_dict = {getattr(train, 'nid'): 
                                     (getattr(train, 'capacity')-getattr(train, 'train_occupancy')) 
                                      for train in self.stop_trains.itertuples()}
        
    def update_location_occupancy(self, t, all_travelers):
        self._initialize_train_location_occupancy()
        self._update_location(t)
        travelers_onboard = all_travelers[all_travelers['traveler_status']==3]
        self._update_occupancy(travelers_onboard)

    def get_all_train_positions(self, network):
        ### get train position
        train_positions = self.all_schedule.loc[self.all_schedule['current_location']=='current', 
                                           ['trip_id', 'status', 'prev_route_stop_id', 'route_stop_id', 'next_route_stop_id']].copy()
        # train_positions['cx'] = np.where(train_positions['status']=='stop',
        #                                   train_positions['location'].map(network.station_cx),
        #                                   train_positions['location'].map(network.link_cx))
        # train_positions['cy'] = np.where(train_positions['status']=='stop',
        #                                   train_positions['location'].map(network.station_cy),
        #                                   train_positions['location'].map(network.link_cy))
        # train_positions['ux'] = np.where(train_positions['status']=='stop',
        #                                   0, train_positions['location'].map(network.link_ux))
        # train_positions['uy'] = np.where(train_positions['status']=='stop',
        #                                   0, train_positions['location'].map(network.link_uy))
        # train_positions['next_routing_stop'] = np.where(train_positions['status']=='stop',
        #                                                 train_positions['location'], 
        #                                                 train_positions['location'].str.split('--').str[-1])
        # train_positions['next_routing_stop_nid'] = train_positions['next_routing_stop'].map(network.station_nm_id_dict)
        return train_positions