import logging
import os

log = logging.getLogger("blackbox.config")
_this_dir = os.path.dirname(os.path.realpath(__file__))

RUN_DELAY = 15  # seconds
# ENV vars. Call strip() incase of unintentional \n
NAMESPACE = os.getenv("OPENSHIFT_NAMESPACE", "black-box-runner").strip()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip()
SINGLE_PLUGIN = os.getenv("SINGLE_PLUGIN").strip()
IQE_USERNAME = os.getenv("IQE_USERNAME").strip()
IQE_PASSWORD = os.getenv("IQE_PASSWORD").strip()
JIRA_USERNAME = os.getenv("JIRA_USERNAME").strip()
JIRA_PASSWORD = os.getenv("JIRA_PASSWORD").strip()
IQE_ACCT_NO = os.getenv("IQE_ACCOUNT_NUMBER").strip()
IQE_TESTS_LOCAL_CONF_PATH = os.environ.get("IQE_TESTS_LOCAL_CONF_PATH", _this_dir)
ENV_FOR_DYNACONF = os.environ.get("ENV_FOR_DYNACONF", "prod")
MAX_RUNNERS = int(os.environ.get("MAX_RUNNERS", 5))
IBUTSU_SERVER = os.environ.get("IBUTSU_SERVER", "https://ibutsu-api.cloud.paas.psi.redhat.com")
IBUTSU_SOURCE = os.environ.get("IBUTSU_SOURCE", "blackbox")


if SINGLE_PLUGIN:
    PLUGINS = [(SINGLE_PLUGIN, "prod_status")]
else:
    PLUGINS = [
        # (Plugin name, pytest marker)
        ("akamai", None),
        #("advisor", "prod_status"),
        ("platform_ui", "prod_status"),
        ("approval", "prod_status"),
        ("sources", "prod_status"),
        ("topology_inventory", "prod_status"),
        ("clientv3", "prod_status"),
        ("compliance", "prod_status"),
        ("drift", "prod_status"),
        ("hccm", "prod_status"),
        ("host_inventory", "prod_status"),
        ("rbac", "prod_status"),
        ("upload", "prod_status"),
        ("vulnerability", "prod_status"),
    ]
