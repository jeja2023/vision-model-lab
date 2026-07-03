import {
  Activity,
  Boxes,
  Database,
  FileCheck2,
  FlaskConical,
  LayoutDashboard,
  PlaySquare,
  RefreshCw
} from "lucide-react";
import type { ReactNode } from "react";

export type ViewKey = "overview" | "packages" | "pipeline" | "experiments" | "data";

const navItems: Array<{ key: ViewKey; label: string; icon: ReactNode }> = [
  { key: "overview", label: "概览", icon: <LayoutDashboard size={18} /> },
  { key: "packages", label: "模型包", icon: <Boxes size={18} /> },
  { key: "pipeline", label: "流水线", icon: <PlaySquare size={18} /> },
  { key: "experiments", label: "实验", icon: <FlaskConical size={18} /> },
  { key: "data", label: "数据标注", icon: <Database size={18} /> }
];

type ShellProps = {
  activeView: ViewKey;
  onViewChange: (view: ViewKey) => void;
  onRefresh: () => void;
  apiStatus: string;
  children: ReactNode;
};

export function Shell({ activeView, onViewChange, onRefresh, apiStatus, children }: ShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <FileCheck2 size={22} />
          <div>
            <strong>视觉模型研发平台</strong>
            <span>模型交付控制台</span>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => (
            <button
              key={item.key}
              className={activeView === item.key ? "nav-item active" : "nav-item"}
              onClick={() => onViewChange(item.key)}
              title={item.label}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="status-line">
            <Activity size={18} />
            <span>{apiStatus}</span>
          </div>
          <button className="icon-button" onClick={onRefresh} title="刷新">
            <RefreshCw size={18} />
          </button>
        </header>
        <section className="content">{children}</section>
      </main>
    </div>
  );
}
