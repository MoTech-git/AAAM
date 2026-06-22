import numpy as np
import pandas as pd
from .routing import batch_routing
import time

class Travelers():
    def __init__(self, all_travelers):
        self.all_travelers = all_travelers
        self.all_travelers['route_id'] = None
        self.all_travelers['next_route_id'] = None
        ### boarding, alignthing, transfering key nodes
        self.all_key_nids = pd.DataFrame([], 
            columns=['traveler_id', 'r_id', 'r_seq', 'key_nid', 'next_key_nid', 'status']) 
        
    def random_od(self, all_nodes=None, num_travelers=1, start_time=3600*6, end_time=3600*7):
        
        od_nodes = all_nodes['route_stop_id'].str.split('-').str[0]=='all'
        traveler_origins = np.random.choice(all_nodes.loc[od_nodes, 'node_id'], num_travelers)
        traveler_destins = np.random.choice(all_nodes.loc[od_nodes, 'node_id'], num_travelers)
        #traveler_origins = [241]
        #traveler_destins = [267]
        self.all_travelers = pd.DataFrame({
            'origin_nid': traveler_origins, 'destin_nid': traveler_destins})
        self.all_travelers = self.all_travelers[self.all_travelers['origin_nid'] != self.all_travelers['destin_nid']].copy()
        self.all_travelers['traveler_id'] = np.arange(self.all_travelers.shape[0])
        self.all_travelers['departure_time'] = np.random.randint(start_time, end_time, self.all_travelers.shape[0])
        #self.all_travelers['departure_time'] = 26664-120
    
    def set_initial_status(self):
        
        ### initialize all_travelers
        self.all_travelers['traveler_status'] = 0 ### {0: 'pretrip', 1: 'walking', 2: 'platform', 3: 'train', 4: 'arrival', 5: 'temporary waiting at platform'}
        self.all_travelers['update_time'] = 0
        self.all_travelers['association'] = -11
        # self.all_travelers['key_nid'] = self.all_travelers['origin_nid']
        # self.all_travelers['prev_key_nid'] = -111
        self.all_travelers['next_key_nid'] = -222
        self.all_travelers['init_boarding_time'] = 1e7
        self.all_travelers['final_alighting_time'] = 1e7

    def _get_next_nid(self, trains, routing_travelers):
        ### get the start nid for routing, which may not be the origin if it is dynamically updated
        
        routing_travelers['next_nid'] = None
        ### if the agent has not started yet, the next possible routing nid is the origin
        routing_travelers['next_nid'] = np.where(routing_travelers['traveler_status']==0, 
                                                 routing_travelers['origin_nid'], routing_travelers['next_nid'])
        ### if the agent is walking, the next possible routing nid is the next platform
        routing_travelers['next_nid'] = np.where(routing_travelers['traveler_status']==1, 
                                                 routing_travelers['next_key_nid'], routing_travelers['next_nid'])
        ### if the agent is waiting, the next possible routing nid is the current platform
        routing_travelers['next_nid'] = np.where(routing_travelers['traveler_status']==2, 
                                                 routing_travelers['association'], routing_travelers['next_nid'])
        ## if the agent is on board, the next possible routing nid is the next train stop
        routing_travelers.loc[routing_travelers['traveler_status']==3, 'next_nid'] = routing_travelers.loc[
            routing_travelers['traveler_status']==3, 'association'].map(trains.trip_nid_dict)
        ### if the agent has arrived, the next possible routing nid is the destination
        routing_travelers['next_nid'] = np.where(routing_travelers['traveler_status']==4, 
                                                 routing_travelers['destin_nid'], routing_travelers['next_nid'])
        routing_travelers['next_nid'] = np.where(routing_travelers['traveler_status']==5, 
                                                 routing_travelers['association'], routing_travelers['next_nid'])
        
        return routing_travelers

    def _truncate_key_nids(self, routing_travelers):
        ### remove unused previous key_nid after routing
        self.all_key_nids = self.all_key_nids.loc[
            ~((self.all_key_nids['status']==-1) &
            (self.all_key_nids['traveler_id'].isin(routing_travelers['traveler_id']))), 
                ['traveler_id', 'r_id', 'r_seq', 'key_nid', 'next_key_nid', 'status']].copy()

        
    def find_routes(self, network, g, trains, routing_traveler_ids, routing_round_id):
        ### routing and abbreviating to key stops
        # display(self.all_key_nids.loc[self.all_key_nids['traveler_id'].isin([665, 678])])
        
        ### only agents not reaching destination will be routed
        routing_travelers = self.all_travelers.loc[
            (self.all_travelers['traveler_id'].isin(routing_traveler_ids)) &
            (self.all_travelers['traveler_status'].isin([0, 1, 2, 3, 5])) &
            (self.all_travelers['next_key_nid'] != self.all_travelers['destin_nid'])].copy()
        routing_travelers = self._get_next_nid(trains, routing_travelers)
        # print('next_nid')
        # display(routing_travelers.loc[routing_travelers['traveler_id'].isin([4])])
        # print('\n')
        routing_travelers_key_nids, unfulfilled_trips = batch_routing(network, g, routing_travelers)
        routing_travelers_key_nids['r_id'] = routing_round_id
        # print('routing')
        # display(routing_travelers_key_nids.loc[routing_travelers_key_nids['traveler_id'].isin([4])])
        
        self._truncate_key_nids(routing_travelers)
        # print('\n\n')
        ### exclude empty df from concat
        frames = [df for df in [self.all_key_nids, routing_travelers_key_nids]
                  if not df.empty and not df.isna().all().all()]
        if len(frames)==0:
            return unfulfilled_trips

        self.all_key_nids = pd.concat(frames)
        self.all_key_nids = self.all_key_nids.sort_values(by=['traveler_id', 'r_id', 'r_seq'])
        self.all_key_nids['route_id'] = self.all_key_nids['key_nid'].map(network.node_id_route_dict)
        self.all_key_nids['prev_route_id'] = self.all_key_nids.groupby(['traveler_id'])['route_id'].shift(1)
        self.all_key_nids['next_route_id'] = self.all_key_nids.groupby(['traveler_id'])['route_id'].shift(-1)
        ### if three key_nids have the same route_id, then the middle one is not necessary
        self.all_key_nids = self.all_key_nids.loc[
            ~((self.all_key_nids['prev_route_id']==self.all_key_nids['next_route_id']) &
            (self.all_key_nids['prev_route_id']==self.all_key_nids['route_id']))
        ].copy()
        self.all_key_nids['next_key_nid'] = self.all_key_nids.groupby(['traveler_id'])['key_nid'].shift(-1)
        ### reset index, as otherwise there will be duplicated index, making wrong results when updating the status change time
        self.all_key_nids = self.all_key_nids.reset_index(drop=True) 
        ### update next_key_nids, which might change after routing
        move_tid = routing_travelers['traveler_id'].values
        move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
            (self.all_key_nids['status']==-1)].sort_values(
            ['r_id', 'r_seq']).drop_duplicates('traveler_id', keep='first')
        move_df['to_map'] = np.where(move_df['traveler_id'].isin(
            routing_travelers.loc[routing_travelers['traveler_status'].isin([1, 3]), 'traveler_id']), move_df['key_nid'], move_df['next_key_nid'])
        move_dict = dict(zip(move_df['traveler_id'], move_df['to_map']))
        self.all_travelers.loc[self.all_travelers['traveler_id'].isin(move_tid), 'next_key_nid'] = self.all_travelers.loc[
            self.all_travelers['traveler_id'].isin(move_tid), 'traveler_id'].map(move_dict)
        # print('update')
        # display(self.all_key_nids.loc[self.all_key_nids['traveler_id'].isin([4])])

        return unfulfilled_trips
    
        
    def _depart(self, t, time_step_size):

        ### load departure travelers
        ### (1) change status from "pretrip" to "walking"
        ### (2) change association from "None" to "origin_nid"
        ### (3) change next_stop from "None" to next key stop
        departure_travelers = (
            self.all_travelers['departure_time']<=t) & (
            self.all_travelers['departure_time']>t-time_step_size) & (
            self.all_travelers['traveler_status']==0)
        self.all_travelers.loc[departure_travelers, 'traveler_status'] = 1
        self.all_travelers.loc[departure_travelers, 'update_time'] = t
        self.all_travelers.loc[departure_travelers, 'association'] = self.all_travelers.loc[
            departure_travelers, 'origin_nid'].values
        move_tid = set(self.all_travelers.loc[departure_travelers, 'traveler_id'].values)
        # move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
        #     (self.all_key_nids['status']==-1)].sort_values(
        #     ['r_id', 'r_seq']).drop_duplicates('traveler_id', keep='first')
        move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
            (self.all_key_nids['status']==-1)].groupby('traveler_id').head(1)
        move_dict = dict(zip(move_df['traveler_id'], move_df['next_key_nid']))
        self.all_travelers.loc[departure_travelers, 'next_key_nid'] = self.all_travelers.loc[
            departure_travelers, 'traveler_id'].map(move_dict)
        self.all_key_nids.loc[move_df.index, 'status'] = t
        status_change = self.all_travelers.loc[departure_travelers, 
                                             ['traveler_id', 'traveler_status', 'update_time', 'association']]
        return status_change

    def _walk_or_transfer(self, t, transfer_time):

        ### transfer
        ### conditions: status is "walking" and transfer time is 2 minutes
        walking_travelers = (
            self.all_travelers['traveler_status']==1) & (
            self.all_travelers['next_key_nid'] != self.all_travelers['destin_nid']) & (
            self.all_travelers['update_time']<=t-transfer_time) 
        self.all_travelers.loc[walking_travelers, 'traveler_status'] = 2
        self.all_travelers.loc[walking_travelers, 'update_time'] = t
        self.all_travelers.loc[walking_travelers, 'association'] = self.all_travelers.loc[walking_travelers, 'next_key_nid']
        move_tid = set(self.all_travelers.loc[walking_travelers, 'traveler_id'].values)
        # move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
        #     (self.all_key_nids['status']==-1)].sort_values(
        #     ['r_id', 'r_seq']).drop_duplicates('traveler_id', keep='first')
        move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
            (self.all_key_nids['status']==-1)].groupby('traveler_id').head(1)
        move_dict = dict(zip(move_df['traveler_id'], move_df['next_key_nid']))
        self.all_travelers.loc[walking_travelers, 'next_key_nid'] = self.all_travelers.loc[
            walking_travelers, 'traveler_id'].map(move_dict)
        status_change = self.all_travelers.loc[walking_travelers, 
                                             ['traveler_id', 'traveler_status', 'update_time', 'association']]
        return status_change
    
    def _arrive(self, t, exit_walking_time):
        
        ### arrival
        arrival_travelers = (
            self.all_travelers['traveler_status']==1) & (
            self.all_travelers['next_key_nid'] == self.all_travelers['destin_nid']) & (
            self.all_travelers['update_time']<=t-exit_walking_time) 
        self.all_travelers.loc[arrival_travelers, 'traveler_status'] = 4
        self.all_travelers.loc[arrival_travelers, 'update_time'] = t #+ exit_walking_time-transfer_time
        self.all_travelers.loc[arrival_travelers, 'final_alighting_time'] = t
        #self.all_travelers.loc[arrival_travelers, 'association'] = None
        self.all_travelers.loc[arrival_travelers, 'next_key_nid'] = -111
        status_change = self.all_travelers.loc[arrival_travelers, 
                                             ['traveler_id', 'traveler_status', 'update_time', 'association']]
        return status_change

    def _turn_around(self, t):
        ### only used during rerouting cases, where waiting agents decide to turn to a different platform
        ### condition 1: status is "platform"
        turn_travelers = self.all_travelers['traveler_status'].isin([2, 5])
        ### condition 2: next_route_id is not along the same route as currently
        turn_travelers = turn_travelers & (self.all_travelers['route_id'] != self.all_travelers['next_route_id'])
        self.all_travelers.loc[turn_travelers, 'traveler_status'] = 1
        self.all_travelers.loc[turn_travelers, 'update_time'] = t
        ### association does not need to be changed
        move_tid = set(self.all_travelers.loc[turn_travelers, 'traveler_id'].values)
        # move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
        #     (self.all_key_nids['status']==-1)].sort_values(
        #     ['r_id', 'r_seq']).drop_duplicates('traveler_id', keep='first')
        move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
            (self.all_key_nids['status']==-1)].groupby('traveler_id').head(1)
        move_dict = dict(zip(move_df['traveler_id'], move_df['next_key_nid']))
        self.all_travelers.loc[turn_travelers, 'next_key_nid'] = self.all_travelers.loc[
            turn_travelers, 'traveler_id'].map(move_dict)
        self.all_key_nids.loc[move_df.index, 'status'] = t
        status_change = self.all_travelers.loc[turn_travelers, 
                                             ['traveler_id', 'traveler_status', 'update_time', 'association']]
        
    
    def _aboard(self, t, trains):
        
        ### aboard: travelers ready to aboard
        ### check if next stop is covered
        ### condition 1: status is "platform"
        board_travelers = self.all_travelers['traveler_status'].isin([2, 5])
        # print('condition 1', board_travelers)
        ### condition 2: a train at the platform
        self.all_travelers['aboard_tmp'] = False
        self.all_travelers.loc[board_travelers, 'aboard_tmp'] = self.all_travelers.loc[
            board_travelers, 'association'].isin(trains.nid_trip_stop_dict.keys())
        board_travelers = board_travelers.values & self.all_travelers['aboard_tmp'].values
        # print('condition 2', board_travelers)
        ### condition 3: a train is not terminating at the stop (for shorter trains)
        ### namely the passengers' association (the nid of a platform) cannot be the final stops platform at this time
        self.all_travelers['final_stop_tmp'] = False
        self.all_travelers.loc[board_travelers, 'final_stop_tmp'] = self.all_travelers.loc[
            board_travelers, 'association'].isin(trains.trip_nid_final_stop_dict.values())
        board_travelers = board_travelers & (~self.all_travelers['final_stop_tmp'].values)
        # print('condition 3', board_travelers)
        ### condition 4: within capacity 
        self.all_travelers['remain_cap'] = 0
        self.all_travelers.loc[board_travelers, 'remain_cap'] = self.all_travelers.loc[
            board_travelers, 'association'].map(trains.stop_train_capacities_dict).fillna(-10)
        self.all_travelers['order'] = 1e7
        self.all_travelers.loc[self.all_travelers['remain_cap']>0, 'order'] = self.all_travelers.loc[
            self.all_travelers['remain_cap']>0].sort_values(
            by='update_time', ascending=True).groupby('association').cumcount()
        board_travelers = board_travelers & (self.all_travelers['order'] < self.all_travelers['remain_cap']).values
        # print('aboard')
        # display(self.all_travelers[self.all_travelers['traveler_id']==31] )
        # print('condition 4', board_travelers)
        ### denied boarding
        denied_boarding = np.sum(board_travelers & (self.all_travelers['order'] > self.all_travelers['remain_cap']).values)
        ### waiting time: all transfer links pointing to this platform nid will need to be updated
        waiting_time = self.all_travelers.loc[board_travelers, ['association', 'update_time']].copy()
        waiting_time['prev_update_time'] = waiting_time['update_time']
        waiting_time['update_time'] = t
        waiting_time['waiting_time'] = waiting_time['update_time'] - waiting_time['prev_update_time']
        # self.all_travelers.loc[board_travelers, 'prev_key_nid'] = self.all_travelers.loc[board_travelers, 'association']
        ### (1) change next stop according to key routes
        ### aboard after temporary alight short train: if agent get off a short trip, and board in the middle of the journey, the temporary waiting and boarding platform will not be shown in travelers_key_stops. As a result, the next_station_id for these travelers need to keep to the previous one.
        self.all_travelers['original_next_key_nid'] = self.all_travelers['next_key_nid'] 
        ### only update those that are not temporarily alight
        move_tid = set(self.all_travelers.loc[(board_travelers) & (self.all_travelers['traveler_status']==2), 'traveler_id'].values)
        # move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
        #     (self.all_key_nids['status']==-1)].sort_values(
        #     ['r_id', 'r_seq']).drop_duplicates('traveler_id', keep='first')
        move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
            (self.all_key_nids['status']==-1)].groupby('traveler_id').head(1)
        self.all_key_nids.loc[move_df.index, 'status'] = t
        ### (2) change association from platform to trip_id
        self.all_travelers.loc[board_travelers, 'association'] = self.all_travelers.loc[board_travelers, 
                                                                     'association'].replace(trains.nid_trip_stop_dict)
        ### (3) change status from "platform" to "train"
        self.all_travelers.loc[board_travelers, 'traveler_status'] = 3
        self.all_travelers.loc[board_travelers, 'update_time'] = t
        self.all_travelers.loc[board_travelers, 'init_boarding_time'] = np.minimum(t, self.all_travelers.loc[board_travelers, 'init_boarding_time'])
        status_change = self.all_travelers.loc[board_travelers, 
                                             ['traveler_id', 'traveler_status', 'update_time', 'association']]
        return status_change, denied_boarding, waiting_time

    def _alight(self, t, trains):
        
        ### alight: travelers ready to get off the train
        ### conditions: (1) status is "train"
        alight_travelers = self.all_travelers['traveler_status'] == 3
        ### conditions: (2) train location is alighting location
        self.all_travelers['train_location_id'] = -1
        self.all_travelers.loc[alight_travelers, 'train_location_id'] = self.all_travelers.loc[
            alight_travelers, 'association'].replace(trains.trip_nid_stop_dict)
        ### combine all conditions
        alight_travelers = alight_travelers.values & (
            self.all_travelers['train_location_id']==self.all_travelers['next_key_nid']).values 
        # print('alight')
        # display(self.all_travelers[self.all_travelers['traveler_id']==31] )
        ### (1) change association from trip_id to platform
        self.all_travelers.loc[alight_travelers, 'association'] = self.all_travelers.loc[alight_travelers, 'next_key_nid'] 
        ### (2) change status from "train" to "walking"
        self.all_travelers.loc[alight_travelers, 'traveler_status'] = 1
        self.all_travelers.loc[alight_travelers, 'update_time'] = t
        ### (3) change next stop according to key routes
        move_tid = set(self.all_travelers.loc[alight_travelers, 'traveler_id'].values)
        # move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
        #     (self.all_key_nids['status']==-1)].sort_values(
        #     ['r_id', 'r_seq']).drop_duplicates('traveler_id', keep='first')
        move_df = self.all_key_nids.loc[(self.all_key_nids['traveler_id'].isin(move_tid)) &
            (self.all_key_nids['status']==-1)].groupby('traveler_id').head(1)
        move_dict = dict(zip(move_df['traveler_id'], move_df['next_key_nid']))
        self.all_travelers.loc[alight_travelers, 'next_key_nid'] = self.all_travelers.loc[
            alight_travelers, 'traveler_id'].map(move_dict)
        self.all_key_nids.loc[move_df.index, 'status'] = t
        status_change = self.all_travelers.loc[alight_travelers, 
                                             ['traveler_id', 'traveler_status', 'update_time', 'association']]
        return status_change

    def _temporary_alight(self, t, trains):
        
        ### temporary alight: travelers get of a shorter train
        ### conditions: (1) status is "train"
        temp_alight_travelers = self.all_travelers['traveler_status'] == 3
        ### conditions: (2) train is at the last stop of the trip, for shorter trips
        self.all_travelers['at_final_location'] = False
        self.all_travelers.loc[temp_alight_travelers, 'at_final_location'] = self.all_travelers.loc[
            temp_alight_travelers, 'association'].isin(trains.trip_nid_final_stop_dict.keys())
        ### combine all conditions
        temp_alight_travelers = temp_alight_travelers.values & self.all_travelers['at_final_location'].values
        ### (1) change association from trip_id to platform
        self.all_travelers.loc[temp_alight_travelers, 'association'] = self.all_travelers.loc[temp_alight_travelers, 'association'].replace(trains.trip_nid_stop_dict)
        ### (2) change status from "train" to "platform"
        self.all_travelers.loc[temp_alight_travelers, 'traveler_status'] = 5
        self.all_travelers.loc[temp_alight_travelers, 'update_time'] = t
        ### (3) change next stop according to key routes
        ### no need to change
        # if 31 in self.all_travelers.loc[temp_alight_travelers, 'traveler_id'].values:
        #     print('temporary alight')
        #     display(self.all_travelers[self.all_travelers['traveler_id']==31] )
        status_change = self.all_travelers.loc[temp_alight_travelers, 
                                             ['traveler_id', 'traveler_status', 'update_time', 'association']]
        return status_change
    
    def traveler_update(self, network, trains, t, time_step_size=20, transfer_time=120, exit_walking_time=120):

        agent_status_change_this_step = []

        ### departure
        status_change = self._depart(t, time_step_size)
        agent_status_change_this_step.append(status_change)

        ### update route_id
        self.all_travelers['route_id'] = self.all_travelers['association'].map(network.node_id_route_dict)
        self.all_travelers['next_route_id'] = self.all_travelers['next_key_nid'].map(network.node_id_route_dict)
        
        ### transfer
        status_change = self._walk_or_transfer(t, transfer_time)
        agent_status_change_this_step.append(status_change)

        ### update route_id
        self.all_travelers['route_id'] = self.all_travelers['association'].map(network.node_id_route_dict)
        self.all_travelers['next_route_id'] = self.all_travelers['next_key_nid'].map(network.node_id_route_dict)
        
        ### arrive
        status_change = self._arrive(t, exit_walking_time)
        agent_status_change_this_step.append(status_change)

        ### update route_id
        ### no need to change
        # self.all_travelers['route_id'] = self.all_travelers['association'].map(network.node_id_route_dict)
        self.all_travelers['next_route_id'] = self.all_travelers['next_key_nid'].map(network.node_id_route_dict)

        ### turn around
        status_change = self._turn_around(t)
        agent_status_change_this_step.append(status_change)

        ### update route_id
        ### no need to change
        # self.all_travelers['route_id'] = self.all_travelers['association'].map(network.node_id_route_dict)
        self.all_travelers['next_route_id'] = self.all_travelers['next_key_nid'].map(network.node_id_route_dict)
        
        ### aborad
        status_change, denied_boarding, waiting_time = self._aboard(t, trains)
        agent_status_change_this_step.append(status_change)

        ### update route_id
        self.all_travelers['route_id'] = self.all_travelers['association'].map(network.node_id_route_dict)
        ### no need to change
        # self.all_travelers['next_route_id'] = self.all_travelers['next_key_nid'].map(network.node_id_route_dict)
        
        ### alight
        status_change = self._alight(t, trains)
        agent_status_change_this_step.append(status_change)

        ### update route_id
        self.all_travelers['route_id'] = self.all_travelers['association'].map(network.node_id_route_dict)
        self.all_travelers['next_route_id'] = self.all_travelers['next_key_nid'].map(network.node_id_route_dict)
        
        ### temporary alight
        status_change = self._temporary_alight(t, trains)
        agent_status_change_this_step.append(status_change)

        ### update route_id
        self.all_travelers['route_id'] = self.all_travelers['association'].map(network.node_id_route_dict)
        ### no need to change
        # self.all_travelers['next_route_id'] = self.all_travelers['next_key_nid'].map(network.node_id_route_dict)

        # print(t)
        # display(self.all_travelers.loc[self.all_travelers['traveler_id'].isin([81021])])
        # display(self.all_key_nids.loc[self.all_key_nids['traveler_id'].isin([81021])])
        
        return agent_status_change_this_step, denied_boarding, waiting_time
    
    def get_all_traveler_positions(self, train_positions):
        
        ### get traveler locations
        ### group by station or train location
        traveler_locations = self.all_travelers.groupby(
            ['traveler_status', 'association']).size().to_frame(
            name='num_travelers').reset_index(drop=False)
        
        travelers_on_trains = traveler_locations[traveler_locations['traveler_status']==3]
        travelers_on_trains['association'] = travelers_on_trains['association'].astype(int)
        travelers_on_trains = travelers_on_trains.merge(train_positions[['trip_id', 'cx', 'cy']], 
                                                        how='left', left_on='association', right_on='trip_id')
        return traveler_locations