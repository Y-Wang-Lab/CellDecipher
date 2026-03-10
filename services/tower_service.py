"""Seqera Platform (Nextflow Tower) service for pipeline monitoring."""

import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WorkflowRun:
    """Information about a workflow run."""
    id: str
    name: str
    status: str
    start_time: Optional[datetime]
    complete_time: Optional[datetime]
    duration: Optional[str]
    project_name: str
    pipeline: str
    error_message: Optional[str] = None
    error_report: Optional[str] = None


@dataclass
class WorkflowLog:
    """Workflow log entry."""
    timestamp: str
    level: str
    message: str
    process: Optional[str] = None


class TowerService:
    """Service for interacting with Seqera Platform API."""

    def __init__(
        self,
        api_endpoint: str = "https://api.cloud.seqera.io",
        access_token: Optional[str] = None,
        workspace: Optional[str] = None,
    ):
        """Initialize Tower service.

        Args:
            api_endpoint: Seqera API endpoint
            access_token: Seqera access token
            workspace: Workspace name (e.g. 'Wang_Lab/multifish') — will be
                       resolved to a numeric workspace ID automatically.
        """
        self.api_endpoint = api_endpoint.rstrip("/")
        self.access_token = access_token
        self._workspace_name = workspace
        self._workspace_id: Optional[int] = None
        self.session = requests.Session()

        if access_token:
            self.session.headers["Authorization"] = f"Bearer {access_token}"

    def _resolve_workspace_id(self) -> Optional[int]:
        """Resolve org/workspace name to numeric workspace ID."""
        if self._workspace_id is not None:
            return self._workspace_id

        if not self._workspace_name:
            return None

        # Try parsing as "org_name/workspace_name"
        parts = self._workspace_name.strip("/").split("/")
        if len(parts) == 2:
            org_name, ws_name = parts
        else:
            # Assume it's just a workspace name, try to find it
            org_name, ws_name = None, self._workspace_name

        try:
            # List user's orgs and workspaces
            resp = self.session.get(f"{self.api_endpoint}/user-info", timeout=10)
            resp.raise_for_status()
            user_info = resp.json()

            # Try the orgs endpoint to find workspaces
            resp = self.session.get(f"{self.api_endpoint}/user/{user_info['user']['id']}/workspaces", timeout=10)
            resp.raise_for_status()
            data = resp.json()

            for entry in data.get("orgsAndWorkspaces", []):
                entry_org = entry.get("orgName", "")
                entry_ws = entry.get("workspaceName", "")
                entry_ws_id = entry.get("workspaceId")

                if org_name:
                    if entry_org == org_name and entry_ws == ws_name:
                        self._workspace_id = entry_ws_id
                        return self._workspace_id
                else:
                    if entry_ws == ws_name:
                        self._workspace_id = entry_ws_id
                        return self._workspace_id

        except Exception as e:
            print(f"Error resolving workspace ID: {e}")

        return None

    def _ws_params(self, params: Optional[Dict] = None) -> Dict:
        """Add workspaceId to query params if workspace is configured."""
        p = dict(params) if params else {}
        ws_id = self._resolve_workspace_id()
        if ws_id is not None:
            p["workspaceId"] = ws_id
        return p

    def test_connection(self) -> bool:
        """Test API connection.

        Returns:
            True if connection successful
        """
        try:
            response = self.session.get(f"{self.api_endpoint}/user-info", timeout=10)
            return response.status_code == 200
        except Exception:
            return False

    def list_workflows(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[WorkflowRun]:
        """List workflow runs.

        Args:
            status: Filter by status (SUBMITTED, RUNNING, SUCCEEDED, FAILED)
            limit: Maximum results

        Returns:
            List of workflow runs
        """
        try:
            params = self._ws_params({"max": limit})
            if status:
                params["search"] = f"status:{status}"

            response = self.session.get(
                f"{self.api_endpoint}/workflow",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            workflows = []
            for entry in data.get("workflows", []):
                w = entry.get("workflow", entry)
                workflows.append(WorkflowRun(
                    id=w.get("id", ""),
                    name=w.get("runName", ""),
                    status=w.get("status", "UNKNOWN"),
                    start_time=self._parse_datetime(w.get("start")),
                    complete_time=self._parse_datetime(w.get("complete")),
                    duration=w.get("duration", ""),
                    project_name=w.get("projectName", ""),
                    pipeline=w.get("pipeline", ""),
                    error_message=w.get("errorMessage"),
                    error_report=w.get("errorReport"),
                ))

            return workflows

        except Exception as e:
            print(f"Error listing workflows: {e}")
            return []

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRun]:
        """Get workflow details.

        Args:
            workflow_id: Workflow ID

        Returns:
            WorkflowRun or None
        """
        try:
            response = self.session.get(
                f"{self.api_endpoint}/workflow/{workflow_id}",
                params=self._ws_params(),
                timeout=30,
            )
            response.raise_for_status()
            w = response.json().get("workflow", {})

            return WorkflowRun(
                id=w.get("id", workflow_id),
                name=w.get("runName", ""),
                status=w.get("status", "UNKNOWN"),
                start_time=self._parse_datetime(w.get("start")),
                complete_time=self._parse_datetime(w.get("complete")),
                duration=w.get("duration", ""),
                project_name=w.get("projectName", ""),
                pipeline=w.get("pipeline", ""),
                error_message=w.get("errorMessage"),
                error_report=w.get("errorReport"),
            )

        except Exception as e:
            print(f"Error getting workflow: {e}")
            return None

    def get_workflow_tasks(
        self,
        workflow_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get tasks for a workflow (summary list).

        Args:
            workflow_id: Workflow ID
            status: Optional filter (e.g. 'FAILED')

        Returns:
            List of task dicts
        """
        try:
            params = self._ws_params()
            if status:
                params["search"] = f"status:{status}"

            response = self.session.get(
                f"{self.api_endpoint}/workflow/{workflow_id}/tasks",
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            return [t.get("task", t) for t in data.get("tasks", [])]

        except Exception as e:
            print(f"Error getting tasks: {e}")
            return []

    def get_task_details(
        self,
        workflow_id: str,
        task_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get full details for a single task, including stderr/stdout.

        Args:
            workflow_id: Workflow ID
            task_id: Task ID

        Returns:
            Task detail dict or None
        """
        try:
            response = self.session.get(
                f"{self.api_endpoint}/workflow/{workflow_id}/task/{task_id}",
                params=self._ws_params(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("task", data)

        except Exception as e:
            print(f"Error getting task details: {e}")
            return None

    def get_failed_task_details(
        self,
        workflow_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get detailed info for failed tasks, including stderr.

        Fetches the task list, then gets individual details for each
        failed task to retrieve stderr/stdout.

        Args:
            workflow_id: Workflow ID
            limit: Max number of failed tasks to fetch details for

        Returns:
            List of task detail dicts with stderr/stdout
        """
        failed_tasks = self.get_workflow_tasks(workflow_id, status="FAILED")
        detailed = []

        for task in failed_tasks[:limit]:
            task_id = task.get("taskId") or task.get("id")
            if not task_id:
                detailed.append(task)
                continue

            detail = self.get_task_details(workflow_id, str(task_id))
            if detail:
                detailed.append(detail)
            else:
                detailed.append(task)

        return detailed

    def launch_workflow(
        self,
        pipeline: str,
        params: Dict[str, Any],
        compute_env: Optional[str] = None,
        run_name: Optional[str] = None,
    ) -> Optional[str]:
        """Launch a new workflow.

        Args:
            pipeline: Pipeline URL or name
            params: Pipeline parameters
            compute_env: Compute environment ID
            run_name: Custom run name

        Returns:
            Workflow ID or None
        """
        try:
            payload = {
                "pipeline": pipeline,
                "params": params,
            }

            if compute_env:
                payload["computeEnvId"] = compute_env
            if run_name:
                payload["runName"] = run_name

            response = self.session.post(
                f"{self.api_endpoint}/workflow/launch",
                json=payload,
                params=self._ws_params(),
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()

            return data.get("workflowId")

        except Exception as e:
            print(f"Error launching workflow: {e}")
            return None

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow.

        Args:
            workflow_id: Workflow ID

        Returns:
            True if cancelled successfully
        """
        try:
            response = self.session.post(
                f"{self.api_endpoint}/workflow/{workflow_id}/cancel",
                params=self._ws_params(),
                timeout=30,
            )
            return response.status_code == 200

        except Exception:
            return False

    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return None
