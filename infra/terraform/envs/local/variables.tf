variable "image_tag" {
  description = "Tag of the local jesteruct image, the git short SHA."
  type        = string
}

variable "openrouter_api_key" {
  description = "Set through TF_VAR_openrouter_api_key; the Makefile reads it from .env."
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.openrouter_api_key) > 0
    error_message = "Set OPENROUTER_API_KEY in .env (make deploy-local exports it as TF_VAR_openrouter_api_key)."
  }
}

variable "wait" {
  description = "Wait for the app rollout; false lets a broken build deploy for inspection."
  type        = bool
  default     = true
}

variable "keda_max_replicas" {
  description = "Workers KEDA may run; raise it with OrbStack's memory (orb config set memory_mib)."
  type        = number
  default     = 8
}
