# api_atbqt
uwsgi-2.0.23 requires: libxml2-dev
and needs python 3.11

run before starting in the app driectory
export APP_BASE=$(pwd)

run: `uwsgi --ini uwsgi.ini`

To reload use:
```
kill -HUP `cat /tmp/api_atbqt.pid`
```
for dev run: `flask_app.run(debug=True)`

docker build -t my_flask_app .
docker run -d -p 8080:8080 my_flask_app