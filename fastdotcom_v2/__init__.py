'''
Python CLI-tool (without need for a GUI) to measure Internet speed with fast.com

'''
import os
import json
import urllib.request, urllib.parse, urllib.error
import sys
import time
from threading import Thread
import random
import string
import socket

from BufferReader import BufferReader


def gethtmlresult_dl(url,result,index,stop=lambda : False):
  '''
  get the stuff from url in chuncks of size CHUNK, and keep writing the number of bytes retrieved into result[index]
  '''
  while not stop():
    try:
      req = urllib.request.urlopen(url)
    except urllib.error.URLError:
      return

    CHUNK = 100 * 1024
    while True:
      chunk = req.read(CHUNK)
      if stop(): return
      if not chunk: break
      result[index] = result[index] + CHUNK


def gethtmlresult_ul(url,result,index,stop=lambda : False):
  size = 5 * 1024 * 1024 # 5MB
  payload = ''.join(random.choice(string.digits) for i in range(size)).encode('ascii')

  def progress(size=None, progress=None, chunk_len=None):
      result[index] = result[index] + chunk_len

  while not stop():
    buffer_payload = BufferReader(payload, progress)
    r = urllib.request.Request(url, buffer_payload)
    r.add_header('Content-Length', '%d' % len(payload))
    r.add_header('Content-Type', 'application/octet-stream')

    start_time = time.time()
    try:
      req = urllib.request.urlopen(r)
    except urllib.error.URLError:
      return

    chunk = req.read()
    # result[index] = result[index] + size
    end_time = time.time()

def application_bytes_to_networkbits(bytes):
  # convert bytes (at application layer) to bits (at network layer)
  return bytes * 8 * 1.0415
  # 8 for bits versus bytes
  # 1.0416 for application versus network layers


def findipv4(fqdn):
  '''
    find IPv4 address of fqdn
  '''
  ipv4 = socket.getaddrinfo(fqdn, 80, socket.AF_INET)[0][4][0]
  return ipv4


def findipv6(fqdn):
  '''
    find IPv6 address of fqdn
  '''
  ipv6 = socket.getaddrinfo(fqdn, 80, socket.AF_INET6)[0][4][0]
  return ipv6


def fast_com(verbose=False, maxtime=15, forceipv4=False, forceipv6=False):
  '''
    verbose: print debug output
    maxtime: max time in seconds to monitor speedtest
    forceipv4: force speed test over IPv4
    forceipv6: force speed test over IPv6
  '''
  # go to fast.com to get the javascript file
  url = 'https://fast.com/'
  jsname = ''
  token = ''
  zero_ret = dict(dl_Mbps=0,ul_Mbps=0)
  try:
    urlresult = urllib.request.urlopen(url)
  except:
    # no connection at all?
    return zero_ret
  response = urlresult.read().decode().strip()
  for line in response.split('\n'):
    # We're looking for a line like
    #           <script src="/app-40647a.js"></script>
    if line.find('script src') >= 0:
      jsname = line.split('"')[1] # At time of writing: '/app-40647a.js'


  # From that javascript file, get the token:
  url = 'https://fast.com' + jsname
  if verbose: print("javascript url is", url)
  try:
    urlresult = urllib.request.urlopen(url)
  except:
    # connection is broken
    return zero_ret
  allJSstuff = urlresult.read().decode().strip() # this is a obfuscated Javascript file
  for line in allJSstuff.split(','):
    if line.find('token:') >= 0:
      if verbose: print("line is", line)
      token = line.split('"')[1]
      if verbose: print("token is", token)
      if token:
        break

  # With the token, get the (3) speed-test-URLS from api.fast.com (which will be in JSON format):
  baseurl = 'https://api.fast.com/'
  if forceipv4:
    # force IPv4 by connecting to an IPv4 address of api.fast.com (over ... HTTP)
    ipv4 = findipv4('api.fast.com')
    baseurl = 'http://' + ipv4 + '/'  # HTTPS does not work IPv4 addresses, thus use HTTP
  elif forceipv6:
    # force IPv6
    ipv6 = findipv6('api.fast.com')
    baseurl = 'http://[' + ipv6 + ']/'

  url = baseurl + 'netflix/speedtest/v2?https=true&token=' + token + '&urlCount=5' # Not more than 3 possible
  if verbose: print("API url is", url)
  try:
    urlresult = urllib.request.urlopen(url, None)
  except:
    # not good
    if verbose: print("No connection possible") # probably IPv6, or just no network
    return zero_ret  # no connection, thus no speed

  jsonresult = urlresult.read().decode().strip()
  parsedjson = json.loads(jsonresult)
  netflix_targets = parsedjson['targets']

  # Prepare for getting those URLs in a threaded way:
  amount = len(netflix_targets)
  if verbose: print("Number of URLs:", amount)
  urls = [''] * amount
  i = 0
  for jsonelement in netflix_targets:
    urls[i] = jsonelement['url']  # fill out speed test url from the json format
    if verbose: print(jsonelement['url'])
    i = i+1

  # Let's check whether it's IPv6:
  for url in urls:
    fqdn = url.split('/')[2]
    try:
      socket.getaddrinfo(fqdn, None, socket.AF_INET6)
      if verbose: print("IPv6")
    except:
      pass

  dl_highestspeedkBps = monitor_download(verbose, urls, maxtime)

  dl_mbps = (application_bytes_to_networkbits(dl_highestspeedkBps)/1024)
  dl_mbps = float("%.1f" % dl_mbps)
  if verbose: print("Highest Download Speed (kB/s):", dl_highestspeedkBps,  "aka Mbps ", dl_mbps)

  ul_highestspeedkBps = monitor_upload(verbose, urls, maxtime)

  ul_mbps = (application_bytes_to_networkbits(ul_highestspeedkBps)/1024)
  ul_mbps = float("%.1f" % ul_mbps)
  if verbose: print("Highest Upload Speed (kB/s):", ul_highestspeedkBps,  "aka Mbps ", ul_mbps)

  return dict(dl_Mbps=dl_mbps,ul_Mbps=ul_mbps, netflix_meta_client = parsedjson['client'])

def monitor_download(verbose=False, urls=[], maxtime=15):
  amount = len(urls)
  threads = [None] * amount
  results = [0] * amount
  stop_threads = False
  # Now start the download threads
  for i in range(len(threads)):
    #print "Thread: i is", i
    threads[i] = Thread(target=gethtmlresult_dl, args=(urls[i], results, i, lambda : stop_threads))
    threads[i].daemon=True
    threads[i].start()

  # Monitor the amount of bytes (and speed) of the threads
  time.sleep(3)
  sleepseconds = 3  # 3 seconds sleep
  highestspeedkBps = 0
  nrloops = int(maxtime / sleepseconds)
  for loop in range(nrloops):
    total = 0
    for i in range(len(threads)):
      total += results[i]
      results[i] = 0
    speedkBps = (total/sleepseconds)/(1024)
    if verbose:
      print("Loop", loop, "Total MB", total/(1024*1024), "Speed kB/s:", speedkBps, "aka Mbps %.1f" % (application_bytes_to_networkbits(speedkBps)/1024))
    if speedkBps > highestspeedkBps:
      highestspeedkBps = speedkBps
    time.sleep(sleepseconds)
  stop_threads = True

  return highestspeedkBps

def monitor_upload(verbose=False, urls=[], maxtime=15):
  amount = len(urls)
  threads = [None] * amount
  results = [0] * amount
  stop_threads = False
  # Now start the download threads
  for i in range(len(threads)):
    #print "Thread: i is", i
    threads[i] = Thread(target=gethtmlresult_ul, args=(urls[i], results, i, lambda : stop_threads))
    threads[i].daemon=True
    threads[i].start()

  # Monitor the amount of bytes (and speed) of the threads
  time.sleep(3)
  sleepseconds = 3  # 3 seconds sleep
  highestspeedkBps = 0
  nrloops = int(maxtime / sleepseconds)
  for loop in range(nrloops):
    total = 0
    for i in range(len(threads)):
      total += results[i]
      results[i] = 0
    speedkBps = (total/sleepseconds)/(1024)
    if verbose:
      print("Loop", loop, "Total MB", total/(1024*1024), "Speed kB/s:", speedkBps, "aka Mbps %.1f" % (application_bytes_to_networkbits(speedkBps)/1024))
    if speedkBps > highestspeedkBps:
      highestspeedkBps = speedkBps
    time.sleep(sleepseconds)
  stop_threads = True

  return highestspeedkBps

######## MAIN #################

if __name__ == "__main__":
  print("let's speed test:")
  print("\nSpeed test, without logging:")
  print(fast_com())
  print("\nSpeed test, with logging:")
  print(fast_com(verbose=True))
  print("\nSpeed test, IPv4, with verbose logging:")
  print(fast_com(verbose=True, maxtime=18, forceipv4=True))
  print("\nSpeed test, IPv6:")
  print(fast_com(maxtime=12, forceipv6=True))
  #fast_com(verbose=True, maxtime=25)

  print("\ndone")

