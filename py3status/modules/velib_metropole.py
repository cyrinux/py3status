# -*- coding: utf-8 -*-
"""
Display Velib shared bike avaibility on our favorite stations.
Use https://www.velib-metropole.fr/map data.

You only need to set id of stations you want to monitor in station_codes param.
Then scroll to cycle stations, and middle clic to force a refresh.

Configuration parameters:
    button_next: Display next station (default 4)
    button_previous: Display previous station (default 5)
    cache_timeout: The time between API polling in seconds
        It is recommended to keep this at a higher value to avoid rate
        limiting with the API's. (default 60)
    format: How to display the velib data.
        (default '{format_station} {index}/{stations}')
    format_station: How to display the velib station data.
        *(default '{station_name}: [\?color=station_state_code {station_state}]'
        '[\?soft  ][\?color=greenyellow {nb_bike}/{nb_free_e_dock}]'
        '[\?soft  ][\?color=deepskyblue {nb_ebike}/{nb_free_e_dock}]')*
    station_codes: List of velib stations to monitor.
        You can get stations id on map here https://www.velib-metropole.fr/map
        (default [20043, 11014, 20012, 20014, 10042])
    thresholds: Configure colors of format station.
        (default [(0, 'good'), (1, 'bad')])

Format placeholders:
    {format_station}            format for station details
    {index}                     current index of displayed station, eg 1
    {stations}                  count of stations find in station_codes, eg 12

format_station placeholders:
    {credit_card}               station take credit card?, eg 'no'
    {density_level}             density level of the station, eg 1
    {kiosk_state}               kiosk in working?, eg 'yes'
    {max_bike_overflow}         max overflow bike, eg 33
    {nb_bike} current           available bike, eg 3
    {nb_bike_overflow}          current number of bike in overflow, eg 0
    {nb_dock}                   number of dock, eg 0
    {nb_e_bike_overflow}        current overflow bike, eg 0
    {nb_e_dock}                 number of electric dock, eg 33
    {nb_ebike}                  current number of electric bike, eg 0
    {nb_free_dock}              current available bike places, eg 0
    {nb_free_e_dock}            current available electric bike places, eg 30
    {overflow}                  station support overflow, eg 'no'
    {overflow_activation}       current state of overflow support, eg 'no'
    {station_code}              station code, eg 10042
    {station_due_date}          station due date timestamp, eg 1527717600 (?)
    {station_due_date_s}        station due date, eg '2018-05-31T00:00:00' (?)
    {station_gps_latitude}      station gps latitude, eg 48.87242006305313
    {station_gps_longitude}     station gps longitude, eg 2.348395236282807
    {station_name}              station location name, eg 'Enghien - Faubourg Poissonnière'
    {station_state}             current station state, eg 'Operative'
    {station_state_code}        current station state code, eg '0'
    {station_type}              station type, eg 'yes' (?)

"""
from datetime import datetime
from re import sub
from time import time

STRING_MISSING_STATIONS = "No velib stations set"
VELIB_ENDPOINT = "https://www.velib-metropole.fr/webapi/map/details"


class Py3status:
    """
    """

    # available configuration parameters
    button_next = 4
    button_previous = 5
    cache_timeout = 60
    format = "{format_station} {index}/{stations}"
    format_station = (
        "{station_name}: [\?color=station_state_code {station_state}]"
        "[\?soft  ][\?color=greenyellow {nb_bike}/{nb_free_e_dock}]"
        "[\?soft  ][\?color=deepskyblue {nb_ebike}/{nb_free_e_dock}]"
    )
    station_codes = [20043, 11014, 20012, 20014, 10042]
    thresholds = [(0, "good"), (1, "bad")]

    class Meta:
        update_config = {
            "update_placeholder_format": [
                {
                    "placeholder_formats": {
                        "density_level": ":.0f",
                        "max_bike_overflow": ":.0f",
                        "nb_bike": ":.0f",
                        "nb_bike_overflow": ":.0f",
                        "nb_dock": ":.0f",
                        "nb_e_bike_overflow": ":.0f",
                        "nb_e_dock": ":.0f",
                        "nb_ebike": ":.0f",
                        "nb_free_dock": ":.0f",
                        "nb_free_e_dock": ":.0f",
                        "station_gps_latitude": ":.3f",
                        "station_gps_longitude": ".3f",
                        "station_due_date": ".0f",
                    },
                    "format_strings": ["format_station"],
                }
            ]
        }

    def post_config_hook(self):
        if not self.station_codes:
            raise Exception(STRING_MISSING_STATIONS)

        # string to list if necessary
        if not isinstance(self.station_codes, list):
            self.station_codes = [self.station_codes]

        # take the whole map for first run
        # default values take all stations
        # around Paris
        # Area is then shrink to only get
        # specified stations
        self.gps_dict = {
            "gpsTopLatitude": 49.0,
            "gpsTopLongitude": 2.5,
            "gpsBotLatitude": 48.6,
            "gpsBotLongitude": 2.2,
            "zoomLevel": 15,
        }
        self.toggled = False
        self.idle_time = 0
        self.request_timeout = 10
        self.station_states = {"Operative": 0, "Close": 1}
        self.station_index = 1
        self.stations = {}
        self.optimal_area = False
        self.first_start = True
        self.button_refresh = 2

        # get placeholders
        self.placeholders = []
        for x in [self.format, self.format_station]:
            self.placeholders += self.py3.get_placeholders_list(x)
        self.placeholders += ["station_gps_latitude", "station_gps_longitude"]

    def _camel_to_snake_case(self, data):
        if not isinstance(data, (int, float)):
            s1 = sub("(.)([A-Z][a-z]+)", r"\1_\2", data)
            return sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
        else:
            return data

    def _cast_number(self, value):
        try:
            value = float(value)
        except ValueError:
            try:
                value = int(value)
            except ValueError:
                pass
        return value

    def _set_optimal_area(self, data):
        """
        reduce the zone to reduce the size of fetched data on refresh
        """

        latitudes = []
        longitudes = []

        for x in data:
            latitudes.append(float(data[x]["station_gps_latitude"]))
            longitudes.append(float(data[x]["station_gps_longitude"]))

        self.gps_dict.update(
            {
                "gpsTopLatitude": max(latitudes),
                "gpsTopLongitude": max(longitudes),
                "gpsBotLatitude": min(latitudes),
                "gpsBotLongitude": min(longitudes),
            }
        )
        self.optimal_area = True

    def _get_velib_data(self):
        try:
            return self.py3.request(
                VELIB_ENDPOINT, params=self.gps_dict, timeout=self.request_timeout
            ).json()
        except self.py3.RequestException:
            return None

    def _manipulate(self, data):
        new_data = {}
        stations = []

        for code in self.station_codes:
            new_station = {}

            # search station
            station = next(
                (item for item in data if int(item["station"]["code"]) == int(code)),
                None,
            )

            # flat, camel to snake and cast...
            for key, value in self.py3.flatten_dict(station, delimiter="_").items():
                key = self._camel_to_snake_case(key)
                if key in self.placeholders:
                    new_station[key] = self._cast_number(value)

            # station_due_date_s: station due date in dateime iso format
            if all("station_due_date" in list for list in [new_station, self.placeholders]):
                station_due_date = datetime.fromtimestamp(
                    new_station["station_due_date"]
                )
                new_station.update({"station_due_date_s": station_due_date.isoformat()})

            # station_state_code: station code for thresholds
            if all("station_state" in list for list in [new_station, self.placeholders]):
                new_station.update(
                    {
                        "station_state_code": int(
                            self.station_states[new_station["station_state"]]
                        )
                    }
                )

            stations.append(new_station)

        # forge return
        for index, station in enumerate(stations, 1):
            new_data[index] = station

        return new_data

    def velib_metropole(self):
        # refresh
        current_time = time()
        refresh = current_time >= self.idle_time

        # time
        if refresh:
            self.idle_time = current_time + self.cache_timeout
            cached_until = self.cache_timeout
        else:
            cached_until = self.idle_time - current_time

        if not self.toggled and not refresh:
            self.toggled = False
            data = self.velib_metropole_data
        else:
            data = self.velib_metropole_data = self._get_velib_data()

        if self.first_start:
            data = self.velib_metropole_data = self._get_velib_data()

        if data:
            self.stations = self._manipulate(data)
            if not self.optimal_area:
                self._set_optimal_area(self.stations)

        self.number_of_stations = len(self.stations) or 0

        if not self.stations:
            velib_data = {"index": 1, "stations": 0, "format_station": {}}
        else:
            # reset station_index counter
            if self.station_index == 0:
                self.station_index = 1

            # thresholds TODO: FIX ME
            for x in self.thresholds:
                if x in self.stations[self.station_index]:
                    self.py3.threshold_get_color(
                        self.stations[self.station_index][x], x
                    )

            # forge data output
            velib_data = {
                "stations": self.number_of_stations,
                "format_station": self.py3.safe_format(
                    self.format_station, self.stations[self.station_index]
                ),
                "index": self.station_index,
            }

        self.first_start = False

        return {
            "cached_until": self.py3.time_in(cached_until),
            "full_text": self.py3.safe_format(self.format, velib_data),
        }

    def on_click(self, event):
        button = event["button"]
        self.toggled = False
        if button == self.button_next:
            self.station_index += 1
            self.station_index %= self.number_of_stations + 1
        elif button == self.button_previous:
            self.station_index -= 1
            self.station_index %= self.number_of_stations + 1
        elif button == self.button_refresh:
            self.toggled = True
            self.idle_time = 0
        else:
            self.py3.prevent_refresh()


if __name__ == "__main__":
    """
    Run module in test mode.
    """
    from py3status.module_test import module_test

    module_test(Py3status)
