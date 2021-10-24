import googlemaps
from flask import Flask
from flask import render_template, request, redirect
from flask import stream_with_context, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import text
from flask_cassandra import CassandraCluster
from datetime import datetime
from collections import OrderedDict
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

app = Flask(__name__)
app.config.from_object('config.DevelopmentConfig')
GoogleMapsKey = app.config["GOOGLEMAPSKEY"]
GoogleMapsJSKey = app.config["GOOGLEMAPSJSKEY"]
CassandraUser = app.config["CASSANDRA_USER"]
CassandraPassword = app.config["CASSANDRA_PASSWORD"]

cloud_config= {'secure_connect_bundle': '/Users/evanmorgan/CQL/secure-connect-epa-weather-history.zip'}
auth_provider = PlainTextAuthProvider(CassandraUser, CassandraPassword)

db = SQLAlchemy(app)
cluster = Cluster(cloud=cloud_config, auth_provider=auth_provider)
gmaps = googlemaps.Client(key=GoogleMapsKey)
API_url = "https://maps.googleapis.com/maps/api/js?key="\
        + GoogleMapsJSKey + "&callback=initMap"

# Parameter codes for weather variables
pressure_code = 64101 # 44201
wind_code = 61103 # 88101  # Federal reference methods
temp_code = 62101
humidity_code = 62201
pm_code = 64101 # 88502  # Non-federal reference methods

# Chicago coordinates as a default
chi = dict()
chi['lat'] = 41.8781136
chi['lon'] = -87.6297982

import models


def get_weather_records(session, data, grid_id, parameter):
    '''
    Add full historical data for weather code (parameter)
    at grid_id to a dictionary data
    '''
    cql = "SELECT * FROM weather.table_hourly WHERE grid_id = {} AND parameter = '{}'"
    cql_command = cql.format(grid_id, parameter)
    print(cql_command)
    records = list(session.execute(cql_command))

    for record in records:
        time = record.time.strftime('%Y-%m-%d %H:%M')
        if not data.get(time):
            data[time] = dict()
        data[time][parameter] = record.measurement


def get_weather_data(grid_id):
    # Connect to Cassandra database and obtain weather data
    session = cluster.connect()
    # session = cassandra.connect()
    print(session)
    session.set_keyspace("weather")

    data = dict()
    get_weather_records(session, data, grid_id, pressure_code)
    print(next(iter((data.items()))))
    get_weather_records(session, data, grid_id, wind_code)
    print(next(iter((data.items()))))
    get_weather_records(session, data, grid_id, temp_code)
    print(next(iter((data.items()))))
    get_weather_records(session, data, grid_id, humidity_code)
    print(next(iter((data.items()))))

    return OrderedDict(sorted(data.items(), key=lambda t: t[0]))


def get_measurements(record):
    '''
    Given record containing weather data, return streamlined record
    '''
    pressure = record.get(pressure_code, None)
    wind = record.get(wind_code, None)
    temp = record.get(temp_code, None)
    humidity = record.get(humidity_code, None)

    return ['{:.2f}'.format(pressure) if pressure is not None else '',
            '{:.2f}'.format(wind) if wind is not None else '',
            '{:.2f}'.format(temp) if temp is not None else '',
            '{:.2f}'.format(humidity) if humidity is not None else '']
            

def make_csv(grid_id):
    '''
    This function makes csv file with the full weather history for a given grid point
    '''
    # OrderedDict assembled from Cassandra
    data = get_weather_data(grid_id)

    yield ",".join(["Timestamp", "Pressure [mbar]", "Wind [mph]", "Temp [F]", "Humidity [%]"]) + '\n'
    for timestep, record in data.items():
        yield ","\
            .join([item for sublist in [[timestep], get_measurements(record)]
                  for item in sublist]) + '\n'


def get_coordinates_from_address(address_request):
    '''
    This function converts address to coordinates using Google Maps API call
    '''
    geocode_result = gmaps.geocode(address_request)

    # Some defaults
    error_message = 'Please enter a valid U.S. address'
    formatted_address = None
    coordinates = None
    latitude, longitude = None, None

    if len(geocode_result) == 0:
        return chi['lat'], chi['lon'], error_message

    address = geocode_result[0]
    # Check if the address is in the U.S.
    try:
        formatted_address = address['formatted_address'].lower()
    except (TypeError, KeyError):
        return chi['lat'], chi['lon'], error_message

    if 'usa' in formatted_address or 'puerto rico' in formatted_address:
        try:
            coordinates = address["geometry"]["location"]
        except (TypeError, KeyError):
            return chi['lat'], chi['lon'], error_message

    if coordinates:
        latitude = coordinates["lat"]
        longitude = coordinates["lng"]
    else:
        return chi['lat'], chi['lon'], error_message

    return latitude, longitude, ''


@app.route('/download', methods=['GET', 'POST'])
def download():

    if request.method == 'GET':
        return redirect('/')

    elif request.method == 'POST':
        grid_id = request.form['grid_id']
        return Response(
            stream_with_context(make_csv(grid_id)),
            mimetype='text/csv',
            headers={
                "Content-Disposition":
                "attachment; filename=data_grid_{}.csv".format(grid_id)
            }
        )


@app.route('/', methods=['GET', 'POST'])
def dashboard():

    def request_from_location(latitude, longitude, error_message=''):
        '''
        This function prepares Http request object,
        based on user's location input
        '''
        sql = text(
            """
            SELECT ST_Distance(location, 'POINT({longitude} {latitude})'::geography) as d, grid_id, longitude, latitude
            FROM grid ORDER BY location <-> 'POINT({longitude} {latitude})'::geography limit 10000;
            """.format(**locals())
        )
        print(sql)
        nearest_grid_points = db.engine.execute(sql).fetchall()
        print(nearest_grid_points[0:10])

        for i in range(0, len(nearest_grid_points)):
            grid_id = nearest_grid_points[i][1]
            history_measurements = models.measurements_monthly\
                .query.filter_by(grid_id=grid_id)\
                .order_by(models.measurements_monthly.time.asc()).all()

            if not history_measurements:
                # The grid point we found does not contain any historical
                # data (for example, it is far from any air quality station)
                continue

            else:
                pressure = [x for x in history_measurements if x.parameter == pressure_code]
                pressure_data = [[1000*int(x.time.strftime('%s')), round(x.c,2)] for x in pressure]

                wind = [x for x in history_measurements if x.parameter == wind_code]
                wind_data = [[1000*int(x.time.strftime('%s')), round(x.c,2)] for x in wind]
                
                temp = [x for x in history_measurements if x.parameter == temp_code]
                temp_data = [[1000*int(x.time.strftime('%s')), round(x.c,2)] for x in temp]

                humidity = [x for x in history_measurements if x.parameter == humidity_code]
                humidity_data = [[1000*int(x.time.strftime('%s')), round(x.c,2)] for x in humidity]
                
                print(len(pressure_data))

                if len(pressure_data) == 0 or len(wind_data) == 0 or len(temp_data) == 0 or len(humidity_data) == 0:
                    rendered_webpage = request_from_location(
                            chi['lat'],
                            chi['lon'],
                            'Location you entered is too far from air quality monitors'
                        )
                    return rendered_webpage

                # Set up charts
                chart_type = 'line'
                chart_height = 350
                chart_pressure = {"renderTo": 'chart_pressure', "type": chart_type, "height": chart_height}
                chart_wind = {"renderTo": 'chart_wind', "type": chart_type, "height": chart_height}
                chart_temp = {"renderTo": 'chart_wind', "type": chart_type, "height": chart_height}
                chart_humidity = {"renderTo": 'chart_humidity', "type": chart_type, "height": chart_height}
                series_pressure = [{'pointInterval': 30 * 24 * 3600 * 1000, "name": 'Pressure', "data": pressure_data}]
                series_wind = [{'pointInterval': 30 * 24 * 3600 * 1000, "name": 'Wind', "data": wind_data}]
                series_temp = [{'pointInterval': 30 * 24 * 3600 * 1000, "name": 'Temp', "data": temp_data}]
                series_humidity = [{'pointInterval': 30 * 24 * 3600 * 1000, "name": 'Humidity', "data": humidity_data}]
                break

        return render_template(
            'dashboard.html', chart_pressure=chart_pressure, chart_wind=chart_wind, 
            chart_temp=chart_temp, chart_humidity=chart_humidity,
            series_pressure=series_pressure, series_wind=series_wind,
            series_temp=series_temp, series_humidity=series_humidity,
            lat=latitude, lon=longitude, grid_id=grid_id, API_url=API_url,
            error_message=error_message
        )

    if request.method == 'GET':
        # Default coordinates in Chicago downtown
        rendered_webpage = request_from_location(chi['lat'], chi['lon'])
        return rendered_webpage

    elif request.method == 'POST':

        # Get address entered by the user
        address_request = request.form['address']

        # Obtain geolocation results from Google Maps
        latitude, longitude, error_message =\
            get_coordinates_from_address(address_request)

        rendered_webpage =\
            request_from_location(latitude, longitude, error_message=error_message)

        return rendered_webpage


@app.route('/about', methods=['GET'])
def about():
    return redirect("https://github.com/evnmrgan/WeatherAware")


@app.route('/slides', methods=['GET'])
def slides():
    return redirect("https://docs.google.com/presentation/d/1BWLKoafapgM5VxpgU_nHYCeJLk38wu1VACwECdN8RIo")


@app.route('/github', methods=['GET'])
def github():
    return redirect("https://github.com/evnmrgan")


if __name__ == '__main__':
    # app.debug = True
    # app.run(host='0.0.0.0')
    app.run(debug=True)