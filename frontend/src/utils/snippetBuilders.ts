import type { DependencySummaryParams } from '../store/api/communicationApi';

const getApiBase = () =>
  typeof window !== 'undefined' ? `${window.location.origin}/api/v1` : '/api/v1';

const getBaseUrl = () =>
  typeof window !== 'undefined' ? window.location.origin : 'https://your-flowfish-instance';

export function buildQueryString(params: DependencySummaryParams | null): string {
  if (!params) return '';
  const qs = new URLSearchParams();
  params.analysis_ids.forEach(id => qs.append('analysis_ids', String(id)));
  if (params.annotation_key) qs.set('annotation_key', params.annotation_key);
  if (params.annotation_value) qs.set('annotation_value', params.annotation_value);
  if (params.label_key) qs.set('label_key', params.label_key);
  if (params.label_value) qs.set('label_value', params.label_value);
  if (params.namespace) qs.set('namespace', params.namespace);
  if (params.owner_name) qs.set('owner_name', params.owner_name);
  if (params.pod_name) qs.set('pod_name', params.pod_name);
  if (params.ip) qs.set('ip', params.ip);
  if (params.depth && params.depth > 1) qs.set('depth', String(params.depth));
  return qs.toString();
}

export function buildCurlSnippet(params: DependencySummaryParams | null): string {
  const qsStr = buildQueryString(params);
  if (!qsStr) return '';
  const API_BASE = getApiBase();
  return `# Get your API key from Settings > API Keys
FLOWFISH_API_KEY='**********'

curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
  "${API_BASE}/communications/dependencies/summary?${qsStr}"`;
}

export function buildPythonSnippet(params: DependencySummaryParams | null): string {
  if (!params) return '';
  const API_BASE = getApiBase();
  const paramLines: string[] = [];
  params.analysis_ids.forEach(id => paramLines.push(`    ("analysis_ids", "${id}"),`));
  if (params.annotation_key) paramLines.push(`    ("annotation_key", "${params.annotation_key}"),`);
  if (params.annotation_value) paramLines.push(`    ("annotation_value", "${params.annotation_value}"),`);
  if (params.label_key) paramLines.push(`    ("label_key", "${params.label_key}"),`);
  if (params.label_value) paramLines.push(`    ("label_value", "${params.label_value}"),`);
  if (params.namespace) paramLines.push(`    ("namespace", "${params.namespace}"),`);
  if (params.owner_name) paramLines.push(`    ("owner_name", "${params.owner_name}"),`);
  if (params.pod_name) paramLines.push(`    ("pod_name", "${params.pod_name}"),`);
  if (params.ip) paramLines.push(`    ("ip", "${params.ip}"),`);
  if (params.depth && params.depth > 1) paramLines.push(`    ("depth", "${params.depth}"),`);

  return `import requests

FLOWFISH_URL = "${API_BASE}"
FLOWFISH_API_KEY = "**********"  # Get from Settings > API Keys

resp = requests.get(
    f"{FLOWFISH_URL}/communications/dependencies/summary",
    params=[
${paramLines.join('\n')}
    ],
    headers={"X-API-Key": FLOWFISH_API_KEY},
)
resp.raise_for_status()
deps = resp.json()

# Extract affected git repos from per-service downstream annotations
affected_repos = []
for matched in deps.get("matched_services", []):
    for category, services in matched.get("downstream", {}).get("by_category", {}).items():
        for svc in services:
            repo = svc.get("annotations", {}).get("git-repo")
            if repo:
                affected_repos.append({
                    "repo": repo,
                    "service": svc["name"],
                    "namespace": svc["namespace"],
                    "upstream": matched["name"],
                    "category": category,
                    "critical": svc.get("is_critical", False),
                })

summary = deps.get("summary", {})
print(f"Matched {summary.get('total_matched', 0)} services, {summary.get('total_downstream_unique', 0)} downstream deps")
print(f"Found {len(affected_repos)} affected repositories")
for r in affected_repos:
    flag = " [CRITICAL]" if r["critical"] else ""
    print(f"  {r['upstream']} -> {r['service']} ({r['category']}){flag} -> {r['repo']}")`;
}

export function buildJsSnippet(params: DependencySummaryParams | null): string {
  const qsStr = buildQueryString(params);
  if (!qsStr) return '';
  const API_BASE = getApiBase();
  return `// Get your API key from Flowfish Settings > API Keys
const FLOWFISH_API_KEY = "**********";
const FLOWFISH_URL = "${API_BASE}";

const resp = await fetch(
  \`\${FLOWFISH_URL}/communications/dependencies/summary?${qsStr}\`,
  { headers: { "X-API-Key": FLOWFISH_API_KEY } }
);
if (!resp.ok) throw new Error(\`HTTP \${resp.status}: \${await resp.text()}\`);
const deps = await resp.json();

// Extract affected repos from per-service downstream
const affectedRepos = (deps.matched_services ?? []).flatMap(matched =>
  Object.entries(matched.downstream?.by_category ?? {})
    .flatMap(([category, services]) =>
      services
        .filter(svc => svc.annotations?.["git-repo"])
        .map(svc => ({
          repo: svc.annotations["git-repo"],
          service: svc.name,
          upstream: matched.name,
          category,
          critical: svc.is_critical,
        }))
    )
);

console.log(\`Matched \${deps.summary?.total_matched ?? 0} services, found \${affectedRepos.length} affected repos\`);`;
}

export function buildPipelineSnippet(
  params: DependencySummaryParams | null,
  platform: string,
): string {
  const qsStr = buildQueryString(params);
  if (!qsStr) return '';
  const baseUrl = getBaseUrl();

  if (platform === 'azure_devops') {
    return `# Azure DevOps Pipeline - Flowfish Integration
# Set FLOWFISH_API_KEY as a secret variable in Pipeline Settings > Variables
variables:
  FLOWFISH_URL: '${baseUrl}'
  FLOWFISH_QUERY: '${qsStr}'

steps:
  - script: |
      DEPS=$(curl -sf -H "X-API-Key: $(FLOWFISH_API_KEY)" \\
        "$(FLOWFISH_URL)/api/v1/communications/dependencies/summary?$(FLOWFISH_QUERY)")
      echo "$DEPS" > flowfish-deps.json
      
      CRITICAL=$(echo "$DEPS" | python3 -c "
import json,sys
d=json.load(sys.stdin)
c=d.get('summary',{}).get('downstream_critical_count',0)
print(c)
")
      echo "##vso[task.setvariable variable=CRITICAL_DEPS]$CRITICAL"
    displayName: 'Flowfish: Get Cross-Project Dependencies'
    env:
      FLOWFISH_API_KEY: $(FLOWFISH_API_KEY)
      FLOWFISH_URL: $(FLOWFISH_URL)
  
  - script: |
      python ai-agent/analyze.py \\
        --pr-diff $(System.PullRequest.PullRequestId) \\
        --deps flowfish-deps.json
    displayName: 'AI Impact Analysis (Cross-Project)'
    condition: succeededOrFailed()`;
  }

  if (platform === 'github_actions') {
    return `# GitHub Actions - Flowfish Integration
# Store your API key in repository secrets as FLOWFISH_API_KEY
# Set FLOWFISH_URL in repository variables (Settings > Secrets and variables > Actions)
env:
  FLOWFISH_QUERY: '${qsStr}'

jobs:
  flowfish:
    steps:
      - name: Get Flowfish Dependencies
        id: flowfish
        run: |
          curl -sf -H "X-API-Key: \${{ secrets.FLOWFISH_API_KEY }}" \\
            "\${{ vars.FLOWFISH_URL }}/api/v1/communications/dependencies/summary?\${FLOWFISH_QUERY}" \\
            > flowfish-deps.json
          
          CRITICAL=$(python3 -c "
import json
d=json.load(open('flowfish-deps.json'))
print(d.get('summary',{}).get('downstream_critical_count',0))
")
          echo "critical_deps=$CRITICAL" >> $GITHUB_OUTPUT

      - name: AI Impact Analysis
        run: |
          python ai-agent/analyze.py \\
            --pr-diff \${{ github.event.pull_request.number }} \\
            --deps flowfish-deps.json`;
  }

  if (platform === 'gitlab_ci') {
    return `# GitLab CI - Flowfish Integration
# Store FLOWFISH_API_KEY and FLOWFISH_URL as CI/CD variables
variables:
  FLOWFISH_URL: '${baseUrl}'
  FLOWFISH_QUERY: '${qsStr}'

flowfish_dependencies:
  stage: test
  script:
    - |
      curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
        "$FLOWFISH_URL/api/v1/communications/dependencies/summary?$FLOWFISH_QUERY" \\
        > flowfish-deps.json
    - python ai-agent/analyze.py --deps flowfish-deps.json
  artifacts:
    paths:
      - flowfish-deps.json`;
  }

  if (platform === 'jenkins') {
    return `// Jenkins Pipeline - Flowfish Integration
// Store API key as a Secret Text credential named 'flowfish-api-key'
def FLOWFISH_URL = '${baseUrl}'
def FLOWFISH_QUERY = '${qsStr}'

stage('Flowfish Dependencies') {
    steps {
        withCredentials([string(credentialsId: 'flowfish-api-key', variable: 'FLOWFISH_API_KEY')]) {
            script {
                def deps = sh(returnStdout: true, script: """
                    curl -sf -H "X-API-Key: \${FLOWFISH_API_KEY}" \\
                      "\${FLOWFISH_URL}/api/v1/communications/dependencies/summary?\${FLOWFISH_QUERY}"
                """).trim()
                writeFile file: 'flowfish-deps.json', text: deps
            }
        }
    }
}`;
  }

  return `# Generic CI/CD - Flowfish Integration
# Get your API key from Flowfish Settings > API Keys
FLOWFISH_API_KEY='**********'
FLOWFISH_URL='${baseUrl}'
FLOWFISH_QUERY='${qsStr}'

curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
  "$FLOWFISH_URL/api/v1/communications/dependencies/summary?$FLOWFISH_QUERY" \\
  > flowfish-deps.json`;
}

export function buildBlastRadiusCurlSnippet(
  namespace?: string,
  ownerName?: string,
): string {
  const baseUrl = getBaseUrl();
  const target = ownerName || 'your-service-name';
  const ns = namespace || 'default';

  return `# Blast Radius - Pre-deployment Impact Assessment
# Returns risk score, affected services, and recommendations
FLOWFISH_API_KEY='**********'  # Get from Settings > API Keys

curl -s -X POST "${baseUrl}/api/v1/blast-radius/assess" \\
  -H "X-API-Key: $FLOWFISH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "cluster_id": 1,
    "change": {
      "type": "image_update",
      "target": "${target}",
      "namespace": "${ns}",
      "triggered_by": "ci-pipeline",
      "pipeline": "main-deploy"
    }
  }'

# Response includes:
#   risk_score (0-100), risk_level (low/medium/high/critical),
#   blast_radius.total_affected, recommendation, suggested_actions[]
#   advisory_only: true (Flowfish never blocks deployments)`;
}

export function buildBlastRadiusPipelineSnippet(
  platform: string,
  namespace?: string,
  ownerName?: string,
): string {
  const baseUrl = getBaseUrl();
  const target = ownerName || 'your-service-name';
  const ns = namespace || 'default';

  if (platform === 'azure_devops') {
    return `# Azure DevOps - Flowfish Blast Radius Check
# Set FLOWFISH_API_KEY as a secret variable
variables:
  FLOWFISH_URL: '${baseUrl}'

steps:
  - script: |
      RESPONSE=$(curl -s -X POST "$(FLOWFISH_URL)/api/v1/blast-radius/assess" \\
        -H "X-API-Key: $(FLOWFISH_API_KEY)" \\
        -H "Content-Type: application/json" \\
        -d '{
          "cluster_id": $(CLUSTER_ID),
          "change": {
            "type": "image_update",
            "target": "${target}",
            "namespace": "${ns}",
            "triggered_by": "$(Build.RequestedFor)",
            "pipeline": "$(Build.DefinitionName)"
          }
        }')
      
      RISK_SCORE=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('risk_score',0))")
      echo "##vso[task.setvariable variable=RISK_SCORE]$RISK_SCORE"
      echo "Risk Score: $RISK_SCORE/100"
    displayName: 'Flowfish: Blast Radius Check'
    continueOnError: true
    env:
      FLOWFISH_API_KEY: $(FLOWFISH_API_KEY)`;
  }

  if (platform === 'github_actions') {
    return `# GitHub Actions - Flowfish Blast Radius Check
- name: Flowfish Blast Radius Check
  id: blast-radius
  continue-on-error: true
  run: |
    RESPONSE=$(curl -s -X POST \\
      "\${{ secrets.FLOWFISH_URL }}/api/v1/blast-radius/assess" \\
      -H "X-API-Key: \${{ secrets.FLOWFISH_API_KEY }}" \\
      -H "Content-Type: application/json" \\
      -d '{
        "cluster_id": \${{ vars.CLUSTER_ID }},
        "change": {
          "type": "image_update",
          "target": "${target}",
          "namespace": "${ns}",
          "triggered_by": "\${{ github.actor }}",
          "pipeline": "\${{ github.workflow }}"
        }
      }')
    
    RISK_SCORE=$(echo "$RESPONSE" | jq -r '.risk_score // 0')
    echo "risk_score=$RISK_SCORE" >> $GITHUB_OUTPUT
    echo "Risk Score: $RISK_SCORE/100"`;
  }

  if (platform === 'gitlab_ci') {
    return `# GitLab CI - Flowfish Blast Radius Check
flowfish_blast_radius:
  stage: test
  allow_failure: true
  script:
    - |
      RESPONSE=$(curl -s -X POST "$FLOWFISH_URL/api/v1/blast-radius/assess" \\
        -H "X-API-Key: $FLOWFISH_API_KEY" \\
        -H "Content-Type: application/json" \\
        -d '{
          "cluster_id": '$CLUSTER_ID',
          "change": {
            "type": "image_update",
            "target": "${target}",
            "namespace": "${ns}",
            "triggered_by": "'$GITLAB_USER_LOGIN'",
            "pipeline": "'$CI_PIPELINE_NAME'"
          }
        }')
      echo "Risk Score: $(echo $RESPONSE | jq -r '.risk_score')/100"`;
  }

  if (platform === 'jenkins') {
    return `// Jenkins - Flowfish Blast Radius Check
stage('Blast Radius Check') {
    steps {
        script {
            def response = httpRequest(
                url: "\${FLOWFISH_URL}/api/v1/blast-radius/assess",
                httpMode: 'POST',
                contentType: 'APPLICATION_JSON',
                customHeaders: [[name: 'X-API-Key', value: "\${FLOWFISH_API_KEY}"]],
                requestBody: """{
                    "cluster_id": \${CLUSTER_ID},
                    "change": {
                        "type": "image_update",
                        "target": "${target}",
                        "namespace": "${ns}",
                        "triggered_by": "\${BUILD_USER}",
                        "pipeline": "\${JOB_NAME}"
                    }
                }""",
                validResponseCodes: '200:500'
            )
            if (response.status == 200) {
                def result = readJSON(text: response.content)
                echo "Risk Score: \${result.risk_score}/100 (\${result.risk_level})"
            }
        }
    }
}`;
  }

  return `# Generic CI/CD - Flowfish Blast Radius Check
FLOWFISH_API_KEY='**********'
FLOWFISH_URL='${baseUrl}'

curl -s -X POST "$FLOWFISH_URL/api/v1/blast-radius/assess" \\
  -H "X-API-Key: $FLOWFISH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "cluster_id": 1,
    "change": {
      "type": "image_update",
      "target": "${target}",
      "namespace": "${ns}",
      "triggered_by": "ci-pipeline",
      "pipeline": "main-deploy"
    }
  }'`;
}

export const PIPELINE_PLATFORMS = [
  { value: 'azure_devops', label: 'Azure DevOps' },
  { value: 'github_actions', label: 'GitHub Actions' },
  { value: 'gitlab_ci', label: 'GitLab CI' },
  { value: 'jenkins', label: 'Jenkins' },
  { value: 'other', label: 'Other (Generic)' },
];

export const ID_METHODS = [
  { value: 'annotation', label: 'Annotation (e.g. git-repo URL)' },
  { value: 'label', label: 'Label (e.g. app name)' },
  { value: 'namespace_deployment', label: 'Namespace + Deployment' },
  { value: 'pod_name', label: 'Pod Name' },
  { value: 'advanced', label: 'Advanced (any combination)' },
];
