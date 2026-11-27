import { useState, type ChangeEvent, type FormEvent } from 'react';
import { Activity, ArrowRight, Brain, CheckCircle2, Cpu, ImagePlus, LoaderCircle, Timer, UploadCloud } from 'lucide-react';
import { env } from '../config/env';
import { MetricCard } from '../components/ui/MetricCard';
import { Panel } from '../components/ui/Panel';
import { StatusBadge, TargetBadge } from '../components/ui/StatusBadge';
import { InlineNote } from '../components/ui/States';

type Priority = 'low' | 'medium' | 'high';

interface InferencePayload {
  count?: number;
  detections?: Array<{ class_name: string; confidence: number; class_id: number }>;
  annotated_image_base64?: string | null;
  inference_ms?: number;
  frame_width?: number;
  frame_height?: number;
}

interface OrchestrationResponse {
  workload_id: string;
  priority: Priority;
  selected_target: string;
  actual_target: string | null;
  decision_score: number;
  decision_reason: string;
  fallback_used: boolean;
  fallback_reason: string | null;
  inference_result: InferencePayload | null;
  scheduler_latency_ms: number;
  inference_latency_ms: number | null;
  total_latency_ms: number;
  timestamp: string;
}

export function InferenceMonitorPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [priority, setPriority] = useState<Priority>('medium');
  const [confidence, setConfidence] = useState(0.25);
  const [annotated, setAnnotated] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<OrchestrationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] ?? null;
    setResult(null);
    setError(null);
    if (!selected) {
      setFile(null);
      setPreview(null);
      return;
    }
    if (!selected.type.startsWith('image/')) {
      setFile(null);
      setPreview(null);
      setError('Please choose an image file (JPEG, PNG or WebP).');
      return;
    }
    if (selected.size > 5 * 1024 * 1024) {
      setFile(null);
      setPreview(null);
      setError('Please choose an image smaller than 5 MB for this live demo.');
      return;
    }
    setFile(selected);
    const reader = new FileReader();
    reader.onload = () => setPreview(typeof reader.result === 'string' ? reader.result : null);
    reader.onerror = () => setError('The selected image could not be read.');
    reader.readAsDataURL(selected);
  };

  const runInference = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setError('Choose an image before starting inference.');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const dataUrl = await readAsDataUrl(file);
      const imageBase64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
      const response = await fetch(`${env.orchestratorUrl}/orchestrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workload: {
            workload_id: `faculty-demo-${Date.now()}`,
            priority,
            workload_type: 'object_detection',
            latency_requirement_ms: 200,
          },
          image_base64: imageBase64,
          confidence,
          annotated,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body);
        throw new Error(`HTTP ${response.status}: ${detail}`);
      }
      setResult(body as OrchestrationResponse);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The orchestration request failed.');
    } finally {
      setLoading(false);
    }
  };

  const detectionCount = result?.inference_result?.count ?? result?.inference_result?.detections?.length ?? 0;
  const detections = result?.inference_result?.detections ?? [];

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-line bg-panel p-5 shadow-card sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-brand">
              <Activity className="h-3.5 w-3.5" /> Live end-to-end experiment
            </div>
            <h2 className="text-2xl font-semibold tracking-tight text-ink">Inference demonstration</h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">
              Upload an image and send a real workload to the deployed AWS orchestrator. The scheduler evaluates live node metrics, selects a destination, and the chosen node runs object detection.
            </p>
          </div>
          <StatusBadge label="LIVE AWS API" tone="ok" pulse />
        </div>
        <div className="mt-5 grid gap-2 sm:grid-cols-3">
          <Step icon={UploadCloud} title="1 · Upload" detail="Select a test image" />
          <Step icon={Brain} title="2 · Schedule" detail="Live resource-aware decision" />
          <Step icon={Cpu} title="3 · Infer" detail="Edge or Cloud execution" />
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Panel title="Workload configuration" subtitle={`POST ${env.orchestratorUrl}/orchestrate`}>
          <form onSubmit={runInference} className="space-y-4">
            <label className="block cursor-pointer rounded-xl border border-dashed border-line-strong bg-raised/40 p-4 transition hover:border-brand/60">
              <div className="flex items-center gap-3">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-brand/30 bg-brand/10 text-brand"><ImagePlus className="h-5 w-5" /></span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-ink">{file ? file.name : 'Choose an image'}</div>
                  <div className="mt-0.5 text-[11px] text-ink-dim">{file ? `${(file.size / 1024).toFixed(0)} KB · ${file.type}` : 'JPEG, PNG or WebP · maximum 5 MB'}</div>
                </div>
                <UploadCloud className="h-4 w-4 text-ink-dim" />
              </div>
              <input type="file" accept="image/jpeg,image/png,image/webp" onChange={onFileChange} className="sr-only" />
            </label>

            {preview && (
              <div className="overflow-hidden rounded-xl border border-line bg-raised/40">
                <img src={preview} alt="Selected inference input" className="max-h-64 w-full object-contain" />
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-ink-muted">Workload priority</span>
                <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)} className="w-full rounded-lg border border-line bg-raised px-3 py-2.5 text-sm text-ink outline-none focus:border-brand">
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-ink-muted">Detection confidence · {confidence.toFixed(2)}</span>
                <input type="range" min="0.05" max="0.95" step="0.05" value={confidence} onChange={(e) => setConfidence(Number(e.target.value))} className="mt-2 w-full accent-sky-400" />
              </label>
            </div>

            <label className="flex items-center gap-2 text-xs text-ink-muted">
              <input type="checkbox" checked={annotated} onChange={(e) => setAnnotated(e.target.checked)} className="accent-sky-400" />
              Return annotated image with detection boxes
            </label>

            {error && <div className="rounded-lg border border-bad/30 bg-bad/[0.06] px-3 py-2.5 text-xs leading-relaxed text-bad">{error}</div>}

            <button type="submit" disabled={!file || loading} className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-brand/40 bg-brand px-4 py-3 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
              {loading ? <><LoaderCircle className="h-4 w-4 animate-spin" /> Running on AWS…</> : <><Activity className="h-4 w-4" /> Run live orchestration</>}
            </button>
            <p className="text-[10px] leading-relaxed text-ink-dim">The request uses live scheduler metrics. No synthetic resource snapshots are supplied by this form.</p>
          </form>
        </Panel>

        <Panel title="Execution result" subtitle={result ? `Workload ${result.workload_id}` : 'Actual response from the deployed orchestrator'}>
          {loading ? (
            <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
              <LoaderCircle className="h-8 w-8 animate-spin text-brand" />
              <div className="text-sm font-medium text-ink">Orchestrating workload</div>
              <div className="text-xs text-ink-dim">Scheduler is checking live Edge and Cloud conditions.</div>
            </div>
          ) : result ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <MetricCard label="Selected target" value={<TargetBadge target={result.selected_target as 'edge' | 'cloud' | 'queue' | 'error'} />} tone="brand" sub="Scheduler decision" />
                <MetricCard label="Actual execution" value={result.actual_target ? <TargetBadge target={result.actual_target as 'edge' | 'cloud'} /> : 'Not executed'} tone={result.actual_target ? 'ok' : 'warn'} sub={result.fallback_used ? 'Failover used' : 'No fallback'} />
                <MetricCard label="Scheduler latency" icon={Brain} value={result.scheduler_latency_ms.toFixed(1)} unit="ms" tone="violet" />
                <MetricCard label="Inference latency" icon={Timer} value={result.inference_latency_ms === null ? '—' : result.inference_latency_ms.toFixed(1)} unit="ms" tone="ok" />
              </div>
              <div className="rounded-xl border border-line bg-raised/40 p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-ink">End-to-end latency</span>
                  <span className="text-lg font-semibold tabular-nums text-ink">{result.total_latency_ms.toFixed(1)} ms</span>
                </div>
                <div className="mt-2 flex items-center justify-between text-[10px] text-ink-dim">
                  <span>Priority: {result.priority.toUpperCase()}</span>
                  <span>Decision score: {result.decision_score.toFixed(1)}</span>
                </div>
              </div>
              <div className="rounded-lg border border-line px-3 py-2.5">
                <div className="mb-1 flex items-center gap-2 text-xs font-medium text-ink"><CheckCircle2 className="h-3.5 w-3.5 text-ok" /> Scheduler explanation</div>
                <p className="text-xs leading-relaxed text-ink-muted">{result.decision_reason}</p>
                {result.fallback_reason && <p className="mt-2 text-xs leading-relaxed text-warn">{result.fallback_reason}</p>}
              </div>
              <div className="flex items-center justify-between rounded-lg border border-line px-3 py-2.5">
                <span className="text-xs text-ink-muted">Objects detected</span>
                <span className="text-lg font-semibold tabular-nums text-ink">{detectionCount}</span>
              </div>
              {detections.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {detections.slice(0, 12).map((item, index) => <span key={`${item.class_id}-${index}`} className="rounded-md border border-line bg-raised px-2 py-1 text-[11px] text-ink-muted">{item.class_name} · {(item.confidence * 100).toFixed(0)}%</span>)}
                </div>
              )}
              {result.inference_result?.annotated_image_base64 && (
                <div className="overflow-hidden rounded-xl border border-line bg-raised/40">
                  <div className="border-b border-line px-3 py-2 text-[10px] uppercase tracking-wider text-ink-dim">Actual annotated inference output</div>
                  <img src={`data:image/jpeg;base64,${result.inference_result.annotated_image_base64}`} alt="Annotated inference result" className="max-h-72 w-full object-contain" />
                </div>
              )}
              <div className="text-right text-[10px] text-ink-dim">Completed {new Date(result.timestamp).toLocaleString()}</div>
            </div>
          ) : (
            <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
              <span className="inline-flex h-12 w-12 items-center justify-center rounded-xl border border-line bg-raised text-ink-dim"><ArrowRight className="h-5 w-5" /></span>
              <div className="text-sm font-medium text-ink">Ready for a live workload</div>
              <div className="max-w-sm text-xs leading-relaxed text-ink-dim">Choose an image, set its priority, and run it through the real scheduler and inference services.</div>
            </div>
          )}
        </Panel>
      </div>

      <InlineNote tone="info">
        This page submits a real inference workload to the existing production orchestrator. A queued decision or upstream error is shown as returned by the backend. It does not create a fake success record or modify cluster configuration.
      </InlineNote>
    </div>
  );
}

function Step({ icon: Icon, title, detail }: { icon: typeof Cpu; title: string; detail: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-line bg-raised/50 px-3 py-2.5">
      <Icon className="h-4 w-4 shrink-0 text-brand" />
      <div><div className="text-xs font-medium text-ink">{title}</div><div className="text-[10px] text-ink-dim">{detail}</div></div>
    </div>
  );
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Could not read image data.'));
    reader.onerror = () => reject(new Error('Could not read the selected image.'));
    reader.readAsDataURL(file);
  });
}
