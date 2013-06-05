computeengineondemand
=====================

This Google AppEngine application will start and stop Google Compute Engine instances on demand.

How it works
------------

### Zone Groups

Load will be tested per group.

> TODO: Currently, instances are started in any random zone within the zone group, but we would like to do this with regard to scheduled downtime.

### Active instance

In each zone group, one server instance will be designated *active instance*. That is an instance that currently can handle new incoming connections without hitting the thresholds.

When the active instance in a zone group is changed, you may announce this to other servers (announce URLs).

### Thresholds

You can add any number of measure points and call them anything you like, for example `connections`, `traffic`, `messages` or `cpu`.

For each measure point, you must set:

* `max` = The maximum allowed number. When an *active instance* hits this number, another instance will become active.
* `slope` = If this server previously has the `max` and stopped being *active*, it must go down to this percentage of `max` until it can become the *active instance* again.
* `start` = When the least loaded instance hits this percentage of `max`, then start a new instance. This new instance will not become active immediately, it is just started at this point to be prepared when the previously active server hits `max`.
* `stop` = If any instance has less than this percentage of `max`, inactive instances should be shut down.

### Instances reporting load

Compute Engine instances should report their current load to computeengineondemand. That can be made just using Curl in a cronjob.

For example:

	curl -F action=report -F connections=1800 -F messages=9000 -F traffic=90000000 http://APPENGINE_ID.appspot.com/report

Computeengineondemand will know which instance is reporting by the IP address.

What HTTP POST variables to report (the load) is defined by the measure poins configuration in the admin.

### Pushing arbitrary instance data

Active instances may push arbitrary data to the announce servers. When reporting load, instances could add a POST variable called `data`. That information would then be sent to all announce URL if this instance is the *active instance* in it's zone group.

	curl -F action=report -F connections=1800 -F messages=9000 -F traffic=90000000 -F data="some data that is important" http://APPENGINE_ID.appspot.com/report

Setup / Install
---------------

Clone the git repository for this project to your computer:

	$ git clone REPOSITORY-URL

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


