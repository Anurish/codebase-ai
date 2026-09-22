"use client";

import { useState } from "react";

import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  Code2,
  Database,
  FileCode2,
  FolderGit2,
  GitBranch,
  Info,
  Loader2,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Wrench,
  XCircle,
} from "lucide-react";


const suggestions = [
  "Where is authentication implemented?",
  "Explain the login flow",
  "Find all API endpoints",
  "Are there possible security issues?",
];


type Source = {
  file?: string;
  path?: string;
  lines?: string;
  score?: string;
  content?: string;
};


type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};


type ChatResponse = {
  answer: string;
  sources: Source[];
};


type IndexResponse = {
  files: number;
  chunks: number;
};


type ReviewFinding = {
  category: string;
  severity: string;
  title: string;
  explanation: string;
  file: string;
  lines: string;
  evidence: string;
  recommended_fix: string;
  confidence: string;
  potential: boolean;
};


type ReviewSummary = {
  critical: number;
  high: number;
  medium: number;
  low: number;
  informational: number;
  potential: number;
};


type ReviewResponse = {
  findings: ReviewFinding[];
  summary: ReviewSummary;
  overall_review: string;
  sources: Source[];
  reviewed_chunks: number;
};


type PageMode = "qa" | "review" | "health";


export default function Home() {
  const [mode, setMode] = useState<PageMode>("qa");

  const [query, setQuery] = useState("");

  const [messages, setMessages] = useState<Message[]>([]);

  const [selectedFile, setSelectedFile] = useState("");

  const [isLoading, setIsLoading] = useState(false);

  const [isIndexing, setIsIndexing] = useState(false);

  const [indexStatus, setIndexStatus] = useState("");

  const [indexedFiles, setIndexedFiles] = useState(0);

  const [indexedChunks, setIndexedChunks] = useState(0);

  const [error, setError] = useState("");

  const [reviewAnswer, setReviewAnswer] = useState("");

  const [reviewSources, setReviewSources] = useState<Source[]>([]);

  const [reviewedChunks, setReviewedChunks] = useState(0);

  const [reviewSummary, setReviewSummary] =
    useState<ReviewSummary | null>(null);

  const [reviewFindings, setReviewFindings] =
    useState<ReviewFinding[]>([]);

  const [selectedFinding, setSelectedFinding] =
    useState<ReviewFinding | null>(null);


  async function indexRepository() {
    if (isIndexing) return;

    setError("");

    setIsIndexing(true);

    setIndexStatus("Indexing repository...");

    try {
      const response = await fetch(
        "http://localhost:8000/api/index",
        {
          method: "POST",
        }
      );

      if (!response.ok) {
        throw new Error(
          `Backend returned HTTP ${response.status}`
        );
      }

      const data: IndexResponse =
        await response.json();

      setIndexedFiles(data.files);

      setIndexedChunks(data.chunks);

      setIndexStatus(
        `${data.files} files · ${data.chunks} chunks indexed`
      );
    } catch (err) {
      console.error(
        "Repository indexing error:",
        err
      );

      setIndexStatus("");

      setError(
        "Unable to index the repository. Make sure the Codebase AI backend is running."
      );
    } finally {
      setIsIndexing(false);
    }
  }


  async function ask(text?: string) {
    const value = (text ?? query).trim();

    if (!value || isLoading) return;

    setError("");

    setMode("qa");

    setMessages((current) => [
      ...current,
      {
        role: "user",
        content: value,
      },
    ]);

    setQuery("");

    setIsLoading(true);

    try {
      const response = await fetch(
        "http://localhost:8000/api/chat",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question: value,
            repository: "codebase-ai",
          }),
        }
      );

      if (!response.ok) {
        throw new Error(
          `Backend returned HTTP ${response.status}`
        );
      }

      const data: ChatResponse =
        await response.json();

      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: data.answer,
          sources: data.sources,
        },
      ]);

      if (
        data.sources &&
        data.sources.length > 0
      ) {
        setSelectedFile(
          data.sources[0].path ||
            data.sources[0].file ||
            ""
        );
      }
    } catch (err) {
      console.error(
        "Codebase AI API error:",
        err
      );

      setError(
        "Unable to connect to the Codebase AI backend."
      );
    } finally {
      setIsLoading(false);
    }
  }


  async function runCodeReview() {
    if (isLoading) return;

    setError("");

    setMode("review");

    setIsLoading(true);

    setReviewAnswer("");

    setReviewSources([]);

    setReviewedChunks(0);

    setReviewSummary(null);

    setReviewFindings([]);

    setSelectedFinding(null);

    try {
      const response = await fetch(
        "http://localhost:8000/api/review",
        {
          method: "POST",
        }
      );

      if (!response.ok) {
        throw new Error(
          `Backend returned HTTP ${response.status}`
        );
      }

      const data: ReviewResponse =
        await response.json();

      setReviewAnswer(
        data.overall_review || ""
      );

      setReviewSources(
        data.sources || []
      );

      setReviewedChunks(
        data.reviewed_chunks || 0
      );

      setReviewSummary(
        data.summary || {
          critical: 0,
          high: 0,
          medium: 0,
          low: 0,
          informational: 0,
          potential: 0,
        }
      );

      setReviewFindings(
        data.findings || []
      );

      if (
        data.sources &&
        data.sources.length > 0
      ) {
        setSelectedFile(
          data.sources[0].path ||
            data.sources[0].file ||
            ""
        );
      }
    } catch (err) {
      console.error(
        "Code review error:",
        err
      );

      setError(
        "Unable to run code review. Make sure the backend is running and the repository is indexed."
      );
    } finally {
      setIsLoading(false);
    }
  }


  function selectMode(nextMode: PageMode) {
    setError("");

    setMode(nextMode);

    if (nextMode === "qa") {
      setSelectedFinding(null);
    }

    if (nextMode === "health") {
      setMessages([]);
      setSelectedFinding(null);
    }
  }


  const latestAssistantMessage =
    [...messages]
      .reverse()
      .find(
        (message) =>
          message.role === "assistant"
      );


  const qaSources =
    latestAssistantMessage?.sources || [];


  const currentSources =
    mode === "review"
      ? reviewSources
      : qaSources;


  const selectedSource =
    currentSources.find(
      (source) =>
        (source.path || source.file) ===
        selectedFile
    ) || currentSources[0];


  return (
    <main className="shell">

      {/* SIDEBAR */}

      <aside className="sidebar">

        <div className="brand">

          <div className="brandIcon">
            <Code2 size={20} />
          </div>

          <div>
            <strong>Codebase AI</strong>

            <span>
              Phase 3 · Code Intelligence
            </span>
          </div>

        </div>


        <div className="repoCard">

          <div className="eyebrow">
            REPOSITORY
          </div>

          <div className="repoName">
            <FolderGit2 size={17} />
            codebase-ai
          </div>

          <div className="repoMeta">
            <GitBranch size={13} />
            main
          </div>

        </div>


        <nav>

          <div className="navLabel">
            WORKSPACE
          </div>


          <button
            className={`navItem ${
              mode === "qa"
                ? "active"
                : ""
            }`}
            onClick={() =>
              selectMode("qa")
            }
          >
            <Bot size={17} />
            Code Q&A
          </button>


          <button
            className={`navItem ${
              mode === "review"
                ? "active"
                : ""
            }`}
            onClick={() =>
              selectMode("review")
            }
          >
            <ShieldCheck size={17} />
            Code Review
          </button>


          <button
            className={`navItem ${
              mode === "health"
                ? "active"
                : ""
            }`}
            onClick={() =>
              selectMode("health")
            }
          >
            <Activity size={17} />
            Repository Health
          </button>

        </nav>


        <div className="sidebarBottom">

          <div className="statusDot" />

          Backend connected

        </div>

      </aside>


      {/* MAIN */}

      <section className="main">

        <header className="topbar">

          <div>

            <div className="breadcrumb">
              WORKSPACE
              <ChevronRight size={14} />
              codebase-ai
            </div>

            <h1>
              {mode === "qa"
                ? "Codebase Q&A"
                : mode === "review"
                ? "Code Review"
                : "Repository Health"}
            </h1>

          </div>


          <div className="phaseBadge">
            <Sparkles size={14} />
            Phase 3 · Code Intelligence
          </div>

        </header>


        <div className="content">

          {/* ========================= */}
          {/* CODE Q&A */}
          {/* ========================= */}

          {mode === "qa" && (
            <>

              <section className="hero">

                <div className="heroIcon">
                  <Sparkles size={25} />
                </div>

                <div>

                  <h2>
                    Ask anything about your codebase
                  </h2>

                  <p>
                    Search architecture, functions,
                    APIs, dependencies and security
                    patterns from one interface.
                  </p>

                </div>

              </section>


              <section className="indexPanel">

                <div className="indexInfo">

                  <div className="indexIcon">
                    <Database size={18} />
                  </div>

                  <div className="indexText">

                    <strong>
                      Repository Intelligence
                    </strong>

                    <span>
                      {indexStatus ||
                        "Index your repository before asking code questions."}
                    </span>

                  </div>

                </div>


                <button
                  className="indexButton"
                  onClick={indexRepository}
                  disabled={isIndexing}
                >

                  {isIndexing ? (
                    <>
                      <Loader2
                        size={16}
                        className="spinner"
                      />
                      Indexing...
                    </>
                  ) : (
                    <>
                      <RefreshCw size={16} />
                      Index Repository
                    </>
                  )}

                </button>

              </section>


              {indexedFiles > 0 && (
                <div className="indexStats">

                  <div className="statCard">
                    <strong>
                      {indexedFiles}
                    </strong>
                    <span>
                      Files indexed
                    </span>
                  </div>


                  <div className="statCard">
                    <strong>
                      {indexedChunks}
                    </strong>
                    <span>
                      Code chunks
                    </span>
                  </div>


                  <div className="statCard">
                    <strong>
                      pgvector
                    </strong>
                    <span>
                      Vector search
                    </span>
                  </div>


                  <div className="statCard">
                    <strong>
                      Gemini
                    </strong>
                    <span>
                      AI analysis
                    </span>
                  </div>

                </div>
              )}


              {messages.length === 0 && (
                <div className="suggestions">

                  {suggestions.map(
                    (suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() =>
                          ask(suggestion)
                        }
                        disabled={isLoading}
                      >
                        <Search size={15} />
                        {suggestion}
                      </button>
                    )
                  )}

                </div>
              )}


              <div className="chat">

                {messages.map(
                  (message, index) => (

                    <div
                      key={index}
                      className={`message ${
                        message.role
                      }`}
                    >

                      <div className="avatar">
                        {message.role ===
                        "user" ? (
                          "A"
                        ) : (
                          <Bot size={16} />
                        )}
                      </div>

                      <div className="bubble">
                        {message.content}
                      </div>

                    </div>

                  )
                )}


                {isLoading && (
                  <div className="message assistant">

                    <div className="avatar">
                      <Bot size={16} />
                    </div>

                    <div className="bubble loadingBubble">

                      <Loader2
                        size={15}
                        className="spinner"
                      />

                      Analyzing your request...

                    </div>

                  </div>
                )}


                {error && (
                  <div className="errorMessage">
                    {error}
                  </div>
                )}


                {currentSources.length > 0 &&
                  !isLoading && (
                    <SourceList
                      sources={currentSources}
                      selectedFile={selectedFile}
                      onSelect={setSelectedFile}
                    />
                  )}


                {selectedSource && (
                  <SourcePreview
                    source={selectedSource}
                  />
                )}

              </div>


              <div className="composer">

                <Search size={18} />

                <input
                  value={query}
                  onChange={(event) =>
                    setQuery(
                      event.target.value
                    )
                  }
                  onKeyDown={(event) => {

                    if (
                      event.key === "Enter" &&
                      !event.shiftKey
                    ) {
                      event.preventDefault();
                      ask();
                    }

                  }}
                  disabled={isLoading}
                  placeholder="Ask a question about the repository..."
                />


                <button
                  className="send"
                  onClick={() => ask()}
                  disabled={
                    isLoading ||
                    !query.trim()
                  }
                >

                  {isLoading ? (
                    <Loader2
                      size={17}
                      className="spinner"
                    />
                  ) : (
                    <Send size={17} />
                  )}

                </button>

              </div>

            </>
          )}


          {/* ========================= */}
          {/* CODE REVIEW */}
          {/* ========================= */}

          {mode === "review" && (
            <>

              <section className="hero">

                <div className="heroIcon">
                  <ShieldCheck size={25} />
                </div>

                <div>

                  <h2>
                    Review your codebase
                  </h2>

                  <p>
                    Analyze indexed code for security
                    risks, bugs, performance issues and
                    maintainability problems.
                  </p>

                </div>

              </section>


              <section className="reviewAction">

                <div>

                  <strong>
                    AI Code Review
                  </strong>

                  <span>
                    Uses your indexed repository
                    as evidence.
                  </span>

                </div>


                <button
                  className="indexButton"
                  onClick={runCodeReview}
                  disabled={isLoading}
                >

                  {isLoading ? (
                    <>
                      <Loader2
                        size={16}
                        className="spinner"
                      />
                      Reviewing...
                    </>
                  ) : (
                    <>
                      <ShieldCheck size={16} />
                      Run Code Review
                    </>
                  )}

                </button>

              </section>


              {reviewSummary && (
                <ReviewSummaryCards
                  summary={reviewSummary}
                  reviewedChunks={reviewedChunks}
                />
              )}


              {reviewAnswer && (
                <section className="overallReview">

                  <div className="overallHeader">

                    <div>
                      <Sparkles size={17} />
                      <strong>
                        Overall Review
                      </strong>
                    </div>

                    <span>
                      {reviewedChunks} chunks analyzed
                    </span>

                  </div>


                  <p>
                    {reviewAnswer}
                  </p>

                </section>
              )}


              {reviewFindings.length > 0 ? (
                <section className="findingsSection">

                  <div className="sectionTitle">

                    <div>
                      <ShieldCheck size={18} />

                      <strong>
                        Review Findings
                      </strong>
                    </div>

                    <span>
                      {reviewFindings.length} finding
                      {reviewFindings.length === 1
                        ? ""
                        : "s"}
                    </span>

                  </div>


                  <div className="findingsGrid">

                    <div className="findingsList">

                      {reviewFindings.map(
                        (finding, index) => (
                          <FindingCard
                            key={`${finding.file}-${finding.lines}-${index}`}
                            finding={finding}
                            selected={
                              selectedFinding ===
                              finding
                            }
                            onClick={() =>
                              setSelectedFinding(
                                finding
                              )
                            }
                          />
                        )
                      )}

                    </div>


                    <div className="findingDetail">

                      {selectedFinding ? (
                        <FindingDetail
                          finding={
                            selectedFinding
                          }
                        />
                      ) : (
                        <div className="emptyFinding">

                          <ShieldCheck size={30} />

                          <strong>
                            Select a finding
                          </strong>

                          <span>
                            Choose a review finding
                            to inspect its evidence,
                            location and recommended
                            fix.
                          </span>

                        </div>
                      )}

                    </div>

                  </div>

                </section>
              ) : (
                reviewAnswer &&
                !isLoading && (
                  <section className="noFindings">

                    <CheckCircle2 size={24} />

                    <div>

                      <strong>
                        No confirmed issues found
                      </strong>

                      <span>
                        The reviewer did not identify
                        any evidence-backed problems
                        in the retrieved code.
                      </span>

                    </div>

                  </section>
                )
              )}


              {error && (
                <div className="errorMessage">
                  {error}
                </div>
              )}


              {reviewSources.length > 0 && (
                <section className="reviewSources">

                  <SourceList
                    sources={reviewSources}
                    selectedFile={selectedFile}
                    onSelect={setSelectedFile}
                  />

                  {selectedSource && (
                    <SourcePreview
                      source={selectedSource}
                    />
                  )}

                </section>
              )}

            </>
          )}


          {/* ========================= */}
          {/* REPOSITORY HEALTH */}
          {/* ========================= */}

          {mode === "health" && (
            <>

              <section className="hero">

                <div className="heroIcon">
                  <Activity size={25} />
                </div>

                <div>

                  <h2>
                    Repository Health
                  </h2>

                  <p>
                    Overview of the repository
                    currently indexed by Codebase AI.
                  </p>

                </div>

              </section>


              <div className="healthGrid">

                <div className="healthCard">

                  <Database size={20} />

                  <strong>
                    {indexedFiles || 21}
                  </strong>

                  <span>
                    Indexed files
                  </span>

                </div>


                <div className="healthCard">

                  <Code2 size={20} />

                  <strong>
                    {indexedChunks || 36}
                  </strong>

                  <span>
                    Code chunks
                  </span>

                </div>


                <div className="healthCard">

                  <CheckCircle2 size={20} />

                  <strong>
                    Ready
                  </strong>

                  <span>
                    Vector index
                  </span>

                </div>


                <div className="healthCard">

                  <Sparkles size={20} />

                  <strong>
                    Gemini
                  </strong>

                  <span>
                    AI engine
                  </span>

                </div>

              </div>


              <section className="healthPanel">

                <div className="healthPanelHeader">

                  <div>
                    <Activity size={18} />
                    <strong>
                      System status
                    </strong>
                  </div>

                </div>


                <div className="healthRow">

                  <span>
                    Repository
                  </span>

                  <strong>
                    codebase-ai
                  </strong>

                  <CheckCircle2 size={16} />

                </div>


                <div className="healthRow">

                  <span>
                    PostgreSQL
                  </span>

                  <strong>
                    Connected
                  </strong>

                  <CheckCircle2 size={16} />

                </div>


                <div className="healthRow">

                  <span>
                    pgvector
                  </span>

                  <strong>
                    Active
                  </strong>

                  <CheckCircle2 size={16} />

                </div>


                <div className="healthRow">

                  <span>
                    Gemini
                  </span>

                  <strong>
                    Connected
                  </strong>

                  <CheckCircle2 size={16} />

                </div>

              </section>

            </>
          )}

        </div>

      </section>

    </main>
  );
}


/* ================================================= */
/* SOURCE LIST */
/* ================================================= */

function SourceList({
  sources,
  selectedFile,
  onSelect,
}: {
  sources: Source[];
  selectedFile: string;
  onSelect: (file: string) => void;
}) {
  return (
    <div className="sources">

     <div className="sourcesHeader">

  <span>
    <FileCode2 size={16} />
    Review Evidence
  </span>

  <small>
    Code supplied to the AI reviewer
  </small>

</div>


      {sources.map(
        (file, index) => {

          const filePath =
            file.path ||
            file.file ||
            `source-${index}`;

          const fileName =
            file.file ||
            file.path
              ?.split("/")
              .pop() ||
            "source";


          return (
            <button
              key={`${filePath}-${index}`}
              className={`source ${
                selectedFile === filePath
                  ? "selected"
                  : ""
              }`}
              onClick={() =>
                onSelect(filePath)
              }
            >

              <FileCode2 size={16} />

              <div className="sourceInfo">

                <strong>
                  {fileName}
                </strong>

                <span>
                  {file.path ||
                    "Repository source"}
                </span>

              </div>


              {file.lines && (
                <span className="lines">
                  L{file.lines}
                </span>
              )}


              {file.score && (
                <span className="score">
                  {file.score}
                </span>
              )}

            </button>
          );
        }
      )}

    </div>
  );
}


/* ================================================= */
/* SOURCE PREVIEW */
/* ================================================= */

function SourcePreview({
  source,
}: {
  source: Source;
}) {
  return (
    <div className="codePreview">

      <div className="previewHeader">

        <span>
          <FileCode2 size={15} />
          {source.path ||
            source.file}
        </span>

        <span className="readOnly">
          READ ONLY
        </span>

      </div>


      <div className="previewMeta">

        <span>
          Lines {source.lines || "N/A"}
        </span>

        <span>
          Similarity {source.score || "N/A"}
        </span>

      </div>


      <pre className="realCode">
        <code>
          {source.content ||
            "Source content unavailable."}
        </code>
      </pre>

    </div>
  );
}


/* ================================================= */
/* REVIEW SUMMARY */
/* ================================================= */

function ReviewSummaryCards({
  summary,
  reviewedChunks,
}: {
  summary: ReviewSummary;
  reviewedChunks: number;
}) {
  return (
    <div className="reviewSummaryGrid">

      <div className="reviewMetric analyzed">

        <div className="metricIcon">
          <Code2 size={17} />
        </div>

        <strong>
          {reviewedChunks}
        </strong>

        <span>
          Chunks analyzed
        </span>

      </div>


      <div className="reviewMetric critical">

        <div className="metricIcon">
          <XCircle size={17} />
        </div>

        <strong>
          {summary.critical}
        </strong>

        <span>
          Critical
        </span>

      </div>


      <div className="reviewMetric high">

        <div className="metricIcon">
          <AlertTriangle size={17} />
        </div>

        <strong>
          {summary.high}
        </strong>

        <span>
          High
        </span>

      </div>


      <div className="reviewMetric medium">

        <div className="metricIcon">
          <AlertTriangle size={17} />
        </div>

        <strong>
          {summary.medium}
        </strong>

        <span>
          Medium
        </span>

      </div>


      <div className="reviewMetric low">

        <div className="metricIcon">
          <Info size={17} />
        </div>

        <strong>
          {summary.low}
        </strong>

        <span>
          Low
        </span>

      </div>


      <div className="reviewMetric potential">

        <div className="metricIcon">
          <Search size={17} />
        </div>

        <strong>
          {summary.potential}
        </strong>

        <span>
          Potential
        </span>

      </div>

    </div>
  );
}


/* ================================================= */
/* FINDING CARD */
/* ================================================= */

function FindingCard({
  finding,
  selected,
  onClick,
}: {
  finding: ReviewFinding;
  selected: boolean;
  onClick: () => void;
}) {
  const severity =
    finding.severity.toLowerCase();


  return (
    <button
      className={`findingCard ${
        selected ? "selected" : ""
      }`}
      onClick={onClick}
    >

      <div className="findingTop">

        <SeverityBadge
          severity={
            finding.severity
          }
        />

        {finding.potential && (
          <span className="potentialBadge">
            Potential
          </span>
        )}

      </div>


      <h3>
        {finding.title}
      </h3>


      <p>
        {finding.explanation}
      </p>


      <div className="findingFooter">

        <span>
          <FileCode2 size={13} />
          {finding.file}
        </span>

        <span>
          L{finding.lines}
        </span>

        <span>
          {finding.confidence}
        </span>

      </div>

    </button>
  );
}


/* ================================================= */
/* SEVERITY BADGE */
/* ================================================= */

function SeverityBadge({
  severity,
}: {
  severity: string;
}) {
  const normalized =
    severity.toLowerCase();


  return (
    <span
      className={`severityBadge severity-${normalized}`}
    >

      {normalized === "critical" && (
        <XCircle size={13} />
      )}

      {normalized === "high" && (
        <AlertTriangle size={13} />
      )}

      {normalized === "medium" && (
        <AlertTriangle size={13} />
      )}

      {normalized === "low" && (
        <Info size={13} />
      )}

      {normalized === "informational" && (
        <Info size={13} />
      )}

      {severity}

    </span>
  );
}


/* ================================================= */
/* FINDING DETAIL */
/* ================================================= */

function FindingDetail({
  finding,
}: {
  finding: ReviewFinding;
}) {
  return (
    <div className="findingDetailInner">

      <div className="detailTop">

        <SeverityBadge
          severity={finding.severity}
        />

        {finding.potential && (
          <span className="potentialBadge">
            Potential issue
          </span>
        )}

      </div>


      <h2>
        {finding.title}
      </h2>


      <div className="detailLocation">

        <FileCode2 size={15} />

        <strong>
          {finding.file}
        </strong>

        <span>
          Lines {finding.lines}
        </span>

      </div>


      <div className="detailBlock">

        <div className="detailBlockTitle">
          <Info size={15} />
          Explanation
        </div>

        <p>
          {finding.explanation}
        </p>

      </div>


      <div className="detailBlock">

        <div className="detailBlockTitle">
          <Code2 size={15} />
          Evidence
        </div>

        <div className="evidenceBlock">
          {finding.evidence}
        </div>

      </div>


      <div className="detailBlock">

        <div className="detailBlockTitle">
          <Wrench size={15} />
          Recommended Fix
        </div>

        <p>
          {finding.recommended_fix}
        </p>

      </div>


      <div className="detailBottom">

        <span>
          Category:
          <strong>
            {finding.category}
          </strong>
        </span>

        <span>
          Confidence:
          <strong>
            {finding.confidence}
          </strong>
        </span>

      </div>

    </div>
  );
}