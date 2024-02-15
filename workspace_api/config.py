import os

PREFIX_FOR_NAME = os.environ["PREFIX_FOR_NAME"]
WORKSPACE_SECRET_NAME = os.environ["WORKSPACE_SECRET_NAME"]
WORKSPACE_CONFIG_MAP_NAME = os.environ["WORKSPACE_CONFIG_MAP_NAME"]

NAMESPACE_FOR_BUCKET_RESOURCE = os.environ["NAMESPACE_FOR_BUCKET_RESOURCE"]

WORKSPACE_CHARTS_CONFIG_MAP = os.environ["WORKSPACE_CHARTS_CONFIG_MAP"]

S3_ENDPOINT = os.environ["S3_ENDPOINT"]
S3_REGION = os.environ["S3_REGION"]
BUCKET_ENDPOINT_URL = os.environ["BUCKET_ENDPOINT_URL"]

# Gluu integration
GLUU_INTEGRATION_ENABLED = os.environ.get("GLUU_INTEGRATION_ENABLED", "false").lower() == "true"
PEP_BASE_URL = os.environ.get("PEP_BASE_URL", "http://workspace-api-pep:5576")
UMA_CLIENT_SECRET_NAME = os.environ["UMA_CLIENT_SECRET_NAME"]
UMA_CLIENT_SECRET_NAMESPACE = os.environ["UMA_CLIENT_SECRET_NAMESPACE"]

# Keycloak integration
KEYCLOAK_INTEGRATION_ENABLED = os.environ.get("KEYCLOAK_INTEGRATION_ENABLED", "false").lower() == "true"
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://identity-keycloak.um.svc.cluster.local:8080")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "master")
IDENTITY_API_URL = os.environ.get("IDENTITY_API_URL", "http://identity-api.um.svc.cluster.local:8080")
WORKSPACE_API_CLIENT_ID = os.environ.get("WORKSPACE_API_CLIENT_ID", "workspace-api")
DEFAULT_IAM_CLIENT_SECRET = os.environ.get("DEFAULT_IAM_CLIENT_SECRET", "changeme")

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
REGISTER_JSON_QUEUE = os.environ.get(
    "REDIS_REGISTER_JSON_QUEUE", "register_json_queue"
)
REGISTER_XML_QUEUE = os.environ.get(
    "REDIS_REGISTER_XML_QUEUE", "register_xml_queue"
)
REGISTER_CATALOGUE_QUEUE = os.environ.get(
    "REDIS_REGISTER_CATALOGUE_QUEUE", "register_catalogue_queue"
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
DEREGISTER_CATALOGUE_QUEUE = os.environ.get(
    "REDIS_DEREGISTER_CATALOGUE_QUEUE", "deregister_catalogue_queue"
)

REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

HARBOR_URL = os.environ["HARBOR_URL"]
HARBOR_ADMIN_USERNAME = os.environ["HARBOR_ADMIN_USERNAME"]
HARBOR_ADMIN_PASSWORD = os.environ["HARBOR_ADMIN_PASSWORD"]

BUCKET_CATALOG_HARVESTER = os.environ.get(
    "BUCKET_CATALOG_HARVESTER", "harvest-bucket-catalog"
)
