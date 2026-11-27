/**
 * Demo data source - thin adapter over `mockStore`.
 * Every value it returns is invented and must stay behind the DEMO DATA badge.
 */
import type {
  DataSource,
  DataSourceMode,
  Decision,
  InferenceFeed,
  LogFeed,
  NodeDetail,
  NodeRole,
  OverviewSnapshot,
  RoutingSnapshot,
  WorkloadInventory,
} from '../../types';
import { mockStore } from './mockStore';

export class DemoDataSource implements DataSource {
  readonly mode: DataSourceMode = 'demo';
  readonly label = 'DEMO DATA';
  readonly hint = 'Mock service (src/services/mock) - simulated values, not production metrics.';

  getOverview(): Promise<OverviewSnapshot> {
    return Promise.resolve(mockStore.getOverview());
  }

  getRouting(): Promise<RoutingSnapshot | null> {
    return Promise.resolve(mockStore.getRouting());
  }

  getNode(role: NodeRole): Promise<NodeDetail> {
    return Promise.resolve(mockStore.getNode(role));
  }

  getWorkloads(): Promise<WorkloadInventory | null> {
    return Promise.resolve(mockStore.getWorkloads());
  }

  getInference(): Promise<InferenceFeed | null> {
    return Promise.resolve(mockStore.getInference());
  }

  getLogs(): Promise<LogFeed | null> {
    return Promise.resolve(mockStore.getLogs());
  }

  probeDecision(): Promise<Decision> {
    return Promise.resolve(mockStore.probeDecision());
  }
}
