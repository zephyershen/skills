class OperatorError(Exception):
    def __init__(self, message, *, code="operator_error", exit_code=2, details=None):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}


class ApiError(OperatorError):
    def __init__(self, message, *, status=None, code="api_error", details=None):
        exit_code = 4 if status in (401, 403) else 5
        safe_details = dict(details or {})
        if status is not None:
            safe_details["status"] = status
        super().__init__(message, code=code, exit_code=exit_code, details=safe_details)
        self.status = status


class ConfirmationRequired(OperatorError):
    def __init__(self, plan):
        super().__init__(
            "操作需要用户确认",
            code="confirmation_required",
            exit_code=3,
            details={"plan": plan},
        )
