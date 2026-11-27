import type { LucideIcon } from 'lucide-react';
import { Boxes, Cloud, Cpu, LayoutDashboard, ScrollText, ScanSearch, Waypoints } from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  title: string;
  subtitle: string;
}

export const NAV_SECTIONS: { section: string; items: NavItem[] }[] = [
  {
    section: 'Monitor',
    items: [
      {
        to: '/',
        label: 'Overview',
        icon: LayoutDashboard,
        end: true,
        title: 'Overview',
        subtitle: 'Live AWS fleet health and resource utilization',
      },
      {
        to: '/orchestration',
        label: 'Live Orchestration',
        icon: Waypoints,
        title: 'Live Orchestration',
        subtitle: 'Request routing, scheduler decisions and edge -> cloud paths',
      },
      {
        to: '/inference',
        label: 'Live Inference Lab',
        icon: ScanSearch,
        title: 'Live Inference Lab',
        subtitle: 'Upload an image and run real Edge-Cloud inference',
      },
    ],
  },
  {
    section: 'Infrastructure',
    items: [
      {
        to: '/edge',
        label: 'Edge Node',
        icon: Cpu,
        title: 'Edge Node',
        subtitle: 'Utilisation, connectivity and edge-side inference latency',
      },
      {
        to: '/cloud',
        label: 'Cloud Node',
        icon: Cloud,
        title: 'Cloud Node',
        subtitle: 'Utilisation, connectivity and cloud-side inference latency',
      },
      {
        to: '/workloads',
        label: 'Workloads',
        icon: Boxes,
        title: 'Kubernetes Workloads',
        subtitle: 'Pods, services, replicas and restart counts',
      },
    ],
  },
  {
    section: 'System',
    items: [
      {
        to: '/logs',
        label: 'Logs & Monitoring',
        icon: ScrollText,
        title: 'Logs & Monitoring',
        subtitle: 'System events, scheduler activity, errors and warnings',
      },
    ],
  },
];

export const ROUTE_META: Record<string, { title: string; subtitle: string }> = Object.fromEntries(
  NAV_SECTIONS.flatMap((section) => section.items.map((item) => [item.to, { title: item.title, subtitle: item.subtitle }])),
);
