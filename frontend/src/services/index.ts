import type { DataSource, DataSourceMode } from '../types';
import { HybridDataSource } from './hybridDataSource';
import { DemoDataSource } from './mock/mockDataSource';

/**
 * Live mode uses the hybrid source: real endpoints where they exist,
 * clearly-labelled sample data for views the backend cannot serve yet.
 * Pure LiveDataSource stays available for reference/tests.
 */
export function createDataSource(mode: DataSourceMode): DataSource {
  return mode === 'live' ? new HybridDataSource() : new DemoDataSource();
}

export { HybridDataSource, DemoDataSource };
