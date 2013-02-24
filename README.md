computeengineondemand
=====================

This Google AppEngine application will start and stop Google Compute Engine instances on demand.

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


