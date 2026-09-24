{{- define "jesteruct.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end }}

{{- define "jesteruct.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* Selector labels for one component; call with (list $ "api"). */}}
{{- define "jesteruct.selector" -}}
{{- $root := index . 0 -}}
app.kubernetes.io/name: {{ $root.Chart.Name }}
app.kubernetes.io/instance: {{ $root.Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end }}

{{- define "jesteruct.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "jesteruct.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end }}

{{- define "jesteruct.openrouterSecret" -}}
{{- if .Values.openrouter.existingSecret -}}
{{- .Values.openrouter.existingSecret -}}
{{- else if .Values.openrouter.apiKey -}}
{{- include "jesteruct.fullname" . }}-openrouter
{{- else -}}
{{- fail "set openrouter.existingSecret or openrouter.apiKey" -}}
{{- end -}}
{{- end }}

{{/* Pod settings both components share: identity, security and the writable scratch paths. */}}
{{- define "jesteruct.podSpec" -}}
serviceAccountName: {{ include "jesteruct.serviceAccountName" . }}
automountServiceAccountToken: false
{{- with .Values.image.pullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  seccompProfile:
    type: RuntimeDefault
volumes:
  - name: tmp
    emptyDir: {}
  - name: home
    emptyDir: {}
{{- end }}

{{- define "jesteruct.container" -}}
image: {{ .Values.image.repository }}:{{ required "image.tag is required" .Values.image.tag }}
imagePullPolicy: {{ .Values.image.pullPolicy }}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
volumeMounts:
  - name: tmp
    mountPath: /tmp
  - name: home
    mountPath: /home/jst
envFrom:
  - configMapRef:
      name: {{ include "jesteruct.fullname" . }}
  {{- with .Values.storeCredentialsSecret }}
  - secretRef:
      name: {{ . }}
  {{- end }}
{{- end }}

{{/* With a password, the app's URL is assembled from valkeyUrl and the Secret at start-up. */}}
{{- define "jesteruct.valkeyEnv" -}}
{{- with .Values.valkeyPassword.existingSecret }}
{{- $u := urlParse $.Values.valkeyUrl }}
- name: VALKEY_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ . }}
      key: {{ $.Values.valkeyPassword.key }}
- name: JST_VALKEY_URL
  value: "{{ $u.scheme }}://:$(VALKEY_PASSWORD)@{{ $u.host }}{{ $u.path }}"
{{- end }}
{{- end }}

{{- define "jesteruct.checksums" -}}
checksum/config: {{ include (print .Template.BasePath "/configmap.yaml") . | sha256sum }}
{{- end }}
