# Local stand-ins for managed Valkey and an S3 bucket (deploy/helm/devstack).

terraform {
  required_version = ">= 1.6"
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
  }
}

locals {
  chart = "${path.module}/../../../../deploy/helm/devstack"
  # Helm upgrades only when values or the chart version change; the digest makes edits to the local chart count too.
  chart_digest = sha1(join("", [for f in sort(fileset(local.chart, "**")) : "${f}:${filesha1("${local.chart}/${f}")}"]))
}

resource "helm_release" "devstack" {
  name             = "devstack"
  chart            = local.chart
  description      = "chart ${local.chart_digest}"
  namespace        = var.namespace
  create_namespace = true
  wait             = true
  values = [yamlencode({
    seaweedfs = {
      bucket    = var.bucket
      accessKey = var.s3_access_key
      secretKey = var.s3_secret_key
    }
  })]
}
