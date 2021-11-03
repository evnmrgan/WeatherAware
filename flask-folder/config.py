import os
import configparser

# Read in configuration file

config = configparser.ConfigParser()
config.read('config/setup.cfg')

print(config.keys())

postgres_url = 'postgresql://'\
               + config["postgres"]["user"] + ':' + config["postgres"]["password"]\
               + '@' + config["postgres"]["host"] + ':' + config["postgres"]["port"] + '/' + config["postgres"]["database"]

secret_key = config["flask"]["secret_key"]
GoogleMapsKey = config["flask"]["GoogleMapsKey"]
GoogleMapsJSKey = config["flask"]["GoogleMapsJSKey"]
CassandraUser = config["cassandra"]["user"]
CassandraPassword = config["cassandra"]["password"]
# CassandraNode = config["cassandra"]["dns"]

print(postgres_url)

basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    DEBUG = False
    TESTING = False
    CSRF_ENABLED = True
    SECRET_KEY = secret_key
    SQLALCHEMY_DATABASE_URI = postgres_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GOOGLEMAPSKEY = GoogleMapsKey
    GOOGLEMAPSJSKEY = GoogleMapsJSKey
    CASSANDRA_USER = CassandraUser
    CASSANDRA_PASSWORD = CassandraPassword
    # CASSANDRA_NODES = CassandraNode


class ProductionConfig(Config):
    DEBUG = False


class StagingConfig(Config):
    DEVELOPMENT = True
    DEBUG = True


class DevelopmentConfig(Config):
    DEVELOPMENT = True
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
