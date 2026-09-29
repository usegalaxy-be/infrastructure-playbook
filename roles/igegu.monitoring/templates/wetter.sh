#!/bin/bash
file=`mktemp`
curl --silent "https://api.openweathermap.org/data/2.5/weather?id=2925177&appid={{ owm_api_key }}" > $file
TEMP=`cat $file | jq .main.temp`
TEMP_MIN=`cat $file | jq .main.temp_min`
TEMP_MAX=`cat $file | jq .main.temp_max`
PRESSURE=`cat $file | jq .main.pressure`
HUMIDITY=`cat $file | jq .main.humidity`
WIND_SPD=`cat $file | jq .wind.speed`
WIND_DEG=`cat $file | jq .wind.deg`
CLOUDINESS=`cat $file | jq .clouds.all` # % cloudiness

echo "wetter temp=$TEMP,temp_min=$TEMP_MIN,temp_max=$TEMP_MAX,pressure=$PRESSURE,humidity=$HUMIDITY,wind.spd=$WIND_SPD,wind.deg=$WIND_DEG,cloudiness=$CLOUDINESS"

rm -f $file;
