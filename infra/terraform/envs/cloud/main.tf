# Any Kubernetes cluster with managed Valkey/Redis and a bucket. Creating the cluster, cache and bucket is out of
# scope; this installs KEDA (optional) and the app, pointed at them. See cloud.example.tfvars.

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

provider "kubernetes" {
  config_path    = var.kubeconfig
  config_context = var.kube_context
}

provider "helm" {
  kubernetes = {
    config_path    = var.kubeconfig
    config_context = var.kube_context
  }
}

module "platform" {
  source       = "../../modules/platform"
  install_keda = var.install_keda
}

module "app" {
  source     = "../../modules/app"
  depends_on = [module.platform]

  namespace          = var.namespace
  create_namespace   = false # it already holds the Secrets below
  image_repository   = var.image_repository
  image_tag          = var.image_tag
  image_pull_secrets = var.image_pull_secrets

  valkey_url             = var.valkey_url
  valkey_password_secret = var.valkey_password_secret
  store_url              = var.store_url
  store_config           = var.store_config

  openrouter_existing_secret  = var.existing_secret
  service_account_annotations = var.service_account_annotations
  pod_labels                  = var.pod_labels

  api_replicas      = var.api_replicas
  worker_max_docs   = var.worker_max_docs
  keda_max_replicas = var.keda_max_replicas
}
