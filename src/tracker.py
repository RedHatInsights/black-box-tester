import json
import logging
import os
import threading


log = logging.getLogger("blackbox.tracker")
TRACKER_FILE = os.path.join("/black-box-runner-storage", "tracker.json")
_lock = threading.RLock()


"""
Example tracker file:
{
    "num_runners": 3,
    "plugins": ["plugin1", "plugin2", "plugin3", "plugin4", "plugin5"]
    "runners": [
        {"name": "runner1", "plugins": ["plugin1", "plugin2"], "last_plugin": "plugin2"},
        {"name": "runner2", "plugins": ["plugin3", "plugin4"], "last_plugin": "plugin3"},
        {"name": "runner3", "plugins": ["plugin5"], "last_plugin": None}
    ]
}
"""


def locked(orig_func):
    def _func(*args, **kwargs):
        with _lock:
            return orig_func(*args, **kwargs)

    return _func


@locked
def read_tracker_data():
    if not os.path.exists(TRACKER_FILE):
        log.info("tracker file does not exist")
        return {}
    try:
        with open(TRACKER_FILE) as fp:
            data = fp.read()
            log.debug("read tracker data: %s", data)
            if not data.strip():
                return {}
            return json.loads(data)
    except (OSError, json.decoder.JSONDecodeError):
        log.exception("error reading tracker file")
        return {}


@locked
def write_tracker_data(data):
    try:
        with open(TRACKER_FILE, "w") as fp:
            json.dump(data, fp)
    except OSError:
        log.exception("error writing to tracker file")


@locked
def set_last_executed_plugin(runner_name, plugin_name):
    data = read_tracker_data()
    get_runner(runner_name, data)["last_plugin"] = plugin_name
    write_tracker_data(data)


def get_runner(runner_name, data=None):
    if data:
        runners = data.get("runners", [])
    else:
        runners = read_tracker_data().get("runners", [])
    for r in runners:
        if r["name"] == runner_name:
            return r
    return None


def init_tracker(plugins, runners):
    data = read_tracker_data()
    current_plugin_names = [p[0] for p in plugins]

    reset = False
    if not data:
        log.info("no tracker data found, re-initializing tracker")
        reset = True
    elif data.get("num_runners") != len(runners) or data.get("plugins") != current_plugin_names:
        log.info("num runners or plugins have changed, re-initializing tracker")
        reset = True
    else:
        for runner in runners:
            stored_runner = get_runner(runner.name, data)
            if not stored_runner:
                log.info("runner %s not in tracker data, re-initializing tracker", runner.name)
                reset = True
            if stored_runner.get("plugins") != [p.name for p in runner.plugins]:
                log.info(
                    "runner %s assigned plugins changed, re-initializing tracker data", runner.name
                )
                reset = True

    if reset:
        fresh_data = {
            "num_runners": len(runners),
            "plugins": current_plugin_names,
            "runners": [r.to_dict() for r in runners],
        }
        write_tracker_data(fresh_data)
    else:
        log.info("no change in plugins/runners -- using previously stored tracker data")
    log.info("tracker data:\n%s", json.dumps(read_tracker_data(), sort_keys=True, indent=4))


def get_last_executed_plugin(runner_name):
    return get_runner(runner_name)["last_plugin"]
