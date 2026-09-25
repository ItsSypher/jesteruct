# Copy to cloud.tfvars (gitignored), then:
#   terraform -chdir=infra/terraform/envs/cloud init
#   terraform -chdir=infra/terraform/envs/cloud apply -var-file=cloud.tfvars
#
# Create the namespace and its Secrets first:
#   kubectl create namespace jesteruct
#   kubectl create secret -n jesteruct generic jesteruct-openrouter --from-literal=OPENROUTER_API_KEY=...
#   kubectl create secret -n jesteruct generic valkey-auth --from-literal=password=...      (if the cache needs auth)
#   kubectl create secret -n jesteruct docker-registry ghcr --docker-server=ghcr.io ...     (while the image is private)

kube_context = "my-cluster"
install_keda = true

image_tag          = "0123abc"
image_pull_secrets = ["ghcr"]

valkey_url             = "rediss://my-cache.example.com:6380/0"
valkey_password_secret = "valkey-auth"

store_url    = "s3://my-jesteruct-bucket"
store_config = { region = "eu-north-1" }

existing_secret = "jesteruct-openrouter"

# AWS IRSA shown; on GKE use iam.gke.io/gcp-service-account, on AKS azure.workload.identity/client-id plus
# pod_labels = { "azure.workload.identity/use" = "true" }.
service_account_annotations = {
  "eks.amazonaws.com/role-arn" = "arn:aws:iam::123456789012:role/jesteruct"
}

# The Studio and the API at one host, through the cluster's ingress controller (leave out to reach them by port-forward).
ingress_host       = "jesteruct.example.com"
ingress_class_name = "nginx"
ingress_tls_secret = "jesteruct-tls"
