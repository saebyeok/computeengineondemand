from md5 import md5
import webapp2
import logging
from google.appengine.api import users
from google.appengine.ext import db
from django.utils import simplejson as json
import dictproperty
from google.appengine.api import memcache
import time
import collections

class TurnConfig(db.Model):
	sites = dictproperty.DictProperty()

def turnconf():
	c = TurnConfig.get_by_key_name("turnconfig")
	if not c:
		c = TurnConfig(key_name = "turnconfig")
		c.sites = {
			"localhost": {
				"origins": [
					"http://localhost",
					"http://127.0.0.1"
				],
				"key": "" # Empty key means the key will not be checked.
			}
		}
	return c

def originToKey(origin):
	otk = memcache.get('turn-otk-cache')
	if otk is None:
		c = turnconf()
		otk = {}
		for sitename, siteconfig in c.sites.iteritems(): # Loop through all thresholds and test them:
			for o in siteconfig["origins"]:
				otk[o] = siteconfig["key"]
		memcache.set('turn-otk-cache', json.dumps(otk))
	else:
		otk = json.loads(otk)
	if origin not in otk:
		return None
	return otk[origin]
		
class TurnAdminRequestHandler(webapp2.RequestHandler):

	def is_authorized(self):
		if users.is_current_user_admin():
			return True
		user = users.get_current_user()
		if user:
			self.response.out.write('<a href="' + users.create_logout_url(self.request.uri) + '">Not authorized.</a>')
		else:
			self.redirect(users.create_login_url(self.request.uri))
		return False

	def get(self):
		if not self.is_authorized():
			return

		self.response.out.write('<h1>TURN Admin</h1>')
		self.response.out.write('<p>Site name is not used for anything (just an identifier). The key can be any string that fits as GET variable in an URL. If the key is an empty string, then the key will not be checked for those origins (any key will be allowed), which is good for dev origins like 127.0.0.1 or localhost.</p>')
		self.response.out.write('<table><tr><th>Site name</th><th>Key</th><th>Origins</th></tr>')
		c = turnconf().sites
		ordered = collections.OrderedDict(sorted(c.items()))
		for sitename, siteconfig in ordered.iteritems(): # Loop through all thresholds and test them:
			self.response.out.write('<tr><td>' + sitename + ' <form action="/turnadmin" method="POST"><input type="hidden" name="site" value="' + sitename + '" /><input type="submit" name="action" value="Remove site" /></form></td><td><form action="/turnadmin" method="POST"><input type="text" name="key" value="' + siteconfig["key"] + '" /><input type="hidden" name="site" value="' + sitename + '" /><input type="submit" name="action" value="Change key" /></form></td><td>')
			for o in siteconfig["origins"]:
				self.response.out.write('<form action="/turnadmin" method="POST"> ' + o + '<input type="hidden" name="site" value="' + sitename + '" /><input type="hidden" name="origin" value="' + o + '" /><input type="submit" name="action" value="Remove origin" /></form></td></tr><tr><td></td><td></td><td>')
			self.response.out.write('<form action="/turnadmin" method="POST"><nobr>Add: <input type="hidden" name="site" value="' + sitename + '" /><input type="text" name="origin" /><input type="submit" name="action" value="Add Origin" /></nobr></form></td></tr>')
		self.response.out.write('</table>')
		self.response.out.write('<h3>Add site</h3><form action="/turnadmin" method="POST">Site name: <input type="input" name="site" /><input type="submit" name="action" value="Add site" /></form>')

	def post(self):
		if not self.is_authorized():
			return

		action = self.request.get('action')
		if action == 'Add Origin':
			if self.request.get('origin') != "":
				c = turnconf()
				if self.request.get('site') in c.sites:
					c.sites[self.request.get('site')]["origins"].append(self.request.get('origin'))
				c.put()
				memcache.delete('turn-otk-cache')

		elif action == 'Remove origin':
			c = turnconf()
			if self.request.get('site') in c.sites:
				neworigins = []
				for o in c.sites[self.request.get('site')]["origins"]:
					if o != self.request.get('origin'):
						neworigins.append(o)
				c.sites[self.request.get('site')]["origins"] = neworigins;
				c.put()
				memcache.delete('turn-otk-cache')

		elif action == 'Change key':
			c = turnconf()
			if self.request.get('site') in c.sites:
				c.sites[self.request.get('site')]["key"] = self.request.get('key')
				c.put()
				memcache.delete('turn-otk-cache')

		elif action == 'Add site':
			c = turnconf()
			if self.request.get('site') not in c.sites:
				if self.request.get('site') != '':
					c.sites[self.request.get('site')] = {
						"key": "secret",
						"origins": [ "http://example.org", "https://www.example.com" ]
					}
					c.put()
					memcache.delete('turn-otk-cache')

		elif action == 'Remove site':
			c = turnconf()
			if self.request.get('site') in c.sites:
				c.sites.pop(self.request.get('site', None))
				c.put()
				memcache.delete('turn-otk-cache')

		elif action == 'Change key':
			c = turnconf()
			if self.request.get('site') in c.sites:
				c.sites[self.request.get('site')]["key"] = self.request.get('key')
				c.put()
				memcache.delete('turn-otk-cache')

		self.response.set_status(303)
		self.response.headers['Location'] = '/turnadmin'

class TurnRequestHandler(webapp2.RequestHandler):

	def get(self):
		key = self.request.get('key')
		if not 'Origin' in self.request.headers:
			return self.response.out.write('{ \"error\":\"No origin.\" }')
		else:

			correctKey = originToKey(self.request.headers['Origin'])
			if correctKey is None:
				self.response.out.write('{ \"error\":\"Origin not allowed.\", \"origin\":\"%s\" }' % (self.request.headers['Origin']))
				return
				
			if correctKey != "" and key != correctKey:
				self.response.out.write('{ \"error\":\"Key error.\" }')
				return

			self.response.headers.add_header("Access-Control-Allow-Origin", self.request.headers['Origin'])

		if not self.request.headers['User-Agent'].startswith('Mozilla'):
			self.response.out.write('{ \"error\":\"Get yourself a web browser!\" }')
			return

		username = self.request.get('username')
		if username is None or username == '':
			self.response.out.write('{ \"error\":\"Username error.\" }')
			return

		geo = 'us-central' # Anything west of Iceland or east of India is America. The rest is Europe'
		if 'X-Appengine-Citylatlong' in self.request.headers and int(round(float(self.request.headers['X-Appengine-Citylatlong'].split(',')[1]), 0)) in range(-25,90):
			geo = 'europe-west'
		instance = memcache.get("active-server-" + geo)
		instanceLoad = memcache.get('load-' + instance['name'])
		shared_key = instanceLoad['data']

		timestamp = str(time.mktime(time.gmtime())).split('.')[0]
		username = username + '-' + timestamp;
		self.response.out.write("{ \"username\":\"%s\", \"uris\": [ \"turn:%s:3478?transport=udp\", \"turn:%s:3478?transport=tcp\" ], \"password\":\"%s\", \"ttl\":86400 }" % (username, instance['ip'], instance['ip'], md5(username + ":" + shared_key).hexdigest()))

logging.getLogger().setLevel(logging.DEBUG)
app = webapp2.WSGIApplication([('/turn', TurnRequestHandler), ('/turnadmin', TurnAdminRequestHandler)], debug=True)

