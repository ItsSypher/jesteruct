variable "kubeconfig" {
  type    = string
  default = "~/.kube/config"
}

variable "kube_context" {
  description = "Context in the kubeconfig; null uses its current context."
  type        = string
  default     = null
}

variable "install_keda" {
  description = "false when the cluster already runs KEDA."
  type        = bool
  default     = true
}

variable "namespace" {
  type    = string
  default = "jesteruct"
}

variable "image_repository" {
  type    = string
  default = "ghcr.io/itssypher/jesteruct"
}

variable "image_tag" {
  description = "Git SHA pushed by CI (or main)."
  type        = string
}

variable "image_pull_secrets" {
  description = "docker-registry Secrets in the namespace, needed while the GHCR package is private."
  type        = list(string)
  default     = []
}

variable "valkey_url" {
  description = "Managed Valkey/Redis without credentials; rediss:// turns on TLS for the app and for KEDA."
  type        = string
}

variable "valkey_password_secret" {
  description = "Existing Secret with the Valkey password under `password`, when the cache requires auth."
  type        = string
  default     = ""
}

variable "store_url" {
  description = "Bucket URL: s3://, gs:// or az://."
  type        = string
}

variable "store_config" {
  description = "obstore config, e.g. { region = \"eu-north-1\" } or { account_name = \"...\" }."
  type        = map(string)
  default     = {}
}

variable "existing_secret" {
  description = "Existing Secret with the OpenRouter key under OPENROUTER_API_KEY."
  type        = string
}

variable "service_account_annotations" {
  description = "Workload identity that grants the bucket, e.g. eks.amazonaws.com/role-arn."
  type        = map(string)
  default     = {}
}

variable "pod_labels" {
  type    = map(string)
  default = {}
}

variable "api_replicas" {
  type    = number
  default = 2
}

variable "worker_max_docs" {
  type    = number
  default = 32
}

variable "keda_max_replicas" {
  type    = number
  default = 6
}

variable "ingress_host" {
  description = "Serve the API and the Studio at this host through the cluster's ingress controller; empty for none."
  type        = string
  default     = ""
}

variable "ingress_class_name" {
  type    = string
  default = ""
}

variable "ingress_tls_secret" {
  description = "An existing TLS Secret for ingress_host, for example one cert-manager issues."
  type        = string
  default     = ""
}
