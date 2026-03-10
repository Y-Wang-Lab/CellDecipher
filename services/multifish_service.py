"""Pipeline assistant service — knowledge base + Seqera monitoring + LLM chat.

Includes GitHub API-backed knowledge sync so multiple users share discoveries.
Works on Streamlit Cloud (no git binary or persistent filesystem required).
"""

import base64
import datetime
import logging
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests

logger = logging.getLogger("multifish-service")

# Error patterns ported from multifish-mcp diagnose.py
ERROR_PATTERNS = [
    {
        "pattern": re.compile(r"container.*null|container:\s*'null'", re.IGNORECASE),
        "title": "Container resolving to null",
        "cause": (
            "In Nextflow 25.x, the Spark module's GString container directives "
            "evaluate at parse time before params are populated, resolving to null."
        ),
        "fix": (
            "Add workflow-scoped `withName` blocks to `nextflow.config`:\n\n"
            "```groovy\n"
            "withName: 'prepare_spark_work_dir|wait_for_master|wait_for_worker|terminate_spark' {\n"
            "    container = 'public.ecr.aws/janeliascicomp/multifish/stitching:1.2.0'\n"
            "}\n"
            "withName: 'stitching:.*:spark_master|stitching:.*:spark_worker|stitching:.*:spark_start_app' {\n"
            "    container = 'public.ecr.aws/janeliascicomp/multifish/stitching:1.2.0'\n"
            "}\n"
            "withName: 'spot_extraction:.*:spark_master|spot_extraction:.*:spark_worker|spot_extraction:.*:spark_start_app' {\n"
            "    container = 'public.ecr.aws/janeliascicomp/multifish/rs_fish:1.0.2'\n"
            "}\n"
            "```"
        ),
    },
    {
        "pattern": re.compile(r"spark_worker.*NEW|spark_worker.*SUBMITTED|spark_worker.*stuck", re.IGNORECASE),
        "title": "Spark worker stuck (CPU resource deadlock)",
        "cause": (
            "The local executor enforces CPU constraints. If "
            "`1 (master) + worker_cores + 1 (wait_for_worker) > total_CPUs`, "
            "the worker can never be scheduled."
        ),
        "fix": (
            "Reduce `worker_cores` in your params JSON so that "
            "`worker_cores <= total_CPUs - 2`.\n"
            "For a 4-CPU machine, set `worker_cores` to 2 or less."
        ),
    },
    {
        "pattern": re.compile(r"exit.?status.*101|exit.?code.*101", re.IGNORECASE),
        "title": "Spark application exit code 101 (wrong container)",
        "cause": (
            "Exit code 101 from `spark_start_app` means the Java class/JAR was not found. "
            "This happens when the wrong container is used (e.g., stitching container for rsfish)."
        ),
        "fix": (
            "Use workflow-scoped `withName` selectors for `spark_start_app`:\n"
            "- `stitching:.*:spark_start_app` -> stitching container\n"
            "- `spot_extraction:.*:spark_start_app` -> rs_fish container"
        ),
    },
    {
        "pattern": re.compile(r"FileNotFoundError.*spots_rsfish.*\.csv", re.IGNORECASE),
        "title": "RS-FISH output CSV not found",
        "cause": "The upstream RS-FISH Spark job didn't produce the expected CSV output.",
        "fix": (
            "Check the Spark log in `{spark_work_dir}/{session_uuid}/`.\n"
            "Verify the correct container is used and check memory settings."
        ),
    },
    {
        "pattern": re.compile(r"Timed out.*waiting for.*sessionId|Timed out.*spark", re.IGNORECASE),
        "title": "Spark startup timeout",
        "cause": "The Spark master failed to start within the timeout period.",
        "fix": (
            "1. Ensure `spark_work_dir` is on a shared filesystem\n"
            "2. Check container availability in Singularity cache\n"
            "3. Increase `wait_for_spark_timeout_seconds`"
        ),
    },
    {
        "pattern": re.compile(r"session id.*does not match", re.IGNORECASE),
        "title": "Spark session ID mismatch",
        "cause": "A stale `.sessionId` file from a previous run exists in `spark_work_dir`.",
        "fix": "Delete the contents of `spark_work_dir` or use `-resume`.",
    },
    {
        "pattern": re.compile(r"OutOfMemoryError|java\.lang\.OutOfMemoryError|Cannot allocate memory", re.IGNORECASE),
        "title": "Out of memory error",
        "cause": "A Spark process ran out of memory. Worker memory = worker_cores * gb_per_core.",
        "fix": (
            "Reduce `worker_cores` or increase `gb_per_core`.\n"
            "For RS-FISH: adjust `rsfish_worker_cores` and `rsfish_gb_per_core`."
        ),
    },
]

SYSTEM_PROMPT = """You are an expert assistant for the EASI-FISH / Multifish Nextflow pipeline.
You help users with: pipeline configuration, troubleshooting errors, understanding outputs,
monitoring runs via Seqera Platform, and data format questions.

You have access to a knowledge base and Seqera Platform run data.
Use the provided context to give accurate, specific answers.
When you don't know something, say so — don't guess.

Keep answers concise but complete. Use markdown formatting for readability.
When citing pipeline parameters, use backticks (e.g., `worker_cores`).
"""

def _format_duration_ms(ms) -> str:
    """Convert milliseconds (from Seqera API) to human-readable duration."""
    try:
        total_seconds = int(ms) // 1000
    except (TypeError, ValueError):
        return str(ms) if ms else "N/A"
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes, secs = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _format_start_time(dt) -> str:
    """Format a UTC datetime to local time string."""
    if not dt:
        return "unknown"
    try:
        local_dt = dt.astimezone()  # converts to system local timezone
        return local_dt.strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return dt.strftime("%Y-%m-%d %H:%M UTC")


# Keywords that suggest the user is asking about run status
RUN_KEYWORDS = re.compile(
    r"\b(run|status|running|fail|failed|succeed|complete|launch|monitor|seqera|tower|workflow|job)\b",
    re.IGNORECASE,
)

# Keywords that suggest a pasted error message
ERROR_KEYWORDS = re.compile(
    r"(error|exception|exit.?code|exit.?status|failed|null|timeout|OutOfMemory|FileNotFound|stack.?trace)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# GitHub API-backed knowledge sync (replaces git-subprocess approach)
# ---------------------------------------------------------------------------

class GitHubKnowledgeSync:
    """GitHub API-backed sync for knowledge base files.

    Uses the GitHub REST API (via requests) instead of git CLI subprocess
    calls, so it works on Streamlit Cloud and other environments without git.
    Markdown files are append-only so conflicts are avoided by always
    reading the latest SHA before writing.
    """

    API_BASE = "https://api.github.com"

    def __init__(self, repo: str, path: str = "knowledge",
                 branch: str = "main", token: str = ""):
        self.repo = repo          # e.g. "Y-Wang-Lab/CellDecipher"
        self.path = path          # e.g. "knowledge"
        self.branch = branch
        self.token = token

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo)

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            h["Authorization"] = f"token {self.token}"
        return h

    def fetch_file(self, filename: str) -> Optional[str]:
        """Fetch a single file's decoded content from GitHub.

        Returns None if the file doesn't exist or the request fails.
        """
        url = f"{self.API_BASE}/repos/{self.repo}/contents/{self.path}/{filename}"
        try:
            resp = requests.get(
                url, headers=self._headers(),
                params={"ref": self.branch}, timeout=15,
            )
            if resp.status_code == 200:
                return base64.b64decode(resp.json()["content"]).decode()
        except Exception as exc:
            logger.warning("GitHub fetch_file(%s) failed: %s", filename, exc)
        return None

    def fetch_all_files(self) -> Dict[str, str]:
        """Fetch all .md files from the knowledge directory on GitHub.

        Returns a dict of {filename: content}. Empty dict on failure.
        """
        url = f"{self.API_BASE}/repos/{self.repo}/contents/{self.path}"
        try:
            resp = requests.get(
                url, headers=self._headers(),
                params={"ref": self.branch}, timeout=15,
            )
            if resp.status_code != 200:
                logger.warning("GitHub list dir failed: %s", resp.status_code)
                return {}

            files: Dict[str, str] = {}
            for item in resp.json():
                if item["name"].endswith(".md"):
                    content = self.fetch_file(item["name"])
                    if content is not None:
                        files[item["name"]] = content
            return files

        except Exception as exc:
            logger.warning("GitHub fetch_all_files failed: %s", exc)
            return {}

    def update_file(self, filename: str, new_content: str,
                    message: str) -> str:
        """Create or update a file in the repo via the GitHub Contents API.

        Reads the current SHA first (required for updates), then PUTs
        the new content.  Returns a human-readable status string.
        """
        if not self.enabled:
            return "GitHub sync not configured (set GITHUB_TOKEN)"

        url = f"{self.API_BASE}/repos/{self.repo}/contents/{self.path}/{filename}"

        try:
            # Get current file SHA (needed for updates, absent for creates)
            resp = requests.get(
                url, headers=self._headers(),
                params={"ref": self.branch}, timeout=15,
            )
            sha = resp.json().get("sha") if resp.status_code == 200 else None

            payload: Dict[str, Any] = {
                "message": message,
                "content": base64.b64encode(new_content.encode()).decode(),
                "branch": self.branch,
            }
            if sha:
                payload["sha"] = sha

            resp = requests.put(
                url, headers=self._headers(), json=payload, timeout=15,
            )
            if resp.status_code in (200, 201):
                return "Knowledge updated in GitHub"
            return f"GitHub API error: {resp.status_code} {resp.text[:200]}"

        except Exception as exc:
            logger.warning("GitHub update_file(%s) failed: %s", filename, exc)
            return f"GitHub sync failed: {exc}"

    def get_status(self) -> str:
        """Human-readable sync status."""
        if not self.enabled:
            return (
                "**Sync**: Not configured\n"
                "Set `GITHUB_TOKEN` in Streamlit secrets or `.env` to enable."
            )
        return (
            f"**Sync**: GitHub API -> `{self.repo}`\n"
            f"**Branch**: `{self.branch}`\n"
            f"**Path**: `{self.path}/`\n"
            f"**Status**: Active"
        )


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class MultifishService:
    """Service combining knowledge base, Seqera monitoring, and LLM chat."""

    def __init__(
        self,
        knowledge_dir: Optional[str] = None,
        tower_service=None,
        llm_provider: str = "openai",
        api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        github_token: str = "",
        github_repo: str = "Y-Wang-Lab/CellDecipher",
        github_knowledge_path: str = "knowledge",
        knowledge_branch: str = "main",
    ):
        if knowledge_dir:
            self.knowledge_dir = Path(knowledge_dir)
        else:
            # Default to bundled knowledge directory
            self.knowledge_dir = Path(__file__).parent.parent / "knowledge"
        self.tower_service = tower_service
        self.llm_provider = llm_provider
        self.api_key = api_key or os.environ.get(
            "OPENAI_API_KEY" if llm_provider == "openai" else "ANTHROPIC_API_KEY"
        )
        self.llm_model = llm_model
        self._client = None
        self._knowledge_cache: Dict[str, str] = {}

        # Set up GitHub API sync
        self.sync = GitHubKnowledgeSync(
            repo=github_repo,
            path=github_knowledge_path,
            branch=knowledge_branch,
            token=github_token,
        )

        self._load_knowledge()

    def _load_knowledge(self):
        """Load knowledge: try GitHub API first, fall back to bundled files."""
        self._knowledge_cache.clear()

        # Try fetching from GitHub
        if self.sync.enabled:
            remote_files = self.sync.fetch_all_files()
            if remote_files:
                self._knowledge_cache = remote_files
                logger.info("Loaded %d knowledge files from GitHub", len(remote_files))
                return

        # Fall back to bundled files
        if self.knowledge_dir and self.knowledge_dir.exists():
            for md_file in sorted(self.knowledge_dir.glob("*.md")):
                try:
                    self._knowledge_cache[md_file.name] = md_file.read_text()
                except Exception:
                    continue
            logger.info("Loaded %d bundled knowledge files", len(self._knowledge_cache))

    def refresh_knowledge(self) -> str:
        """Fetch latest from GitHub and reload knowledge files.

        Returns:
            Sync status message
        """
        self._load_knowledge()
        n = len(self._knowledge_cache)
        source = "GitHub" if self.sync.enabled else "bundled files"
        return f"Loaded {n} knowledge files from {source}"

    def _get_client(self):
        """Lazy load the LLM client."""
        if self._client is None:
            if self.llm_provider == "openai":
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            else:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
        return self._client

    def search_knowledge(self, query: str) -> str:
        """Search all knowledge base files for relevant context.

        Pulls latest from shared repo before searching.

        Args:
            query: Search terms

        Returns:
            Matching context snippets as a string
        """
        # Knowledge is loaded at init and on refresh — no per-query fetch
        # to avoid excessive GitHub API calls

        if not self._knowledge_cache:
            return ""

        query_lower = query.lower()
        query_words = query_lower.split()
        results = []

        for filename, content in self._knowledge_cache.items():
            lines = content.split("\n")
            matches = []

            for i, line in enumerate(lines):
                line_lower = line.lower()
                if any(word in line_lower for word in query_words):
                    start = max(0, i - 2)
                    end = min(len(lines), i + 6)
                    context = "\n".join(lines[start:end])
                    matches.append((i + 1, context))

            if matches:
                # Deduplicate overlapping matches
                seen_lines = set()
                unique_matches = []
                for line_num, context in matches:
                    if line_num not in seen_lines:
                        unique_matches.append((line_num, context))
                        for j in range(line_num - 2, line_num + 6):
                            seen_lines.add(j)

                for _, context in unique_matches[:3]:
                    results.append(f"[{filename}]\n{context}")

        if not results:
            return ""

        return "\n\n---\n\n".join(results)

    def diagnose_error(self, error_msg: str) -> str:
        """Pattern match an error message against known errors.

        Args:
            error_msg: The error message or log snippet

        Returns:
            Diagnosis string with cause and fix, or empty string
        """
        matches = []
        for entry in ERROR_PATTERNS:
            if entry["pattern"].search(error_msg):
                matches.append(entry)

        if not matches:
            return ""

        parts = []
        for m in matches:
            parts.append(
                f"**{m['title']}**\n\n"
                f"Cause: {m['cause']}\n\n"
                f"Fix: {m['fix']}"
            )
        return "\n\n---\n\n".join(parts)

    # -- Knowledge contribution methods -------------------------------------

    def _append_to_knowledge_file(
        self, filename: str, entry: str, commit_message: str,
        default_header: str = "",
    ) -> str:
        """Read a knowledge file, append an entry, and push via GitHub API.

        Falls back to local file write if GitHub sync is not enabled.

        Args:
            filename: Name of the .md file (e.g. "known_errors.md")
            entry: Markdown text to append
            commit_message: Git commit message for the update
            default_header: Header to use if the file doesn't exist yet

        Returns:
            Status message
        """
        if self.sync.enabled:
            # Read current content from GitHub (or cache)
            current = self.sync.fetch_file(filename)
            if current is None:
                current = default_header or ""
            new_content = current + entry
            sync_msg = self.sync.update_file(filename, new_content, commit_message)
            # Refresh cache with new content
            self._knowledge_cache[filename] = new_content
            return sync_msg

        # Fallback: write to local bundled file
        if not self.knowledge_dir:
            return "Knowledge directory not configured."

        filepath = self.knowledge_dir / filename
        try:
            if not filepath.exists() and default_header:
                filepath.write_text(default_header)
            with open(filepath, "a") as f:
                f.write(entry)
            self._knowledge_cache[filename] = filepath.read_text()
            return "Saved locally (GitHub sync not configured)"
        except Exception as e:
            return f"Failed to save: {e}"

    def save_error(self, title: str, symptoms: str, root_cause: str, fix: str) -> str:
        """Save a newly discovered error to the knowledge base.

        Args:
            title: Short title for the error
            symptoms: What the user sees (error messages, exit codes)
            root_cause: Why the error occurs
            fix: How to fix it

        Returns:
            Status message
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
        entry = f"""
---

## {title}
_Added: {timestamp}_

### Symptoms
{symptoms}

### Root Cause
{root_cause}

### Fix
{fix}
"""
        result = self._append_to_knowledge_file(
            "known_errors.md", entry, f"New error: {title}",
        )
        return f"Error saved: '{title}'\n{result}"

    def save_lesson(self, category: str, title: str, problem: str, solution: str) -> str:
        """Save a lesson learned to the knowledge base.

        Args:
            category: Category (e.g. parameter_tuning, setup, workflow)
            title: Short descriptive title
            problem: What the user was trying to do
            solution: What worked

        Returns:
            Status message
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
        entry = f"""
---

## [{category}] {title}
_Added: {timestamp}_

### Problem
{problem}

### Solution
{solution}
"""
        result = self._append_to_knowledge_file(
            "lessons_learned.md", entry, f"Lesson: [{category}] {title}",
            default_header=(
                "# Lessons Learned\n\nInsights accumulated from helping users "
                "with the EASI-FISH pipeline.\n"
            ),
        )
        return f"Lesson saved: [{category}] {title}\n{result}"

    def save_faq(self, question: str, answer: str) -> str:
        """Save a frequently asked question to the knowledge base.

        Args:
            question: The question as a user would ask it
            answer: Clear, complete answer

        Returns:
            Status message
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d")
        entry = f"""
---

### Q: {question}
_Added: {timestamp}_

**A:** {answer}
"""
        result = self._append_to_knowledge_file(
            "faq.md", entry, f"FAQ: {question}",
            default_header=(
                "# Frequently Asked Questions\n\nCommon questions from "
                "EASI-FISH pipeline users.\n"
            ),
        )
        return f"FAQ saved: {question}\n{result}"

    # -- Seqera helpers -----------------------------------------------------

    def _fetch_seqera_context(self) -> str:
        """Fetch recent runs from Seqera Platform for context."""
        if not self.tower_service:
            return ""

        try:
            if not self.tower_service.test_connection():
                return "(Seqera Platform is not connected.)"

            workflows = self.tower_service.list_workflows(limit=10)
            if not workflows:
                return "(No workflow runs found in Seqera Platform.)"

            lines = ["Recent Seqera Platform runs:"]
            for w in workflows:
                started = _format_start_time(w.start_time)
                duration = _format_duration_ms(w.duration)
                run_line = (
                    f"- [{w.status}] {w.name} (id: {w.id}) | "
                    f"pipeline: {w.pipeline} | started: {started} | "
                    f"duration: {duration}"
                )
                lines.append(run_line)

                # For failed runs in the summary, include error report
                if w.status == "FAILED":
                    # The list endpoint may not include errorReport,
                    # so fetch full workflow details
                    detail = self.tower_service.get_workflow(w.id)
                    if detail and detail.error_report:
                        lines.append(f"  Error: {detail.error_report[:500]}")
                    elif detail and detail.error_message:
                        lines.append(f"  Error: {detail.error_message[:300]}")

            return "\n".join(lines)
        except Exception as e:
            return f"(Error fetching from Seqera: {e})"

    def _fetch_failed_run_details(self) -> str:
        """Fetch details about failed runs — workflow errors + task errors."""
        if not self.tower_service:
            return ""

        try:
            failed = self.tower_service.list_workflows(status="FAILED", limit=5)
            if not failed:
                return "(No failed runs found.)"

            lines = ["Failed run details:"]
            for w in failed:
                lines.append(f"\n**{w.name}** (id: {w.id})")
                lines.append(f"  Pipeline: {w.pipeline}")
                lines.append(f"  Started: {_format_start_time(w.start_time)}")

                # Get full workflow details for errorReport
                detail = self.tower_service.get_workflow(w.id)
                if detail and detail.error_report:
                    lines.append(f"  Workflow error report:\n    {detail.error_report[:800]}")
                elif detail and detail.error_message:
                    lines.append(f"  Workflow error message: {detail.error_message[:500]}")

                # Also get failed tasks with full details (stderr/stdout)
                failed_tasks = self.tower_service.get_failed_task_details(w.id, limit=5)
                if failed_tasks:
                    lines.append("  Failed tasks:")
                    for task in failed_tasks:
                        name = task.get("name", task.get("process", "unknown"))
                        exit_code = task.get("exitStatus", task.get("exit", "N/A"))
                        stderr = task.get("stderr", "")
                        stdout = task.get("stdout", "")
                        lines.append(f"    - {name} (exit code: {exit_code})")
                        if stderr:
                            lines.append(f"      stderr: {stderr[:500]}")
                        if stdout and not stderr:
                            lines.append(f"      stdout: {stdout[:300]}")

            return "\n".join(lines)
        except Exception as e:
            return f"(Error fetching failed run details: {e})"

    # -- Main chat ----------------------------------------------------------

    def chat(
        self,
        user_message: str,
        history: List[Dict[str, str]],
    ) -> str:
        """Main chat method — detects intent, gathers context, calls LLM.

        Args:
            user_message: The user's message
            history: Conversation history as list of {"role": ..., "content": ...}

        Returns:
            The assistant's response
        """
        if not self.api_key:
            return (
                "No LLM API key configured. Please set `OPENAI_API_KEY` or "
                "`ANTHROPIC_API_KEY` in your `.env` file to enable the assistant."
            )

        # Build context sections
        context_parts = []

        # 1. Search knowledge base for terms in the user message
        kb_context = self.search_knowledge(user_message)
        if kb_context:
            context_parts.append(f"## Knowledge Base Context\n\n{kb_context}")

        # 2. Check for error patterns
        if ERROR_KEYWORDS.search(user_message):
            diagnosis = self.diagnose_error(user_message)
            if diagnosis:
                context_parts.append(f"## Error Diagnosis\n\n{diagnosis}")

        # 3. Check for run/status related questions
        if RUN_KEYWORDS.search(user_message):
            if "fail" in user_message.lower() or "error" in user_message.lower():
                seqera_ctx = self._fetch_failed_run_details()
            else:
                seqera_ctx = self._fetch_seqera_context()
            if seqera_ctx:
                context_parts.append(f"## Seqera Platform Data\n\n{seqera_ctx}")

        # Assemble system message with context
        system_msg = SYSTEM_PROMPT
        if context_parts:
            system_msg += "\n\n---\n\nUse the following context to answer the user's question:\n\n"
            system_msg += "\n\n".join(context_parts)


        # Build messages for LLM
        messages = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        try:
            client = self._get_client()

            if self.llm_provider == "openai":
                model = self.llm_model if self.llm_model and not self.llm_model.startswith("claude") else "gpt-4-turbo"
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system_msg}] + messages,
                    max_tokens=2000,
                )
                return response.choices[0].message.content

            else:  # anthropic
                model = self.llm_model if self.llm_model and not self.llm_model.startswith("gpt") else "claude-sonnet-4-20250514"
                response = client.messages.create(
                    model=model,
                    max_tokens=2000,
                    system=system_msg,
                    messages=messages,
                )
                return response.content[0].text

        except Exception as e:
            return f"Error calling LLM: {e}"
