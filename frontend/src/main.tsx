import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  FileWarning,
  FlaskConical,
  Moon,
  ExternalLink,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  Send,
  Sun,
  XCircle,
} from "lucide-react";
import "./styles.css";
import "./workspace-overrides.css";

type Module = {
  id: string;
  title?: string;
  status?: string;
  category?: string;
};
type Report = {
  id: number;
  project_id: string;
  run_at: string;
  status: string;
  engine_version?: string;
  pipeline_version?: string;
  output_formats: string[];
  modules: Module[];
  output_available: boolean;
  artifact_availability?: string;
  manifest_status?: string;
  warnings: string[];
};
type Page = { items: Report[]; next_cursor: string | null };
type Evidence = {
  module_id: string;
  comparison?: string;
  evidence_hash?: string;
  availability?: string;
  integrity?: string;
  statistics: Record<string, unknown>;
  tables: Array<{ columns: string[]; rows: Array<Record<string, unknown>> }>;
  figures?: Array<{
    figure_id: string;
    content_type?: string;
    size?: number;
    sha256?: string;
  }>;
  warnings: string[];
};
type Artifact = {
  artifact_id: string;
  role: string;
  size_bytes?: number | null;
  sha256?: string | null;
  available: boolean;
  integrity: string;
  content_type?: string | null;
};
type Interpretation = {
  id: string;
  module_id: string;
  evidence_hash: string;
  status: string;
  provider: string;
  model: string;
  created_at: string;
  version?: number;
  output?: { summary?: string; observations?: Array<{ text: string }> };
  validation?: { valid: boolean };
};
type Provenance = {
  run_id: number;
  project_id?: string;
  availability?: string;
  manifests: Record<
    string,
    {
      availability: string;
      artifacts?: Array<{
        artifact?: string;
        role?: string;
        sha256?: string;
        size?: number;
      }>;
      [key: string]: unknown;
    }
  >;
};
type ChatMessage = { role: "user" | "assistant"; content: string };

type Language = "en" | "zh";
const translations: Record<string, string> = {
  HISTORY: "历史记录", Reports: "报告", "Filter project or module": "筛选项目或模块", "Loading history": "正在加载历史记录", Retry: "重试", "No reports match this filter.": "没有符合筛选条件的报告。", " modules": " 个模块", "Artifacts available": "结果文件可用", "Output missing": "缺少输出文件", "Load more history": "加载更多记录", "Refresh reports": "刷新报告", "Toggle theme": "切换主题", "Toggle language": "切换语言", Provenance: "溯源信息", Modules: "分析模块", "Show modules": "显示模块", "Hide modules": "隐藏模块", "Resize module panel": "调整模块面板宽度", Evidence: "分析证据", "Read-only": "只读", Comparison: "比较组", Load: "加载", "Loading evidence": "正在加载证据", "Evidence unavailable": "证据不可用", "Choose a module to inspect evidence": "选择模块查看证据", "Unavailable artifacts stay visible and are never inferred.": "不可用的结果文件仍会显示，不会推测缺失数据。", "No module metadata": "暂无模块信息", "Interpretation Agent": "结果解读助手", "Deterministic mock": "确定性模拟", "Show agent": "显示助手", "Hide agent": "隐藏助手", "Cancel operation": "取消任务", "Generating...": "生成中...", "Generate interpretation": "生成解读", Operation: "任务", "Validated interpretation stored.": "已保存经过校验的解读。", "Evidence-backed interpretation": "基于证据的解读", "Generate a deterministic interpretation after evidence is available.": "证据就绪后生成确定性解读。", "Ask about this module evidence.": "询问有关此模块证据的问题。", "Ask a scoped question": "输入相关问题", "Send question": "发送问题", You: "你", Agent: "助手", "Registered figures": "已登记图表", "Report artifacts": "报告文件", "No manifest-backed artifacts available.": "没有可用的清单记录文件。", "Open artifact": "打开文件", "Select a report to inspect its modules and evidence.": "选择报告以查看分析模块和证据。", "Evidence hash": "证据哈希", "format unknown": "格式未知", partial: "部分可用", available: "可用", " artifacts": " 个文件", "No verified evidence is available for this module.": "此模块没有经过验证的证据。", unavailable: "不可用",
};
async function getReports(
  signal: AbortSignal,
  cursor?: string | null,
): Promise<Page> {
  const query = new URLSearchParams({ limit: "50" });
  if (cursor) query.set("cursor", cursor);
  const response = await fetch(`/api/v1/reports?${query.toString()}`, {
    signal,
  });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<Page>;
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const body = (await response.json().catch(() => ({}))) as {
    detail?: { message?: string };
  };
  if (!response.ok)
    throw new Error(
      body.detail?.message ?? `API request failed (${response.status})`,
    );
  return body as T;
}

async function readOperation(
  operationId: string,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `/api/v1/operations/${encodeURIComponent(operationId)}/events`,
    { signal },
  );
  if (!response.ok || !response.body)
    throw new Error(`SSE request failed (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = frame.match(/^event: ([^\n]+)$/m)?.[1];
      if (event) {
        const rawData = frame.match(/^data: (.*)$/m)?.[1] ?? "{}";
        let data: Record<string, unknown> = {};
        try {
          const parsed = JSON.parse(rawData);
          if (parsed && typeof parsed === "object") data = parsed;
        } catch {
          data = {};
        }
        onEvent(event, data);
      }
    }
  }
}

function App() {
  const [reports, setReports] = useState<Report[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<Report | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem("bioreport.theme");
    return saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  });
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem("bioreport.language") === "zh" ? "zh" : "en");
  const t = (text: string) => language === "zh" ? (translations[text] ?? text) : text;
  const [selectedModule, setSelectedModule] = useState<Module | null>(null);
  const [comparison, setComparison] = useState("2_vs_1");
  const [comparisonInput, setComparisonInput] = useState("2_vs_1");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [interpretations, setInterpretations] = useState<Interpretation[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [operationId, setOperationId] = useState<string | null>(null);
  const [operationStatus, setOperationStatus] = useState<string | null>(null);
  const [operationText, setOperationText] = useState("");
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [showProvenance, setShowProvenance] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const operationAbort = useRef<AbortController | null>(null);
  const cancelRequested = useRef(false);
  const [moduleWidth, setModuleWidth] = useState(220);
  const [agentWidth, setAgentWidth] = useState(300);
  const [modulesCollapsed, setModulesCollapsed] = useState(false);
  const [agentCollapsed, setAgentCollapsed] = useState(false);
  const dragPane = useRef<"modules" | "agent" | null>(null);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (dragPane.current === "modules") {
        setModuleWidth(Math.max(160, Math.min(360, event.clientX - 250)));
      } else if (dragPane.current === "agent") {
        setAgentWidth(Math.max(240, Math.min(420, window.innerWidth - event.clientX - 34)));
      }
    };
    const stop = () => {
      dragPane.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
  }, []);

  const startPaneDrag = (pane: "modules" | "agent") => (event: React.PointerEvent) => {
    dragPane.current = pane;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const load = () => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getReports(controller.signal)
      .then((page) => {
        setReports(page.items);
        setNextCursor(page.next_cursor);
        setSelected((current) =>
          current
            ? (page.items.find((item) => item.id === current.id) ?? null)
            : (page.items[0] ?? null),
        );
      })
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError"))
          setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  };
  const loadMore = async () => {
    if (!nextCursor || loading) return;
    setLoading(true);
    try {
      const page = await getReports(new AbortController().signal, nextCursor);
      setReports((current) => [...current, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  };
  useEffect(load, []);

  useEffect(() => {
    localStorage.setItem("bioreport.theme", dark ? "dark" : "light");
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  }, [dark]);
  useEffect(() => localStorage.setItem("bioreport.language", language), [language]);

  useEffect(() => {
    setSelectedModule((current) =>
      current && selected?.modules.some((module) => module.id === current.id)
        ? current
        : (selected?.modules[0] ?? null),
    );
    setEvidence(null);
    setEvidenceError(null);
    setInterpretations([]);
    setProvenance(null);
    setArtifacts([]);
    setShowProvenance(false);
    setConversationId(null);
    setChatInput("");
    setChatMessages([]);
    setOperationId(null);
    setOperationStatus(null);
    setOperationText("");
    if (selected)
      getJson<Provenance>(`/api/v1/reports/${selected.id}/provenance`)
        .then(setProvenance)
        .catch(() => setProvenance(null));
    if (selected)
      getJson<{ artifacts: Artifact[] }>(
        `/api/v1/reports/${selected.id}/artifacts`,
      )
        .then((result) => setArtifacts(result.artifacts))
        .catch(() => setArtifacts([]));
  }, [selected?.id]);

  useEffect(() => {
    if (!selected || !selectedModule) return;
    const controller = new AbortController();
    setEvidenceLoading(true);
    setEvidenceError(null);
    const query =
      selectedModule.id === "rna.results.deg"
        ? `?comparison=${encodeURIComponent(comparison)}`
        : "";
    getJson<Evidence>(
      `/api/v1/reports/${selected.id}/modules/${encodeURIComponent(selectedModule.id)}/evidence${query}`,
      { signal: controller.signal },
    )
      .then(setEvidence)
      .catch((reason) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError"))
          setEvidenceError(
            reason instanceof Error ? reason.message : String(reason),
          );
      })
      .finally(() => setEvidenceLoading(false));
    getJson<{ items: Interpretation[] }>(
      `/api/v1/reports/${selected.id}/interpretations?module_id=${encodeURIComponent(selectedModule.id)}`,
      { signal: controller.signal },
    )
      .then((result) => setInterpretations(result.items))
      .catch(() => setInterpretations([]));
    return () => controller.abort();
  }, [selected?.id, selectedModule?.id, comparison]);

  const visible = useMemo(
    () =>
      reports.filter((item) =>
        `${item.project_id} ${item.status} ${item.modules.map((module) => module.id).join(" ")}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [reports, query],
  );

  const generateInterpretation = async () => {
    if (!selected || !selectedModule || !evidence || agentLoading) return;
    setAgentLoading(true);
    setEvidenceError(null);
    setOperationStatus("starting");
    setOperationText("");
    cancelRequested.current = false;
    try {
      const result = await getJson<{ operation_id: string }>(
        `/api/v1/reports/${selected.id}/interpretations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ module_id: selectedModule.id, comparison }),
        },
      );
      setOperationId(result.operation_id);
      const streamController = new AbortController();
      operationAbort.current = streamController;
      const timeout = window.setTimeout(() => streamController.abort(), 30_000);
      try {
        await readOperation(
          result.operation_id,
          (event, data) => {
            setOperationStatus(event);
            if (event === "token" && typeof data.text === "string") {
              setOperationText((current) => current + data.text);
            }
          },
          streamController.signal,
        );
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === "AbortError") {
          if (cancelRequested.current) {
            setOperationStatus("cancelled");
            return;
          }
          setOperationStatus("timeout");
          throw new Error("Interpretation stream timed out after 30 seconds");
        }
        throw reason;
      } finally {
        window.clearTimeout(timeout);
        operationAbort.current = null;
      }
      const latest = await getJson<{ items: Interpretation[] }>(
        `/api/v1/reports/${selected.id}/interpretations?module_id=${encodeURIComponent(selectedModule.id)}`,
      );
      setInterpretations(latest.items);
    } catch (reason) {
      setEvidenceError(
        reason instanceof Error ? reason.message : String(reason),
      );
      setOperationStatus("error");
    } finally {
      setAgentLoading(false);
    }
  };

  const cancelOperation = async () => {
    if (!operationId) return;
    cancelRequested.current = true;
    try {
      const result = await getJson<{ status: string }>(
        `/api/v1/operations/${encodeURIComponent(operationId)}/cancel`,
        { method: "POST" },
      );
      operationAbort.current?.abort();
      setOperationStatus(result.status);
    } catch (reason) {
      setEvidenceError(
        reason instanceof Error ? reason.message : String(reason),
      );
    }
  };

  const sendChat = async () => {
    const content = chatInput.trim();
    if (!content || !selected || !selectedModule || chatLoading) return;
    setChatLoading(true);
    setChatInput("");
    try {
      let sessionId = conversationId;
      if (!sessionId) {
        const created = await getJson<{ session_id: string }>(
          "/api/v1/conversations",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              run_id: selected.id,
              module_id: selectedModule.id,
              evidence_hash: evidence?.evidence_hash ?? null,
            }),
          },
        );
        sessionId = created.session_id;
        setConversationId(sessionId);
      }
      const result = await getJson<{ assistant?: { content: string } }>(
        `/api/v1/conversations/${sessionId}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role: "user", content }),
        },
      );
      setChatMessages((messages) => [
        ...messages,
        { role: "user", content },
        ...(result.assistant
          ? [{ role: "assistant" as const, content: result.assistant.content }]
          : []),
      ]);
    } catch (reason) {
      setEvidenceError(
        reason instanceof Error ? reason.message : String(reason),
      );
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className={dark ? "app dark" : "app"}>
      <header className="topbar">
        <div className="brand">
          <FlaskConical size={20} />
          <span>BioReport Workspace</span>
        </div>
        <div className="top-actions">
          <button
            className="icon-button"
            title={t("Refresh reports")}
            onClick={load}
          >
            <RefreshCw size={17} />
          </button>
          <button
            className="icon-button"
            title={t("Toggle theme")}
            onClick={() => setDark((value) => !value)}
          >
            {dark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button className="small-button" title={t("Toggle language")} onClick={() => setLanguage((value) => value === "en" ? "zh" : "en")}>{language === "en" ? "中文" : "EN"}</button>
        </div>
      </header>
      <main className="workspace">
        <aside className="library panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">{t("HISTORY")}</span>
              <h1>{t("Reports")}</h1>
            </div>
            <span className="count">{reports.length}</span>
          </div>
          <label className="search">
            <Search size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("Filter project or module")}
            />
          </label>
          {loading && (
            <div className="state">
              <RefreshCw className="spin" size={18} />
              {t("Loading history")}
            </div>
          )}
          {error && (
            <div className="state error">
              <AlertCircle size={18} />
              <span>
                {error}
                <button className="text-button" onClick={load}>
                  {t("Retry")}
                </button>
              </span>
            </div>
          )}
          {!loading && !error && visible.length === 0 && (
            <div className="state">
              <FileWarning size={18} />
              {t("No reports match this filter.")}
            </div>
          )}
          <div className="report-list">
            {visible.map((report) => (
              <button
                className={
                  selected?.id === report.id
                    ? "report-row selected"
                    : "report-row"
                }
                key={report.id}
                onClick={() => setSelected(report)}
              >
                <div className="row-top">
                  <strong>{report.project_id}</strong>
                  <ChevronRight size={15} />
                </div>
                <div className="row-meta">
                  <span>{new Date(report.run_at).toLocaleString()}</span>
                  <Status status={report.status} />
                </div>
                <div className="row-meta">
                  <span>{report.modules.length}{t(" modules")}</span>
                  <span>
                    {report.artifact_availability === "AVAILABLE"
                      ? t("Artifacts available")
                      : report.output_available
                        ? `Artifacts ${report.artifact_availability?.toLowerCase() ?? "partial"}`
                        : t("Output missing")}
                  </span>
                </div>
              </button>
            ))}
          </div>
          {nextCursor && !loading && !error && (
            <button className="load-more" onClick={() => void loadMore()}>
              {t("Load more history")}
            </button>
          )}
        </aside>
        <section className="detail panel">
          {selected ? (
            <>
              <div className="detail-heading">
                <div>
                  <span className="eyebrow">RUN #{selected.id}</span>
                  <h2>{selected.project_id}</h2>
                  <p>
                    {new Date(selected.run_at).toLocaleString()} - Engine{" "}
                    {selected.engine_version ?? "unknown"} ·{" "}
                    {selected.output_formats.join(", ") || "format unknown"}
                  </p>
                </div>
                <div className="heading-actions">
                  <Status status={selected.status} />
                  <button
                    className="small-button"
                    onClick={() => setShowProvenance((value) => !value)}
                  >
                    Provenance
                  </button>
                </div>
              </div>
              <div
                className="three-pane"
                style={{
                  "--module-width": modulesCollapsed ? "0px" : `${moduleWidth}px`,
                  "--agent-width": agentCollapsed ? "0px" : `${agentWidth}px`,
                } as React.CSSProperties}
              >
                <section className={modulesCollapsed ? "module-pane collapsed" : "module-pane"}>
                  <div className="pane-heading">
                  <h3>{t("Modules")}</h3>
                    <button
                      className="icon-button"
                      title={t(modulesCollapsed ? "Show modules" : "Hide modules")}
                      aria-label={t(modulesCollapsed ? "Show modules" : "Hide modules")}
                      onClick={() => setModulesCollapsed((value) => !value)}
                    >
                      {modulesCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
                    </button>
                  </div>
                  {selected.modules.length === 0 ? (
                    <div className="empty-small">{t("No module metadata")}</div>
                  ) : (
                    selected.modules.map((module) => (
                      <button
                        className={
                          selectedModule?.id === module.id
                            ? "module-item active"
                            : "module-item"
                        }
                        key={module.id}
                        onClick={() => setSelectedModule(module)}
                      >
                        <span
                          className={
                            module.status === "unknown"
                              ? "module-dot unknown"
                              : "module-dot"
                          }
                        />
                        <div>
                          <strong>{module.title ?? module.id}</strong>
                          <span>{module.id}</span>
                        </div>
                      </button>
                    ))
                  )}
                </section>
                <div
                  className="pane-resizer"
                  role="separator"
                  aria-label="Resize module panel"
                  aria-orientation="vertical"
                  onPointerDown={startPaneDrag("modules")}
                />
                <section className="evidence-pane">
                  <div className="section-head">
                    <h3>{t("Evidence")}</h3>
                    <span className="pill">{t("Read-only")}</span>
                  </div>
                  {selectedModule?.id === "rna.results.deg" && (
                    <div className="comparison-control">
                      <label htmlFor="comparison">{t("Comparison")}</label>
                      <input
                        id="comparison"
                        value={comparisonInput}
                        onChange={(event) =>
                          setComparisonInput(event.target.value)
                        }
                      />
                      <button
                        className="small-button"
                        onClick={() =>
                          setComparison(comparisonInput.trim() || "2_vs_1")
                        }
                      >
                        {t("Load")}
                      </button>
                    </div>
                  )}
                  {evidenceLoading && (
                    <div className="state">
                      <RefreshCw className="spin" size={18} />
                      {t("Loading evidence")}
                    </div>
                  )}
                  {evidenceError && (
                    <div className="state error">
                      <AlertCircle size={18} />
                      {evidenceError}
                    </div>
                  )}
                  {!evidenceLoading && !evidenceError && evidence && (
                    <EvidenceCard evidence={evidence} t={t} />
                  )}
                  {!evidenceLoading && !evidenceError && !evidence && (
                    <div className="evidence-empty">
                      <FileWarning size={26} />
                      <strong>
                        {selectedModule
                          ? t("Evidence unavailable")
                          : t("Choose a module to inspect evidence")}
                      </strong>
                      <span>
                        {t("Unavailable artifacts stay visible and are never inferred.")}
                      </span>
                    </div>
                  )}
                </section>
                <div
                  className="pane-resizer"
                  role="separator"
                  aria-label={t("Resize agent panel")}
                  aria-orientation="vertical"
                  onPointerDown={startPaneDrag("agent")}
                />
                <section className={agentCollapsed ? "agent-pane collapsed" : "agent-pane"}>
                  <div className="section-head">
                    <h3>{t("Interpretation Agent")}</h3>
                    <div className="agent-heading-actions">
                      <span className="pill muted">{t("Deterministic mock")}</span>
                      <button
                        className="icon-button"
                        title={t(agentCollapsed ? "Show agent" : "Hide agent")}
                        aria-label={t(agentCollapsed ? "Show agent" : "Hide agent")}
                        onClick={() => setAgentCollapsed((value) => !value)}
                      >
                        {agentCollapsed ? <PanelRightOpen size={15} /> : <PanelRightClose size={15} />}
                      </button>
                    </div>
                  </div>
                  {evidence?.evidence_hash && (
                    <div className="agent-actions">
                      <button
                        className="primary-button"
                        disabled={agentLoading}
                        onClick={() => void generateInterpretation()}
                      >
                        {agentLoading
                          ? t("Generating...")
                          : t("Generate interpretation")}
                      </button>
                      {agentLoading && (
                        <button
                          className="icon-button"
                          title={t("Cancel operation")}
                          onClick={() => void cancelOperation()}
                        >
                          <XCircle size={16} />
                        </button>
                      )}
                    </div>
                  )}
                  {operationStatus && (
                    <div className="operation-status">
                      <span>{t("Operation")}</span>
                      <Status status={operationStatus} />
                    </div>
                  )}
                  {operationText && (
                    <p className="operation-output">{operationText}</p>
                  )}
                  {interpretations.length > 0 ? (
                    interpretations.map((item) => (
                      <article className="interpretation" key={item.id}>
                        <div className="row-meta">
                          <span>
                            {item.provider} - {item.model}
                            {item.version ? ` · v${item.version}` : ""}
                          </span>
                          <Status status={item.status} />
                        </div>
                        <p>
                          {item.output?.summary ??
                            item.output?.observations?.[0]?.text ??
                            t("Validated interpretation stored.")}
                        </p>
                        <small>
                          {new Date(item.created_at).toLocaleString()} -{" "}
                          {item.evidence_hash.slice(0, 12)}
                        </small>
                      </article>
                    ))
                  ) : (
                    <div className="agent-empty">
                      <CheckCircle2 size={26} />
                      <strong>{t("Evidence-backed interpretation")}</strong>
                      <span>
                        {t("Generate a deterministic interpretation after evidence is available.")}
                      </span>
                    </div>
                  )}
                  <div className="chat-box">
                    <div className="chat-messages">
                      {chatMessages.length === 0 ? (
                        <span className="chat-placeholder">
                          {t("Ask about this module evidence.")}
                        </span>
                      ) : (
                        chatMessages.map((message, index) => (
                          <div
                            className={`chat-message ${message.role}`}
                            key={`${message.role}-${index}`}
                          >
                            <span>
                              {t(message.role === "user" ? "You" : "Agent")}
                            </span>
                            <p>{message.content}</p>
                          </div>
                        ))
                      )}
                    </div>
                    <div className="chat-composer">
                      <input
                        value={chatInput}
                        onChange={(event) => setChatInput(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") void sendChat();
                        }}
                        placeholder={t("Ask a scoped question")}
                        aria-label={t("Ask a scoped question")}
                      />
                      <button
                        className="icon-button"
                        title={t("Send question")}
                        disabled={chatLoading || !chatInput.trim()}
                        onClick={() => void sendChat()}
                      >
                        <Send size={16} />
                      </button>
                    </div>
                  </div>
                </section>
              </div>
              <ArtifactPanel reportId={selected.id} artifacts={artifacts} t={t} />
              {showProvenance && provenance && (
                <ProvenancePanel provenance={provenance} t={t} />
              )}
              {selected.warnings.length > 0 && (
                <div className="warning">
                  <AlertCircle size={16} />
                  <span>{selected.warnings.join(" · ")}</span>
                </div>
              )}
            </>
          ) : (
            <div className="state detail-empty">
              <FlaskConical size={28} />
              {t("Select a report to inspect its modules and evidence.")}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function Status({ status }: { status: string }) {
  return <span className={`status ${status}`}>{status}</span>;
}
function EvidenceCard({ evidence, t }: { evidence: Evidence; t: (text: string) => string }) {
  if (evidence.availability && !evidence.evidence_hash) {
    return (
      <div className="evidence-empty">
        <FileWarning size={26} />
        <strong>{evidence.availability}</strong>
        <span>
          {evidence.warnings.join(" · ") ||
            t("No verified evidence is available for this module.")}
        </span>
      </div>
    );
  }
  const table = evidence.tables[0];
  return (
    <div className="evidence-card">
      <div className="stat-grid">
        {Object.entries(evidence.statistics).map(([key, value]) => (
          <div key={key}>
            <span>{key}</span>
            <strong>
              {typeof value === "object"
                ? JSON.stringify(value)
                : String(value)}
            </strong>
          </div>
        ))}
      </div>
      <p className="hash">
        {t("Evidence hash")}: <code>{evidence.evidence_hash ?? t("unavailable")}</code>
      </p>
      {table && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {table.columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.slice(0, 10).map((row, index) => (
                <tr key={index}>
                  {table.columns.map((column) => (
                    <td key={column}>{String(row[column] ?? "-")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {evidence.figures && evidence.figures.length > 0 && (
        <div className="figure-list">
          <div className="figure-list-heading">{t("Registered figures")}</div>
          {evidence.figures.map((figure) => (
            <div className="figure-item" key={`${figure.figure_id}-${figure.sha256 ?? "unknown"}`}>
              <div>
                <strong>{figure.figure_id}</strong>
                <span>{figure.content_type ?? "image"} · {figure.size ?? "?"} bytes</span>
              </div>
              <code>{figure.sha256?.slice(0, 12) ?? "unverified"}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
function ProvenancePanel({ provenance, t }: { provenance: Provenance; t: (text: string) => string }) {
  return (
    <section className="provenance-panel">
      <div className="section-head">
        <h3>{t("Provenance")}</h3>
        <span className="pill">{provenance.availability ?? "available"}</span>
      </div>
      <div className="manifest-grid">
        {Object.entries(provenance.manifests).map(([name, manifest]) => (
          <div className="manifest-item" key={name}>
            <strong>{name}</strong>
            <Status status={String(manifest.availability)} />
            <span>{manifest.artifacts?.length ?? 0}{t(" artifacts")}</span>
            {Boolean(manifest.quarto) && (
              <span>Quarto {String(manifest.quarto)}</span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
function ArtifactPanel({
  reportId,
  artifacts,
  t,
}: {
  reportId: number;
  artifacts: Artifact[];
  t: (text: string) => string;
}) {
  return (
    <section className="artifact-panel">
      <div className="section-head">
        <h3>{t("Report artifacts")}</h3>
        <span className="pill">{artifacts.length}</span>
      </div>
      {artifacts.length === 0 ? (
        <span className="muted-copy">
          {t("No manifest-backed artifacts available.")}
        </span>
      ) : (
        <div className="artifact-list">
          {artifacts.map((artifact) => (
            <div className="artifact-item" key={artifact.artifact_id}>
              <div>
                <strong>{artifact.artifact_id}</strong>
                <span>{artifact.role}</span>
              </div>
              <div className="artifact-actions">
                <Status status={artifact.integrity} />
                {artifact.available &&
                  (artifact.integrity === "verified" ||
                    artifact.integrity === "unverified") && (
                    <a
                      className="icon-link"
                      href={`/api/v1/reports/${encodeURIComponent(reportId)}/artifacts/${encodeURIComponent(artifact.artifact_id)}/content`}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={t("Open artifact")}
                      aria-label={`Open ${artifact.artifact_id}`}
                    >
                      <ExternalLink size={14} />
                    </a>
                  )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
