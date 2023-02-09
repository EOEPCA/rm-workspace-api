import os

PREFIX_FOR_NAME = os.environ["PREFIX_FOR_NAME"]
WORKSPACE_SECRET_NAME = os.environ["WORKSPACE_SECRET_NAME"]
WORKSPACE_CONFIG_MAP_NAME = os.environ["WORKSPACE_CONFIG_MAP_NAME"]

NAMESPACE_FOR_BUCKET_RESOURCE = os.environ["NAMESPACE_FOR_BUCKET_RESOURCE"]

WORKSPACE_CHARTS_CONFIG_MAP = os.environ["WORKSPACE_CHARTS_CONFIG_MAP"]

S3_ENDPOINT = os.environ["S3_ENDPOINT"]
S3_REGION = os.environ["S3_REGION"]
BUCKET_ENDPOINT_URL = os.environ["BUCKET_ENDPOINT_URL"]
PEP_BASE_URL = os.environ.get("PEPBaseUrl", "http://workspace-api-pep:5576")
AUTO_PROTECTION_ENABLED = "True" == os.environ.get("AUTO_PROTECTION_ENABLED", "True")
# TODO: whitelistings = list of strings (applied to helm chart)

# registration endpoint variables
REDIS_SERVICE_NAME = os.environ.get("REDIS_SERVICE_NAME", "vs-redis-master")
REGISTER_QUEUE = os.environ.get("REDIS_REGISTER_QUEUE_KEY", "register_queue")
REGISTER_PATH_QUEUE = os.environ.get(
    "REDIS_REGISTER_PATH_QUEUE_KEY", "register_path_queue"
)

REGISTER_QUEUE = os.environ.get("REDIS_REGISTER_QUEUE", "register_queue")
REGISTER_ADES_QUEUE = os.environ.get("REDIS_REGISTER_ADES_QUEUE", "register_ades_queue")
REGISTER_APPLICATION_QUEUE = os.environ.get(
    "REDIS_REGISTER_APPLICATION_QUEUE", "register_application_queue"
)
REGISTER_COLLECTION_QUEUE = os.environ.get(
    "REDIS_REGISTER_COLLECTION_QUEUE", "register_collection_queue"
)
HARVESTER_QUEUE = os.environ.get("REDIS_HARVESTER_QUEUE", "harvester_queue")

DEREGISTER_QUEUE = os.environ.get("REDIS_DEREGISTER_QUEUE", "deregister_queue")
DEREGISTER_ADES_QUEUE = os.environ.get(
    "REDIS_DEREGISTER_ADES_QUEUE", "deregister_ades_queue"
)
DEREGISTER_APPLICATION_QUEUE = os.environ.get(
    "REDIS_DEREGISTER_APPLICATION_QUEUE", "deregister_application_queue"
)
DEREGISTER_COLLECTION_QUEUE = os.environ.get(
    "REDIS_DEREGISTER_COLLECTION_QUEUE", "deregister_collection_queue"
)

REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

# Guard specific values
UMA_CLIENT_SECRET_NAME = os.environ["UMA_CLIENT_SECRET_NAME"]
UMA_CLIENT_SECRET_NAMESPACE = os.environ["UMA_CLIENT_SECRET_NAMESPACE"]

HARBOR_URL = os.environ["HARBOR_URL"]
HARBOR_ADMIN_USERNAME = os.environ["HARBOR_ADMIN_USERNAME"]
HARBOR_ADMIN_PASSWORD = os.environ["HARBOR_ADMIN_PASSWORD"]

BUCKET_CATALOG_HARVESTER = os.environ.get(
    "BUCKET_CATALOG_HARVESTER", "harvest-bucket-catalog"
)
