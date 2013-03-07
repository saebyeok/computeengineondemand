#!/usr/bin/env python

import httplib2
import logging
import time
import urllib
from random import randint
from apiclient.discovery import build
from oauth2client.appengine import AppAssertionCredentials
from google.appengine.api import memcache
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from django.utils import simplejson as json
from random import choice
from google.appengine.api import urlfetch
from google.appengine.api import users

# Some configuration:
PROJECT_ID = 'turnserver'
API_VERSION = 'v1beta13'
GCE_URL = 'https://www.googleapis.com/compute/%s/projects' % (API_VERSION)
GCE_PROJECT_URL = GCE_URL + '/' + PROJECT_ID;
IMAGE = 'images/centos-6-v20130104'
ANNOUNCE_URLS = [
	'http://dev.klandestino.se/gce_announce'
]
TRESHOLDS = {
	'connections': { 'max': 2000, 'slope': 98, 'start': 95, 'stop': 90 },
	'traffic': { 'max': 100, 'slope': 98, 'start': 95, 'stop': 90 },
	'messages': { 'max': 10000, 'slope': 98, 'start': 95, 'stop': 90 }
}
ZONEGROUPS = { # Load will checked within each zone group, adding new servers in random zone within the group.
	'europe-west': [ 'europe-west1-a', 'europe-west1-b' ],
	'us-central': [ 'us-central1-a', 'us-central1-b', 'us-central2-a' ]
}

# Build our connection to the Compute Engine API:
credentials = AppAssertionCredentials(scope = 'https://www.googleapis.com/auth/compute')
http = credentials.authorize(httplib2.Http(memcache))
compute = build('compute', API_VERSION, http = http)

def zones(): # Returns a list with all available zone names. Caching the data in global _zones variable.
	zones = compute.zones().list(project = PROJECT_ID).execute().get('items', []);
	return zones

def instances():
	instances = []
	for instance in compute.instances().list(project=PROJECT_ID).execute().get('items', []):
		if instance["status"] == "PROVISIONING" or instance["status"] == "STAGING" or instance["status"] == "RUNNING":
			if memcache.get('status-' + instance['name']) != 'stopping':
				ip = '127.0.0.1' # Default - will show if no networkInterface is there yet.
				if len(instance["networkInterfaces"][0]["accessConfigs"]) > 0 and 'natIP' in instance["networkInterfaces"][0]["accessConfigs"][0]:
					ip = instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
				zone = instance["zone"].split('/')
				zone = zone[-1] 
				instances.append({
					"name": instance["name"],
					"zone": zone,
					"ip": ip
				})
		elif instance["status"] == "TERMINATED":
			# Terminated instances should be deleted to not occupy quota.
			# Instances can become TERMINATED on datacenter maintenance, on instance crashes or virtualization host crashes.
			shutdownInstance(instance["name"])

	return instances

def loadReport(ip, load):
	announce = False
	for instance in instances():
		if ip == instance['ip']:
			logging.debug("Got report request from instance at %s" % ip)
			instanceLoad = memcache.get('load-' + instance['name']) # Get the load for the server
			if (instanceLoad is not None and 'data' in instanceLoad and 'data' not in load) or (instanceLoad is not None and 'data' in instanceLoad and 'data' not in load) or (instanceLoad is n    ot None and 'data' in instanceLoad and 'data' in load and instanceLoad['data'] != load['data']):
				# Data string from instance changed. We should announce!
				logging.debug("Data parameter from instance has changed.")
				announce = True
			else:
				logging.debug('Data parameter from instance did not change.')
			memcache.set('load-' + instance['name'], load)
			if reconsiderServers():
				logging.debug('Something was reconsidered. We should announce it!')
				announce = True
	if announce:
		announceActiveServers()

def reconsiderServers():
	announce = False
	for key, zones in ZONEGROUPS.iteritems():
		instancesInZoneGroup = []
		for instance in instances(): # Loop all running instances
			if instance['zone'] in zones:
				instancesInZoneGroup.append(instance)
		logging.debug('Reconsidering zonegroup %s' % (key))
		logging.debug('Running instances in the zonegroup are %s', (', '.join(i['name'] for i in instancesInZoneGroup)))

		addServersInZoneGroup(key, instancesInZoneGroup) # In case we need more servers in a zone group, start more servers!
		destroyServersInZoneGroup(key, instancesInZoneGroup) # In case we can shut down some servers in a zone group, do it.
		if setActiveServerInZoneGroup(key, instancesInZoneGroup): # Decide what server to be the active one (the one we send new connections to)
			logging.debug("setActiveServerInZoneGroup returned that we should announce.")
			announce = True
	return announce # Return wheather we should announce a change?

def addServersInZoneGroup(zonegroup, instancesInZoneGroup):
	if len(instancesInZoneGroup) == 0:
		logging.debug('Starting instance in zonegroup ' + zonegroup + ' since there are no instances in that zone group.')
		startInstance(zone = choice(ZONEGROUPS[zonegroup]))
		return
	instanceLoad = memcache.get('load-' + instancesInZoneGroup[-1]['name']) # Get the load for the last started server
	if instanceLoad == None:
		# No data on this instance yet. Just w8 until it has reported it's load.
		return
	for key, treshold in TRESHOLDS.iteritems(): # Loop through all tresholds and test them:
		if int(instanceLoad[key]) >= int(treshold['max'] / 100.0 * treshold['start']):
			# Yes we are over the treshold for starting a new server.
			logging.debug(key + ' for instance ' + instancesInZoneGroup[-1]['name'] + ' is ' + instanceLoad[key] + ', which is over treshold ' + str(int(treshold['max'] / 100.0 * treshold['start'])))
			logging.debug('Starting instance in zonegroup ' + zonegroup + ' because the last started instance is over the start treshold.')
			startInstance(zone = choice(ZONEGROUPS[zonegroup]))
			return

def destroyServersInZoneGroup(zonegroup, instancesInZoneGroup):
	okToShutDown = False
	for instance in instancesInZoneGroup:
		instanceLoad = memcache.get('load-' + instance['name']) # Get the load for the server
		if instanceLoad != None: # We have no load data on this machine.
			if not okToShutDown:
				okToShutDown = True
				for key, treshold in TRESHOLDS.iteritems(): # Loop through all tresholds and test them:
					if int(instanceLoad[key]) >= int(treshold['max'] / 100.0 * treshold['stop']):
						okToShutDown = False
				if okToShutDown:
					logging.debug('Server ' + instance['name'] + ' has resources left, so we could shut some other servers down.')
			else:
				# Previous server treshold told us it is okey to shut stuff down.
				# Now, just check there are no current connections to actually do it:
				if int(instanceLoad['connections']) == 0:
					logging.debug('Shutting down ' + instance['name'] + ' since there are resources left on other servers.')
					shutdownInstance(instance['name'])
				else:
					logging.debug('Does not shut down ' + instance['name'] + ' yet, since there still are connections on that instance.')
		else:
			logging.debug('No load info on instance ' + instance['name'] + ', so we can not evaluate wheather the server should be shut down or not.')

def setActiveServerInZoneGroup(zonegroup, instancesInZoneGroup):
	active = memcache.get('active-server-' + zonegroup)
	for instance in instancesInZoneGroup:
		ok = True
		instanceLoad = memcache.get('load-' + instance['name']) # Get the load for the server
		instanceStatus = memcache.get("status-" + instance['name'])
		if instanceLoad != None: # If we have no load info on this instance, it probably just started. `ok` stays True...
			if instanceStatus == 'sloping':
				for key, treshold in TRESHOLDS.iteritems(): # Loop through all treshold checks:
					if int(instanceLoad[key]) > int(treshold['max'] / 100.0 * treshold['slope']): 
						ok = False
			else:
				for key, treshold in TRESHOLDS.iteritems(): # Loop through all treshold checks:
					if int(instanceLoad[key]) > treshold['max']: 
						ok = False
						memcache.set("status-" + instance['name'], 'sloping')
		if ok:
			if active == None or not 'name' in active or instanceStatus != 'active' or active['name'] != instance['name']:
				logging.debug('Active server changed (or was not set).')
				memcache.set("status-" + instance['name'], 'active')
				memcache.set('active-server-' + zonegroup, instance)
				return True # True = we need to announce that something changed
			else:
				logging.debug('No change in active server.')
			return False # False = we do not need to announce anything
	logging.debug('There is no good candidate for being the active server.')
	return False # False = we do not need to announce anything

def announceActiveServers():

	logging.debug('Announcing our instances');

	# Make HTTP POST request to the ANNOUNCE_URLS with active ip:s for each zonegroup.
	payload = {}
	for key, zonegroup in ZONEGROUPS.iteritems():
		instance = memcache.get("active-server-" + key)
		if instance is not None and 'ip' in instance:
			payload[key] = instance['ip']
			payload[key + "_data"] = ""
			logging.debug('Active server for %s is %s.' % (zonegroup, instance['ip']))
			instanceLoad = memcache.get('load-' + instance['name'])
			if instanceLoad is not None and 'data' in instanceLoad:
				payload[key + "_data"] = instanceLoad['data']

	for url in ANNOUNCE_URLS:
		logging.debug(' - Announcing to: %s' % url);
		urlfetch.fetch(
			url = url,
			method = urlfetch.POST,
			headers = { 'Content-Type': 'application/x-www-form-urlencoded' },
			payload = urllib.urlencode(payload)
		)

def startInstance(zone): # Start a new server in a given zone.
	name = "instance-" + str(int(time.time())) + "-" + str(randint(1000, 9999))
	memcache.set("status-" + name, 'starting')
	config = {
		"name": name,
		"kind": 'compute#instance',
		"disks": [],
		"networkInterfaces": [
			{
				"kind": 'compute#instanceNetworkInterface',
				"accessConfigs": [
					{
						"name": "External NAT",
						"type": "ONE_TO_ONE_NAT"
					}
				],
				"network": "%s/networks/default" % (GCE_PROJECT_URL)
			}
		],
		"serviceAccounts": [
			{
				"kind": 'compute#serviceAccount',
				"email": "default",
				"scopes": [
					"https://www.googleapis.com/auth/userinfo.email",
					"https://www.googleapis.com/auth/compute",
					"https://www.googleapis.com/auth/devstorage.full_control"
				]
			}
		],
		"metadata": {
			"items": []
		},
		"machineType": "%s/machineTypes/n1-standard-1" % (GCE_PROJECT_URL),
		"zone": "%s/zones/%s" % (GCE_PROJECT_URL, zone),
		"image": "%s/google/%s" % (GCE_URL, IMAGE) 
	}
	logging.debug(config)
	result = compute.instances().insert(project = PROJECT_ID, body = config).execute()
	logging.debug(result)

	# Clear instances cache:
	memcache.delete('instances')

	return True

def shutdownInstance(name): # Shut down a server with a specific IP.

	logging.debug('Shutting down instance ' + name)

	memcache.set("status-" + name, 'stopping')
	compute.instances().delete(project = PROJECT_ID, instance = name).execute()

	return True

class HttpRequestHandler(webapp.RequestHandler): # Class for handling incoming HTTP requests.

	def is_authorized(self):
		if users.is_current_user_admin():
			return True
		user = users.get_current_user()
		if user:
			self.response.out.write('<a href="' + users.create_logout_url(self.request.uri) + '">Not authorized.</a>')
		else:
			self.redirect(users.create_login_url(self.request.uri))
		return False

	def get(self): # The administration web page.
		if not self.is_authorized():
			return

		self.response.out.write('<h1>Administration</h1>')
		self.response.out.write('<p><a href="' + users.create_logout_url(self.request.uri) + '">Log out.</a></p>')

		# Output table with info on all current instances:
		self.response.out.write('<h2>Instances</h2>')
		self.response.out.write('<table><tr><th>Active in zonegroup</th><th>Name</th><th>IP</th><th>Zone</th>')
		for key, treshold in TRESHOLDS.iteritems():
			self.response.out.write('<th>%s (max %s)</th>' % (key, str(treshold['max'])))
		self.response.out.write('<th>Data</th></tr>')

		for instance in instances():
			self.response.out.write('<tr><form action="/" method="POST"><td>')
			for key, zonegroup in ZONEGROUPS.iteritems():
				if instance['zone'] in zonegroup:
					active = memcache.get('active-server-' + key)
					if active is not None and active['name'] == instance['name']:
						self.response.out.write(key)

			self.response.out.write('</td><td>%s</td><td>%s</td><td>%s</td>' % (instance['name'], instance['ip'], instance['zone']))
			instanceLoad = memcache.get('load-' + instance['name']) # Get the load for this server
			for key, treshold in TRESHOLDS.iteritems():
				self.response.out.write('<td>')
				if instanceLoad is not None and key in instanceLoad and instanceLoad[key]:
					self.response.out.write(instanceLoad[key] + ' (' + str(int(float(instanceLoad[key]) / float(treshold['max']) * 100.0)) + '%)')
				else:
					self.response.out.write('-')
				self.response.out.write('</td>')
			if instanceLoad is not None and 'data' in instanceLoad:
				self.response.out.write('<td>' + instanceLoad['data'] + '</td>')
			else:
				self.response.out.write('<td></td>')
			self.response.out.write('<td><input type="hidden" name="instance" value="%s" /><input type="submit" name="action" value="Shutdown" /></td></form></tr>' % (instance['name']));

		self.response.out.write('</table>')

		# Output form for manually starting new instances (which you normally would not do, this is for testing/debugging):
		self.response.out.write('<h3>Start new instance</h3>')
		self.response.out.write('<form method="POST" action="/">Start in zone: <select name="zone">')
		for zone in zones():
			self.response.out.write('<option value="' + zone['name'] + '">' + zone['name'] + '</option>')
		self.response.out.write('<input type="submit" name="action" value="Start" /></select></form>')

		# Debug stuff:
		#self.response.out.write(compute.machineTypes().list(project = PROJECT_ID).execute().get('items', []));
		# self.response.out.write(compute.networks().list(project = PROJECT_ID).execute().get('items', []));

		self.response.out.write('<h2>Report load</h2>')
		self.response.out.write('<h3>Example</h3>')
		self.response.out.write('<pre>curl -F action=report ')
		for key, treshold in TRESHOLDS.iteritems():
			self.response.out.write('-F ' + key + '=' + str(int(treshold['max'] / 100.0 * treshold['stop'])) + ' ')
		self.response.out.write('%s/report' % (self.request.host_url))

	def post(self):
		action = self.request.get('action')
		if action == 'report':
			loadReport(ip = self.request.remote_addr, load = {
				'connections': self.request.get('connections'),
				'traffic': self.request.get('traffic'),
				'messages': self.request.get('messages'),
				'data': self.request.get('data')
			})
		else:
			if not self.is_authorized():
				return
			if action == 'Start':
				startInstance(zone=self.request.get('zone'))
			elif action == 'Shutdown':
				shutdownInstance(name=self.request.get('instance'))
			self.response.set_status(303)
			self.response.headers['Location'] = '/'

def main():
	logging.getLogger().setLevel(logging.DEBUG)
	run_wsgi_app(webapp.WSGIApplication([('/', HttpRequestHandler), ('/report', HttpRequestHandler)], debug = True))

if __name__ == '__main__':
	main()
