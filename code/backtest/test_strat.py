import sys
import os
from itertools import izip
sys.path.append('/home/egrois/git/code/pybt')
sys.path.append('/home/egrois/git/code/preprocess')
sys.path.append('/home/egrois/git/code/analysis')
sys.path.append('/home/egrois/git/code/backtest')
import pybt

import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime,time, timedelta
import pandas as pd
import utils
reload(utils)
import matplotlib.finance

import csv
import math
import copy

import mkdt_utils
import tech_anal

import simulator4



"""Event-specific parameter setting"""
event_name = "ADP"
instrument_root = '6E'
event_start_time = '08:15:00'
event_time_offset_s = 0  # for example, for Payrolls can be =1.0

event_dates = ['2013-04-03', '2013-05-01', '2013-06-05', '2013-07-03', '2013-07-31', '2013-09-05', '2013-10-02', '2013-10-30', '2013-12-04', '2014-01-08', '2014-02-05', '2014-03-05', '2014-04-02', '2014-04-30', '2014-06-04', '2014-07-02', '2014-07-30', '2014-09-04', '2014-10-01', '2014-11-05', '2014-12-03', '2015-01-07', '2015-02-04', '2015-03-04', '2015-04-01', '2015-05-06', '2015-06-03', '2015-07-01', '2015-08-05', '2015-09-02']
#event_dates = ['2013-05-01']
#event_dates = ['2013-10-02']
#event_dates = ['2014-01-08']
#event_dates = ['2014-04-02']
#event_dates = ['2013-09-05']
#event_dates = ['2014-12-03']
#event_dates = ['2013-10-30', '2015-02-04', '2015-03-04']


event_durations = {'2013-04-03': 'medium', '2013-05-01': 'medium', '2013-06-05': 'short', '2013-07-03': 'short', '2013-07-31': 'short', '2013-09-05': 'short', '2013-10-02': 'long', '2013-10-30': 'short', '2013-12-04': 'short', '2014-01-08': 'long', '2014-02-05': 'medium', '2014-03-05': 'medium', '2014-04-02': 'long', '2014-04-30': 'short', '2014-06-04': 'short', '2014-07-02': 'long', '2014-07-30': 'short', '2014-09-04': 'short', '2014-10-01': 'medium', '2014-11-05': 'medium', '2014-12-03': 'short', '2015-01-07': 'short', '2015-02-04': 'medium', '2015-03-04': 'medium', '2015-04-01': 'medium', '2015-05-06': 'short', '2015-06-03': 'short', '2015-07-01': 'medium', '2015-08-05': 'medium', '2015-09-02': 'short'}

"""Parameter settings for valuing an entry/trade.  These are specific to ADP and 6E (for now)."""
min_price_increment = 1  # need to have a lookup structure for these
dollar_value_per_price_level = 12.5  #6.25
max_size_on_level = 10
max_levels_to_cross = 5
book_depth = 5
trading_start_time = "08:14:00"
#trading_stop_time = "10:07:00"
trading_stop_time = "08:27:30"

#trading_stop_time_short = "08:29:45"
#trading_stop_time_medium = "09:29:50"
#trading_stop_time_long = "10:29:50"
trading_stop_times = {'short': '08:29:35', 'medium': '09:30:00', 'long': '09:30:00'} 
pre_trading_stop_secs = 10


opposite_stacker_off_time = "08:15:30"
#opposite_stacker_off_time = "15:55:00"

entry_stop_time = "08:15:30"

small_abs_pos = 10

bid_form = "quadratic"
bid_param1 = 0.005
bid_param2 = 3.0
bid_depth = 100 #100
bid_skip = 0
bid_edge = 5

ask_form = "quadratic"
ask_param1 = 0.005
ask_param2 = 3.0
ask_depth = 100 #100
ask_skip = 0
ask_edge = 5



class Stacker:
    def __init__(self):
	self.ask_stacker_orders = []
	self.bid_stacker_orders = []




class Strategy:

    _pos = 0
    _cash = 0
    _vol = 0
    _ltp = 0
    _pnl = 0

    potential_pnl = 0
    best_potential_pnl = 0
    #max_pos_pos = 0
    #max_neg_pos = 0

    
    def __init__(self, df, event_dt, start_dt, stop_dt, opposite_stacker_off_dt, entry_stop_time_dt, Sim, dollar_value_per_price_level):
	self.df = df
	self.mySim = Sim
        self.dollar_value_per_price_level = dollar_value_per_price_level

	self.myStacker = Stacker

	self.event_dt = event_dt
	self.start_dt = start_dt
        self.start_loc = df.index.get_loc(start_dt)
	self.stop_dt = stop_dt
        self.stop_loc = df.index.get_loc(stop_dt)
	self.opposite_stacker_off_dt = opposite_stacker_off_dt
	self.opposite_stacker_off_loc = df.index.get_loc(opposite_stacker_off_dt)
	self.entry_stop_time_dt = entry_stop_time_dt
	self.entry_stop_time_loc = df.index.get_loc(entry_stop_time_dt)
	self.trade_termination_dt = self.stop_dt - timedelta(seconds=pre_trading_stop_secs)
	self.trade_termination_loc = df.index.get_loc(self.trade_termination_dt)

	self.pre_event_price = 0
	self.max_up_disl_ticks = 0
	self.max_down_disl_ticks = 0

	self.max_pos_pos = 0
	self.max_neg_pos = 0
	self.max_abs_pos = 0

	self.out_orders = []
	self.last_order_id = 0

	self.my_live_orders = []  # always comes from Simulator
	self.my_exit_orders = []  # kept internal to the Strategy


    def round_to_nearest_price(self, raw_price):
	return round(raw_price / min_price_increment) * min_price_increment 


    def start(self):
        self.cur_loc  = self.mySim.start_sim(self.start_dt)
	
	self.cur_loc, fills = self.initOrderStack()

	self.pre_event_price = self.round_to_nearest_price(self.df.ix[self.cur_loc, 'microprice'])

	while (self.cur_loc < self.stop_loc):
	    self.out_orders = []
	    #print self.df.ix[self.cur_loc, 'time'], "mid market:", str((self.df.ix[self.cur_loc, 'top_bid_price'] + self.df.ix[self.cur_loc, 'top_ask_price']) / 2.0)
#TEMP OFF	    print self.df.ix[self.cur_loc, 'time'], "ask:", self.df.ix[self.cur_loc, 'top_ask_price'], "bid:", self.df.ix[self.cur_loc, 'top_bid_price']
	    self.cur_loc, fills = self.onTick()
            self.update(self.cur_loc, fills)
	
	    #print "fills:", fill

	    if fills:
                print "        pos: ", self._pos
                print "        PnL: ", self._pnl
		print
	return 1


    def update(self, mkt_data_loc, fills):
        self.process_fills(fills)
        self._pnl = self.computePnL()
	self.computeEstimatePnL()


    def on_fill(self, size, price):
        if size != 0:
            self._pos += size
            self._cash -= (size * price * self.dollar_value_per_price_level)
            self._vol += abs(size)
            self._ltp = price

  	    if self.best_potential_pnl == 0 and self._pnl < 0:
		self.best_potential_pnl = self._pnl
	    elif self._pnl > self.best_potential_pnl:
		self.best_potential_pnl = self._pnl

	    #print self.df.ix[self.cur_loc, 'time'], self._pos, self.max_pos_pos, self.max_neg_pos, self._pnl, self.best_potential_pnl

	    if self._pos > 0:
		if self._pos > self.max_pos_pos:
		    self.max_pos_pos = self._pos
	    elif self._pos < 0:
		if abs(self._pos) > self.max_neg_pos:
		    self.max_neg_pos = abs(self._pos)
	    self.max_abs_pos = max(self.max_pos_pos, self.max_neg_pos)


    def process_fills(self, fills):
        for fill in fills:
	    #print fill
	    for partial_fill in fill['partial_fills']:
		self.on_fill(partial_fill['size'], partial_fill['price'])
            #self.on_fill(fill['filled_size'], fill['price'])


    def computePnL(self):
        if self._pos >= 0:
            price = self.df.ix[self.cur_loc, 'top_bid_price']
        else:
            price = self.df.ix[self.cur_loc, 'top_ask_price']

        return self._cash + float(self._pos) * float(price) * self.dollar_value_per_price_level


    def computeEstimatePnL(self):
	self.potential_pnl = self.computePnL()

	if self.best_potential_pnl == 0 and self.potential_pnl < 0:
            self.best_potential_pnl = self.potential_pnl
        elif self.potential_pnl > self.best_potential_pnl:
            self.best_potential_pnl = self.potential_pnl


    def updateExitOrders(self):
	valid_exit_orders = []

	exit_order_ids = [exit_order['id'] for exit_order in self.my_exit_orders]
	#live_order_ids = [live_order['id'] for live_order in self.my_live_orders]
	#for exit_order in self.my_exit_orders:
	#    if 	    
	valid_exit_orders = [live_order for live_order in self.my_live_orders if live_order['id'] in exit_order_ids]
	self.my_exit_orders = valid_exit_orders	


    def time_offset_loc(self, offset_secs):
        return self.df.index.get_loc(self.start_dt + timedelta(seconds=offset_secs))


    def getNewOrderID(self):
	new_order_id = self.last_order_id + 1
	self.last_order_id = new_order_id
	return new_order_id


    def createNewOrder(self, direction, price, size, order_time_loc):
	new_order = {'id': self.getNewOrderID(), 'direction': direction, 'price': price, 'size': size, 'order_time_loc': order_time_loc}
	
	#self.out_orders.append(new_order)
	return new_order


    def createBuyOrder(self, price, size, order_time_loc):
	new_order = self.createNewOrder("buy", price, size, order_time_loc)

	return new_order


    def createSellOrder(self, price, size, order_time_loc):
	new_order = self.createNewOrder("sell", price, size, order_time_loc)

	return new_order


    def createCancelOrder(self, id, order_time_loc):
	cancel_order = {'id': id, 'direction': "cancel", 'price': None, 'size': None, 'order_time_loc': order_time_loc}
	
	#self.out_orders.append(cancel_order)
	return cancel_order


    def sizeCurveFunction(self, form, param1, param2, edge, X):
	if form == "linear":
	    Y = param1 * (X - edge) + param2
        elif form == "quadratic":
            Y = param1 * (X - edge)**2 + param2

	Yrounded = int(round(Y,0))

	return Yrounded
		
	
    def buildBidOrderCurve(self, form, param1, param2, depth, skip, edge, top_bid_price):
	bid_curve_orders = []

	start_price = top_bid_price - edge * min_price_increment

	first_price_level = edge
	last_price_level = first_price_level + depth - 1

	for lev in xrange(first_price_level, first_price_level + depth, skip+1):
	    size = min(self.sizeCurveFunction(form, param1, param2, edge, lev), max_size_on_level)
	    price = top_bid_price - lev * min_price_increment

	    new_order = self.createNewOrder("buy", price, size, self.cur_loc)
	    bid_curve_orders.append(new_order)

	return bid_curve_orders
	

    def buildAskOrderCurve(self, form, param1, param2, depth, skip, edge, top_ask_price):
	ask_curve_orders = []
	
	start_price = top_ask_price + edge * min_price_increment

	first_price_level = edge
	last_price_level = first_price_level + depth - 1

        for lev in xrange(first_price_level, first_price_level + depth, skip+1):
            size = min(self.sizeCurveFunction(form, param1, param2, edge, lev), max_size_on_level)
            price = top_ask_price + lev * min_price_increment

	    new_order = self.createNewOrder("sell", price, size, self.cur_loc)
	    ask_curve_orders.append(new_order)

	return ask_curve_orders


    def buildFullOrderStack(self, bid_form, bid_param1, bid_param2, bid_depth, bid_skip, bid_edge,
				ask_form, ask_param1, ask_param2, ask_depth, ask_skip, ask_edge,
				top_bid_price, top_ask_price):
	order_stack = []
	bid_order_stack = []
	ask_order_stack = []
	if bid_form != "none":
	    bid_order_stack = self.buildBidOrderCurve(bid_form, bid_param1, bid_param2, bid_depth, bid_skip, bid_edge, top_bid_price)
	    self.myStacker.bid_stacker_orders = bid_order_stack
	    order_stack.extend(bid_order_stack)
	if ask_form != "none":
	    ask_order_stack = self.buildAskOrderCurve(ask_form, ask_param1, ask_param2, ask_depth, ask_skip, ask_edge, top_ask_price)
	    self.myStacker.ask_stacker_orders = reversed(ask_order_stack)
	    order_stack.extend(ask_order_stack)

	#self.printOrderStack(ask_order_stack, bid_order_stack)

	return order_stack

	
    def initOrderStack(self):
	top_bid_price = self.df.ix[self.cur_loc, 'top_bid_price']
        top_ask_price = self.df.ix[self.cur_loc, 'top_ask_price']

	print "sending stack to market:", self.df.ix[self.cur_loc, 'time']
	stack_orders = self.buildFullOrderStack(bid_form, bid_param1, bid_param2, bid_depth, bid_skip, bid_edge,
                                		ask_form, ask_param1, ask_param2, ask_depth, ask_skip, ask_edge,
                                		top_bid_price, top_ask_price)

	self.out_orders.extend(stack_orders)
	

	mkt_loc, fills, self.my_live_orders = self.mySim.execute(stack_orders)

	return mkt_loc, fills


    def printOrderStack(self, ask_order_stack, bid_order_stack):
	print "ORDER STACK:"
        for ao in reversed(ask_order_stack):
            print(str(ao['id']) + "\t" + "\t" + str(ao['price']) + "\t" + str(ao['size'])).expandtabs(15)
        print "-----------------------------------------------"
        for bo in bid_order_stack:
            print(str(bo['id']) + "\t" + str(bo['size']) + "\t" + str(bo['price']) + "\t" + "  ").expandtabs(15)
        print


    def cancelAskOrderStack(self):
	for order in self.myStacker.ask_stacker_orders:
            cancel_order = self.createCancelOrder(order['id'], self.cur_loc)
            self.out_orders.append(cancel_order)
        self.myStacker.ask_stacker_orders = []	


    def cancelBidOrderStack(self):
	for order in self.myStacker.bid_stacker_orders:
            cancel_order = self.createCancelOrder(order['id'], self.cur_loc)
            self.out_orders.append(cancel_order)
        self.myStacker.bid_stacker_orders = []


    def cancelOrderStack(self):
	self.cancelAskOrderStack()
	self.cancelBidOrderStack()


    def isLiveStacker(self):
	if self.myStacker.ask_stacker_orders or self.myStacker.bid_stacker_orders:
	    return True
	else:
	    return False


    def buildExitOrder(self, top_bid_price, top_ask_price, ticks_to_cross, size):
        if self._pos > 0:
            exit_price = top_bid_price - ticks_to_cross * min_price_increment
            exit_size = size
            exit_sell_order = self.createSellOrder(exit_price, exit_size, self.cur_loc)
            self.out_orders.append(exit_sell_order)
	elif self._pos < 0:
	    exit_price = top_ask_price + ticks_to_cross * min_price_increment
	    exit_size = size
	    exit_buy_order = self.createBuyOrder(exit_price, exit_size, self.cur_loc)
	    self.out_orders.append(exit_buy_order)


    def cancelExitOrder(self, exit_order):
	cancel_exit_order = self.createCancelOrder(exit_order['id'], self.cur_loc)
        self.out_orders.append(cancel_exit_order)
        if exit_order in self.my_exit_orders:
            #self.my_exit_orders.remove(next((x for x in self.my_exit_orders if x['id'] == exit_order['id']), None))
	    #print self.my_exit_orders
	    #print exit_order
	    self.my_exit_orders.remove(next((x for x in self.my_exit_orders if x['id'] == exit_order['id']), None))	

	    #print "  ********"
	    #print "  exit_order: ", exit_order
	    #print "  ", self.df.ix[self.cur_loc, 'time'], "self.my_exit_orders: ", self.my_exit_orders
	    #print "  ********"

    def cancelAllExitOrders(self, total_exit_size_at_risk):
	my_exit_orders_cpy = copy.deepcopy(self.my_exit_orders)
	for exit_order in my_exit_orders_cpy:
	    self.cancelExitOrder(exit_order)
	    total_exit_size_at_risk -= exit_order['size'] 

	return total_exit_size_at_risk


    def cancelExitOrders(self, exit_orders_to_cancel, total_exit_size_at_risk):
	for exit_order in exit_orders_to_cancel:
	    self.cancelExitOrder(exit_order)
            total_exit_size_at_risk -= exit_order['size']

	return total_exit_size_at_risk


    def reEvaluateExitOrders(self, exit_checkpoints_locs, exit_cp_prices, total_exit_size_at_risk, max_size_per_level=10, max_num_exit_levels=2):
	#print "self._pos:", self._pos
	#print "total_exit_size_at_risk: ", total_exit_size_at_risk
        #print "self.my_live_orders:", self.my_live_orders
	#print self.df.ix[self.cur_loc, 'time'], "self.my_exit_orders: ", self.my_exit_orders
	if self._pos != 0 and abs(self._pos) < total_exit_size_at_risk:
            self.cancelAllExitOrders()
            #self.reEvaluateExitOrders(exit_checkpoints_locs, exit_cp_prices, max_size_per_level, max_num_exit_levels) -- wait for next sim turn	
	elif abs(self._pos) < self.max_abs_pos and self.cur_loc >= self.entry_stop_time_loc and abs(self._pos) < small_abs_pos and self.isLiveStacker():
	    self.cancelOrderStack()
	    print "cancelled Curve |#1|", self.df.ix[self.cur_loc, 'time']	
	elif self.cur_loc >= self.entry_stop_time_loc and abs(self._pos) == 0 and self.isLiveStacker():    
	    self.cancelOrderStack()
	    print "cancelled Curve |#2|", self.df.ix[self.cur_loc, 'time']
	elif self._pos != 0: # and abs(self._pos) > total_exit_size_at_risk:
	    #print reversed(exit_checkpoints_locs)
	    if self._pos > 0:
		exit_direction = "sell"
	    else:
		exit_direction = "buy"

	    wrong_direction_exit_orders = [o for o in self.my_exit_orders if o['direction'] != exit_direction]  # for case where position flips
	    total_exit_size_at_risk = self.cancelExitOrders(wrong_direction_exit_orders, total_exit_size_at_risk)

	    if self.cur_loc >= self.trade_termination_loc:
		if self.my_exit_orders:
		    total_exit_size_at_risk = self.cancelAllExitOrders(total_exit_size_at_risk)
		
		exit_size = abs(self._pos)
		if self._pos > 0:
		    #exit_price = self.df.ix[self.cur_loc, 'top_ask_price'] + min_price_increment * max_levels_to_cross
		    exit_price = self.df.ix[self.cur_loc, 'top_bid_price'] - min_price_increment * max_levels_to_cross
		    exit_order = self.createSellOrder(exit_price, exit_size, self.cur_loc)
                    self.out_orders.append(exit_order)
                    self.my_exit_orders.append(exit_order)
		    print "sent emergency sell order: ", exit_size, exit_price, self.df.ix[self.cur_loc, 'time']
		elif self._pos < 0:
		    #exit_price = self.df.ix[self.cur_loc, 'top_bid_price'] - min_price_increment * max_levels_to_cross
		    exit_price = self.df.ix[self.cur_loc, 'top_ask_price'] + min_price_increment * max_levels_to_cross
		    exit_order = self.createBuyOrder(exit_price, exit_size, self.cur_loc)
                    self.out_orders.append(exit_order)
                    self.my_exit_orders.append(exit_order)
		    print "sent emergency buy order: ", exit_size, exit_price, self.df.ix[self.cur_loc, 'time']
		
		return

	    for checkpoint_loc in reversed(exit_checkpoints_locs):
		#print "checkpoint: ", checkpoint_loc
		if self.cur_loc == checkpoint_loc:
		    total_exit_size_at_risk = self.cancelAllExitOrders(total_exit_size_at_risk)  # needed for cancel-replace effect
	        if self.cur_loc >= checkpoint_loc:
		    base_exit_price = exit_cp_prices[checkpoint_loc]	    
		    
		    available_exit_size = abs(self._pos) - total_exit_size_at_risk
		    #print "available_exit_size: ", available_exit_size
		    #print "base_exit_price: ", base_exit_price
		    for x in xrange(0, max_num_exit_levels):
                	if self._pos > 0:
                    	    exit_price = base_exit_price + x
                	elif self._pos < 0:
                    	    exit_price = base_exit_price - x

                	total_size_on_exit_level = 0
                	for live_order in self.my_live_orders:
                    	    if live_order['price'] == exit_price and live_order['direction'] == exit_direction:
                        	total_size_on_exit_level += live_order['size']
			    
			
			exit_size = 0
                	if total_size_on_exit_level < max_size_per_level and available_exit_size:
                    	    exit_size = min(max_size_per_level - total_size_on_exit_level, available_exit_size)
			    available_exit_size -= exit_size

                	if self._pos > 0 and exit_size > 0:
                    	    exit_order = self.createSellOrder(exit_price, exit_size, self.cur_loc)
                    	    self.out_orders.append(exit_order)
                    	    self.my_exit_orders.append(exit_order)
                	elif self._pos < 0 and exit_size > 0:
                            exit_order = self.createBuyOrder(exit_price, exit_size, self.cur_loc)
                    	    self.out_orders.append(exit_order)
                    	    self.my_exit_orders.append(exit_order)	    
		    break
	elif self._pos == 0 and total_exit_size_at_risk > 0:
            self.cancelAllExitOrders()

	#print self.df.ix[self.cur_loc, 'time'], "self.my_exit_orders: ", self.my_exit_orders
	#print "-----"


    def exitLogic1(self, top_bid_price, top_ask_price):
	ticks_to_cross = 2
	#event_datetime_obj = datetime.strptime(event_date + " " + event_start_time, '%Y-%m-%d %H:%M:%S')
	checkpoint1_dt = self.event_dt + timedelta(seconds=60)
	checkpoint2_dt = self.event_dt + timedelta(seconds=180)
	checkpoint3_dt = self.event_dt + timedelta(seconds=300)
	checkpoint4_dt = self.event_dt + timedelta(seconds=600)
	
	checkpoint1_loc = self.df.index.get_loc(checkpoint1_dt)
	checkpoint2_loc = self.df.index.get_loc(checkpoint2_dt)
	checkpoint3_loc = self.df.index.get_loc(checkpoint3_dt)
	checkpoint4_loc = self.df.index.get_loc(checkpoint4_dt)

	checkpoint1_proportion = 0.1
	checkpoint2_proportion = 0.35
	checkpoint3_proportion = 0.55
	checkpoint4_proportion = 1.0

	exit_size = 0
	if self._pos != 0:
	    if self.cur_loc == checkpoint1_loc:
		exit_size = self._pos * checkpoint1_proportion
	    elif self.cur_loc == checkpoint2_loc:
		exit_size = self._pos * checkpoint2_proportion	
	    elif self.cur_loc == checkpoint3_loc:
                exit_size = abs(self._pos) * checkpoint3_proportion
	    elif self.cur_loc == checkpoint4_loc:
                exit_size = abs(self._pos) * checkpoint4_proportion

	    self.buildExitOrder(top_bid_price, top_ask_price, ticks_to_cross, exit_size)
	#=====> find place for cancel curve action somewhere here -- can be one side at a time
	#========> in fact, should cancel entry-side curve at some point
	#=====> also definitely need stop losses



    def exitLogic2(self, max_disl_ticks, top_bid_price, top_ask_price):
	#checkpoint1_dt = self.event_dt + timedelta(seconds=60)
        #checkpoint2_dt = self.event_dt + timedelta(seconds=180)
        #checkpoint3_dt = self.event_dt + timedelta(seconds=300)
        #checkpoint4_dt = self.event_dt + timedelta(seconds=600)

        #checkpoint1_loc = self.df.index.get_loc(checkpoint1_dt)
        #checkpoint2_loc = self.df.index.get_loc(checkpoint2_dt)
        #checkpoint3_loc = self.df.index.get_loc(checkpoint3_dt)
        #checkpoint4_loc = self.df.index.get_loc(checkpoint4_dt)

        #checkpoint1_proportion = 0.1
        #checkpoint2_proportion = 0.35
        #checkpoint3_proportion = 0.55
        #checkpoint4_proportion = 0.75

	#exit_ticks = int(disl_ticks * checkpoint1_proportion
	#exit_ticks = int(disl_ticks * checkpoint2_proportion)
	#exit_ticks = int(disl_ticks * checkpoint3_proportion)
	#exit_ticks = int(disl_ticks * checkpoint4_proportion)

	#base_exit_price = self.pre_event_price + exit_ticks * min_price_increment



	checkpoints = [30, 60, 180, 300, 600]  # seconds
	checkpoint_proportions = [0.1, 0.35, 0.55, 0.75]  # proportion of max dislocation from pre-num price at which to place exit
	checkpoint_proportions = [0.35, 0.55, 0.65, 0.75, 0.85]
	checkpoint_proportions = [0.25, 0.45, 0.55, 0.65, 0.75]

	checkpoints_locs = [self.df.index.get_loc(self.event_dt + timedelta(seconds=cp))  for cp in checkpoints]
	#print checkpoints_locs
	exit_cp_ticks = [int(max_disl_ticks * p) for p in checkpoint_proportions]
	prices = [(self.pre_event_price + t * min_price_increment) for t in exit_cp_ticks]
	#print prices	
	#=====> zip the locs and prices into a dictionary
	exit_cp_prices = dict(zip(checkpoints_locs, prices))
	#print exit_cp_prices

	max_size_per_level = 20
	max_num_exit_levels = 5

	live_order_ids = [o['id'] for o in self.my_live_orders]
	total_exit_size_at_risk = sum(o['size'] for o in self.my_exit_orders if o['id'] in live_order_ids)
	#print "total_exit_size_at_risk: ", total_exit_size_at_risk

	#=====> add call to re-evaluate method here
	self.reEvaluateExitOrders(checkpoints_locs, exit_cp_prices, total_exit_size_at_risk, max_size_per_level, max_num_exit_levels)

#	if self._pos != 0:
#	    exit_ticks = 0
#	    if self.cur_loc == checkpoint1_loc:
#                exit_ticks = int(disl_ticks * checkpoint1_proportion)
#            elif self.cur_loc == checkpoint2_loc:
#                exit_ticks = int(disl_ticks * checkpoint2_proportion)
#            elif self.cur_loc == checkpoint3_loc:
#                exit_ticks = int(disl_ticks * checkpoint3_proportion)
#            elif self.cur_loc == checkpoint4_loc:
#                exit_ticks = int(disl_ticks * checkpoint4_proportion)
#
#	    base_exit_price = self.pre_event_price + exit_ticks * min_price_increment
#
#	    for x in xrange(0, max_num_exit_levels):
#		exit_size = 0
#		if self._pos > 0:
#		    exit_price = base_exit_price + x
#		elif self._pos < 0:
#		    exit_price = base_exit_price - x
#
#		total_size_on_exit_level = 0
#		for live_order in self.my_live_orders:
#		    if live_order['price'] == exit_price:
#		        total_size_on_exit_level += live_order['size']
#	
#		if total_size_on_exit_level < max_size_per_level:
#		    exit_size = max_size_per_level - total_size_on_exit_level	
#
#		if self._pos > 0:
#            	    exit_order = self.createSellOrder(exit_price, exit_size, self.cur_loc)
#		    self.out_orders.append(exit_order)
#		    self.my_exit_orders.append(exit_order)
#        	elif self._pos < 0:
#            	    exit_order = self.createBuyOrder(exit_price, exit_size, self.cur_loc)
#                    self.out_orders.append(exit_order)
#		    self.my_exit_orders.append(exit_order)
#	elif self._pos == 0 and total_exit_size_at_risk > 0:
#	    self.cancelAllExitOrders()
#	elif self._pos != 0 and abs(self._pos) < total_exit_size_at_risk:
#	    self.cancelAllExitOrders()
#	    - call this function again


    def onTick(self):
	top_bid_price = self.df.ix[self.cur_loc, 'top_bid_price']
	top_ask_price = self.df.ix[self.cur_loc, 'top_ask_price']

	ask_size = self.df.ix[self.cur_loc, ['ask_size_0', 'ask_size_1', 'ask_size_2', 'ask_size_3', 'ask_size_4']]
	bid_size = self.df.ix[self.cur_loc, ['bid_size_0', 'bid_size_1', 'bid_size_2', 'bid_size_3', 'bid_size_4']]

	if self.cur_loc >= self.start_loc and self.cur_loc < self.opposite_stacker_off_loc:
	    #up_disl_ticks = (self.df.ix[self.cur_loc, 'microprice'] - self.pre_event_price) / float(min_price_increment)
	    #down_disl_ticks = (self.df.ix[self.cur_loc, 'microprice'] - self.pre_event_price) / float(min_price_increment)
	    #if up_disl_ticks > self.max_up_disl_ticks:
		#self.max_up_disl_ticks = up_disl_ticks
	    #elif down_disl_ticks < self.max_down_disl_ticks:
                #self.max_down_disl_ticks = down_disl_ticks	

	    disl_ticks = (self.df.ix[self.cur_loc, 'microprice'] - self.pre_event_price) / float(min_price_increment)
	    if disl_ticks > self.max_up_disl_ticks:
		self.max_up_disl_ticks = disl_ticks
	    elif disl_ticks < self.max_down_disl_ticks:
		self.max_down_disl_ticks = disl_ticks   

	    #print "self.max_up_disl_ticks: ", self.max_up_disl_ticks, "  self.max_down_disl_ticks: ", self.max_down_disl_ticks

	if self.cur_loc == self.opposite_stacker_off_loc:
	    #if self.max_up_disl_ticks > abs(self.max_down_disl_ticks):  # cancel bid side
	    if self.max_up_disl_ticks > abs(self.max_down_disl_ticks) or self._pos < 0:  # cancel bid side
		for order in self.myStacker.bid_stacker_orders:
		    cancel_order = self.createCancelOrder(order['id'], self.cur_loc)
		    self.out_orders.append(cancel_order)
		self.myStacker.bid_stacker_orders = []	    			
	    #if abs(self.max_down_disl_ticks) > self.max_up_disl_ticks:  # cancel ask size
	    elif abs(self.max_down_disl_ticks) > self.max_up_disl_ticks or self._pos > 0:  # cancel ask side
		for order in self.myStacker.ask_stacker_orders:
                    cancel_order = self.createCancelOrder(order['id'], self.cur_loc)
                    self.out_orders.append(cancel_order)
                self.myStacker.ask_stacker_orders = []

	if self.max_up_disl_ticks > abs(self.max_down_disl_ticks) or self._pos < 0:
	    max_disl_ticks = self.max_up_disl_ticks
	elif abs(self.max_down_disl_ticks) > self.max_up_disl_ticks or self._pos > 0:
	    max_disl_ticks = self.max_down_disl_ticks
	else:
	    max_disl_ticks = 0

	self.exitLogic2(max_disl_ticks, top_bid_price, top_ask_price)

	fills = []

	mkt_loc, fills, self.my_live_orders = self.mySim.execute(self.out_orders)

	self.updateExitOrders()

	return mkt_loc, fills



def main():
    print "starting..."
    import timeit
    results = []
    for event_date in event_dates:
        print event_date
        event_datetime_obj = datetime.strptime(event_date + " " + event_start_time, '%Y-%m-%d %H:%M:%S')
        symbol = mkdt_utils.getSymbol(instrument_root, event_datetime_obj)
	df = mkdt_utils.getMarketDataFrameForTradingDate(event_date, instrument_root, symbol, "100ms")
        if isinstance(df.head(1).time[0], basestring):
            df.time = df.time.apply(mkdt_utils.str_to_dt)
        df.set_index(df['time'], inplace=True)

        start_dt = datetime.strptime(event_date + " " + trading_start_time, '%Y-%m-%d %H:%M:%S')
	trading_stop_time = trading_stop_times[event_durations[event_date]]
	stop_dt = datetime.strptime(event_date + " " + trading_stop_time, '%Y-%m-%d %H:%M:%S')

	opposite_stacker_off_dt = datetime.strptime(event_date + " " + opposite_stacker_off_time, '%Y-%m-%d %H:%M:%S')
	entry_stop_time_dt = datetime.strptime(event_date + " " + entry_stop_time, '%Y-%m-%d %H:%M:%S')

        Sim = simulator4.Simulator(df, symbol, min_price_increment)
        Strat = Strategy(df, event_datetime_obj, start_dt, stop_dt, opposite_stacker_off_dt, entry_stop_time_dt, Sim, dollar_value_per_price_level)
        Sim.initStrategy(Strat)
	Strat.start()

	event_results = {'pnl': Strat._pnl, 'pos': Strat._pos, 'vol': Strat._vol}
	results.append({'event_date': event_date, 'event_results': event_results, 'best_potential_pnl': Strat.best_potential_pnl, 'max_abs_pos': Strat.max_abs_pos})


	print "FINISHED:", event_date
	print "  pos: ", Strat._pos
        print "  PnL: ", Strat._pnl
	print "  vol: ", Strat._vol

    print
    print "--------" 
    print "RESULTS:"
    print "--------"
    #print "event_date" + "\t" + "PnL" + "\t\t" + "pos" + "\t" + "vol" + "\t" + "max_abs_pos" + "\t" + "best_potential_pnl" 
    #for result in results:
    #    print result['event_date'] + "\t" + str(result['event_results']['pnl']) + "\t\t" + str(result['event_results']['pos']) + "\t" \
#		+ str(result['event_results']['vol']) + "\t" + str(result['max_abs_pos']) + "\t" + str(result['best_potential_pnl'])

    print "event_date".ljust(16) + "PnL".ljust(20) + "pos".ljust(12) + "vol".ljust(12) + "max_abs_pos".ljust(16) + "best_potential_pnl".ljust(20)
    for result in results:
        print result['event_date'].ljust(16) + str(result['event_results']['pnl']).ljust(20) + str(result['event_results']['pos']).ljust(12) \
                + str(result['event_results']['vol']).ljust(12) + str(result['max_abs_pos']).ljust(16) + str(result['best_potential_pnl']).ljust(20)

    

if __name__ == "__main__": main()
