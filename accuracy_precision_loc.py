#!/usr/bin/env python
# encoding: utf-8

'''
@file   accuracy_precision_loc.py 
@author  Rémi Pincent - INRIA
@date    10/04/2017

 @brief Precision and localisation viewer for 3D RTLS
 Project : localization_tools 
 Contact:  Rémi Pincent - remi.pincent@inria.fr

 Revision History:
     https://github.com/OpHaCo/localisation_tools.git 

  LICENSE :
      localization_tools (c) by Rémi Pincent
      localization tools is licensed under a
      Creative Commons Attribution-NonCommercial 3.0 Unported License.

  You should have received a copy of the license along with this
  work.  If not, see <http://creativecommons.org/licenses/by-nc/3.0/>.
  '''
import numpy as np
import scipy.stats
import sys
import os
import threading
import time
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.mlab as mlab
import colorsys

import paho.mqtt.client as mqtt
import select, socket 

'''
Either MQTT or UDP
'''
COORDINATE_GETTER="mqtt"


'''
Global variables
'''
fig=None
axx = None
axy = None
axz = None
tag_ref = None
# points x, y, z
points=np.array([]).reshape(3, 0)
# mutex to protect points
points_mutex = threading.Lock()
client = None
s = None

'''
Clear all histograms when pressing 'c'
'''
def keypress(event):
    if event.key == 'c' :
        clear_histograms() 



def on_mqtt_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("localisation/be_spoon/+")


def on_mqtt_message(client, userdata, msg):
    global points  
    data = msg.payload.decode('utf-8').split(',')
    tag_id = msg.topic[msg.topic.index('bsp_') + len('bsp_'):] 
    if tag_ref == tag_id : 
        with points_mutex : 
            points = np.append(points, [[float(data[0])], [float(data[1])], [float(data[2])]], axis=1) 


def mqtt_loop():
    client.loop_forever() 


def listen_udp():
    global points  
    while True:
        result = select.select([s],[],[])
        msg = result[0][0].recv(bufferSize) 
        data = msg.decode('utf-8').split(',')
        print('tag_ref={} - pos({}, {}, {})'.format(data[0], data[1], data[2], data[3]))
        if data[0] == tag_ref : 
            with points_mutex : 
                points = np.append(points, [[float(data[0])], [float(data[1])], [float(data[2])]], axis=1) 


''' 
Simulate new points, following normal distribution
'''
def on_new_point():
    global points 
    while True : 
        with points_mutex : 
            points = np.append(points, [[4 + 1*np.random.randn()], [10 + 2*np.random.randn()], [1 + 10*np.random.randn()]], axis=1) 
        time.sleep(0.001) 


'''
Update displayed graphs
'''
def update_canvas():
    # plt.pause(0.001) update graph but is very slow, 
    # plt.draw() do not update graphs 
    # a fast solution is to call these methods 
    fig.canvas.update()
    fig.canvas.flush_events()
    # Some updates in title are possible 
    fig.tight_layout()
    
    # depending on backend, plt.pause muste be called to display graph 
    if update_canvas.first_update :
        update_canvas.first_update = False
        plt.pause(0.001) 
update_canvas.first_update = True


def init_loc_getter():
    global client
    global s
    if COORDINATE_GETTER == 'udp' :
        # UDP broadcast parameters
        port = 5540  
        bufferSize = 1024 
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(('<broadcast>', port))
        s.setblocking(0)
    elif COORDINATE_GETTER == 'mqtt' :
        client = mqtt.Client()
        client.connect("192.168.130.22", 1883)
        client.on_connect = on_mqtt_connect
        client.on_message = on_mqtt_message

def init_histograms() :
    global fig
    global axx, axy, axz 
    fig = plt.figure() 
    fig.canvas.mpl_connect('key_press_event', keypress)
    fig.canvas.set_window_title('Localization - accuracy and precision')

    # interactive graphs
    plt.ion()

    # x-y-z graphs
    gs1 = gridspec.GridSpec(3, 1)
    axx = fig.add_subplot(gs1[0])  

    axy = fig.add_subplot(gs1[1])  

    axz = fig.add_subplot(gs1[2])  


def update_histogram(name, graph, data, ref) :
    graph.cla() 
    graph.set_title('{} - probability density'.format(name), color='g')
    graph.set_xlabel('{}(m) - ref={}'.format(name, ref))
    # n    : records for each bin
    # bins : value of current bin (on x)
    # patch  : rectangle of bin
    n, bins, patchs = graph.hist(data, bins=100, alpha=0.75) 
    bincenters = 0.5*(bins[1:]+bins[:-1])
    graph.plot(bincenters,n,'-')
    
    max_prob=None
    for bin_size, bin, patch in zip(n, bins, patchs):
        if bin_size == max(n):
            patch.set_facecolor("#FF0000")
            patch.set_label("max")
            max_prob='[{:.2f}, {:.2f}]'.format(bin, bin + patch.get_width()) 
            accuracy=abs(bin + patch.get_width()/2 - ref)
            # Adjust graph color with accuracy level 
            graph.set_title('{} - probability density\n  max bin : {} -  nb points = {}\n  accuracy = {:.4f} - resolution={:.4f}'.format(name, max_prob, len(data), accuracy, np.std(data)), color=get_accuracy_color(accuracy), size=10)


def get_accuracy_color(accuracy) :
    # from this accuracy value, accuracy color is max 
    MAX_VAL = 0.6
    # from best to worst 
    HUE_RANGE=(120, 0) 
    hue = None
    if accuracy > MAX_VAL : 
        hue = HUE_RANGE[1]
    else :
        hue = HUE_RANGE[0] - accuracy*(HUE_RANGE[0] - HUE_RANGE[1])/MAX_VAL
    hls = colorsys.hls_to_rgb(hue/360, 0.5, 1)
    return hls 
    

def clear_histograms():
    global points 
    with points_mutex :
        points=np.array([]).reshape(3, 0)
    

def main(argv=None):
    global tag_ref 
    usage='USAGE : python ./accuracy_precision_loc.py tag_id x y z' 
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) != 4:
        raise ValueError('a tag_id and 3d coordonate must be given as argument\n{}'.format(usage))
    try :
        tag_ref = argv[0] 
        ref_point=(float(argv[1]), float(argv[2]), float(argv[3]))   
        
        init_loc_getter() 
        
        capture_th = threading.Thread(target=mqtt_loop, ) 
        capture_th.daemon = True
        capture_th.start()
        
        init_histograms()

        while True and plt.get_fignums():
           # update graphs with new data, redraw all as 
           # there is no histogram live update
            if len(points[0]) > 0 : 
                update_histogram('x', axx, points[0], ref_point[0])
            if len(points[1]) > 0 : 
                update_histogram('y', axy, points[1], ref_point[1])
            if len(points[1]) > 0 : 
                update_histogram('z', axz, points[2], ref_point[2])
            
            update_canvas()
            time.sleep(0.1)
        
    except Exception as e:
        sys.stderr.write("Exception in main thread : " + str(e) + "\n")
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
        return 2
    
    finally:
        plt.close()

if __name__ == "__main__":
	sys.exit(main())






