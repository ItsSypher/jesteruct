variable "namespace" {
  type    = string
  default = "jesteruct"
}

variable "create_namespace" {
  type    = bool
  default = true
}

variable "release_name" {
  type    = string
  default = "jesteruct"
}

variable "wait" {
  description = "Wait for the rollout to become ready."
  type        = bool
  default     = true
}

# image

variable "image_repository" {
  type    = string
  default = "ghcr.io/itssypher/jesteruct"
}

variable "image_tag" {
  description = "Git SHA the image was built from."
  type        = string
}

variable "image_pull_policy" {
  type    = string
  default = "IfNotPresent"
}

variable "image_pull_secrets" {
  description = "Names of existing docker-registry Secrets, needed while the GHCR package is private."
  type        = list(string)
  default     = []
}

# dependencies

variable "valkey_url" {
  description = "redis:// or rediss:// URL without credentials."
  type        = string
}

variable "valkey_password_secret" {
  description = "Existing Secret with the Valkey password under the key `password`; empty when Valkey has no auth."
  type        = string
  default     = ""
}

variable "store_url" {
  description = "Object store URL: s3://, gs:// or az://."
  type        = string
}

variable "store_config" {
  description = "obstore config (JST_STORE_CONFIG)."
  type        = map(string)
  default     = {}
}

variable "store_client_options" {
  description = "obstore client options (JST_STORE_CLIENT_OPTIONS)."
  type        = map(string)
  default     = {}
}

variable "store_credentials" {
  description = "Env vars for obstore (AWS_*, GOOGLE_*, AZURE_*), kept in a Secret; leave empty with workload identity."
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "openrouter_api_key" {
  description = "Creates a Secret with the key. Set this or openrouter_existing_secret."
  type        = string
  default     = ""
  sensitive   = true
}

variable "openrouter_existing_secret" {
  description = "Existing Secret holding the key under OPENROUTER_API_KEY."
  type        = string
  default     = ""
}

# identity

variable "service_account_annotations" {
  description = "Workload identity, e.g. eks.amazonaws.com/role-arn or iam.gke.io/gcp-service-account."
  type        = map(string)
  default     = {}
}

variable "pod_labels" {
  description = "Extra pod labels, e.g. azure.workload.identity/use = \"true\"."
  type        = map(string)
  default     = {}
}

# sizing

variable "env" {
  description = "Other JST_* settings, shared by API and workers."
  type        = map(string)
  default     = {}
}

variable "api_replicas" {
  type    = number
  default = 2
}

variable "api_resources" {
  type = object({ requests = map(string), limits = map(string) })
  default = {
    requests = { cpu = "250m", memory = "512Mi" }
    limits   = { memory = "1Gi" }
  }
}

variable "worker_replicas" {
  description = "Fixed worker count, used only when KEDA is disabled."
  type        = number
  default     = 1
}

variable "worker_max_docs" {
  description = "Documents one worker routes at a time."
  type        = number
  default     = 2
}

variable "worker_resources" {
  description = "limits.cpu also sizes each worker's probe process pool."
  type        = object({ requests = map(string), limits = map(string) })
  default = {
    requests = { cpu = "2", memory = "2Gi" }
    limits   = { cpu = "2", memory = "4Gi" }
  }
}

variable "keda_enabled" {
  type    = bool
  default = true
}

variable "keda_min_replicas" {
  type    = number
  default = 0
}

variable "keda_max_replicas" {
  description = "Jev's 1,200 requests a minute bound total throughput; about 6 workers reach it."
  type        = number
  default     = 6
}

variable "keda_cooldown_seconds" {
  type    = number
  default = 300
}

variable "ingress" {
  description = "One host for the API and the Studio; an empty host creates no Ingress. tls_secret is an existing TLS Secret."
  type = object({
    host       = optional(string, "")
    class_name = optional(string, "")
    tls_secret = optional(string, "")
  })
  default = {}
}
