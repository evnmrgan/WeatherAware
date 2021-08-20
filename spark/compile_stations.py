import json
import csv
from dateutil import parser
from io import StringIO
from math import radians, sin, cos, sqrt, asin
import configparser

from pyspark import SparkContext, SparkConf

'''
True for a string that represents a nonzero float or int
This function is used to test our latitude and longitude values

Parameters
----
string: string, required
        String representing the property value

Returns
----
float
        If string can be represented as a valid nonzero float
    None
        Otherwise
'''

'''
This function splits station record efficiently using csv packages

Input
----
station_record: str
        One line containing air monitor reading

Returns
----
tuple
        Tuple characterizing station (station_id, latitude, longitude)
'''

'''
Compute distance between two geographical adjacent_grid_points
Source: https://rosettacode.org/wiki/Haversine_formula#Python

'''

'''
Determine the list of stations within 30 miles of the current stations

Parameters
----
rdd: RDD
        RDD of air monitor readings

Returns
----
RDD
        RDD of air monitor reading transformed to nearest grid points
'''
def valid_nonzero_float(string):
    try:
        number = float(string)
        if number != 0.:
            return number
        else:
            return None
    except ValueError:
        return None

def parse_station_record(station_record):
    f = StringIO(station_record)
    reader = csv.reader(f, delimiter=',')
    record = next(reader)
    
    state_id = record[0]
    
    # Filter out header, Canada, Mexico, US Virgin Islands, and Guam
    if state_id in ['State Code', 'CC', '80', '78', '66']:
        return None
    
    county_id = record[1]
    site_number = record[2]
    station_id = '|'.join([state_id, county_id, site_number])
    
    latitude = valid_nonzero_float(record[3])
    longitude = valid_nonzero_float(record[4])
    
    if not latitude or not longitude:
        return None
    
    datum = record[5]
    
    if datum not in ['WGS84', 'NAD83']:
        # Filter out old or malformed geospatial coordinates
        return None
    
    closed = record[10]
    if closed:
        closed_date = parser.parse(closed)
        history_span = parser.parse('1980-01-01')
        # Do not consider stations closed before January 1, 1980
        if closed_date < history_span:
            return None
    
    return(station_id, latitude, longitude)
    
def calc_distance(lat1, lon1, lat2, lon2):
    R = 3959. # Earth's radius in miles
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    lat1 = radians(lat1)
    lat2 = radians(lat2)
    a = sin(delta_lat / 2.0) ** 2 + \
        cos(lat1) * cos(lat2) * sin(delta_lon / 2.0) ** 2
    c = 2 * asin(sqrt(a))
    return R * c
    
def determine_grid_point_neighbors(rdd):
    d_cutoff = 30.
    precision = 1 # Store one decimal point for distance in miles
    station_id = rdd[0]
    station_latitude = rdd[1]
    station_longitude = rdd[2]
    adjacent_grid_points = {}
    # Loop over the entire 350,000-point grid
    # Return all grid points closer than 30 miles
    for grid in GRID:
        grid_id = grid["id"]
        grid_longitude = grid["lon"]
        grid_latitude = grid["lat"]
        d = calc_distance(grid_latitude, grid_longitude,
                            station_latitude, station_longitude)
        if d < d_cutoff:
            adjacent_grid_points[grid_id] = round(d, precision)
    return (station_id, adjacent_grid_points)

def main():
    # Read in data from the configuration files

    config = configparser.ConfigParser()
    config.read('config/setup.cfg')

    bucket_name = config["s3"]["bucket"]
    s3 = 's3a://' + bucket_name + '/'

    # conf = SparkConf().setMaster('local')
    # sc = SparkContext(conf=conf)
  
    # Create Spark context and session
    conf = SparkConf().set("spark.jars.packages", "org.apache.hadoop:hadoop-aws:3.2.0,com.datastax.spark:spark-cassandra-connector_2.12:3.0.1")\
                      .set("spark.hadoop.fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.AnonymousAWSCredentialsProvider")\

    sc = SparkContext(conf=conf)

    # sc = SparkContext(spark_url, "Batch")
  
    # Read in json containing grid

    with open('grid.json', 'r') as f:
        raw_json = f.readline()

    global GRID
    GRID = json.loads(raw_json)

    # This is the file of measurement stations from the EPA
    data_file = 'aqs_sites.csv'
    raw = s3 + data_file

    data_rdd = sc.textFile(raw, 3)

    stations = data_rdd.map(parse_station_record)\
                       .filter(lambda line: line is not None)\
                       .map(determine_grid_point_neighbors)\
                       .collectAsMap()

    with open('stations.json', 'w') as f:
        json.dump(stations, f)

if __name__ == '__main__':
    main()
