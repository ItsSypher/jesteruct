# OrbStack Kubernetes: KEDA, the devstack (Valkey + SeaweedFS) and the app from a locally built image.
#   make deploy-local    builds jesteruct:<git sha> and applies this
#   make destroy-local   removes all of it

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

locals {
  kubeconfig = "~/.kube/config"
  context    = "orbstack"
}

provider "kubernetes" {
  config_path    = local.kubeconfig
  config_context = local.context
}

provider "helm" {
  kubernetes = {
    config_path    = local.kubeconfig
    config_context = local.context
  }
}

module "platform" {
  source = "../../modules/platform"
}

module "devstack" {
  source = "../../modules/devstack"
}

# The app reaches the devstack with (see outputs.tf):
#   JST_VALKEY_URL           redis://valkey.devstack.svc.cluster.local:6379/0
#   JST_STORE_URL            s3://jesteruct
#   JST_STORE_CONFIG         {"endpoint": "http://seaweedfs.devstack.svc.cluster.local:8333", "region": "us-east-1"}
#   JST_STORE_CLIENT_OPTIONS {"allow_http": "true"}
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY from the Secret jesteruct-store (SeaweedFS's static identity)
module "app" {
  source     = "../../modules/app"
  depends_on = [module.platform, module.devstack]

  image_repository   = "jesteruct"
  image_tag          = var.image_tag
  image_pull_policy  = "Never" # OrbStack's cluster shares the local Docker engine
  wait               = var.wait
  openrouter_api_key = var.openrouter_api_key

  valkey_url           = module.devstack.valkey_url
  store_url            = module.devstack.store_url
  store_config         = module.devstack.store_config
  store_client_options = module.devstack.store_client_options
  store_credentials    = module.devstack.store_credentials

  # Sized for a laptop: OrbStack's default VM (12 GiB) fits eight workers of about 1 GiB next to the devstack.
  api_replicas      = 1
  keda_max_replicas = var.keda_max_replicas
  worker_resources = {
    requests = { cpu = "1", memory = "1Gi" }
    limits   = { cpu = "2", memory = "3Gi" }
  }
}
