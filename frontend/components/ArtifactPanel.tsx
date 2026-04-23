"use client";

import { useState } from "react";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";
import type { ArtifactData } from "@/types";

interface ArtifactPanelProps {
  artifactData: ArtifactData;
}

const COLORS = ["#10b981", "#f87171", "#34d399", "#60a5fa", "#fbbf24", "#f472b6", "#2dd4bf", "#fb923c"];

type TabKey = "languages" | "files" | "security" | "structure";

interface TabDef {
  key: TabKey;
  label: string;
  icon: string;
  hasData: (d: ArtifactData) => boolean;
}

const TABS: TabDef[] = [
  { key: "languages", label: "Languages", icon: "📊", hasData: (d) => Object.keys(d.language_chart).length > 0 },
  { key: "files", label: "Largest Files", icon: "📁", hasData: (d) => d.file_size_graph.length > 0 },
  { key: "structure", label: "Structure", icon: "🏗️", hasData: (d) => (d.project_structure?.total_files ?? 0) > 0 },
  { key: "security", label: "Security", icon: "🔒", hasData: () => true },
];

export default function ArtifactPanel({ artifactData }: ArtifactPanelProps) {
  const availableTabs = TABS.filter((t) => t.hasData(artifactData));
  const [activeTab, setActiveTab] = useState<TabKey>(availableTabs[0]?.key ?? "languages");

  if (availableTabs.length === 0) return null;

  return (
    <div className="w-full rounded-2xl border border-[#1e1e3a] bg-[#13131f] overflow-hidden backdrop-blur-sm">
      {/* Tab bar */}
      <div className="flex border-b border-[#1e1e3a] overflow-x-auto">
        {availableTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors ${
              activeTab === tab.key
                ? "text-emerald-300 border-b-2 border-emerald-400 bg-emerald-950/20"
                : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50"
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-5">
        {activeTab === "languages" && <LanguageChart data={artifactData.language_chart} />}
        {activeTab === "files" && <FileSizeChart data={artifactData.file_size_graph} />}
        {activeTab === "security" && <SecurityReport data={artifactData.security_report} />}
        {activeTab === "structure" && <ProjectStructureView data={artifactData.project_structure} />}
      </div>
    </div>
  );
}

function LanguageChart({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort(([, a], [, b]) => b - a).slice(0, 8);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  if (total === 0) return <Empty msg="No language data" />;

  const pieData = entries.map(([name, value]) => ({ name, value, pct: ((value / total) * 100).toFixed(1) }));

  return (
    <div className="flex flex-col md:flex-row items-center gap-6">
      <div className="w-48 h-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pieData} dataKey="value" cx="50%" cy="50%" outerRadius={80} strokeWidth={0}>
              {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: "8px", fontSize: "12px" }}
              itemStyle={{ color: "#e4e4e7" }}
              formatter={(value) => [`${((Number(value) / total) * 100).toFixed(1)}%`, "Lines"]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-col gap-2 flex-1">
        {pieData.map((item, i) => (
          <div key={item.name} className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
            <span className="text-zinc-200 text-sm font-medium flex-1">{item.name}</span>
            <span className="text-zinc-400 text-sm">{item.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FileSizeChart({ data }: { data: Array<{ file: string; size: number }> }) {
  if (data.length === 0) return <Empty msg="No file data" />;
  const sorted = [...data].sort((a, b) => b.size - a.size).slice(0, 8);
  const chartData = sorted.map((d) => ({
    name: d.file.split("/").pop() || d.file,
    size: Math.round(d.size / 1024 * 10) / 10,
    fullPath: d.file,
  }));

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 30 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis type="number" tick={{ fill: "#a1a1aa", fontSize: 11 }} unit=" KB" />
          <YAxis type="category" dataKey="name" tick={{ fill: "#e4e4e7", fontSize: 11 }} width={120} />
          <Tooltip
            contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: "8px", fontSize: "12px" }}
            itemStyle={{ color: "#e4e4e7" }}
            formatter={(value) => [`${Number(value)} KB`, "Size"]}
          />
          <Bar dataKey="size" radius={[0, 4, 4, 0]}>
            {chartData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SecurityReport({ data }: { data: string[] }) {
  if (data.length === 0) {
    return (
      <div className="flex items-center gap-3 p-4 bg-emerald-950/30 border border-emerald-800/40 rounded-xl">
        <span className="text-2xl">✅</span>
        <div>
          <p className="text-emerald-300 text-sm font-semibold">No security issues detected</p>
          <p className="text-emerald-400/60 text-xs mt-0.5">No hardcoded secrets or exposed credentials found</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-red-300 text-xs font-medium mb-1">⚠️ {data.length} potential issue{data.length > 1 ? "s" : ""} found</p>
      {data.slice(0, 8).map((issue, i) => (
        <div key={i} className="flex items-start gap-2 p-3 bg-red-950/20 border border-red-800/30 rounded-lg">
          <span className="text-red-400 text-xs mt-0.5 flex-shrink-0">●</span>
          <span className="text-zinc-300 text-xs font-mono break-all">{issue}</span>
        </div>
      ))}
    </div>
  );
}

function ProjectStructureView({ data }: { data: { total_files: number; file_types: Record<string, number> } }) {
  if (!data || data.total_files === 0) return <Empty msg="No structure data" />;

  const types = Object.entries(data.file_types).sort(([, a], [, b]) => b - a);
  const chartData = types.map(([ext, count]) => ({ name: ext, count }));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-xl">
        <span className="text-3xl">📂</span>
        <div>
          <p className="text-zinc-200 text-lg font-bold">{data.total_files}</p>
          <p className="text-zinc-400 text-xs">Total files analyzed</p>
        </div>
      </div>
      <div className="w-full h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ left: 0, right: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis dataKey="name" tick={{ fill: "#a1a1aa", fontSize: 10 }} />
            <YAxis tick={{ fill: "#a1a1aa", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: "8px", fontSize: "12px" }}
              itemStyle={{ color: "#e4e4e7" }}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {chartData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Empty({ msg }: { msg: string }) {
  return <div className="flex items-center justify-center p-8 text-zinc-500 text-sm">{msg}</div>;
}
