from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    group: str
    name: str
    method: str
    path: str
    scope: str
    risk: str
    summary: str
    response_secret: bool = False
    confirmation_text: str | None = None


ACTIONS = (
    Action("tokens", "capabilities", "GET", "/access-tokens/capabilities", "", "read", "查看可签发令牌范围"),
    Action("tokens", "list", "GET", "/access-tokens", "tokens:manage", "read", "列出自己的令牌"),
    Action("tokens", "create", "POST", "/access-tokens", "tokens:manage", "high", "创建个人访问令牌", response_secret=True),
    Action("tokens", "revoke", "DELETE", "/access-tokens/{tokenId}", "tokens:manage", "high", "撤销个人访问令牌"),

    Action("projects", "list", "GET", "/projects", "wiki:read", "read", "列出可见 Wiki Group"),
    Action("projects", "directory", "GET", "/projects/directory", "workspace:manage", "read", "读取 Group 管理目录"),
    Action("projects", "explorer", "GET", "/projects/explorer", "wiki:read", "read", "读取资源树入口"),
    Action("projects", "get", "GET", "/projects/{projectId}", "wiki:read", "read", "读取 Wiki Group"),
    Action("projects", "create", "POST", "/projects", "workspace:manage", "high", "创建或接入 Wiki Group"),
    Action("projects", "update", "PUT", "/projects/{projectId}", "workspace:manage", "medium", "修改 Wiki Group"),

    Action("workspace", "get", "GET", "/projects/{projectId}/workspace", "wiki:read", "read", "读取 Group 工作区"),
    Action("workspace", "group-candidates", "GET", "/projects/{projectId}/namespace-candidates", "workspace:manage", "read", "列出 Subgroup 候选"),
    Action("workspace", "wiki-candidates", "GET", "/projects/{projectId}/repository-candidates", "workspace:manage", "read", "列出 Wiki 候选"),
    Action("workspace", "group-create", "POST", "/projects/{projectId}/namespaces", "workspace:manage", "high", "创建或接入 Subgroup"),
    Action("workspace", "wiki-create", "POST", "/projects/{projectId}/wiki-repositories", "workspace:manage", "high", "创建或接入 Wiki"),
    Action("workspace", "wiki-archive", "DELETE", "/projects/{projectId}/wiki-repositories/{repositoryId}", "workspace:manage", "high", "归档 Wiki"),
    Action("workspace", "group-archive", "DELETE", "/projects/{projectId}/namespaces/{namespaceId}", "workspace:manage", "high", "归档 Group 或 Subgroup"),

    Action("repo", "tree", "GET", "/repositories/{repositoryId}/tree", "wiki:read", "read", "读取 Wiki 文件树"),
    Action("repo", "snapshot", "GET", "/repositories/{repositoryId}/snapshot", "wiki:read", "read", "读取精确版本快照"),
    Action("repo", "file", "GET", "/repositories/{repositoryId}/files", "wiki:read", "read", "读取 Wiki 文件"),
    Action("repo", "commits", "GET", "/repositories/{repositoryId}/commits", "wiki:read", "read", "列出 Wiki 提交"),
    Action("repo", "sync", "POST", "/repositories/{repositoryId}/sync", "wiki:write", "medium", "同步 Wiki 搜索索引"),

    Action("changes", "list", "GET", "/change-requests", "wiki:read", "read", "列出修改申请"),
    Action("changes", "get", "GET", "/change-requests/{changeRequestId}", "wiki:read", "read", "读取修改申请"),
    Action("changes", "diff", "GET", "/change-requests/{changeRequestId}/diff", "wiki:read", "read", "读取修改申请文件差异"),
    Action("changes", "submit", "POST", "/repositories/{repositoryId}/change-requests", "wiki:write", "medium", "提交修改申请"),
    Action("changes", "approve", "POST", "/change-requests/{changeRequestId}/approve", "wiki:review", "high", "批准修改申请"),
    Action("changes", "reject", "POST", "/change-requests/{changeRequestId}/reject", "wiki:review", "high", "驳回修改申请"),

    Action("knowledge", "graph", "GET", "/projects/{projectId}/graph", "wiki:read", "read", "读取知识图谱"),
    Action("knowledge", "backlinks", "GET", "/projects/{projectId}/documents/{documentId}/backlinks", "wiki:read", "read", "读取文档反向链接"),
    Action("knowledge", "search", "GET", "/projects/{projectId}/search", "wiki:read", "read", "搜索 Wiki"),
    Action("knowledge", "ask", "POST", "/projects/{projectId}/ask", "wiki:read", "read", "进行带引用的 Wiki 问答"),

    Action("people", "list", "GET", "/personnel", "personnel:manage", "read", "读取人员和人员组"),
    Action("people", "candidates", "GET", "/personnel/candidates", "personnel:manage", "read", "搜索可加入人员"),
    Action("people", "add", "POST", "/personnel/members", "personnel:manage", "high", "添加 Wiki 平台成员"),
    Action("people", "group-create", "POST", "/personnel/groups", "personnel:manage", "medium", "创建人员组"),
    Action("people", "group-update", "PATCH", "/personnel/groups/{id}", "personnel:manage", "medium", "修改人员组"),
    Action("people", "group-delete", "DELETE", "/personnel/groups/{id}", "personnel:manage", "high", "删除空人员组"),
    Action("people", "user-update", "PATCH", "/personnel/users/{id}", "personnel:manage", "high", "修改人员角色或人员组"),
    Action("people", "management-get", "GET", "/personnel/users/{id}/management", "personnel:manage", "read", "读取人员完整授权"),
    Action("people", "management-set", "PUT", "/personnel/users/{id}/management", "personnel:manage", "high", "保存人员资料和完整授权"),
    Action("people", "admin-grant", "PUT", "/personnel/platform-admins/{id}", "admins:manage", "critical", "授予平台管理员", confirmation_text="CHANGE PLATFORM ADMIN {id}"),
    Action("people", "admin-revoke", "DELETE", "/personnel/platform-admins/{id}", "admins:manage", "critical", "撤销平台管理员", confirmation_text="CHANGE PLATFORM ADMIN {id}"),

    Action("access", "matrix", "GET", "/access/matrix", "access:manage", "read", "读取权限矩阵"),
    Action("access", "project-set", "PUT", "/projects/{projectId}/access/{userId}", "access:manage", "high", "设置 Group 权限"),
    Action("access", "project-batch", "POST", "/projects/{projectId}/access/batch", "access:manage", "high", "批量设置 Group 权限"),
    Action("access", "namespace-set", "PUT", "/namespaces/{namespaceId}/access/{userId}", "access:manage", "high", "设置 Subgroup 权限"),
    Action("access", "namespace-batch", "POST", "/namespaces/{namespaceId}/access/batch", "access:manage", "high", "批量设置 Subgroup 权限"),
    Action("access", "repository-set", "PUT", "/repositories/{repositoryId}/access/{userId}", "access:manage", "high", "设置 Wiki 权限"),
    Action("access", "repository-batch", "POST", "/repositories/{repositoryId}/access/batch", "access:manage", "high", "批量设置 Wiki 权限"),
    Action("access", "resource-manager", "PUT", "/projects/{projectId}/resource-managers/{userId}", "access:manage", "high", "设置 Group 资源管理者"),

    Action("archives", "list", "GET", "/archives", "archives:manage", "read", "列出归档资源"),
    Action("archives", "restore", "POST", "/archives/{kind}/{id}/restore", "archives:manage", "high", "恢复归档资源"),
    Action("archives", "purge", "DELETE", "/archives/{kind}/{id}", "archives:manage", "critical", "永久清理归档资源", confirmation_text="PERMANENTLY DELETE {kind} {id}"),

    Action("gitlab", "status", "GET", "/integrations/gitlab/status", "integrations:manage", "read", "检查 GitLab 连接"),
    Action("gitlab", "namespaces", "GET", "/integrations/gitlab/namespaces", "integrations:manage", "read", "搜索 GitLab 顶级 Group"),

    Action("jira", "status", "GET", "/integrations/jira/status", "integrations:manage", "read", "读取 Jira 绑定状态"),
    Action("jira", "projects", "GET", "/integrations/jira/projects", "integrations:manage", "read", "列出 Jira 项目"),
    Action("jira", "parents", "GET", "/integrations/jira/parents", "integrations:manage", "read", "列出 Jira 导入位置"),
    Action("jira", "import-preview", "POST", "/integrations/jira/imports/preview", "integrations:manage", "medium", "预览 Jira 导入"),
    Action("jira", "import", "POST", "/integrations/jira/imports", "integrations:manage", "high", "执行 Jira 导入"),
)


ACTION_BY_KEY = {(action.group, action.name): action for action in ACTIONS}
