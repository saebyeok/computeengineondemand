computeengineondemand
=====================

This Google AppEngine application will start and stop Google Compute Engine instances on demand.

How it works
------------

### Tresholds

In the Python code, we are defining what to check when deciding wheather to start or stop instances.

	TRESHOLDS = {
		'connections': { 'max': 2000, 'slope': 98, 'start': 95, 'stop': 90 },
		'traffic': { 'max': 100000000, 'slope': 98, 'start': 95, 'stop': 90 },
		'messages': { 'max': 10000, 'slope': 98, 'start': 95, 'stop': 90 }
	}

> TODO: It would be nice with a web configuration interface for this, instead of hard coded variables in Python.

### Instances reporting load

Compute Engine instances should report their current load to computeengineondemand. That can be made just using Curl in a cronjob.

	curl -F action=report -F connections=1800 -F messages=9000 -F traffic=90000000 http://APPENGINE_ID.appspot.com/report

Computeengineondemand will know which instance is reporting by the IP address.

What HTTP POST variables to report (the load) is defined by the TRESHOLD configuration variable (see above).

### Zone Groups

In the configuration, you group any number of Compute Engine zones into a *zone group*, like this:

	ZONEGROUPS = {
		'europe': [ 'europe-west1-a', 'europe-west1-b' ],
		'america': [ 'us-central1-a', 'us-central1-b', 'us-central2-a' ]
	}

Load will be tested per group zone, so if you need more instances running in Europe, new instances will start up in any of the zones in Europe.

> TODO: Currently, instances are started in any random zone within the zone group, but we would like to do this with regard to scheduled downtime.

### Active instance

In each zone group, one server instance will be designated *active instance*. That is an instance that currently can handle new incoming connections without hitting the tresholds. So, in the ZONEGROUP configuration example above, there will be two active instances: One for the zone group *europe* and one for the zone group *america*.

When the active instance in a zone group is changed, you may announce this to other servers. All addresses defined in the array ANNOUNCE_URLS will get a HTTP POST request with the IP of the currently active instances.

	ANNOUNCE_URLS = [
		'http://example.org/gce_announce',
		'http://example.appspot.com/whatever'
	]


Setup / Install
---------------

Clone the git repository for this project to your computer:

	$ git clone REPOSITORY-URL

Install [Google API Python Client with dependencies for App Engine](http://code.google.com/p/google-api-python-client/downloads/list).
Visit the download page, find "Full Dependecies Build for Google App Engine Projects" and download it into the root of your repository, for example:

	$ wget http://google-api-python-client.googlecode.com/files/google-api-python-client-gae-1.0.zip

Unzip it into the root of your repository:

	$ unzip google-api-python-client-gae-1.0.zip

You will need to make three configuration changes before deploying:

* `app.yaml`: Change the value of `application:` to your App Engine application ID.
* `main.py`: Change the value of `PROJECT_ID` to your project id which has GCE enabled.

Give your App Engine application's service account `edit` access to your GCE project:

* Log into the App Engine Admin Console.
* Click on the application you want to authorize.
* Click on Application Settings under the Administration section on the left-hand side.
* Copy the value under Service Account Name. This is the service account name of your application, in the format application-id@appspot.gserviceaccount.com. If you are using an App Engine Premier Account, the service account name for your application is in the format application-id.example.com@appspot.gserviceaccount.com.
* Use the Google APIs Console to add the service account name of the app as a team member to the project. Give the account `edit` permission.

Deploy the application to App Engine:

	$ appcfg.py update .

> Note: Because this application is using GAE app identity for authentication to GCE, it will not work on the local development server.


