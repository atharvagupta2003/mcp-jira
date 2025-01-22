import logging
import os
import re
from datetime import datetime
from typing import List, Optional

from atlassian import Jira
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-jira")


class JiraFetcher:
    """Handles fetching and parsing content from Jira."""

    def __init__(self):
        self.server = os.getenv("JIRA_SITE", "")
        self.email = os.getenv("JIRA_EMAIL", "")
        self.api_token = os.getenv("JIRA_API_TOKEN", "")

        if not all([self.server, self.email, self.api_token]):
            raise ValueError("Missing required Jira environment variables")

        self.jira = Jira(
            url=self.server,
            username=self.email,
            password=self.api_token,  # API token is used as password
            cloud=True,
        )

    def _clean_text(self, text: str) -> str:
        """Cleans Jira text by removing formatting, links, and redundant spaces."""
        if not text:
            return ""

        text = re.sub(r'\{color:[^}]+\}', '', text)  # Remove color formatting
        text = text.replace('{color}', '')

        text = re.sub(r'\{\{.*?\}\}', '', text, flags=re.DOTALL)  # Remove JIRA code blocks
        text = re.sub(r'!\[?[^\]]*?!', '', text)  # Remove images
        text = re.sub(r'\[(.*?)\|[^\]]+\]', r'\1', text)  # Remove JIRA links but keep display text

        return re.sub(r'\n+', '\n', text).strip()  # Remove excessive newlines and trim spaces

    def get_issue(self, issue_key: str, expand: Optional[str] = None) -> dict:
        """Retrieves a Jira issue with cleaned content."""
        try:
            issue = self.jira.issue(issue_key, expand=expand)

            # Handle missing or inaccessible issues
            if not issue or not isinstance(issue, dict):
                logger.warning(f"Issue {issue_key} not found or API returned invalid data.")
                return {"key": issue_key, "error": "Issue not found or missing data"}

            fields = issue.get("fields", {})

            # Ensure `fields` is a dictionary
            if not isinstance(fields, dict):
                logger.warning(f"Issue {issue_key} is missing fields.")
                return {"key": issue_key, "error": "Issue missing fields"}

            description = self._clean_text(fields.get("description", ""))

            # Get comments safely
            comments = []
            if isinstance(fields.get("comment"), dict):
                for comment in fields["comment"].get("comments", []):
                    processed_comment = self._clean_text(comment.get("body", ""))
                    created = comment.get("created", "1970-01-01T00:00:00.000+0000").replace("Z", "+00:00")
                    created_date = datetime.fromisoformat(created).strftime("%Y-%m-%d")
                    author = comment.get("author", {}).get("displayName", "Unknown")
                    comments.append({"body": processed_comment, "created": created_date, "author": author})

            # Format created date safely
            created_date = fields.get("created", "1970-01-01T00:00:00.000+0000").replace("Z", "+00:00")
            formatted_created = datetime.fromisoformat(created_date).strftime("%Y-%m-%d")

            # Structure response
            return {
                "key": issue_key,
                "title": fields.get("summary", "No Summary"),
                "type": fields.get("issuetype", {}).get("name", "Unknown"),
                "status": fields.get("status", {}).get("name", "Unknown"),
                "created": formatted_created,
                "priority": fields.get("priority", {}).get("name", "None"),
                "description": description,
                "assignee": fields.get("assignee", {}).get("displayName", "Unassigned"),
                "reporter": fields.get("reporter", {}).get("displayName", "Unknown Reporter"),
                "comments": comments,
                "link": f"{self.server.rstrip('/')}/browse/{issue_key}",
            }

        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {str(e)}")
            return {"key": issue_key, "error": str(e)}

    def search_issues(
        self, jql: str, fields: str = "*all", start: int = 0, limit: int = 50, expand: Optional[str] = None
    ) -> List[dict]:
        """Searches for Jira issues using JQL."""
        try:
            results = self.jira.jql(jql, fields=fields, start=start, limit=limit, expand=expand)

            if not results or "issues" not in results:
                logger.warning(f"No issues found for JQL: {jql}")
                return []

            documents = []
            for issue in results.get("issues", []):
                doc = self.get_issue(issue.get("key", "UNKNOWN"), expand=expand)
                if "error" not in doc:
                    documents.append(doc)

            return documents

        except Exception as e:
            logger.error(f"Error searching issues with JQL {jql}: {str(e)}")
            return []

    def get_project_issues(self, project_key: str, start: int = 0, limit: int = 50) -> List[dict]:
        """Retrieves all issues for a specific Jira project."""
        jql = f"project = {project_key} ORDER BY created DESC"
        return self.search_issues(jql, start=start, limit=limit)
    
    def get_all_projects(self) -> List[dict]:
        """
        Retrieves all Jira projects.

        Returns:
            List of project dictionaries with 'key' and 'name'.
        """
        try:
            projects = self.jira.projects()

            if not projects:
                logger.warning("No projects found.")
                return []

            project_list = [{"key": project.get("key"), "name": project.get("name")} for project in projects]
            return project_list

        except Exception as e:
            logger.error(f"Error fetching projects: {str(e)}")
            return []
 

# Initialize the JiraFetcher
jira_fetcher = JiraFetcher()

projects = jira_fetcher.get_all_projects()
for project in projects:
    print(f"{project['key']}: {project['name']}")
# # Fetch a single issue
# issue_details = jira_fetcher.get_issue("AGAILEP-314")
# print(issue_details)

# # Fetch all issues for a project
# project_issues = jira_fetcher.get_project_issues("AGAILEP")
# print(project_issues)
