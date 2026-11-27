/**
 * Shared types.
 *
 * The `ServiceHealth`, `ServiceInfo`, `SystemMetrics`, `Decision` and
 * `DetectionResult` shapes mirror the Pydantic response models of the real
 * FastAPI services (edge/api/routes.py, cloud/api/routes.py,
 * scheduler/api/routes.py, orchestrator/api/routes.py). Everything below them
 * is a dashboard view-model assembled by the data-source layer.
 */

export type DataSourceMode = 'demo' | 'live';
export type NodeRole = 'edge' | 'cloud';
export type Target = 'edge' | 'cloud' | 'queue' | 'error';
export type Priority = 'low' | 'medium' | 'high';

// ---------------------------------------------------------------------------
// Backend API models (real endpoints)
// ---------------------------------------------------------------------------

export interface ServiceHealth {
  status: string;
  service: string;
  version: string;
  timestamp: string;
  model_loaded?: boolean;
  camera_open?: boolean;
  camera_status?: "connected" | "not_connected";
}

export interface ServiceInfo {
  service: string;
  version: string;
  uptime_sec: number;
  endpoints: string[];
  edge_url?: string;
  cloud_url?: string;
  scheduler_url?: string;
  policy?: string;
  scheduler?: Decision;
}

export interface SystemMetrics {
  cpu_percent: number;
  ram_percent: number;
  ram_used_gb: number;
  ram_total_gb: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
  timestamp: string;
}

export interface Decision {
  workload_id: string;
  target: Target;
  score: number;
  reason: string;
  priority: Priority;
  timestamp: string;
}

export interface DetectionBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface Detection {
  bbox: DetectionBox;
  confidence: number;
  class_id: number;
  class_name: string;
}

export interface DetectionResult {
  source: string;
  timestamp: string;
  frame_width: number;
  frame_height: number;
  inference_ms: number;
  detections: Detection[];
  annotated_image_base64?: string | null;
  count?: number;
}

// ---------------------------------------------------------------------------
// Dashboard view-models
// ---------------------------------------------------------------------------

export interface NodeStatus {
  role: NodeRole;
  reachable: boolean;
  health: ServiceHealth | null;
  metrics: SystemMetrics | null;
  info: ServiceInfo | null;
  probeLatencyMs: number | null;
  probedAt: number;
  error: string | null;
}

export interface LatencyPoint {
  t: number;
  edgeMs: number;
  cloudMs: number;
  schedulerMs: number;
  totalMs: number;
}

export interface ResourcePoint {
  t: number;
  edgeCpu: number;
  edgeRam: number;
  edgeDisk: number;
  cloudCpu: number;
  cloudRam: number;
  cloudDisk: number;
}

export interface RequestTotals {
  total: number;
  edge: number;
  cloud: number;
  failed: number;
  queued: number;
  windowHours: number;
}

export type RoutingStatus = 'success' | 'failed' | 'queued' | 'fallback';

export interface RoutingRecord {
  id: string;
  t: number;
  priority: Priority;
  workloadType: string;
  selectedTarget: Target;
  actualTarget: Target | null;
  score: number;
  reason: string;
  status: RoutingStatus;
  schedulerMs: number;
  inferenceMs: number | null;
  totalMs: number;
  fallbackUsed: boolean;
  fallbackReason: string | null;
  detectionCount: number;
}

export interface OverviewSnapshot {
  mode: DataSourceMode;
  edge: NodeStatus;
  cloud: NodeStatus;
  orchestrator: ServiceHealth | null;
  scheduler: ServiceHealth | null;
  orchestratorInfo: ServiceInfo | null;
  totals: RequestTotals | null;
  distribution: { edge: number; cloud: number } | null;
  avgInferenceMs: number | null;
  avgSchedulerMs: number | null;
  p95InferenceMs: number | null;
  latencySeries: LatencyPoint[] | null;
  resourceSeries: ResourcePoint[] | null;
  recentActivity: RoutingRecord[] | null;
}

export interface RoutingSnapshot {
  records: RoutingRecord[];
  decisionCounts: { target: Target; count: number }[];
  avgSchedulerMs: number | null;
  edgeSharePct: number | null;
}

export interface ConnectivityInfo {
  label: string;
  baseUrl: string;
  transport: string;
  reachable: boolean;
  probeLatencyMs: number | null;
  note: string;
}

export interface InferenceClassCount {
  name: string;
  count: number;
  confidence: number;
}

export interface InferenceRecord {
  id: string;
  t: number;
  destination: NodeRole;
  source: string;
  inferenceMs: number;
  status: 'success' | 'failed';
  frameWidth: number;
  frameHeight: number;
  classes: InferenceClassCount[];
  detectionCount: number;
}

export interface InferenceFeed {
  records: InferenceRecord[];
  total: number;
  avgMs: number | null;
  p95Ms: number | null;
  edgeAvgMs: number | null;
  cloudAvgMs: number | null;
  classHistogram: { name: string; value: number }[];
  series: LatencyPoint[] | null;
}

export type PodStatus = 'Running' | 'Pending' | 'Failed' | 'Succeeded';

export interface WorkloadItem {
  name: string;
  namespace: string;
  role: string;
  status: PodStatus;
  ready: string;
  restarts: number;
  node: string;
  image: string;
  age: string;
  cpu: string;
  memory: string;
}

export interface ServiceItem {
  name: string;
  namespace: string;
  type: string;
  port: number;
  nodePort: number | null;
  selector: string;
  endpoints: number;
}

export interface ClusterNode {
  name: string;
  status: 'Ready' | 'NotReady';
  role: string;
  version: string;
  internalIp: string;
  pods: number;
}

export interface WorkloadInventory {
  summary: { running: number; pending: number; failed: number; restarts: number };
  pods: WorkloadItem[];
  services: ServiceItem[];
  nodes: ClusterNode[];
}

export interface NodeDetail extends NodeStatus {
  connectivity: ConnectivityInfo;
  utilizationSeries: ResourcePoint[] | null;
  inferenceSeries: LatencyPoint[] | null;
  workloads: WorkloadItem[] | null;
  recentInference: InferenceRecord[] | null;
}

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface SystemEvent {
  id: string;
  t: number;
  level: LogLevel;
  source: 'orchestrator' | 'scheduler' | 'edge' | 'cloud' | 'k3s' | 'kubeedge';
  message: string;
}

export interface LogFeed {
  events: SystemEvent[];
  counts: Record<LogLevel, number>;
}

export interface DecisionProbeInput {
  edgeUrl?: string;
  cloudUrl?: string;
}

/**
 * Single interface implemented twice: once by the live service layer (real
 * FastAPI endpoints) and once by the clearly-labelled mock service.
 *
 * Methods returning `null` mean "the backend does not expose an endpoint for
 * this view yet" - the UI renders an explicit not-available state instead of
 * inventing production numbers.
 */
export interface DataSource {
  mode: DataSourceMode;
  label: string;
  hint: string;
  getOverview(): Promise<OverviewSnapshot>;
  getRouting(): Promise<RoutingSnapshot | null>;
  getNode(role: NodeRole): Promise<NodeDetail>;
  getWorkloads(): Promise<WorkloadInventory | null>;
  getInference(): Promise<InferenceFeed | null>;
  getLogs(): Promise<LogFeed | null>;
  probeDecision(input?: DecisionProbeInput): Promise<Decision>;
}
