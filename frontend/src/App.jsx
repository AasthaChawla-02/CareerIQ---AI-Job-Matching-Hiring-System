import React, { useEffect, useMemo, useState } from "react";
import { apiRequest, getToken, setToken, uploadFile } from "./api.js";

const DEFAULT_SOURCES = {
  Remotive: true,
  RemoteOK: true,
};

function App() {
  const [user, setUser] = useState(null);
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [registerForm, setRegisterForm] = useState({
    email: "",
    password: "",
    role: "Candidate",
  });
  const [loginForm, setLoginForm] = useState({ email: "", password: "" });

  const [resume, setResume] = useState(null);
  const [resumeStatus, setResumeStatus] = useState("");

  const [keywords, setKeywords] = useState("");
  const [sources, setSources] = useState(DEFAULT_SOURCES);
  const [jobs, setJobs] = useState([]);
  const [jobsStatus, setJobsStatus] = useState("");
  const [matchScores, setMatchScores] = useState({});
  const [selectedJob, setSelectedJob] = useState(null);
  const [applicationText, setApplicationText] = useState("");

  const [employerJobs, setEmployerJobs] = useState([]);
  const [employerStatus, setEmployerStatus] = useState("");
  const [candidateSearch, setCandidateSearch] = useState("");
  const [jobForm, setJobForm] = useState({
    title: "",
    company_name: "",
    description: "",
    location: "",
    category: "",
    url: "",
    salary_min: "",
    salary_max: "",
    work_mode: "Remote",
  });
  const [jobMatches, setJobMatches] = useState({});

  const [candidateMatches, setCandidateMatches] = useState([]);
  const [candidateStatus, setCandidateStatus] = useState("");
  const [minMatchScore, setMinMatchScore] = useState(70);

  const sourceList = useMemo(
    () => Object.keys(sources).filter((key) => sources[key]),
    [sources]
  );

  useEffect(() => {
    const token = getToken();
    if (!token) {
      return;
    }
    apiRequest("/auth/me")
      .then((data) => setUser(data))
      .catch(() => setToken(""));
  }, []);

  useEffect(() => {
    if (!user) {
      return;
    }
    if (user.role === "Employer") {
      loadEmployerJobs();
    }
    if (user.role === "Candidate") {
      loadResume();
    }
  }, [user]);

  const loadResume = async () => {
    try {
      const data = await apiRequest("/resumes/me");
      setResume(data);
    } catch {
      setResume(null);
    }
  };

  const handleRegister = async (event) => {
    event.preventDefault();
    setAuthLoading(true);
    setAuthError("");
    try {
      await apiRequest("/auth/register", {
        method: "POST",
        body: JSON.stringify(registerForm),
      });
      await handleLogin(null, registerForm.email, registerForm.password);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogin = async (event, emailOverride, passwordOverride) => {
    if (event) {
      event.preventDefault();
    }
    setAuthLoading(true);
    setAuthError("");
    try {
      const payload = {
        email: emailOverride || loginForm.email,
        password: passwordOverride || loginForm.password,
      };
      const data = await apiRequest("/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setToken(data.access_token);
      setUser(data.user);
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    setToken("");
    setUser(null);
    setJobs([]);
    setEmployerJobs([]);
    setMatchScores({});
    setResume(null);
    setSelectedJob(null);
    setApplicationText("");
  };

  const handleResumeUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setResumeStatus("Uploading...");
    try {
      const data = await uploadFile("/resumes", file);
      setResume(data);
      setResumeStatus("Resume uploaded.");
    } catch (err) {
      setResumeStatus(err.message);
    }
  };

  const fetchJobs = async () => {
    setJobsStatus("Fetching jobs...");
    setJobs([]);
    setMatchScores({});
    setSelectedJob(null);
    setApplicationText("");
    try {
      const query = new URLSearchParams();
      if (keywords.trim()) {
        query.set("keywords", keywords.trim());
      }
      if (sourceList.length) {
        query.set("sources", sourceList.join(","));
      }
      const data = await apiRequest(`/jobs/external?${query.toString()}`);
      setJobs(data);
      setJobsStatus(`${data.length} jobs loaded.`);
    } catch (err) {
      setJobsStatus(err.message);
    }
  };

  const scoreJob = async (job) => {
    if (!resume?.resume_text) {
      setJobsStatus("Upload a resume before scoring.");
      return;
    }
    setJobsStatus(`Scoring ${job.title}...`);
    try {
      const data = await apiRequest("/matches/score", {
        method: "POST",
        body: JSON.stringify({
          resume_text: resume.resume_text,
          job_description: job.description,
          explain: true,
        }),
      });
      setMatchScores((prev) => ({ ...prev, [job.apply_url || job.title]: data }));
      setJobsStatus("Score updated.");
    } catch (err) {
      setJobsStatus(err.message);
    }
  };

  const generateApplication = async () => {
    if (!resume?.resume_text || !selectedJob) {
      return;
    }
    setApplicationText("Generating application...");
    try {
      const data = await apiRequest("/applications/generate", {
        method: "POST",
        body: JSON.stringify({
          resume_text: resume.resume_text,
          job_title: selectedJob.title,
          company_name: selectedJob.company,
          job_description: selectedJob.description,
        }),
      });
      setApplicationText(data.content);
    } catch (err) {
      setApplicationText(err.message);
    }
  };

  const loadEmployerJobs = async () => {
    try {
      const data = await apiRequest("/jobs/employer");
      setEmployerJobs(data);
    } catch (err) {
      setEmployerStatus(err.message);
    }
  };

  const createEmployerJob = async (event) => {
    event.preventDefault();
    setEmployerStatus("Posting job...");
    try {
      const payload = {
        ...jobForm,
        salary_min: jobForm.salary_min ? Number(jobForm.salary_min) : null,
        salary_max: jobForm.salary_max ? Number(jobForm.salary_max) : null,
      };
      const data = await apiRequest("/jobs", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setEmployerJobs((prev) => [data, ...prev]);
      // Auto load matches for new job
      setTimeout(() => loadEmployerMatches(data.id), 1000);
      setEmployerStatus("Job posted and matches computed automatically.");
      setJobForm({
        title: "",
        company_name: "",
        description: "",
        location: "",
        category: "",
        url: "",
        salary_min: "",
        salary_max: "",
        work_mode: "Remote",
      });
    } catch (err) {
      setEmployerStatus(err.message);
    }
  };

  const computeEmployerMatches = async (jobId) => {
    setEmployerStatus("Scoring candidates...");
    try {
      const data = await apiRequest(`/matches/compute-job/${jobId}`, {
        method: "POST",
      });
      setEmployerStatus(`Scored ${data.count} candidate(s).`);
    } catch (err) {
      setEmployerStatus(err.message);
    }
  };

  const loadEmployerMatches = async (jobId) => {
    setEmployerStatus("Loading matches...");
    try {
      const query = new URLSearchParams();
      query.set("min_score", minMatchScore.toString());
      if (candidateSearch.trim()) {
        query.set("candidate_search", candidateSearch.trim());
      }
      const data = await apiRequest(`/matches/job/${jobId}?${query.toString()}`);
      setJobMatches((prev) => ({ ...prev, [jobId]: data }));
      setEmployerStatus("");
    } catch (err) {
      setEmployerStatus(err.message);
    }
  };

  const computeCandidateMatches = async () => {
    setCandidateStatus("Scoring employer jobs...");
    try {
      const data = await apiRequest("/matches/compute-candidate", { method: "POST" });
      setCandidateStatus(`Scored ${data.count} job(s).`);
    } catch (err) {
      setCandidateStatus(err.message);
    }
  };

  const loadCandidateMatches = async () => {
    setCandidateStatus("Loading matches...");
    try {
      const data = await apiRequest(`/matches/candidate?min_score=${minMatchScore}`);
      setCandidateMatches(data);
      setCandidateStatus("");
    } catch (err) {
      setCandidateStatus(err.message);
    }
  };

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">AI Job Application Assistant</p>
          <h1>Match, craft, and ship applications faster.</h1>
          <p className="hero-sub">
            React on the front. FastAPI and Postgres underneath. OpenAI for the
            hard thinking.
          </p>
        </div>
        <div className="hero-card">
          <div className="hero-card-row">
            <span>Frontend</span>
            <strong>React</strong>
          </div>
          <div className="hero-card-row">
            <span>Backend</span>
            <strong>FastAPI</strong>
          </div>
          <div className="hero-card-row">
            <span>Database</span>
            <strong>PostgreSQL</strong>
          </div>
          <div className="hero-card-row">
            <span>AI</span>
            <strong>OpenAI API</strong>
          </div>
        </div>
      </header>

      <section className="grid">
        <div className="panel">
          <h2>Access</h2>
          <p className="muted">Create an account or sign in.</p>
          {user ? (
            <div className="stack">
              <div className="chip">
                Signed in as {user.email} ({user.role})
              </div>
              <button className="btn ghost" onClick={handleLogout}>
                Log out
              </button>
            </div>
          ) : (
            <div className="split">
              <form onSubmit={handleRegister} className="stack">
                <h3>Register</h3>
                <input
                  type="email"
                  placeholder="Email"
                  value={registerForm.email}
                  onChange={(event) =>
                    setRegisterForm({ ...registerForm, email: event.target.value })
                  }
                  required
                />
                <input
                  type="password"
                  placeholder="Password"
                  value={registerForm.password}
                  onChange={(event) =>
                    setRegisterForm({ ...registerForm, password: event.target.value })
                  }
                  required
                />
                <select
                  value={registerForm.role}
                  onChange={(event) =>
                    setRegisterForm({ ...registerForm, role: event.target.value })
                  }
                >
                  <option value="Candidate">Candidate</option>
                  <option value="Employer">Employer</option>
                </select>
                <button className="btn" disabled={authLoading}>
                  Create account
                </button>
              </form>
              <form onSubmit={handleLogin} className="stack">
                <h3>Login</h3>
                <input
                  type="email"
                  placeholder="Email"
                  value={loginForm.email}
                  onChange={(event) =>
                    setLoginForm({ ...loginForm, email: event.target.value })
                  }
                  required
                />
                <input
                  type="password"
                  placeholder="Password"
                  value={loginForm.password}
                  onChange={(event) =>
                    setLoginForm({ ...loginForm, password: event.target.value })
                  }
                  required
                />
                <button className="btn ghost" disabled={authLoading}>
                  Sign in
                </button>
              </form>
            </div>
          )}
          {authError && <div className="alert">{authError}</div>}
        </div>

        <div className="panel">
          <h2>Candidate Studio</h2>
          <p className="muted">
            Upload a resume, find roles, and get AI match explanations.
          </p>
          {!user ? (
            <div className="placeholder">Sign in as a Candidate to continue.</div>
          ) : user.role !== "Candidate" ? (
            <div className="placeholder">Switch to a Candidate account.</div>
          ) : (
            <div className="stack">
              <div className="card">
                <h3>Resume</h3>
                <input type="file" accept=".pdf" onChange={handleResumeUpload} />
                {resume && (
                  <div className="chip">
                    {resume.resume_filename || "Resume uploaded"} - updated{" "}
                    {new Date(resume.updated_at).toLocaleString()}
                  </div>
                )}
                {resumeStatus && <div className="status">{resumeStatus}</div>}
              </div>

              <div className="card">
                <h3>External Jobs</h3>
                <input
                  type="text"
                  placeholder="Keywords (comma-separated)"
                  value={keywords}
                  onChange={(event) => setKeywords(event.target.value)}
                />
                <div className="inline">
                  {Object.keys(sources).map((source) => (
                    <label key={source} className="toggle">
                      <input
                        type="checkbox"
                        checked={sources[source]}
                        onChange={() =>
                          setSources((prev) => ({
                            ...prev,
                            [source]: !prev[source],
                          }))
                        }
                      />
                      <span>{source}</span>
                    </label>
                  ))}
                </div>
                <button className="btn" onClick={fetchJobs}>
                  Fetch jobs
                </button>
                {jobsStatus && <div className="status">{jobsStatus}</div>}
                <div className="list">
                  {jobs.map((job) => {
                    const key = job.apply_url || job.title;
                    const score = matchScores[key];
                    return (
                      <div className="list-item" key={key}>
                        <div>
                          <strong>{job.title}</strong>
                          <div className="muted">{job.company}</div>
                          <div className="meta">
                            {job.location || "Location not listed"} · {job.source}
                          </div>
                        </div>
                        <div className="stack align-right">
                          <button className="btn ghost" onClick={() => scoreJob(job)}>
                            Score match
                          </button>
                          <button
                            className="btn subtle"
                            onClick={() => setSelectedJob(job)}
                          >
                            Select
                          </button>
                          {score && (
                            <div className="chip score">Score {score.score}%</div>
                          )}
                        </div>
                        {score?.explanation && (
                          <div className="explanation">{score.explanation}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="card">
                <h3>Generate Application</h3>
                {selectedJob ? (
                  <div className="stack">
                    <div className="chip">
                      {selectedJob.title} at {selectedJob.company}
                    </div>
                    <button className="btn" onClick={generateApplication}>
                      Generate application
                    </button>
                    {applicationText && (
                      <textarea
                        className="output"
                        value={applicationText}
                        readOnly
                      />
                    )}
                  </div>
                ) : (
                  <div className="placeholder">Select a job to generate.</div>
                )}
              </div>

              <div className="card">
                <h3>Employer Matches</h3>
                <div className="inline">
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={minMatchScore}
                    onChange={(event) =>
                      setMinMatchScore(Number(event.target.value || 0))
                    }
                  />
                  <button className="btn ghost" onClick={computeCandidateMatches}>
                    Re-score
                  </button>
                  <button className="btn subtle" onClick={loadCandidateMatches}>
                    Load matches
                  </button>
                </div>
                {candidateStatus && <div className="status">{candidateStatus}</div>}
                <div className="list">
                  {candidateMatches.map((match) => (
                    <div className="list-item" key={`${match.job_id}-${match.match_score}`}>
                      <div>
                        <strong>{match.title}</strong>
                        <div className="muted">{match.company_name}</div>
                        <div className="meta">
                          Score {match.match_score}% · {match.work_mode || "Unknown"}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="panel">
          <h2>Employer Studio</h2>
          <p className="muted">Post roles and review matched candidates.</p>
          {!user ? (
            <div className="placeholder">Sign in as an Employer to continue.</div>
          ) : user.role !== "Employer" ? (
            <div className="placeholder">Switch to an Employer account.</div>
          ) : (
            <div className="stack">
              <form className="card stack" onSubmit={createEmployerJob}>
                <h3>Post a Job</h3>
                <input
                  type="text"
                  placeholder="Job title"
                  value={jobForm.title}
                  onChange={(event) =>
                    setJobForm({ ...jobForm, title: event.target.value })
                  }
                  required
                />
                <input
                  type="text"
                  placeholder="Company"
                  value={jobForm.company_name}
                  onChange={(event) =>
                    setJobForm({ ...jobForm, company_name: event.target.value })
                  }
                  required
                />
                <textarea
                  placeholder="Job description"
                  value={jobForm.description}
                  onChange={(event) =>
                    setJobForm({ ...jobForm, description: event.target.value })
                  }
                  required
                />
                <div className="inline">
                  <input
                    type="text"
                    placeholder="Location"
                    value={jobForm.location}
                    onChange={(event) =>
                      setJobForm({ ...jobForm, location: event.target.value })
                    }
                  />
                  <select
                    value={jobForm.work_mode}
                    onChange={(event) =>
                      setJobForm({ ...jobForm, work_mode: event.target.value })
                    }
                  >
                    <option value="Remote">Remote</option>
                    <option value="Hybrid">Hybrid</option>
                    <option value="On-site">On-site</option>
                    <option value="Unknown">Unknown</option>
                  </select>
                </div>
                <div className="inline">
                  <input
                    type="text"
                    placeholder="Category"
                    value={jobForm.category}
                    onChange={(event) =>
                      setJobForm({ ...jobForm, category: event.target.value })
                    }
                  />
                  <input
                    type="text"
                    placeholder="Apply URL"
                    value={jobForm.url}
                    onChange={(event) =>
                      setJobForm({ ...jobForm, url: event.target.value })
                    }
                  />
                </div>
                <div className="inline">
                  <input
                    type="number"
                    placeholder="Min salary"
                    value={jobForm.salary_min}
                    onChange={(event) =>
                      setJobForm({ ...jobForm, salary_min: event.target.value })
                    }
                  />
                  <input
                    type="number"
                    placeholder="Max salary"
                    value={jobForm.salary_max}
                    onChange={(event) =>
                      setJobForm({ ...jobForm, salary_max: event.target.value })
                    }
                  />
                </div>
                <button className="btn" type="submit">
                  Post job
                </button>
                {employerStatus && <div className="status">{employerStatus}</div>}
              </form>

              <div className="card">
                <h3>Your Jobs</h3>
                <div className="inline">
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={minMatchScore}
                    onChange={(event) => setMinMatchScore(Number(event.target.value || 0))}
                    placeholder="Min score"
                  />
                  <input
                    type="text"
                    value={candidateSearch}
                    onChange={(event) => setCandidateSearch(event.target.value)}
                    placeholder="Search candidates"
                  />
                  <button className="btn ghost" onClick={() => employerJobs.forEach(job => loadEmployerMatches(job.id))}>
                    Refresh all
                  </button>
                </div>
                <div className="list">
                  {employerJobs.map((job) => (
                    <div className="list-item" key={job.id}>
                      <div>
                        <strong>{job.title}</strong>
                        <div className="muted">{job.company_name}</div>
                        <div className="meta">
                          {job.work_mode || "Unknown"} · {job.location || "Location not listed"}
                        </div>
                      </div>
                      <div className="stack align-right">
                        <button
                          className="btn ghost"
                          onClick={() => computeEmployerMatches(job.id)}
                        >
                          Re-compute matches
                        </button>
                        <button
                          className="btn subtle"
                          onClick={() => loadEmployerMatches(job.id)}
                        >
                          View matches
                        </button>
                      </div>
                      {jobMatches[job.id] && (
                        <div className="nested">
                          {jobMatches[job.id].length === 0 ? (
                            <div className="muted">No matches yet.</div>
                          ) : (
                            jobMatches[job.id].map((match, idx) => (
                              <div className="match" key={`${job.id}-${idx}`}>
                                <div>
                                  <strong>{match.candidate_email}</strong>
                                  <div className="meta">
                                    Score {match.match_score}% 
                                    {match.matched_skills && match.matched_skills.length > 0 && (
                                      <div>Matched: {match.matched_skills.join(', ')}</div>
                                    )}
                                    {match.missing_skills && match.missing_skills.length > 0 && (
                                      <div>Missing: {match.missing_skills.join(', ')}</div>
                                    )}
                                  </div>
                                </div>
                                <details>
                                  <summary>View Resume</summary>
                                  <textarea
                                    className="output"
                                    value={match.resume_text}
                                    readOnly
                                  />
                                </details>
                              </div>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

export default App;
