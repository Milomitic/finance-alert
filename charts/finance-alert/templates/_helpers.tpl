{{/*
Reusable template snippets. `helm template` expands these; keeping name/label
logic in one place means every manifest stays consistent (a Service selector
that drifts from the pod labels is the classic "why is my Service empty" bug).
*/}}

{{- define "finance-alert.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{/* Fully-qualified release name: <release>-<chart>, truncated to K8s' 63-char limit. */}}
{{- define "finance-alert.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Labels stamped on every object — the recommended Kubernetes label set. */}}
{{- define "finance-alert.labels" -}}
app.kubernetes.io/name: {{ include "finance-alert.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* The subset used for pod↔Service matching — must NOT change across upgrades
     or the StatefulSet's pod identity + Service selector break. */}}
{{- define "finance-alert.selectorLabels" -}}
app.kubernetes.io/name: {{ include "finance-alert.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Name of the Secret holding SECRET_KEY — either the one we create or a
     pre-existing externally-managed one. */}}
{{- define "finance-alert.secretName" -}}
{{- if .Values.secret.existingSecret -}}
{{- .Values.secret.existingSecret -}}
{{- else -}}
{{- printf "%s-secret" (include "finance-alert.fullname" .) -}}
{{- end -}}
{{- end -}}
