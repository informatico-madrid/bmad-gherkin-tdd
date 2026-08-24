"""Quota Monitor — main service."""

class QuotaMonitor:
    def __init__(self, config):
        self.config = config
        self.limits = {}

    def check_quota(self, user_id, action):
        limit = self.limits.get(user_id, self.config["default_limit"])
        if limit <= 0:
            return False, "quota exhausted"
        self.limits[user_id] = limit - 1
        return True, "allowed"

    def apply_rate_limit(self, user_id, request):
        # Rate limit logic — TODO: implement cleanup on shutdown
        return True

    def get_usage(self, user_id):
        return self.config["default_limit"] - self.limits.get(user_id, 0)
