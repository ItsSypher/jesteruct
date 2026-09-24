# The router itself (deploy/helm/jesteruct), pointed at dependencies that live elsewhere.

terraform {
  required_version = ">= 1.6"
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.2"
    }
  }
}

resource "kubernetes_namespace_v1" "app" {
  count = var.create_namespace ? 1 : 0
  metadata {
    name = var.namespace
  }
}

locals {
  namespace = var.create_namespace ? kubernetes_namespace_v1.app[0].metadata[0].name : var.namespace
  chart     = "${path.module}/../../../../deploy/helm/jesteruct"
  # Helm upgrades only when values or the chart version change; the digest makes edits to the local chart count too.
  chart_digest = sha1(join("", [for f in sort(fileset(local.chart, "**")) : "${f}:${filesha1("${local.chart}/${f}")}"]))
}

resource "kubernetes_secret_v1" "openrouter" {
  count = nonsensitive(var.openrouter_api_key != "") ? 1 : 0
  metadata {
    name      = "${var.release_name}-openrouter"
    namespace = local.namespace
  }
  data = { OPENROUTER_API_KEY = var.openrouter_api_key }
}

resource "kubernetes_secret_v1" "store" {
  count = nonsensitive(length(var.store_credentials) > 0) ? 1 : 0
  metadata {
    name      = "${var.release_name}-store"
    namespace = local.namespace
  }
  data = var.store_credentials
}

resource "helm_release" "app" {
  name        = var.release_name
  chart       = local.chart
  description = "chart ${local.chart_digest}"
  namespace   = local.namespace
  wait        = var.wait
  timeout     = 600

  values = [yamlencode({
    image = {
      repository  = var.image_repository
      tag         = var.image_tag
      pullPolicy  = var.image_pull_policy
      pullSecrets = [for name in var.image_pull_secrets : { name = name }]
    }
    valkeyUrl              = var.valkey_url
    valkeyPassword         = { existingSecret = var.valkey_password_secret }
    storeUrl               = var.store_url
    storeConfig            = var.store_config
    storeClientOptions     = var.store_client_options
    storeCredentialsSecret = try(kubernetes_secret_v1.store[0].metadata[0].name, "")
    env                    = var.env
    openrouter             = { existingSecret = try(kubernetes_secret_v1.openrouter[0].metadata[0].name, var.openrouter_existing_secret) }
    serviceAccount         = { annotations = var.service_account_annotations }
    podLabels              = var.pod_labels
    api                    = { replicas = var.api_replicas, resources = var.api_resources }
    worker = {
      replicas  = var.worker_replicas
      maxDocs   = var.worker_max_docs
      resources = var.worker_resources
    }
    keda = {
      enabled         = var.keda_enabled
      minReplicas     = var.keda_min_replicas
      maxReplicas     = var.keda_max_replicas
      cooldownSeconds = var.keda_cooldown_seconds
    }
    ingress = {
      enabled   = var.ingress.host != ""
      className = var.ingress.class_name
      host      = var.ingress.host
      tls       = var.ingress.tls_secret != "" ? [{ secretName = var.ingress.tls_secret, hosts = [var.ingress.host] }] : []
    }
  })]

  lifecycle {
    precondition {
      condition     = nonsensitive(var.openrouter_api_key != "") != (var.openrouter_existing_secret != "")
      error_message = "Set exactly one of openrouter_api_key and openrouter_existing_secret."
    }
  }
}
