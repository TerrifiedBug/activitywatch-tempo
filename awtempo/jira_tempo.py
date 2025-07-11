"""
Jira Tempo API integration for time tracking
"""

import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional

from .models import Config, TimeEntry

logger = logging.getLogger(__name__)


class JiraTempoError(Exception):
    """Raised when there's an issue with Jira Tempo integration"""
    pass


class JiraTempoIntegration:
    """Handles Jira Tempo API integration with comprehensive error handling"""

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {config.jira_pat_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self._user_cache = None

    def _make_request(self, method: str, url: str, **kwargs):
        """Make HTTP request with proper error handling and retries"""
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            raise JiraTempoError(f"Request timeout for {method} {url}")
        except requests.exceptions.ConnectionError:
            raise JiraTempoError(f"Connection error for {method} {url}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise JiraTempoError("Authentication failed. Please check your Jira PAT token.")
            elif e.response.status_code == 403:
                raise JiraTempoError("Access denied. Please check your Jira permissions.")
            elif e.response.status_code == 404:
                raise JiraTempoError(f"Resource not found: {url}")
            else:
                raise JiraTempoError(f"HTTP error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise JiraTempoError(f"Request failed: {e}")

    def get_current_user(self) -> Optional[Dict]:
        """Get current user information from Jira API with caching"""
        if self._user_cache is not None:
            return self._user_cache

        try:
            response = self._make_request('GET', f"{self.config.jira_url}/rest/api/2/myself")
            user_info = response.json()
            self._user_cache = user_info
            logger.info(f"Retrieved user info: {user_info.get('displayName', 'Unknown')}")
            return user_info
        except JiraTempoError as e:
            logger.error(f"Failed to get current user: {e}")
            return None

    def get_worker_id(self) -> Optional[str]:
        """Get the worker ID for the current user"""
        user_info = self.get_current_user()
        if user_info:
            # Try different possible fields for worker ID
            worker_id = user_info.get('key') or user_info.get('accountId') or user_info.get('name')
            if worker_id:
                logger.info(f"Auto-detected worker_id: {worker_id}")
                return worker_id
            else:
                logger.warning("Could not determine worker_id from user info")
                logger.debug(f"User info: {user_info}")
        return None

    def validate_jira_key(self, jira_key: str) -> bool:
        """Validate that a Jira key exists"""
        try:
            response = self._make_request('GET', f"{self.config.jira_url}/rest/api/2/issue/{jira_key}")
            return response.status_code == 200
        except JiraTempoError as e:
            logger.error(f"Error validating Jira key {jira_key}: {e}")
            return False

    def submit_time_entry(self, entry: TimeEntry) -> bool:
        """Submit a time entry to Jira Tempo with validation"""
        try:
            # Validate Jira key first
            if not self.validate_jira_key(entry.jira_key):
                logger.error(f"Invalid Jira key: {entry.jira_key}")
                return False

            # Convert to Tempo format
            tempo_entry = {
                "worker": self.config.worker_id,
                "comment": entry.description,
                "started": entry.start_time.strftime("%Y-%m-%dT%H:%M:%S.000"),
                "timeSpentSeconds": entry.duration_seconds,
                "originTaskId": entry.jira_key,
                "originId": -1
            }

            logger.debug(f"Submitting time entry: {entry.jira_key} - {entry.duration_seconds/3600:.2f}h")

            # Submit to Tempo API
            response = self._make_request(
                'POST',
                f"{self.config.jira_url}/rest/tempo-timesheets/4/worklogs/",
                json=tempo_entry
            )

            if response.status_code in [200, 201]:
                logger.info(f"Successfully logged {entry.duration_seconds/3600:.2f}h to {entry.jira_key}")
                return True
            else:
                logger.error(f"Failed to log time to {entry.jira_key}: {response.text}")
                return False

        except JiraTempoError as e:
            logger.error(f"Error submitting time entry: {e}")
            return False

    def submit_time_entries_batch(self, entries: List[TimeEntry]) -> bool:
        """Submit multiple time entries in a single API call (if supported)"""
        if not entries:
            logger.info("No entries to submit")
            return True

        try:
            # Prepare batch data
            batch_data = []
            for entry in entries:
                tempo_entry = {
                    "worker": self.config.worker_id,
                    "comment": entry.description,
                    "started": entry.start_time.strftime("%Y-%m-%dT%H:%M:%S.000"),
                    "timeSpentSeconds": entry.duration_seconds,
                    "originTaskId": entry.jira_key,
                    "originId": -1
                }
                batch_data.append(tempo_entry)

            logger.info(f"Submitting {len(entries)} time entries in batch")

            # Try batch submission first
            try:
                response = self._make_request(
                    'POST',
                    f"{self.config.jira_url}/rest/tempo-timesheets/4/worklogs/batch",
                    json={"worklogs": batch_data}
                )
                
                if response.status_code in [200, 201]:
                    logger.info(f"Successfully submitted {len(entries)} entries in batch")
                    return True
                else:
                    logger.warning(f"Batch submission failed, falling back to individual submissions")
                    return self.submit_daily_entries(entries)

            except JiraTempoError:
                logger.warning("Batch submission not supported, falling back to individual submissions")
                return self.submit_daily_entries(entries)

        except Exception as e:
            logger.error(f"Error in batch submission: {e}")
            return self.submit_daily_entries(entries)

    def submit_daily_entries(self, entries: List[TimeEntry]) -> bool:
        """Submit all daily time entries individually"""
        if not entries:
            logger.info("No entries to submit")
            return True

        success_count = 0
        failed_entries = []

        logger.info(f"Submitting {len(entries)} time entries individually")

        for entry in entries:
            if self.submit_time_entry(entry):
                success_count += 1
            else:
                failed_entries.append(entry)

        if failed_entries:
            logger.error(f"Failed to submit {len(failed_entries)} entries:")
            for entry in failed_entries:
                logger.error(f"  - {entry.jira_key}: {entry.duration_seconds/3600:.2f}h")

        logger.info(f"Successfully submitted {success_count}/{len(entries)} time entries")
        return success_count == len(entries)

    def test_connection(self) -> bool:
        """Test the connection to Jira and Tempo"""
        try:
            # Test basic Jira connection
            user_info = self.get_current_user()
            if not user_info:
                logger.error("Failed to connect to Jira API")
                return False

            # Test Tempo API access
            response = self._make_request('GET', f"{self.config.jira_url}/rest/tempo-timesheets/4/worklogs/")
            logger.info("Successfully connected to Jira Tempo API")
            return True

        except JiraTempoError as e:
            logger.error(f"Connection test failed: {e}")
            return False

    def get_worklog_summary(self, date: datetime) -> Dict:
        """Get summary of worklogs for a specific date"""
        try:
            start_date = date.strftime("%Y-%m-%d")
            end_date = date.strftime("%Y-%m-%d")

            response = self._make_request(
                'GET',
                f"{self.config.jira_url}/rest/tempo-timesheets/4/worklogs/",
                params={
                    'worker': self.config.worker_id,
                    'dateFrom': start_date,
                    'dateTo': end_date
                }
            )

            worklogs = response.json()
            
            summary = {
                'total_hours': 0,
                'entries': [],
                'by_project': {}
            }

            for worklog in worklogs:
                hours = worklog.get('timeSpentSeconds', 0) / 3600
                jira_key = worklog.get('originTaskId', 'Unknown')
                
                summary['total_hours'] += hours
                summary['entries'].append({
                    'jira_key': jira_key,
                    'hours': hours,
                    'comment': worklog.get('comment', '')
                })

                if jira_key not in summary['by_project']:
                    summary['by_project'][jira_key] = 0
                summary['by_project'][jira_key] += hours

            logger.info(f"Retrieved worklog summary for {start_date}: {summary['total_hours']:.2f}h")
            return summary

        except JiraTempoError as e:
            logger.error(f"Failed to get worklog summary: {e}")
            return {'total_hours': 0, 'entries': [], 'by_project': {}} 