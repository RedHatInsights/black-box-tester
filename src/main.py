#!/usr/bin/env python3
"""
Script that executes all plugins with prod_status tests.  The output of this
runner is exposed via a prometheus exporter, showing the number of total test
runs and failed runs for each plugin.

Each plugin is executed in a separate process to enable some parallel execution
as well as to cleanly segment the test runs for prometheus.
"""
import logging
import signal
import time

from ocdeployer.utils import switch_to_project
from prometheus_client import start_http_server

import config
from pod_mgr import SeleniumPodMgr
from runner import IqeRunner
from tracker import init_tracker

log = logging.getLogger("blackbox.main")
RUNNERS = []


def sigterm_handler(_, __):
    log.info("Got SIGTERM, stopping IQE Runners")
    for runner in RUNNERS:
        runner.stop()


def get_groups(l, n):
    """
    Divide list 'l' into 'n' groups

    https://stackoverflow.com/a/43922107/6476672
    """
    return (l[i::n] for i in range(n))


def main():
    logging.basicConfig(
        level=config.LOG_LEVEL, format="%(asctime)s %(name)s:%(levelname)s %(message)s"
    )
    logging.getLogger("sh").setLevel(logging.CRITICAL)

    pod_mgr = SeleniumPodMgr()

    # Create runners and split the plugins across them
    initial_run_id = int(time.time())
    plugin_groups = get_groups(config.PLUGINS, config.MAX_RUNNERS)
    for i, plugin_group in enumerate(plugin_groups):
        if plugin_group:
            runner_name = f"runner-{i}"
            RUNNERS.append(IqeRunner(runner_name, plugin_group, pod_mgr, run_id=initial_run_id))

    init_tracker(config.PLUGINS, RUNNERS)

    # Ensure number of selenium pods matches number runners
    switch_to_project(config.NAMESPACE)
    pod_mgr.scale_selenium_pods(config.MAX_RUNNERS)

    start_http_server(8000)

    signal.signal(signal.SIGTERM, sigterm_handler)

    for runner in RUNNERS:
        runner.start()

    for runner in RUNNERS:
        runner.join()


if __name__ == "__main__":
    main()
