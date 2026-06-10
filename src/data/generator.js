/**
 * Synthetic document generator for vector-search-demo.
 * Returns ~15 documents spread across 5 topic areas.
 * No imports from src/commands/.
 */

const DOCUMENTS = [
  // --- Infrastructure (infra) ---
  {
    doc_id: "infra-001",
    topic: "infra",
    title: "Kubernetes Cluster Autoscaling and Node Management",
    body: `Kubernetes cluster autoscaling allows infrastructure teams to dynamically adjust the number
of worker nodes based on workload demand. The Cluster Autoscaler monitors pending pods that
cannot be scheduled due to insufficient resources and automatically provisions new nodes within
configured minimum and maximum limits. Node groups can be configured with different instance
types to optimize cost and performance. When demand decreases, the autoscaler identifies
underutilized nodes and safely evicts workloads before terminating the underlying virtual
machines. This prevents unnecessary cloud spending during periods of low traffic. Infrastructure
teams should configure pod disruption budgets to ensure that critical services maintain minimum
replica counts during scale-down events. Node affinity and taints can be used to guide the
scheduler toward specific node pools for specialized workloads such as GPU-accelerated machine
learning jobs. Monitoring node pool utilization through metrics pipelines like Prometheus enables
teams to fine-tune autoscaling thresholds and avoid thrashing, where nodes are repeatedly
provisioned and deprovisioned within short intervals. Health checks and readiness probes are
essential to ensure newly provisioned nodes integrate smoothly into the cluster routing table
before traffic is directed to them. Documentation and runbooks should describe the escalation
path when autoscaling reaches its maximum node count and manual intervention is required.`,
  },
  {
    doc_id: "infra-002",
    topic: "infra",
    title: "Terraform Infrastructure as Code Best Practices",
    body: `Terraform enables infrastructure teams to define, provision, and manage cloud resources
using declarative configuration files. Adopting a modular structure separates concerns between
networking, compute, storage, and identity layers so that individual modules can be versioned
and reused across environments. Remote state backends such as AWS S3 with DynamoDB locking
prevent concurrent modification conflicts when multiple engineers apply changes simultaneously.
Workspaces provide lightweight isolation between development, staging, and production without
duplicating configuration files. Variable files and environment-specific overrides allow a
single module to serve multiple deployment targets. Sensitive values like database passwords
should be managed through secret management systems such as HashiCorp Vault or AWS Secrets
Manager and injected at apply time rather than committed to version control. Automated plan
and apply pipelines in CI/CD systems enforce code review before infrastructure changes reach
production environments. Drift detection jobs periodically compare the actual cloud state
against the Terraform state file and alert when manual changes have been made outside the
automation layer. Lifecycle rules prevent accidental destruction of stateful resources such
as database clusters and object storage buckets. Module versioning through a private registry
or Git tags allows teams to adopt improvements incrementally without breaking existing stacks.
Documentation embedded in variable descriptions and output definitions improves discoverability
and reduces onboarding friction for new team members.`,
  },
  {
    doc_id: "infra-003",
    topic: "infra",
    title: "Observability Stack with Prometheus, Grafana, and Loki",
    body: `A modern observability stack combines metrics, logs, and traces to give infrastructure
and application teams complete visibility into system behavior. Prometheus scrapes time-series
metrics from instrumented services through pull-based collection at configurable intervals.
Recording rules pre-aggregate expensive queries so that dashboards load quickly even when
querying millions of data points. Alertmanager receives firing alerts from Prometheus and routes
them to the appropriate on-call channels based on label matchers and routing trees. Grafana
provides a unified visualization layer that can query multiple data sources simultaneously,
enabling correlated views across metrics and logs on a single dashboard. Loki indexes log
streams by label set rather than full-text indexing, which significantly reduces storage costs
while preserving the ability to filter and search log content at query time. Tempo provides
distributed tracing storage and integrates with Grafana to enable trace-to-metric and
trace-to-log correlation. Service level objectives can be modeled as multi-window multi-burn-rate
alerts that detect budget consumption rates and trigger pages before users experience noticeable
degradation. Cardinality management is critical for Prometheus deployments at scale because
high-cardinality labels such as user identifiers can cause memory exhaustion. Sampling strategies
for traces should balance observability coverage with storage costs, typically collecting all
traces for error-bearing requests while sampling a fraction of successful ones. Dashboards should
distinguish between golden signals: latency, traffic, errors, and saturation.`,
  },

  // --- Security (sec) ---
  {
    doc_id: "sec-001",
    topic: "security",
    title: "Zero-Trust Network Architecture Implementation",
    body: `Zero-trust network architecture eliminates implicit trust within corporate network perimeters
and requires continuous verification of every user, device, and workload attempting to access
resources. The core principle assumes that threats exist both outside and inside the traditional
network boundary, making perimeter-based security insufficient in a world of remote work and
cloud-hosted applications. Identity providers authenticate subjects through strong mechanisms
such as hardware security keys or FIDO2 passkeys before granting access tokens. Policy
enforcement points evaluate contextual signals including device health attestation, geolocation,
and behavioral baselines before forwarding requests to protected services. Micro-segmentation
divides the network into fine-grained zones so that a compromised workload cannot laterally
move to adjacent services without re-authenticating. Software-defined perimeters replace VPNs
by provisioning encrypted tunnels only for specific authorized sessions rather than granting
broad network access. Continuous monitoring captures telemetry from every access decision and
feeds it into security information and event management systems for anomaly detection. Access
policies should follow the principle of least privilege and expire automatically so that
standing permissions do not accumulate over time. Regular access reviews ensure that dormant
accounts and over-permissioned service principals are revoked promptly. Integration with
endpoint detection and response platforms allows policy engines to respond dynamically to
threats by revoking certificates or isolating compromised devices without waiting for human
intervention.`,
  },
  {
    doc_id: "sec-002",
    topic: "security",
    title: "Secrets Management and Rotation Strategy",
    body: `Effective secrets management prevents credential exposure across application lifecycle
stages from development through production. Centralized secret stores such as HashiCorp Vault,
AWS Secrets Manager, or Azure Key Vault provide audit logging, access control, and versioning
for all sensitive values including API keys, database passwords, and TLS private keys. Dynamic
secrets reduce the blast radius of credential leakage by generating short-lived credentials
scoped to specific operations rather than sharing static long-lived tokens. Secret injection
at container startup through init containers or sidecar agents avoids baking credentials into
container images or environment variable files that might be logged by orchestration systems.
Rotation schedules should be automated and tested against staging environments before rollout
to production so that applications gracefully handle credential refreshes without downtime.
Break-glass procedures define emergency access pathways when the secrets management system
itself becomes unavailable, typically using hardware-protected master keys stored offline.
Scanning pipelines detect secrets accidentally committed to source control and alert repository
owners within minutes of the push event. Pre-commit hooks provide a complementary local
detection layer that prevents secrets from reaching version control in the first place.
Audit trails from the secrets manager should feed into the centralized logging infrastructure
so that security teams can investigate suspicious access patterns. Encryption at rest for
secret storage backends and in-transit protection for all API calls are baseline requirements
that should be verified through automated compliance checks in the deployment pipeline.`,
  },
  {
    doc_id: "sec-003",
    topic: "security",
    title: "Vulnerability Management and Patch Cadence",
    body: `A structured vulnerability management program reduces the window of exposure between
the public disclosure of security weaknesses and their remediation in production systems.
Asset inventory is the foundation of effective vulnerability management because you cannot
protect what you cannot enumerate. Software composition analysis tools scan application
dependencies for known vulnerabilities reported in databases such as the National Vulnerability
Database and advisories from language package registries. Container image scanning in CI/CD
pipelines blocks promotion of images containing critical or high severity vulnerabilities
unless explicit waivers are approved through a documented exception process. Operating system
packages on virtual machines and container base images should be updated on a regular cadence
aligned with the severity classification of available patches. Critical vulnerabilities with
active public exploits warrant emergency patch cycles that bypass normal change windows.
Penetration testing supplements automated scanning by identifying business logic vulnerabilities
and chained attack paths that automated tools cannot detect. Bug bounty programs incentivize
external security researchers to responsibly disclose vulnerabilities before malicious actors
can exploit them. Mean time to remediation metrics track program effectiveness and highlight
teams or systems where patching velocity is below acceptable thresholds. Compensating controls
such as web application firewall rules can temporarily mitigate exploitable vulnerabilities
while patches are being developed and tested. Executive reporting on vulnerability counts and
aging provides organizational visibility and ensures that security receives appropriate
prioritization alongside feature development.`,
  },

  // --- HR (hr) ---
  {
    doc_id: "hr-001",
    topic: "hr",
    title: "Performance Review and Goal-Setting Framework",
    body: `A well-designed performance review framework aligns individual contributions with
organizational objectives while providing employees with meaningful feedback for professional
growth. Objectives and key results connect team-level goals to measurable outcomes that can
be tracked throughout the review period rather than evaluated only at year-end. Calibration
sessions across departments prevent grade inflation and ensure that performance ratings carry
consistent meaning across different managers and business units. Continuous feedback mechanisms
supplement formal reviews by allowing managers and peers to share observations close to the
relevant event rather than relying on memory months later. Structured templates guide reviewers
toward specific behavioral evidence rather than vague impressions so that feedback is actionable
and defensible. Upward feedback surveys give employees a channel to share observations about
management effectiveness which helps organizations identify high-potential leaders and
managers who need coaching. Compensation planning tied to performance outcomes requires
careful calibration to ensure that rewards reflect both individual performance and market
competitiveness. Talent mobility programs use performance and skills data to match internal
candidates with open roles before resorting to external hiring. Documentation requirements
ensure that performance issues are recorded consistently in personnel files to support fair
and legally defensible disciplinary processes. Career laddering frameworks describe the
competencies expected at each level so that employees understand the criteria for advancement
and can direct their development efforts accordingly.`,
  },
  {
    doc_id: "hr-002",
    topic: "hr",
    title: "Employee Onboarding and Retention Programs",
    body: `Structured onboarding programs reduce time-to-productivity for new hires and
significantly improve early-tenure retention rates. Preboarding activities completed before
the first day ensure that equipment, system access, and compliance training are ready when
employees arrive, eliminating frustrating delays that erode first impressions. Buddy programs
pair new hires with experienced colleagues who can answer informal questions and help them
build internal networks beyond their immediate team. Ninety-day plans set clear expectations
for the ramp period and establish checkpoints where managers and new hires assess progress
together. Cultural immersion components introduce new employees to the company's values,
history, and unwritten norms through storytelling sessions with senior leaders. Exit interview
data should feed directly into onboarding design so that known attrition drivers can be
addressed proactively. Retention analytics identify flight risk signals such as declining
engagement survey scores, reduced project involvement, or internal transfer requests so that
managers can intervene with targeted conversations. Competitive compensation benchmarking
ensures that offer packages remain attractive relative to the external market as the labor
landscape evolves. Career development planning helps employees articulate their aspirations
and connect them to opportunities within the organization before they seek them externally.
Employee resource groups build community and provide belonging for underrepresented groups
whose retention is disproportionately affected by the quality of their social connections
at work. Regular pulse surveys track engagement at high frequency so that emerging issues
surface quickly rather than festering until the annual engagement survey.`,
  },
  {
    doc_id: "hr-003",
    topic: "hr",
    title: "Diversity, Equity, and Inclusion Strategy",
    body: `Building a diverse, equitable, and inclusive organization requires sustained intentional
effort across the full employee lifecycle from sourcing and selection through advancement and
retention. Structured interview processes with standardized questions and rubrics reduce
the influence of unconscious bias in hiring decisions by anchoring evaluations on predetermined
competency criteria. Diverse interview panels ensure that candidates interact with a range of
perspectives during the selection process and signal organizational commitment to inclusion.
Pay equity analyses should be conducted annually to identify and remediate systemic gaps in
compensation across demographic groups before they compound. Promotion rate parity tracking
highlights advancement disparities that may indicate structural barriers or sponsorship gaps
for underrepresented talent. Inclusive leadership training equips managers with language
and frameworks for facilitating belonging in team settings and recognizing microaggressions
before they erode psychological safety. Supplier diversity programs extend inclusion commitments
beyond the workforce to the broader ecosystem of vendors and partners. Transparency in
representation metrics through public reporting creates accountability and allows external
stakeholders to assess progress against stated commitments. Employee resource groups provide
community, mentorship, and feedback channels that help shape organizational policies affecting
their constituencies. Allyship programs empower majority group members to actively support
colleagues from underrepresented backgrounds through advocacy, sponsorship, and interrupting
exclusionary behavior. Accessibility accommodations ensure that employees with disabilities
can participate fully in the workplace without navigating unnecessary friction.`,
  },

  // --- Product (prod) ---
  {
    doc_id: "prod-001",
    topic: "product",
    title: "Product Discovery and User Research Methods",
    body: `Effective product discovery reduces the risk of building features that fail to create
meaningful value for users. Jobs-to-be-done interviews uncover the underlying motivations
and frustrations that drive user behavior rather than surface-level feature preferences that
may not reflect genuine needs. Diary studies track user behavior in natural contexts over
extended periods and reveal patterns that are invisible in controlled lab settings. Prototype
testing with low-fidelity wireframes validates interaction concepts before engineering effort
is committed to production implementation. Usability testing sessions identify friction points
in existing features and provide qualitative evidence that complements quantitative analytics
data. Opportunity scoring frameworks help product teams prioritize discovery themes based on
the combination of user importance and satisfaction with current solutions. Continuous discovery
habits embed lightweight research activities into weekly team routines rather than treating
discovery as a phase that precedes development. Customer advisory boards bring together
power users who can provide strategic input on product direction and early access to validate
concepts with high contextual knowledge. Assumption mapping externalizes the riskiest beliefs
underlying a product strategy so that experiments can be designed to test them efficiently.
Synthesis methods like affinity diagramming and experience mapping translate raw research data
into insights that are accessible to stakeholders across the organization. Northstar metrics
connect discovery work to the outcomes the product is designed to create in users' lives
rather than outputs like features shipped or release frequency.`,
  },
  {
    doc_id: "prod-002",
    topic: "product",
    title: "Agile Release Planning and Roadmap Communication",
    body: `Agile release planning balances long-term strategic direction with the flexibility
to adapt as new information emerges from users, the market, and technical constraints.
Outcome-based roadmaps communicate intent in terms of problems to solve and metrics to move
rather than features to ship, which preserves team autonomy and prevents premature commitment
to specific solutions. Rolling quarterly planning horizons allow teams to incorporate recent
discovery findings without the overhead of full annual planning cycles. OKR frameworks cascade
organizational strategy into team-level objectives that can be evaluated independently while
contributing to company-wide goals. Stakeholder communication rhythms including monthly
business reviews and engineering forums ensure that product direction is visible across
the organization and feedback channels are open. Dependency mapping surfaces cross-team
coordination requirements early enough to address them through architecture decisions or
sequencing adjustments. Capacity planning accounts for technical debt reduction, operational
support, and unplanned work alongside feature delivery so that commitments are realistic.
Release notes and changelog communication inform users about improvements and demonstrate
responsiveness to their feedback. Metrics review cadences close the feedback loop between
shipped features and business outcomes so that teams learn which investments created value
and refine their prioritization models accordingly. Product strategy documents articulate
the market positioning, target user segments, and differentiated value proposition that
guide investment decisions across planning cycles.`,
  },
  {
    doc_id: "prod-003",
    topic: "product",
    title: "Feature Flagging and Controlled Rollouts",
    body: `Feature flags decouple code deployment from feature activation and enable controlled
rollouts that reduce risk while accelerating the pace of experimentation. Percentage rollouts
gradually expose a new feature to an increasing fraction of the user population, allowing
teams to monitor error rates and user engagement metrics before full activation. User
segmentation targets specific cohorts such as beta users, employees, or high-value accounts
for early access without affecting the broader population. Kill switches allow instant
deactivation of problematic features without requiring a code rollback and an emergency
deployment cycle. A/B tests compare the performance of two variants against a primary
metric and secondary guardrail metrics to establish causal evidence that a change improves
outcomes. Multivariate experiments test combinations of changes simultaneously to identify
interaction effects that would be invisible in sequential single-variable tests. Flag hygiene
processes schedule removal of stale flags that have been fully rolled out or permanently
disabled to prevent configuration debt from accumulating in the codebase. Targeting rules
based on company, plan tier, or geographic region support enterprise sales motions where
specific customers need early access to capabilities under negotiation. Audit logs capture
every flag state change with the actor identity and timestamp to support compliance investigations
and incident post-mortems. Integration with observability platforms enables automatic rollback
triggers when key metrics breach predefined thresholds during a rollout event.`,
  },

  // --- Finance (fin) ---
  {
    doc_id: "fin-001",
    topic: "finance",
    title: "Cloud Cost Optimization and FinOps Practices",
    body: `Cloud cost optimization requires continuous collaboration between engineering,
finance, and product teams to align spending with business value creation. Reserved instances
and savings plans reduce compute costs by thirty to sixty percent compared to on-demand
pricing in exchange for one-year or three-year usage commitments. Spot and preemptible
instances offer additional savings of up to ninety percent for fault-tolerant batch workloads
that can tolerate interruption with sufficient notice. Right-sizing analysis compares actual
CPU and memory utilization against provisioned capacity and flags resources where downsizing
would yield savings without performance impact. Storage tiering automatically migrates
infrequently accessed objects to cheaper storage classes based on access frequency metrics,
reducing object storage costs for archival data. Network egress fees represent a significant
and often overlooked cost driver in multi-cloud and hybrid deployments; architecture patterns
that minimize cross-region and cross-cloud data transfer can deliver substantial savings.
FinOps frameworks establish shared accountability by allocating cloud costs to the teams and
products that generate them through tagging strategies and chargeback models. Unit economics
metrics such as cost per active user or cost per transaction enable product teams to evaluate
the financial sustainability of their designs rather than optimizing purely for performance.
Anomaly detection on cost metrics surfaces unexpected spending spikes that may indicate
misconfigurations, security incidents, or runaway automation jobs. Executive dashboards
visualize cloud spending trends and forecast end-of-quarter variance against budget to
support financial planning processes.`,
  },
  {
    doc_id: "fin-002",
    topic: "finance",
    title: "Financial Planning, Budgeting, and Forecasting",
    body: `Annual financial planning processes translate organizational strategy into resource
allocation decisions that determine which initiatives receive investment and at what scale.
Zero-based budgeting requires teams to justify each budget line from first principles rather
than incrementing the prior year's allocation, which surfaces hidden inefficiencies and
reallocates resources toward higher-priority activities. Driver-based forecasting models
connect financial projections to operational metrics such as headcount, customer count, or
transaction volume so that finance teams can update forecasts rapidly as business conditions
change. Rolling forecasts replace static annual budgets with continuously updated twelve-
to eighteen-month projections that incorporate the latest available information. Scenario
planning evaluates financial outcomes under bear, base, and bull case assumptions to stress
test the business model against adverse conditions and identify early warning indicators.
Variance analysis compares actual results to plan and forecast at sufficient granularity
to isolate root causes and update forward-looking models accordingly. Capital expenditure
approval workflows enforce governance over large asset purchases and software development
investments that should be amortized over multiple periods. Revenue recognition policies
must comply with accounting standards such as ASC 606 to ensure that recorded revenue
accurately reflects performance obligations fulfilled during the reporting period. Cash
flow forecasting distinguishes between accrual accounting results and actual liquidity
positions to prevent situations where profitable operations are constrained by working
capital shortfalls. Financial close automation reduces the time required to complete month-
end processes and improves accuracy by eliminating manual data entry and reconciliation steps.`,
  },
  {
    doc_id: "fin-003",
    topic: "finance",
    title: "Procurement, Vendor Management, and Contract Governance",
    body: `Effective procurement governance reduces costs, manages supplier risk, and ensures
that vendor relationships align with organizational policies and regulatory obligations.
Strategic sourcing processes evaluate vendors across multiple dimensions including financial
stability, technical capability, security posture, and sustainability commitments rather
than optimizing solely for unit price. Request for proposal templates standardize evaluation
criteria so that comparisons across competing vendors are objective and defensible. Contract
lifecycle management systems track key terms, renewal dates, and performance obligations
across the vendor portfolio to prevent unintended auto-renewals and surface renegotiation
opportunities. Service level agreements define minimum acceptable performance standards and
remedies for vendor failures that create measurable business impact. Preferred vendor programs
consolidate spending with high-performing suppliers to unlock volume discounts and improve
account management quality. Software asset management ensures that licenses are right-sized
to actual consumption patterns and audits detect overpayment for unused entitlements.
Supplier risk assessments evaluate concentration risk, geopolitical exposure, and business
continuity plans for critical vendors whose failure would disrupt key business processes.
Sustainability procurement policies screen vendors against environmental and social governance
criteria to manage reputational risk and comply with emerging supply chain disclosure
regulations. Vendor performance reviews held quarterly with strategic partners create
accountability and identify improvement opportunities before relationship deterioration
triggers costly switching processes. Purchase order controls and three-way matching between
purchase orders, receipts, and invoices reduce the risk of fraudulent billing and duplicate
payments.`,
  },
];

export function generateDocuments() {
  return DOCUMENTS;
}
