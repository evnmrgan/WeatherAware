# WeatherAware

WeatherAware is a web application for monitoring key weather data at any location in the United States. 

It is a fork of Alex Gaiduk's AirAware application, which is used for pollution monitoring.

Screencast: Link here

## Table of contents
1. [Introduction](README.md#introduction)
2. [Practical significance](README.md#practical-significance)
3. [Data pipeline](README.md#data-pipeline)
    * [Data extraction](README.md#data-extraction)
    * [Data transformation](README.md#data-transformation)
    * [Data loading](README.md#data-loading)
4. [Challenges](README.md#challenges)
    * [Computation](README.md#computation)
    * [Storage](README.md#storage)
    * [Complex task automation](README.md#complex-task-automation)
5. [Technologies](README.md#technologies)

## Introduction

Pressure, temperature, wind, and humidity are primary factors determining the weather in a given location.

**Atmospheric pressure** is the downward force exerted by the air as a result of gravity. Low pressure systems bring clouds, wind, and precipitation, while high-pressure systems mean fairer, calmer weather.

**Temperature** measures the average speed of molecules in a substance. Temperature varies across the globe due to latitude, geography, ocean currents, and winds.

**Wind** is the movement of air across Earth's surface as the planet is unevenly heated by the sun. Winds blow to restore the balance of temperature and pressure across the globe.

**Humidity** measures the water vapor content of the air. Humidity helps determine precipitation and the volume of cloud formation.

## Practical significance

WeatherAware displays the vital monthly weather data for any United States location. For the chosen location, a user can download years of historical hourly data. The app could be useful for homeowners planning a move to a new location, pilots looking to understand the weather patterns in their flight path, or construction companies looking to determine the number of workable days in the year.

## Data pipeline

### Data extraction

The complete measurement data is available free of charge on [EPA website](https://aqs.epa.gov/aqsweb/airdata/download_files.html#Raw) for the years 1980-2021, measured every hour at all locations across US. The amount of data is ~10 Gb/year for years after 2000. The data is constantly updated. Extraction step consists in downloading data into an Amazon S3 storage bucket, then loading it into Spark's RDD object and cleaning it up.

### Data transformation

The main data transformation in this project is calculation of air quality levels at arbitrary grid points. The grid constructed in this work contains 100,000 points, ensuring sufficiently fine mesh, with any arbitrary U.S. address being at most ~15 miles away from one of the grid points. Computing pollution levels at grid points is a spacial inter(extra)polation problem, with several common ways to address it [[link](http://www.integrated-assessment.eu/eu/guidebook/spatial_interpolation_and_extrapolation_methods.html)]. Since the focus of this project is on the data pipelines rather than models, I decided to use more common inverse distance weighting to estimate pollution levels on the grid.

After the calculations, several metrics are computed, including averages and percentiles, to provide more detail about the air quality in the area.

### Data loading

Cleaned data, as well as various pollution metrics are loaded into the PostgreSQL database with PostGIS extension for an easier location-based search. Detailed data in the hourly resolution is also loaded into Cassandra database, to be used for historical data retrieval.

## Challenges

### Computation

Interpolation geospatial data is expensive---for each time step, around 50 million unique combinations of stations/grid points need to be considered, for each pollutant. In addition, each of these calculations involve computing distance between two geographical points, using 5 trigonometric function estimations. Doing these calculations brute-force would result in unacceptably long waiting times. To mitigate the computational cost, I precomputed distances between the grid points and stations, and used this information in my calculations.

### Storage

Once the computation for each given moment of time is complete, the resulting map overlay needs to be stored in the database for all the points on the map, as a time series. This means storing ~100,000 points for every hour in the day, for almost 40 years of observation history. Within this vast amount of data, my application needs to have a way to efficiently locate a grid point which is close to a given address.

Given these unique data organization challenges, a two-database storage scheme seems to be appropriate. A PostgreSQL database with PostGIS extension is used for quick location look-up and presenting rough aggregated historical data, and Cassandra distributed database is used for full historical data look-up, at hourly resolution.

### Complex task automation

EPA updates pollution data on hourly basis. Building automatic tools for ingesting the data, processing it, and updating tables in databases is a challenge that has to be addressed in my applications.

## Technologies

Taking into account the unique challenges of my project and technical trade-offs that had to be made when working on it, I designed the following data pipeline for my application:

1. Store raw sensory data obtained from EPA (Amazon S3)
2. Load EPA data into a Spark batch job; compute the pollution map, averages over long periods of time, and various analytic quantities;
3. Store computed map and aggregated quantities in a PostgreSQL database with PostGIS extension for quick location look-up; store full historical data at hourly resolution in a Cassandra database;
4. In a Flask application, use Google Maps API to find latitude and longitude of a given U.S. address; locate a grid point closest to it, and retrieve data for this grid point.

![Project's pipeline](./pipeline.png)
