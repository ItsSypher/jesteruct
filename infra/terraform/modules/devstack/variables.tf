variable "namespace" {
  type    = string
  default = "devstack"
}

variable "bucket" {
  type    = string
  default = "jesteruct"
}

variable "s3_access_key" {
  type    = string
  default = "devstack"
}

variable "s3_secret_key" {
  type      = string
  default   = "devstack-secret"
  sensitive = true
}
