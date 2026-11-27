import json
import unittest

from hotseat_core.cronjob import (
    DEFAULT_TITLE,
    CronJobError,
    ensure_keepalive,
    list_jobs,
)


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        status, payload = self.responses.pop(0)
        if isinstance(payload, bytes):
            body = payload
        else:
            body = json.dumps(payload).encode("utf-8")
        return status, body


class CronJobTests(unittest.TestCase):
    def test_creates_a_keepalive_for_the_public_room(self):
        transport = FakeTransport(
            (200, {"jobs": []}),
            (200, {"jobId": 42}),
        )
        result = ensure_keepalive(
            "secret", "https://hotseat.example", interval_minutes=10, transport=transport
        )

        self.assertEqual(result["action"], "created")
        self.assertEqual(result["job_id"], 42)
        self.assertEqual(result["url"], "https://hotseat.example/")
        self.assertEqual(len(transport.requests), 2)

        create = transport.requests[1]
        self.assertEqual(create.get_method(), "PUT")
        self.assertEqual(create.full_url, "https://api.cron-job.org/jobs")
        self.assertEqual(create.get_header("Authorization"), "Bearer secret")
        job = json.loads(create.data.decode("utf-8"))["job"]
        self.assertEqual(job["url"], "https://hotseat.example/")
        self.assertTrue(job["enabled"])
        self.assertFalse(job["saveResponses"])
        self.assertEqual(job["requestMethod"], 0)
        self.assertEqual(job["schedule"]["minutes"], [0, 10, 20, 30, 40, 50])
        self.assertEqual(job["schedule"]["timezone"], "UTC")

    def test_updates_the_job_with_the_same_title(self):
        transport = FakeTransport(
            (200, {"jobs": [{"jobId": 7, "title": DEFAULT_TITLE}]}),
            (200, {}),
        )
        result = ensure_keepalive(
            "secret", "https://hotseat.example", transport=transport
        )

        self.assertEqual(result["action"], "updated")
        self.assertEqual(result["job_id"], 7)
        update = transport.requests[1]
        self.assertEqual(update.get_method(), "PATCH")
        self.assertEqual(update.full_url, "https://api.cron-job.org/jobs/7")

    def test_every_minute_uses_the_wildcard(self):
        transport = FakeTransport(
            (200, {"jobs": []}),
            (200, {"jobId": 3}),
        )
        ensure_keepalive(
            "secret", "https://hotseat.example", interval_minutes=1, transport=transport
        )
        job = json.loads(transport.requests[1].data.decode("utf-8"))["job"]
        self.assertEqual(job["schedule"]["minutes"], [-1])

    def test_api_errors_keep_the_status_and_detail(self):
        transport = FakeTransport((401, {"error": "Unauthorized"}))
        with self.assertRaisesRegex(CronJobError, "401"):
            list_jobs("bad-key", transport=transport)

    def test_missing_key_is_explained(self):
        with self.assertRaisesRegex(CronJobError, "CRONJOB_API_KEY"):
            ensure_keepalive("", "https://hotseat.example")

    def test_invalid_url_and_interval_are_rejected(self):
        with self.assertRaises(ValueError):
            ensure_keepalive("secret", "not-a-url")
        with self.assertRaises(ValueError):
            ensure_keepalive("secret", "https://hotseat.example", interval_minutes=0)
        with self.assertRaises(ValueError):
            ensure_keepalive("secret", "https://hotseat.example", interval_minutes=61)


if __name__ == "__main__":
    unittest.main()
