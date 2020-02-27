import json
import logging
import os
import shlex
import threading
import time
from itertools import cycle

import sh
from prometheus_client import Counter

import config
from pod_mgr import PodsNotAvailable
import tracker


log = logging.getLogger("blackbox.runner")


DURATION_COUNTER = Counter(
    "black_box_test_duration_total", "Total duration of all test runs", ["plugin"]
)
RUN_COUNTER = Counter("black_box_test_runs_total", "Total count of test runs", ["plugin"])
FAIL_COUNTER = Counter(
    "black_box_test_failures_total",
    "Total count of test run failures. "
    "At least one test failure counts "
    "as the whole run failing.",
    ["plugin"],
)


class Plugin:
    def __init__(self, name, marker=None):
        self.name = name
        self.last_start = 0.0
        marker = f" -m {marker}" if marker else ""
        ibutsu_server = f" -o ibutsu_server={config.IBUTSU_SERVER}" if config.IBUTSU_SERVER else ""
        ibutsu_src = f" -o ibutsu_source={config.IBUTSU_SOURCE}" if config.IBUTSU_SOURCE else ""
        self.run_args = shlex.split(
            f"tests plugin {name}{marker}{ibutsu_server}{ibutsu_src} -s -v --color=no"
        )
        self.runs = RUN_COUNTER.labels(plugin=self.name)
        self.failures = FAIL_COUNTER.labels(plugin=self.name)
        self.duration = DURATION_COUNTER.labels(plugin=self.name)
        self.last_start = 0.0
        self.last_completion = 0.0
        self._run_id = int(
            time.time()
        )  # use int of time to ensure an ever-increasing unique number

        self.env = os.environ.copy()
        # Pass configuration into IQE via env var (instead of using a settings.local.yaml)
        main_opts = {
            "username": config.IQE_USERNAME,
            "password": config.IQE_PASSWORD,
            "identity": {"account_number": config.IQE_ACCT_NO},
        }
        users_opts = {
            "primary_user": {
                "username": config.IQE_USERNAME,
                "password": config.IQE_PASSWORD,
                "identity": {"account_number": config.IQE_ACCT_NO},
            }
        }
        self.env.update(
            {
                "MERGE_ENABLED_FOR_DYNACONF": "true",
                "ENV_FOR_DYNACONF": config.ENV_FOR_DYNACONF,
                "IQE_TESTS_LOCAL_CONF_PATH": config.IQE_TESTS_LOCAL_CONF_PATH,
                "DYNACONF_MAIN": f"@json {json.dumps(main_opts)}",
                "DYNACONF_USERS": f"@json {json.dumps(users_opts)}",
            }
        )

    def update_env(self, key, val):
        self.env.update({key: str(val)})

    def _out(self, line):
        log.debug(" |out| [%s|run:%d] %s", self.name, self._run_id, line.rstrip())

    def _cmd_done(self, cmd, success, __):
        self.last_completion = time.time()
        duration = self.last_completion - self.last_start
        log.info("[%s|run:%d] test stopped, took %d sec", self.name, self._run_id, duration)
        self.runs.inc()
        self.duration.inc(duration)
        if not success:
            self.failures.inc()
            log.error(
                "[%s|run:%d] test output:\n%s", self.name, self._run_id, cmd.stdout.decode("utf-8")
            )
            log.error("******** %s: failure ********", self.name)

    def set_run_id(self, run_id):
        self.update_env("IBUTSU_ENV_ID", run_id)
        self._run_id = run_id

    def run_test(self):
        # Uncomment if debugging and you want to check the value of the creds...
        """
        sh.iqe(
            "debug", "keysearch", "main", _env=self.env, _out=self._out, _tee=True, _err_to_out=True
        )
        sh.iqe(
            "debug",
            "keysearch",
            "users",
            _env=self.env,
            _out=self._out,
            _tee=True,
            _err_to_out=True,
        )
        """
        log.info(
            "[%s|run:%d] starting test with: iqe %s",
            self.name,
            self._run_id,
            " ".join(self.run_args),
        )

        self.last_start = time.time()
        try:
            sh.iqe(
                *self.run_args,
                _env=self.env,
                _out=self._out,
                _done=self._cmd_done,
                _tee=True,
                _err_to_out=True,
            )
        except sh.ErrorReturnCode:
            # Let the done callback handle errors
            pass


class IqeRunner(threading.Thread):
    def __init__(self, runner_name, plugin_configs, pod_mgr=None, run_id=0):
        super().__init__()
        self.name = runner_name
        self.daemon = True
        self.plugins = [Plugin(*cfg) for cfg in plugin_configs]
        self.pod_mgr = pod_mgr
        self.stop_event = threading.Event()
        self.proc = None
        self._run_id = run_id
        self._last_plugin = None
        self.plugin_cycler = cycle(self.plugins)
        log.info("assigned plugins: %s", [", ".join(p.name for p in self.plugins)])

    @property
    def last_plugin_name(self):
        return getattr(self._last_plugin, "name", None)

    def to_dict(self):
        return {
            "name": self.name,
            "plugins": [plugin.name for plugin in self.plugins],
            "last_plugin": self.last_plugin_name,
        }

    def reserve_pod(self, plugin):
        ip, pod = self.pod_mgr.reserve_pod()
        log.debug("[%s|run:%d] reserved pod '%s'", plugin.name, self._run_id, pod.name)
        opts = {"command_executor": f"http://{ip}:4444/wd/hub"}
        plugin.update_env("DYNACONF_BROWSER", f"@json {json.dumps(opts)}")
        return pod

    def run_plugin(self, plugin):
        plugin.set_run_id(self._run_id)
        try:
            pod = self.reserve_pod(plugin)
        except PodsNotAvailable:
            log.error(
                "[%s|run:%d] no pods are free ... skipping this test run", plugin.name, self._run_id
            )
            return

        try:
            plugin.run_test()
        finally:
            if self.pod_mgr:
                self.pod_mgr.release_pod(pod)
                log.debug("[%s|run:%d] released pod '%s'", plugin.name, self._run_id, pod.name)

    def _delay_passed(self, plugin):
        log.debug(
            "[%s|run:%d] plugin last completion: %f",
            plugin.name,
            self._run_id,
            plugin.last_completion,
        )
        passed = plugin.last_completion + config.RUN_DELAY < time.time()
        log.debug("[%s|run:%d] plugin delay passed: %s", plugin.name, self._run_id, passed)
        return passed

    def run(self):
        last_plugin = self.last_plugin_name or tracker.get_last_executed_plugin(self.name)
        log.info("runner %s last plugin executed: %s", self.name, last_plugin)

        if last_plugin and last_plugin in self.to_dict()["plugins"]:
            # Make the tests pick up where they left off.
            # We'll start at the NEXT plugin past the one we last executed
            while next(self.plugin_cycler).name != last_plugin:
                continue

        counter = 0
        while not self.stop_event.is_set():
            plugin = next(self.plugin_cycler)
            if not plugin.last_completion or self._delay_passed(plugin):
                self.run_plugin(plugin)
                self._last_plugin = plugin
                tracker.set_last_executed_plugin(self.name, plugin.name)
                counter += 1
            else:
                log.debug("[%s|run:%d] skipping due to time delay", plugin.name, self._run_id)

            if counter % len(self.plugins) == 0:
                self._run_id += 1  # increase run id for each full loop through the plugin list
            time.sleep(1)

    def stop(self):
        self.stop_event.set()
