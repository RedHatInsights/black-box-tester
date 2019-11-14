"""Cachet Update Daemon
This script is a daemon that handles incoming webhooks from Alertmanager.
Each webhook should represent a test suite for a component represented
in the Cachet status page.

The only configuration that needs to be done is to export the cachet
URL and the cachet X token as ENV variables.  Example:

export CACHET_URL="cachet.cachet.svc"
export CACHET_TOKEN="fXPydfUD3c1aBUGiQnSb"
"""
import json
import os
import logging
import requests
from flask import Flask, request

APP = Flask(__name__)
CACHET_IDS = ""
CACHET_URL = os.getenv("CACHET_URL")
CACHET_TOKEN = os.getenv("CACHET_TOKEN")
logging.basicConfig(level='INFO', format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
logger = logging.getLogger(__name__)

@APP.route('/', methods=['POST'])
def handle_alert():
    """ This function handles incoming post calls from the Alertmanager
    webhook. After receiving the post from AM it reaches out to Cachet
    and builds a map of it's components. Once the components are
    searched and the component from the alert is located it updates said
    component with the proper status.
    """
    alert_in = json.loads(request.data)
    logging.info("Dumping incoming JSON from Alertmanager:")
    logging.info(str(json.dumps(alert_in, indent=4)))
    status = alert_in["status"]
    logging.info("Root Status is: %s", str(status))
    for status_in in alert_in["alerts"]:
        plugin_name = status_in['labels']['plugin']
        logging.info("Plugin Name: %s", str(plugin_name))
        logging.info("Plugin Status: %s", str(status_in['status']))
        CACHET_IDS = build_cachet_map()
        logging.info("Cachet IDs: %s", str(CACHET_IDS))
        component_number = search_component(plugin_name.capitalize(), CACHET_IDS)
        if component_number == 9999:
            logging.error("Component not found!")
            return "FAIL"
        logging.info("Component Number: %s", str(component_number))
        if str(status_in['status']) == "firing":
            output = update_component(component_number, 4)
        elif str(status_in['status']) == "resolved":
            output = update_component(component_number, 1)
        else:
            output = update_component(component_number, 1)
        logging.info("Output: %s", str(output))
    return "OK"

def build_cachet_map():
    """Builds a map of the components in the Cachet instance, returns
    the number that represents that component.
    """
    url = "http://" + str(CACHET_URL) + "/api/v1/components/?per_page=1000"
    try:
        req = requests.get(url)
        return {component["name"]: component["id"] for component in req.json()["data"]}
    except requests.exceptions.RequestException as map_exception:
        logging.exception(map_exception)

def search_component(key, CACHET_IDS):
    """ Searches the list of componets in cachet for the
    component returned from alertmanager. If found it returns the component,
    if not 9999 is returned.
    """
    return CACHET_IDS.get(key, 9999)

def update_component(component_id, status):
    """ Updates the component status in cachet.
    """
    headers = {
        'Content-Type': 'application/json',
        'X-Cachet-Token': str(CACHET_TOKEN)
    }
    url = "http://" + str(CACHET_URL) + "/api/v1/components/" + str(component_id)
    data = '{"status":"' + str(status) + '"}'
    try:
        ret = requests.put(url, data=data, headers=headers, verify=False)
    except requests.exceptions.RequestException as update_exception:
        logging.error("Return Code = %s", str(ret.status_code))
        logging.exception(update_exception)
    return 0

if __name__ == '__main__':
    APP.run(APP.run(host='0.0.0.0', port=10000))
