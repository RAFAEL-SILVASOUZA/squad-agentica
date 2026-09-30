"use client";

import * as React from "react";
import Link from "next/link";
import { Play, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Stats strip do dashboard (protótipo view-dashboard, 4 stat cards).
 * - Execuções em andamento → /pipelines?run=running
 * - Concluídas (24h) → /pipelines?since=24h
 * - Completadas → /pipelines?run=completed
 * - Aprovações pendentes → /approvals
 *
 * Sem emojis; ícones via lucide-react. Todos os cards são links reais.
 */

export interface DashboardStats {
  runningPipelines: number;
  recentRuns: number;
  completedRuns: number;
  pendingApprovals: number;
}

export interface StatsStripProps {
  stats: DashboardStats;
  loading?: boolean;
}

interface StatCardProps {
  icon: React.ReactNode;
  value: number;
  label: string;
  href: string;
  loading?: boolean;
}

function StatCard({ icon, value, label, href, loading }: StatCardProps) {
  return (
    <Link
      href={href}
      aria-label={`${label}: ${value}`}
      style={{ display: "block", textDecoration: "none", color: "inherit" }}
    >
      <Card variant="stat" hoverable style={{ height: "100%" }}>
        <span
          aria-hidden="true"
          style={{
            width: 30,
            height: 30,
            borderRadius: "var(--radius-sm)",
            background: "var(--bg-hover)",
            color: "var(--text-secondary)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {icon}
        </span>
        <div style={{ minWidth: 0 }}>
          {loading ? (
            <Skeleton width={36} height={18} label="stat" />
          ) : (
            <div
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: "var(--text)",
                lineHeight: 1.2,
              }}
            >
              {value}
            </div>
          )}
          <div
            style={{
              fontSize: "11px",
              color: "var(--text-secondary)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {label}
          </div>
        </div>
      </Card>
    </Link>
  );
}

function StatChip({ icon, value, label, href, loading }: StatCardProps) {
  return (
    <Link
      href={href}
      aria-label={`${label}: ${value}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "6px 12px",
        borderRadius: "999px",
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        textDecoration: "none",
        color: "inherit",
        whiteSpace: "nowrap",
        flexShrink: 0,
      }}
    >
      <span style={{ color: "var(--text-secondary)", display: "flex", alignItems: "center" }}>
        {icon}
      </span>
      {loading ? (
        <Skeleton width={20} height={14} label="stat" />
      ) : (
        <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--text)" }}>{value}</span>
      )}
      <span style={{ fontSize: "11px", color: "var(--text-secondary)" }}>{label}</span>
    </Link>
  );
}

export function StatsStrip({ stats, loading = false }: StatsStripProps) {
  const [isMobile, setIsMobile] = React.useState(false);

  React.useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  if (isMobile) {
    return (
      <div
        style={{
          display: "flex",
          gap: "8px",
          overflowX: "auto",
          paddingBottom: "4px",
          WebkitOverflowScrolling: "touch",
        }}
      >
        <StatChip
          icon={<Play size={13} aria-hidden="true" />}
          value={stats.runningPipelines}
          label="Em andamento"
          href="/pipelines?run=running"
          loading={loading}
        />
        <StatChip
          icon={<Clock size={13} aria-hidden="true" />}
          value={stats.recentRuns}
          label="24h"
          href="/pipelines?since=24h"
          loading={loading}
        />
        <StatChip
          icon={<CheckCircle2 size={13} aria-hidden="true" />}
          value={stats.completedRuns}
          label="Completadas"
          href="/pipelines?run=completed"
          loading={loading}
        />
        <StatChip
          icon={<AlertCircle size={13} aria-hidden="true" />}
          value={stats.pendingApprovals}
          label="Pendentes"
          href="/approvals"
          loading={loading}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: "12px",
      }}
    >
      <StatCard
        icon={<Play size={15} aria-hidden="true" />}
        value={stats.runningPipelines}
        label="Execuções em andamento"
        href="/pipelines?run=running"
        loading={loading}
      />
      <StatCard
        icon={<Clock size={15} aria-hidden="true" />}
        value={stats.recentRuns}
        label="Concluídas (24h)"
        href="/pipelines?since=24h"
        loading={loading}
      />
      <StatCard
        icon={<CheckCircle2 size={15} aria-hidden="true" />}
        value={stats.completedRuns}
        label="Completadas"
        href="/pipelines?run=completed"
        loading={loading}
      />
      <StatCard
        icon={<AlertCircle size={15} aria-hidden="true" />}
        value={stats.pendingApprovals}
        label="Aprovações pendentes"
        href="/approvals"
        loading={loading}
      />
    </div>
  );
}
