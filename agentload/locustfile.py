"""Locust integration point.

AgentLoad's programmatic runner uses the same HTTP load-testing model. This module is
provided for users who want to invoke Locust directly with their scenario adapters.
"""
from locust import HttpUser, task


class AgentLoadUser(HttpUser):
    @task
    def agent_task(self):
        with self.client.post("/agent", json={"prompt": "healthcheck"}, catch_response=True) as response:
            if response.status_code >= 400:
                response.failure(f"HTTP {response.status_code}")
