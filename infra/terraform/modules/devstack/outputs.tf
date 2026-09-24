# How the app reaches the devstack: JST_VALKEY_URL, JST_STORE_* and the AWS_* pair obstore signs with.

locals {
  domain = "${var.namespace}.svc.cluster.local"
}

output "valkey_url" {
  value = "redis://valkey.${local.domain}:6379/0"
}

output "store_url" {
  value = "s3://${var.bucket}"
}

output "store_config" {
  value = { endpoint = "http://seaweedfs.${local.domain}:8333", region = "us-east-1" }
}

output "store_client_options" {
  value = { allow_http = "true" }
}

output "store_credentials" {
  value     = { AWS_ACCESS_KEY_ID = var.s3_access_key, AWS_SECRET_ACCESS_KEY = var.s3_secret_key }
  sensitive = true
}
