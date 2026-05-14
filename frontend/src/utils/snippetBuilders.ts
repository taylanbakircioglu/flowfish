import type { DependencySummaryParams } from '../store/api/communicationApi';

const getApiBase = () =>
  typeof window !== 'undefined' ? `${window.location.origin}/api/v1` : '/api/v1';

const getBaseUrl = () =>
  typeof window !== 'undefined' ? window.location.origin : 'https://your-flowfish-instance';

// Plan v3 (audit): the snippet generators interpolate user-provided
// strings (annotation values, namespaces, workload names) into
// Python tuples, JSON bodies, and YAML pipeline templates. Without
// escaping, a value like `it's` or `a"b` would silently break the
// generated code at copy/paste time. We centralise the escapes so
// every snippet path uses the same safe semantics.
//
// `escapePython` produces a Python double-quoted string literal where
// backslashes and double quotes are escaped (matches `json.dumps`).
// `escapeYamlSingle` doubles up apostrophes inside YAML/Bash single
// quotes (the standard YAML 1.2 escape for the single-quoted form).
// Newline characters are stripped — they shouldn't appear in any
// dependency identifier and would break every quoting style at once.
export const escapePython = (s: unknown): string => {
  const v = String(s ?? '').replace(/[\r\n]/g, ' ');
  return v.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
};

export const escapeYamlSingle = (s: unknown): string => {
  const v = String(s ?? '').replace(/[\r\n]/g, ' ');
  return v.replace(/'/g, "''");
};

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
  // Plan v3 Akış D m.8 fix: discovery mode (`match_all=true`) and the
  // tenant-guard cluster_id were resolved by IntegrationHub at form
  // submit time but never propagated to the snippet copy/paste path.
  // Operators saw the UI succeed, copied the curl, ran it on their
  // machine, and got `match_all=true required` from the backend
  // tenant guard. We surface both fields so the snippet matches what
  // the live UI actually sends.
  if (params.cluster_id != null) qs.set('cluster_id', String(params.cluster_id));
  if (params.match_all) qs.set('match_all', 'true');
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
  // Audit fix (escape): every value is run through `escapePython` so
  // identifiers containing a quote (`a"b`), backslash, or any control
  // character don't silently break the generated Python tuple syntax
  // when the operator copies the snippet onto their own machine.
  params.analysis_ids.forEach(id => paramLines.push(`    ("analysis_ids", "${escapePython(id)}"),`));
  if (params.annotation_key) paramLines.push(`    ("annotation_key", "${escapePython(params.annotation_key)}"),`);
  if (params.annotation_value) paramLines.push(`    ("annotation_value", "${escapePython(params.annotation_value)}"),`);
  if (params.label_key) paramLines.push(`    ("label_key", "${escapePython(params.label_key)}"),`);
  if (params.label_value) paramLines.push(`    ("label_value", "${escapePython(params.label_value)}"),`);
  if (params.namespace) paramLines.push(`    ("namespace", "${escapePython(params.namespace)}"),`);
  if (params.owner_name) paramLines.push(`    ("owner_name", "${escapePython(params.owner_name)}"),`);
  if (params.pod_name) paramLines.push(`    ("pod_name", "${escapePython(params.pod_name)}"),`);
  if (params.ip) paramLines.push(`    ("ip", "${escapePython(params.ip)}"),`);
  // Plan v3 Akış D m.8 fix: same as buildQueryString — propagate the
  // discovery-mode tenant guard so the Python snippet matches the UI.
  if (params.cluster_id != null) paramLines.push(`    ("cluster_id", "${escapePython(params.cluster_id)}"),`);
  if (params.match_all) paramLines.push(`    ("match_all", "true"),`);
  if (params.depth && params.depth > 1) paramLines.push(`    ("depth", "${escapePython(params.depth)}"),`);

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

// Audit v3 (B-15, B-19): the L7 `/dependencies/summary` endpoint now
// accepts the full L4 identification set — annotation_key/value,
// label_key/value, owner_name (alias for workload_name), pod_name —
// plus the noise filter. We forward every field the IntegrationHub
// collected so the generated snippet matches the live UI Test Query.
//
// `depth` is still NOT a valid L7 summary parameter and is omitted
// here; tree-summary handles depth separately.
function buildL7QueryString(params: DependencySummaryParams | null): string {
  if (!params) return '';
  const qs = new URLSearchParams();
  if (params.analysis_ids?.length) qs.set('analysis_id', String(params.analysis_ids[0]));
  if (params.cluster_id != null) qs.set('cluster_id', String(params.cluster_id));
  if (params.namespace) qs.set('namespace', params.namespace);
  if (params.annotation_key) qs.set('annotation_key', params.annotation_key);
  if (params.annotation_value) qs.set('annotation_value', params.annotation_value);
  if (params.label_key) qs.set('label_key', params.label_key);
  if (params.label_value) qs.set('label_value', params.label_value);
  // owner_name is the L4 nomenclature; the L7 backend aliases it to
  // workload_name via the proxy. We send `owner_name` here so the
  // operator sees the same field name in both L4 and L7 snippets and
  // the proxy normalises it on the way through.
  if (params.owner_name) qs.set('owner_name', params.owner_name);
  if (params.pod_name) qs.set('pod_name', params.pod_name);
  // IntegrationHub always opts in to the noise filter so annotation
  // dumps stay readable (matches the L4 summary aggregator behaviour).
  qs.set('filter_noise_annotations', 'true');
  return qs.toString();
}

export function buildL7CurlSnippet(params: DependencySummaryParams | null): string {
  const qsStr = buildL7QueryString(params);
  if (!qsStr) return '';
  const API_BASE = getApiBase();
  return `# L7 dependency summary (application-level captures)
FLOWFISH_API_KEY='**********'

curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
  "${API_BASE}/l7/dependencies/summary?${qsStr}"`;
}

export function buildL7PythonSnippet(params: DependencySummaryParams | null): string {
  if (!params) return '';
  const API_BASE = getApiBase();
  const paramLines: string[] = [];
  // Audit v3 (B-15): keep the parameter set 1:1 with
  // `buildL7QueryString` so curl, Python, and JS snippets stay in
  // lockstep. Every interpolated value is run through escapePython.
  if (params.analysis_ids?.length) paramLines.push(`    ("analysis_id", "${escapePython(params.analysis_ids[0])}"),`);
  if (params.cluster_id != null) paramLines.push(`    ("cluster_id", "${escapePython(params.cluster_id)}"),`);
  if (params.namespace) paramLines.push(`    ("namespace", "${escapePython(params.namespace)}"),`);
  if (params.annotation_key) paramLines.push(`    ("annotation_key", "${escapePython(params.annotation_key)}"),`);
  if (params.annotation_value) paramLines.push(`    ("annotation_value", "${escapePython(params.annotation_value)}"),`);
  if (params.label_key) paramLines.push(`    ("label_key", "${escapePython(params.label_key)}"),`);
  if (params.label_value) paramLines.push(`    ("label_value", "${escapePython(params.label_value)}"),`);
  if (params.owner_name) paramLines.push(`    ("owner_name", "${escapePython(params.owner_name)}"),`);
  if (params.pod_name) paramLines.push(`    ("pod_name", "${escapePython(params.pod_name)}"),`);
  paramLines.push(`    ("filter_noise_annotations", "true"),`);

  return `import requests, sys

FLOWFISH_URL = "${API_BASE}"
FLOWFISH_API_KEY = "**********"

resp = requests.get(
    f"{FLOWFISH_URL}/l7/dependencies/summary",
    params=[
${paramLines.join('\n')}
    ],
    headers={"X-API-Key": FLOWFISH_API_KEY},
    timeout=30,
)
resp.raise_for_status()
data = resp.json()

if not data.get("success"):
    print(f"Error: {data.get('error', 'Unknown')}", file=sys.stderr)
    sys.exit(1)

workloads = data.get("workloads", [])
print(f"Total workloads: {len(workloads)}")
for w in workloads[:10]:
    err_pct = w.get("error_rate_percent", 0)
    print(f"  {w['namespace']}/{w['name']}: {w.get('request_count', 0)} reqs, {err_pct:.1f}% errors")`;
}

export function buildL7JsSnippet(params: DependencySummaryParams | null): string {
  const qsStr = buildL7QueryString(params);
  if (!qsStr) return '';
  const API_BASE = getApiBase();
  return `const FLOWFISH_API_KEY = "**********";
const FLOWFISH_URL = "${API_BASE}";

const resp = await fetch(
  \`\${FLOWFISH_URL}/l7/dependencies/summary?${qsStr}\`,
  { headers: { "X-API-Key": FLOWFISH_API_KEY } }
);
if (!resp.ok) throw new Error(\`HTTP \${resp.status}: \${await resp.text()}\`);
const data = await resp.json();
console.log(data);`;
}

export function buildL7JavaSnippet(params: DependencySummaryParams | null): string {
  const qsStr = buildL7QueryString(params);
  if (!qsStr) return '';
  const API_BASE = getApiBase();
  return `// Java 11+ HttpClient — Flowfish L7 dependency summary
String FLOWFISH_API_KEY = "**********"; // Settings > API Keys
HttpClient client = HttpClient.newHttpClient();
String url = "${API_BASE}/l7/dependencies/summary?${qsStr}";
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create(url))
    .header("X-API-Key", FLOWFISH_API_KEY)
    .GET()
    .build();

HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
JsonObject data = JsonParser.parseString(response.body()).getAsJsonObject();
System.out.println("Workloads: " + data.getAsJsonArray("workloads").size());`;
}

// Audit v3 (B-17): the L7 tree-summary backend supports label and
// annotation filters. We forward every IntegrationHub form field
// that has a tree-summary analogue, including `workload_name_exact`
// which we pin to `false` so the snippet reproduces the
// case-insensitive substring behaviour the live IntegrationHub uses.
// Default backend semantics (exact match) are preserved for any
// non-IntegrationHub caller because the parameter is only emitted
// when the snippet builder runs.
function buildL7TreeQueryString(params: DependencySummaryParams | null): string {
  if (!params) return '';
  const qs = new URLSearchParams();
  if (params.analysis_ids?.length) qs.set('analysis_id', String(params.analysis_ids[0]));
  if (params.cluster_id != null) qs.set('cluster_id', String(params.cluster_id));
  if (params.namespace) qs.set('namespace', params.namespace);
  if (params.owner_name) {
    qs.set('workload_name', params.owner_name);
    // Match the live UI behaviour — IntegrationHub treats owner_name
    // as a substring identifier (L4 parity), so the snippet uses the
    // same matcher.
    qs.set('workload_name_exact', 'false');
  }
  if (params.label_key) qs.set('label_key', params.label_key);
  if (params.label_value) qs.set('label_value', params.label_value);
  if (params.annotation_key) qs.set('annotation_key', params.annotation_key);
  if (params.annotation_value) qs.set('annotation_value', params.annotation_value);
  if (params.depth && params.depth > 1) qs.set('depth', String(params.depth));
  return qs.toString();
}

export function buildL7TreeCurlSnippet(params: DependencySummaryParams | null): string {
  const qsStr = buildL7TreeQueryString(params);
  if (!qsStr) return '';
  const API_BASE = getApiBase();
  return `# L7 dependency tree-summary (per-workload downstream/callers)
FLOWFISH_API_KEY='**********'

curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
  "${API_BASE}/l7/dependencies/tree-summary?${qsStr}"

# Filter by label:
# curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
#   "${API_BASE}/l7/dependencies/tree-summary?${qsStr}&label_key=app&label_value=frontend"

# Filter by annotation:
# curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
#   "${API_BASE}/l7/dependencies/tree-summary?${qsStr}&annotation_key=team&annotation_value=platform"`;
}

export function buildL7TreePythonSnippet(params: DependencySummaryParams | null): string {
  if (!params) return '';
  const API_BASE = getApiBase();
  const paramLines: string[] = [];
  // Audit fix: escape every value, mirror buildL7TreeQueryString so
  // the Python and curl snippets always agree, and surface real
  // label/annotation values when the operator filled them in (the
  // commented hints stay in place when the field is empty as a
  // discoverability aid).
  if (params.analysis_ids?.length) paramLines.push(`    ("analysis_id", "${escapePython(params.analysis_ids[0])}"),`);
  if (params.cluster_id != null) paramLines.push(`    ("cluster_id", "${escapePython(params.cluster_id)}"),`);
  if (params.namespace) paramLines.push(`    ("namespace", "${escapePython(params.namespace)}"),`);
  if (params.owner_name) paramLines.push(`    ("workload_name", "${escapePython(params.owner_name)}"),`);
  if (params.depth && params.depth > 1) paramLines.push(`    ("depth", "${escapePython(params.depth)}"),`);
  if (params.label_key) {
    paramLines.push(`    ("label_key", "${escapePython(params.label_key)}"),`);
  } else {
    paramLines.push(`    # ("label_key", "app"),          # optional label filter`);
  }
  if (params.label_value) {
    paramLines.push(`    ("label_value", "${escapePython(params.label_value)}"),`);
  } else {
    paramLines.push(`    # ("label_value", "frontend"),    # optional label value`);
  }
  if (params.annotation_key) {
    paramLines.push(`    ("annotation_key", "${escapePython(params.annotation_key)}"),`);
  } else {
    paramLines.push(`    # ("annotation_key", "team"),     # optional annotation filter`);
  }
  if (params.annotation_value) {
    paramLines.push(`    ("annotation_value", "${escapePython(params.annotation_value)}"),`);
  } else {
    paramLines.push(`    # ("annotation_value", "platform"), # optional annotation value`);
  }

  return `import requests

FLOWFISH_URL = "${API_BASE}"
FLOWFISH_API_KEY = "**********"

resp = requests.get(
    f"{FLOWFISH_URL}/l7/dependencies/tree-summary",
    params=[
${paramLines.join('\n')}
    ],
    headers={"X-API-Key": FLOWFISH_API_KEY},
)
resp.raise_for_status()
tree = resp.json()

for svc in tree.get("matched_services", []):
    ds_total = svc.get("downstream", {}).get("total", 0)
    cl_total = svc.get("callers", {}).get("total", 0)
    labels = svc.get("labels", {})
    print(f"{svc['namespace']}/{svc['name']}: {ds_total} downstream, {cl_total} callers, labels={labels}")`;
}

export function buildL7PipelineSnippet(
  params: DependencySummaryParams | null,
  platform: string,
): string {
  const rawQs = buildL7QueryString(params);
  if (!rawQs) return '';
  // Audit fix (SB6): every pipeline snippet wraps `qsStr` and
  // `baseUrl` in YAML/Bash single quotes. URLSearchParams does NOT
  // encode the apostrophe character, so a value like `it's` would
  // collapse the surrounding string and produce a syntax error in
  // the operator's YAML/Bash. We escape both values with the
  // YAML 1.2 single-quoted form ('foo''bar') so any apostrophe is
  // safely round-tripped through the generated config.
  const qsStr = escapeYamlSingle(rawQs);
  const baseUrl = escapeYamlSingle(getBaseUrl());

  if (platform === 'azure_devops') {
    return `# Azure DevOps — L7 dependency summary with quality gates
variables:
  FLOWFISH_URL: '${baseUrl}'
  FLOWFISH_QUERY: '${qsStr}'
steps:
  - script: |
      curl -sf -H "X-API-Key: $(FLOWFISH_API_KEY)" \\
        "$(FLOWFISH_URL)/api/v1/l7/dependencies/summary?$(FLOWFISH_QUERY)" | tee flowfish-l7-deps.json
      # Quality gate: fail if error rate exceeds threshold
      TOTAL_WORKLOADS=$(jq '.workloads | length' flowfish-l7-deps.json)
      HIGH_ERROR=$(jq '[.workloads[] | select(.error_rate_percent > 20)] | length' flowfish-l7-deps.json)
      echo "##vso[task.setvariable variable=L7_WORKLOADS]$TOTAL_WORKLOADS"
      echo "##vso[task.setvariable variable=L7_HIGH_ERROR]$HIGH_ERROR"
      if [ "$HIGH_ERROR" -gt 0 ]; then echo "##vso[task.logissue type=warning]$HIGH_ERROR workloads with >20% error rate"; fi
    displayName: Flowfish L7 dependencies
    env:
      FLOWFISH_API_KEY: $(FLOWFISH_API_KEY)`;
  }

  if (platform === 'github_actions') {
    return `# GitHub Actions — L7 dependency summary with quality gates
env:
  FLOWFISH_QUERY: '${qsStr}'
jobs:
  flowfish_l7:
    runs-on: ubuntu-latest
    steps:
      - name: Get L7 Dependencies
        run: |
          curl -sf -H "X-API-Key: \${{ secrets.FLOWFISH_API_KEY }}" \\
            "\${{ vars.FLOWFISH_URL }}/api/v1/l7/dependencies/summary?\${FLOWFISH_QUERY}" \\
            > flowfish-l7-deps.json
          echo "L7_WORKLOADS=$(jq '.workloads | length' flowfish-l7-deps.json)" >> $GITHUB_ENV
          echo "L7_HIGH_ERROR=$(jq '[.workloads[] | select(.error_rate_percent > 20)] | length' flowfish-l7-deps.json)" >> $GITHUB_ENV`;
  }

  if (platform === 'gitlab_ci') {
    return `# GitLab CI — L7 dependency summary
variables:
  FLOWFISH_URL: '${baseUrl}'
  FLOWFISH_QUERY: '${qsStr}'

flowfish_l7_dependencies:
  stage: test
  script:
    - |
      curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
        "$FLOWFISH_URL/api/v1/l7/dependencies/summary?$FLOWFISH_QUERY" \\
        > flowfish-l7-deps.json
  artifacts:
    paths:
      - flowfish-l7-deps.json`;
  }

  if (platform === 'jenkins') {
    return `// Jenkins Pipeline — L7 dependency summary
def FLOWFISH_URL = '${baseUrl}'
def FLOWFISH_QUERY = '${qsStr}'

stage('L7 Dependencies') {
    steps {
        withCredentials([string(credentialsId: 'flowfish-api-key', variable: 'FLOWFISH_API_KEY')]) {
            script {
                def deps = sh(returnStdout: true, script: """
                    curl -sf -H "X-API-Key: \${FLOWFISH_API_KEY}" \\
                      "\${FLOWFISH_URL}/api/v1/l7/dependencies/summary?\${FLOWFISH_QUERY}"
                """).trim()
                writeFile file: 'flowfish-l7-deps.json', text: deps
            }
        }
    }
}`;
  }

  return `# Generic — L7 dependency summary
FLOWFISH_API_KEY='**********'
FLOWFISH_URL='${baseUrl}'
FLOWFISH_QUERY='${qsStr}'
curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
  "$FLOWFISH_URL/api/v1/l7/dependencies/summary?$FLOWFISH_QUERY"`;
}

export function buildL7TreePipelineSnippet(
  params: DependencySummaryParams | null,
  platform: string,
): string {
  const rawQs = buildL7TreeQueryString(params);
  if (!rawQs) return '';
  const qsStr = escapeYamlSingle(rawQs);
  const baseUrl = escapeYamlSingle(getBaseUrl());

  if (platform === 'azure_devops') {
    return `# Azure DevOps — L7 tree-summary with quality gates
variables:
  FLOWFISH_URL: '${baseUrl}'
  FLOWFISH_QUERY: '${qsStr}'
steps:
  - script: |
      curl -sf -H "X-API-Key: $(FLOWFISH_API_KEY)" \\
        "$(FLOWFISH_URL)/api/v1/l7/dependencies/tree-summary?$(FLOWFISH_QUERY)" | tee flowfish-l7-tree.json
      TOTAL_SVC=$(jq '.matched_services | length' flowfish-l7-tree.json)
      HIGH_ERROR=$(jq '[.matched_services[] | select(.error_rate_percent > 20)] | length' flowfish-l7-tree.json)
      echo "##vso[task.setvariable variable=L7_TREE_SERVICES]$TOTAL_SVC"
      echo "##vso[task.setvariable variable=L7_TREE_HIGH_ERROR]$HIGH_ERROR"
      if [ "$HIGH_ERROR" -gt 0 ]; then echo "##vso[task.logissue type=warning]$HIGH_ERROR services with >20% error rate"; fi
    displayName: Flowfish L7 tree-summary
    env:
      FLOWFISH_API_KEY: $(FLOWFISH_API_KEY)`;
  }

  if (platform === 'github_actions') {
    return `# GitHub Actions — L7 tree-summary with quality gates
env:
  FLOWFISH_QUERY: '${qsStr}'
jobs:
  flowfish_l7_tree:
    runs-on: ubuntu-latest
    steps:
      - name: Get L7 Tree Summary
        run: |
          curl -sf -H "X-API-Key: \${{ secrets.FLOWFISH_API_KEY }}" \\
            "\${{ vars.FLOWFISH_URL }}/api/v1/l7/dependencies/tree-summary?\${FLOWFISH_QUERY}" \\
            > flowfish-l7-tree.json
          echo "L7_TREE_SERVICES=$(jq '.matched_services | length' flowfish-l7-tree.json)" >> $GITHUB_ENV
          echo "L7_TREE_HIGH_ERROR=$(jq '[.matched_services[] | select(.error_rate_percent > 20)] | length' flowfish-l7-tree.json)" >> $GITHUB_ENV`;
  }

  if (platform === 'gitlab_ci') {
    return `# GitLab CI — L7 tree-summary with quality gates
variables:
  FLOWFISH_URL: '${baseUrl}'
  FLOWFISH_QUERY: '${qsStr}'

flowfish_l7_tree:
  stage: test
  script:
    - |
      curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
        "$FLOWFISH_URL/api/v1/l7/dependencies/tree-summary?$FLOWFISH_QUERY" \\
        | tee flowfish-l7-tree.json
      HIGH_ERROR=$(jq '[.matched_services[] | select(.error_rate_percent > 20)] | length' flowfish-l7-tree.json)
      if [ "$HIGH_ERROR" -gt 0 ]; then echo "WARNING: $HIGH_ERROR services with >20% error rate"; fi
  artifacts:
    paths:
      - flowfish-l7-tree.json`;
  }

  if (platform === 'jenkins') {
    return `// Jenkins Pipeline — L7 tree-summary with quality gates
def FLOWFISH_URL = '${baseUrl}'
def FLOWFISH_QUERY = '${qsStr}'

stage('L7 Tree Summary') {
    steps {
        withCredentials([string(credentialsId: 'flowfish-api-key', variable: 'FLOWFISH_API_KEY')]) {
            script {
                def tree = sh(returnStdout: true, script: """
                    curl -sf -H "X-API-Key: \${FLOWFISH_API_KEY}" \\
                      "\${FLOWFISH_URL}/api/v1/l7/dependencies/tree-summary?\${FLOWFISH_QUERY}"
                """).trim()
                writeFile file: 'flowfish-l7-tree.json', text: tree
                def highError = sh(returnStdout: true, script: "jq '[.matched_services[] | select(.error_rate_percent > 20)] | length' flowfish-l7-tree.json").trim()
                if (highError.toInteger() > 0) { unstable("\${highError} services with >20% error rate") }
            }
        }
    }
}`;
  }

  return `# Generic — L7 tree-summary
FLOWFISH_API_KEY='**********'
FLOWFISH_URL='${baseUrl}'
FLOWFISH_QUERY='${qsStr}'
curl -sf -H "X-API-Key: $FLOWFISH_API_KEY" \\
  "$FLOWFISH_URL/api/v1/l7/dependencies/tree-summary?$FLOWFISH_QUERY" | tee flowfish-l7-tree.json
# Quality gate: check for high-error services
jq '[.matched_services[] | select(.error_rate_percent > 20)] | length' flowfish-l7-tree.json`;
}

export function buildPipelineSnippet(
  params: DependencySummaryParams | null,
  platform: string,
): string {
  const rawQs = buildQueryString(params);
  if (!rawQs) return '';
  const qsStr = escapeYamlSingle(rawQs);
  const baseUrl = escapeYamlSingle(getBaseUrl());

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

// Audit fix (SB4): Blast Radius snippets used to hard-code
// `cluster_id: 1`, which silently misled every operator running on
// a cluster other than the original demo install — and broke
// completely on multi-cluster setups. The IntegrationHub now passes
// the cluster_id resolved from the selected analysis (it knows the
// owning cluster, even for multi-cluster analyses where it picks
// the primary). The placeholder fallback only triggers when the
// caller of the builder didn't have a cluster context (e.g. legacy
// usage); in that case we leave a clearly-named token the operator
// has to replace before running the curl.
//
// Embedded JSON values are wrapped in `escapePython`-style escaping
// (it doubles as JSON-string-safe: backslash and double-quote) so a
// service name like `payment"v2` doesn't break the JSON body.
const escapeJsonString = escapePython;

export function buildBlastRadiusCurlSnippet(
  namespace?: string,
  ownerName?: string,
  clusterId?: number,
): string {
  const baseUrl = getBaseUrl();
  const target = escapeJsonString(ownerName || 'your-service-name');
  const ns = escapeJsonString(namespace || 'default');
  const cluster = clusterId != null ? String(clusterId) : 'YOUR_CLUSTER_ID';
  // Round 2 audit (snippet UX): when no cluster id was supplied we
  // emit `YOUR_CLUSTER_ID` as a literal placeholder. JSON parsers
  // refuse the unquoted identifier, so without a banner the operator
  // would copy/paste, run, and get an opaque "expected value" parse
  // error from curl. We add a TODO/heading line so it's impossible
  // to miss before submission.
  const clusterTodo = clusterId == null
    ? `# !!! TODO: replace YOUR_CLUSTER_ID with a numeric cluster id from Settings > Clusters\n`
    : '';

  return `# Blast Radius - Pre-deployment Impact Assessment
# Returns risk score, affected services, and recommendations
${clusterTodo}FLOWFISH_API_KEY='**********'  # Get from Settings > API Keys

curl -s -X POST "${baseUrl}/api/v1/blast-radius/assess" \\
  -H "X-API-Key: $FLOWFISH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "cluster_id": ${cluster},
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
  clusterId?: number,
): string {
  const baseUrl = escapeYamlSingle(getBaseUrl());
  const target = escapeJsonString(ownerName || 'your-service-name');
  const ns = escapeJsonString(namespace || 'default');
  // Pipeline platforms still expose the cluster_id via env/secrets
  // ($(CLUSTER_ID), ${{ vars.CLUSTER_ID }}, $CLUSTER_ID), so when the
  // operator's selection has a definite cluster we render it as a
  // literal default and emit a comment that they can switch back to
  // the variable form for multi-environment pipelines. When no
  // cluster is supplied we keep the existing variable form.
  const clusterLiteral = clusterId != null ? String(clusterId) : null;

  if (platform === 'azure_devops') {
    const azureCluster = clusterLiteral ?? '$(CLUSTER_ID)';
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
          "cluster_id": ${azureCluster},
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
    const ghCluster = clusterLiteral ?? '${{ vars.CLUSTER_ID }}';
    // Round 2 audit (snippet consistency): the URL is a public
    // endpoint, not a secret. Use `vars.FLOWFISH_URL` (repository
    // variable) just like the dependency snippet, instead of
    // `secrets.FLOWFISH_URL`. Mixing vars/secrets between snippets
    // forces operators to define the same value twice — and putting a
    // URL in `secrets` masks it from logs which makes debugging much
    // harder than it needs to be.
    return `# GitHub Actions - Flowfish Blast Radius Check
- name: Flowfish Blast Radius Check
  id: blast-radius
  continue-on-error: true
  run: |
    RESPONSE=$(curl -s -X POST \\
      "\${{ vars.FLOWFISH_URL }}/api/v1/blast-radius/assess" \\
      -H "X-API-Key: \${{ secrets.FLOWFISH_API_KEY }}" \\
      -H "Content-Type: application/json" \\
      -d '{
        "cluster_id": ${ghCluster},
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
    const glCluster = clusterLiteral ?? "'$CLUSTER_ID'";
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
          "cluster_id": ${glCluster},
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
    // Jenkins/Groovy uses `${CLUSTER_ID}` for variable interpolation.
    // Single-quoted JS strings don't perform template interpolation,
    // so the literal text "${CLUSTER_ID}" survives intact into the
    // generated Groovy script. When a concrete cluster id is provided
    // we substitute the numeric literal instead.
    const jenkinsCluster = clusterLiteral ?? '${CLUSTER_ID}';
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
                    "cluster_id": ${jenkinsCluster},
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

  const genericCluster = clusterLiteral ?? 'YOUR_CLUSTER_ID';
  const genericClusterTodo = clusterLiteral == null
    ? `# !!! TODO: replace YOUR_CLUSTER_ID with a numeric cluster id (or set CLUSTER_ID as a CI variable)\n`
    : '';
  return `# Generic CI/CD - Flowfish Blast Radius Check
${genericClusterTodo}FLOWFISH_API_KEY='**********'
FLOWFISH_URL='${baseUrl}'

curl -s -X POST "$FLOWFISH_URL/api/v1/blast-radius/assess" \\
  -H "X-API-Key: $FLOWFISH_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "cluster_id": ${genericCluster},
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
  // Audit v3 (UI parity): L4 and L7 share this identification field
  // — L4 resolves the Pod controller (Deployment/StatefulSet) while
  // L7 resolves the L7Workload owner. The wider label reflects the
  // shared semantic so a single radio button covers both flows.
  { value: 'namespace_deployment', label: 'Namespace + Deployment / Workload' },
  { value: 'pod_name', label: 'Pod Name' },
  { value: 'advanced', label: 'Advanced (any combination)' },
];
